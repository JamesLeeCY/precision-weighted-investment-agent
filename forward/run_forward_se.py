"""前瞻記錄 se：每月自結損益驚奇（ESUE），同月前三分之一 − 後三分之一的異常報酬差。

研究依據：docs/self_earnings_report.md（點子卡 I015；2019 ~ 2026/04，87 個月：前 − 後 CAR[+2,+21] +1.19%，t 4.4；
金融股內部 +1.06%，t 4.9）。可交易版本扣成本後很弱，所以這裡只記錄訊號本身是否在研究期間之後仍成立。紀錄在 forward/se/。

規則（凍結於 forward/se/spec.yaml；解析與 ESUE 用 analysis/self_earnings_parse.py，整個檔案的雜湊一併凍結）：
- 資料：公開資訊觀測站重大訊息，主旨含「自結」與損益／盈餘／獲利／淨利；每天重抓當年（1、2 月另抓前一年）的主旨清單，
  新公告逐則抓內文，依 self_earnings_parse.py 解析、計算 ESUE。
- 事件：發言日期 2026-05-01 以後、有 ESUE 的公告；13:30 以後發言者事件日 0 為下一個交易日。事件第一次出現時寫入 events.csv
  （之後不改）；股票池成員與產業取 config/universe_mcap_membership.csv 中事件年度的市值前 500 名。
- 報酬：CAR[+2, +21] = Σ（個股含息報酬 − β × 加權指數含息報酬），β 為前一日以前 250 日（最少 120 日）的迴歸係數。
- 主要指標：每個事件月份（事件日 0 所在月），前 500 名成員依 ESUE 分三組（至少 6 家），前三分之一 − 後三分之一的平均 CAR；
  另記金融股（產業「金融保險」「金融業」）內部的同一指標。月份內所有事件的視窗都結束後才結算。
- 類型：事件月份在凍結日所在月份以前者為 backfill（研究期間之後、凍結之前的樣本外資料），之後為 live。
- 檢定（事前寫下）：12 個 live 月份時，平均 < 0 視為失效警訊；24 個 live 月份（約 2 年）時正式檢定，
  主要指標平均 > 0 且 t > 2 才算確認（回測每月標準差約 2.5%，預期 t 約 2.3）。

用法（於專案根目錄）：
    .venv/Scripts/python forward/run_forward_se.py freeze
    .venv/Scripts/python forward/run_forward_se.py update     # 抓新公告、登錄新事件
    .venv/Scripts/python forward/run_forward_se.py resolve    # 結算視窗已結束的月份
    .venv/Scripts/python forward/run_forward_se.py report
    （forward/run_forward.py auto 每天呼叫 auto()：update + resolve + report）
研究記錄，非投資建議。
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import inspect
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "analysis"))

from data import fetch_financials as ff  # noqa: E402
from forward import run_forward as fv1  # noqa: E402
import fetch_self_earnings as fse  # noqa: E402
import self_earnings_parse as sp  # noqa: E402

SE_DIR = ROOT / "forward" / "se"
SPEC_PATH = SE_DIR / "spec.yaml"
EVENTS = SE_DIR / "events.csv"
RECORDS = SE_DIR / "records.csv"
REPORT = SE_DIR / "REPORT.md"
PUBLISH_FILES = [str(p.relative_to(ROOT)).replace("\\", "/") for p in (SPEC_PATH, EVENTS, RECORDS, REPORT)]
HEADLINES = sp.EV / "self_earnings_headlines.csv"
MEMBERSHIP = ROOT / "config" / "universe_mcap_membership.csv"
START = "2026-05-01"
WIN = (2, 21)
TOP_N = 500
FIN = ("金融保險", "金融業")
LATE = "133000"
EVENT_COLUMNS = ["stock_id", "name", "data_ym", "announce_date", "spoke_time", "day0", "measure", "x", "esue", "in_top500", "fin",
                 "subject", "recorded_utc", "git_commit"]
RECORD_COLUMNS = ["month", "mode", "n", "n_fin", "top", "bottom", "spread", "fin_spread", "last_exit", "detail", "resolved_utc"]


# ---------------------------------------------------------------------------
# 規則（凍結）
# ---------------------------------------------------------------------------

def day0_of(days: pd.DatetimeIndex, announce: pd.Timestamp, spoke_time: str) -> pd.Timestamp | None:
    """13:30 以後發言 → 下一個交易日；否則當日（非交易日取下一個交易日）。"""
    d = announce + pd.Timedelta(days=1) if str(spoke_time).zfill(6) >= LATE else announce
    k = int(days.searchsorted(d, side="left"))
    return days[k] if k < len(days) else None


def terciles(x: np.ndarray) -> np.ndarray:
    """同 analysis/corp_event_study.terciles：至少 6 個有效值；≤ 1/3 分位為 0、≤ 2/3 為 1、其餘 2。"""
    out = np.full(len(x), -1)
    ok = np.isfinite(x)
    if ok.sum() < 6:
        return out
    q1, q2 = np.nanquantile(x[ok], [1 / 3, 2 / 3])
    out[ok] = np.where(x[ok] <= q1, 0, np.where(x[ok] <= q2, 1, 2))
    return out


def car(stock: pd.Series, mkt: pd.Series, day0: pd.Timestamp) -> float:
    """stock、mkt：含息指數（日期索引）；CAR[+2,+21]，β 用前一日以前 250 日（最少 120 日）。"""
    df = pd.concat([stock.pct_change(), mkt.pct_change()], axis=1, keys=["r", "m"], sort=True).dropna(subset=["m"])
    beta = (df["r"].rolling(250, min_periods=120).cov(df["m"]) / df["m"].rolling(250, min_periods=120).var()).shift(1)
    k0 = int(df.index.searchsorted(day0))
    if k0 >= len(df) or df.index[k0] != day0 or k0 + WIN[1] >= len(df):
        return float("nan")
    w = df.iloc[k0 + WIN[0]: k0 + WIN[1] + 1]
    ar = w["r"] - beta.iloc[k0 + WIN[0]: k0 + WIN[1] + 1].fillna(1.0) * w["m"]
    return float(ar.sum()) if ar.notna().any() else float("nan")


def month_spread(g: pd.DataFrame) -> tuple[float, float, float]:
    """g：同一事件月份的 [esue, car]；回傳（前三分之一平均, 後三分之一平均, 前 − 後）。"""
    q = terciles(g["esue"].to_numpy(float))
    hi, lo = g.loc[q == 2, "car"].dropna(), g.loc[q == 0, "car"].dropna()
    if not len(hi) or not len(lo):
        return float("nan"), float("nan"), float("nan")
    return float(hi.mean()), float(lo.mean()), float(hi.mean() - lo.mean())


def frozen_sources() -> dict[str, str]:
    return {"se.day0_of": inspect.getsource(day0_of), "se.terciles": inspect.getsource(terciles), "se.car": inspect.getsource(car),
            "se.month_spread": inspect.getsource(month_spread),
            "self_earnings_parse.py": Path(sp.__file__).read_text(encoding="utf-8"),
            "fetch_financials.total_return_index": inspect.getsource(ff.total_return_index),
            "se.constants": repr((START, WIN, TOP_N, FIN, LATE))}


def source_hashes() -> dict[str, str]:
    return {k: hashlib.sha256(v.replace("\r\n", "\n").encode("utf-8")).hexdigest() for k, v in frozen_sources().items()}


def git_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def load_spec() -> dict:
    if not SPEC_PATH.exists():
        raise SystemExit(f"{SPEC_PATH} 不存在；先執行 freeze。")
    spec = yaml.safe_load(SPEC_PATH.read_text(encoding="utf-8"))
    changed = [k for k, h in spec["frozen_source_sha256"].items() if source_hashes().get(k) != h]
    if changed:
        raise SystemExit("se 規則程式碼已與凍結時不同：" + "、".join(changed) + "。修改規則請建立新版本。")
    return spec


# ---------------------------------------------------------------------------
# 指令
# ---------------------------------------------------------------------------

def cmd_freeze(args) -> None:
    if SPEC_PATH.exists():
        raise SystemExit(f"{SPEC_PATH} 已存在；凍結只做一次。")
    SE_DIR.mkdir(parents=True, exist_ok=True)
    spec = {
        "spec_version": "se-v1",
        "frozen_utc": fv1.now_utc(),
        "frozen_git_commit": git_commit(),
        "rules": {
            "data": "公開資訊觀測站重大訊息（主旨含自結與損益／盈餘／獲利／淨利），內文依 analysis/self_earnings_parse.py 解析",
            "signal": "ESUE =（本月 − 去年同月 − 過去 24 個月年差平均）÷ 年差標準差；稅後涵蓋率 ≥ 80% 的公司用稅後，否則稅前",
            "event": f"發言日期 {START} 以後、有 ESUE 的公告；13:30 以後發言者事件日 0 為下一個交易日；第一次出現時登錄、之後不改",
            "universe": f"事件年度市值前 {TOP_N} 名（config/universe_mcap_membership.csv）",
            "return": "CAR[+2,+21] = Σ（個股含息 − β × 加權指數含息），β 為前一日以前 250 日迴歸",
            "metric": "每個事件月份：ESUE 前三分之一 − 後三分之一的平均 CAR（至少 6 家）；另記金融股內部",
            "mode": "事件月份在凍結月份以前為 backfill，之後為 live",
        },
        "preregistration": {
            "hypothesis": "每月前 − 後的 CAR 差長期平均 > 0",
            "backtest_expectation": {"mean_spread": 0.0119, "t": 4.4, "n_months": 87, "fin_mean_spread": 0.0106, "fin_t": 4.9,
                                     "source": "docs/self_earnings_report.md"},
            "evaluation": ["只把 mode = live 的月份算入正式檢定，backfill 另列",
                           "12 個 live 月份時：主要指標平均 < 0 視為失效警訊",
                           "24 個 live 月份（約 2 年）時正式檢定：主要指標平均 > 0 且 t > 2 才算確認"],
            "notes": "只記錄訊號，不代表可交易（回測的金融股月度多空扣成本後 Sharpe 只有 0.04 / 0.51）。",
        },
        "frozen_source_sha256": source_hashes(),
    }
    SPEC_PATH.write_text(yaml.safe_dump(spec, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(f"已凍結 se 前瞻規格 → {SPEC_PATH}")


def _client():
    import dotenv

    dotenv.load_dotenv(ROOT / ".env")
    return ff.FinMindClient(cache_dir=fv1.SNAPSHOT_ROOT / "se" / dt.date.today().isoformat())


def _market(client) -> pd.Series:
    tri = client.get("TaiwanStockTotalReturnIndex", "TAIEX", "2024-06-01")
    return pd.Series(tri["price"].astype(float).to_numpy(), index=pd.to_datetime(tri["date"])).sort_index()


def _tri(client, sid: str) -> pd.Series:
    px = client.get("TaiwanStockPrice", sid, "2024-06-01")
    if px.empty:
        return pd.Series(dtype=float)
    px = px[px["close"].astype(float) > 0].copy()
    px["date"] = pd.to_datetime(px["date"])
    ev = ff.get_adjustment_events(client, sid + ".TW", "2024-06-01", dt.date.today().isoformat())
    return pd.Series(ff.total_return_index(px[["date", "close"]], ev).to_numpy(), index=px["date"]).sort_index()


def cmd_update(args) -> int:
    """抓當年主旨、新公告內文，解析後登錄新事件；回傳新增事件數。"""
    spec = load_spec()
    today = dt.date.today()
    years = [today.year - 1, today.year] if today.month <= 2 else [today.year]
    rows = []
    for kw2 in fse.KW2:
        for kind in ("L", "O"):
            for y in years:
                rows += fse.year_rows(kw2, kind, y, cache=False)
    new = fse.clean(rows)
    old = pd.read_csv(HEADLINES, dtype={"stock_id": str, "seq": str, "spoke_time": str}, parse_dates=["date"])
    new["date"] = pd.to_datetime(new["date"])
    for c in ("stock_id", "seq", "spoke_time"):
        new[c] = new[c].astype(str)
    h = pd.concat([old, new], ignore_index=True).drop_duplicates(["stock_id", "date", "seq", "subject"]).sort_values("date").reset_index(drop=True)
    if len(h) > len(old):
        h.to_csv(HEADLINES, index=False)
        print(f"主旨新增 {len(h) - len(old)} 則")
    fse.contents(h[h["date"] >= START])
    e = sp.esue(sp.series(sp.parse_all(h)))
    e = e[e["esue"].notna() & (e["date"] >= START)]
    ev = fv1.read_csv(EVENTS, EVENT_COLUMNS)
    have = set(zip(ev["stock_id"].astype(str).str.zfill(4), ev["data_ym"].astype(str))) if not ev.empty else set()
    e = e[[(s, d) not in have for s, d in zip(e["stock_id"], e["data_ym"])]]
    if e.empty:
        return 0
    client = _client()
    days = _market(client).index
    mem = pd.read_csv(MEMBERSHIP, dtype={"stock_id": str})
    out, now, commit = [], fv1.now_utc(), git_commit()
    for r in e.itertuples():
        d0 = day0_of(days, pd.Timestamp(r.date), r.spoke_time)
        if d0 is None:
            continue                                                # 事件日 0 的資料還沒出來，明天再登錄
        m = mem[(mem["year"] == d0.year) & (mem["stock_id"] == r.stock_id)]
        out.append({"stock_id": r.stock_id, "name": r.name, "data_ym": r.data_ym, "announce_date": pd.Timestamp(r.date).date().isoformat(),
                    "spoke_time": str(r.spoke_time).zfill(6), "day0": d0.date().isoformat(), "measure": r.measure, "x": r.x,
                    "esue": round(float(r.esue), 6), "in_top500": bool(len(m) and m["rank"].iloc[0] <= TOP_N),
                    "fin": bool(len(m) and m["sector"].iloc[0] in FIN), "subject": r.subject, "recorded_utc": now, "git_commit": commit})
    if out:
        fv1.append_csv(EVENTS, pd.DataFrame(out), EVENT_COLUMNS)
        print(f"登錄 {len(out)} 個新事件（規格 {spec['spec_version']}）")
    return len(out)


def cmd_resolve(args) -> int:
    spec = load_spec()
    ev = fv1.read_csv(EVENTS, EVENT_COLUMNS)
    if ev.empty:
        return 0
    ev["stock_id"] = ev["stock_id"].astype(str).str.zfill(4)
    ev["day0"] = pd.to_datetime(ev["day0"])
    ev["month"] = ev["day0"].dt.strftime("%Y-%m")
    done = set(fv1.read_csv(RECORDS, RECORD_COLUMNS)["month"].astype(str))
    this_month = dt.date.today().strftime("%Y-%m")
    todo = sorted(m for m in ev["month"].unique() if m not in done and m < this_month)
    if not todo:
        return 0
    client = _client()
    mkt = _market(client)
    days = mkt.index
    frozen_month = spec["frozen_utc"][:7]
    rows = []
    for mth in todo:
        g = ev[(ev["month"] == mth) & (ev["in_top500"].astype(str) == "True")].copy()
        k_last = int(days.searchsorted(g["day0"].max())) + WIN[1] if len(g) else -1
        if len(g) and k_last >= len(days):
            continue                                                # 視窗還沒結束
        tris = {s: _tri(client, s) for s in g["stock_id"].unique()}
        g["car"] = [car(tris[s], mkt, d) for s, d in zip(g["stock_id"], g["day0"])]
        top, bot, spr = month_spread(g)
        f = g[g["fin"].astype(str) == "True"]
        fin_spr = month_spread(f)[2]
        detail = ";".join(f"{s}:{e:+.2f}:{c:+.4f}" for s, e, c in zip(g["stock_id"], g["esue"].astype(float), g["car"]))
        rows.append({"month": mth, "mode": "backfill" if mth <= frozen_month else "live", "n": len(g), "n_fin": len(f),
                     "top": top, "bottom": bot, "spread": spr, "fin_spread": fin_spr,
                     "last_exit": days[k_last].date().isoformat() if len(g) else "", "detail": detail, "resolved_utc": fv1.now_utc()})
    if rows:
        fv1.append_csv(RECORDS, pd.DataFrame(rows), RECORD_COLUMNS)
        print(f"結算 {len(rows)} 個月份")
    return len(rows)


def _t(x: pd.Series) -> str:
    x = x.dropna()
    if len(x) < 2 or x.std(ddof=1) == 0:
        return f"平均 {x.mean():+.2%}（{len(x)} 個月）" if len(x) else "—"
    return f"平均 {x.mean():+.2%}、t {x.mean() / x.std(ddof=1) * math.sqrt(len(x)):.2f}（{len(x)} 個月）"


def cmd_report(args) -> None:
    spec = load_spec()
    rec = fv1.read_csv(RECORDS, RECORD_COLUMNS)
    ev = fv1.read_csv(EVENTS, EVENT_COLUMNS)
    f = lambda x: "—" if pd.isna(x) or x == "" else f"{float(x):+.2%}"  # noqa: E731
    lines = ["# 前瞻記錄 se：每月自結損益驚奇（自動產生）", "",
             f"規格：[spec.yaml](spec.yaml)（凍結於 {spec['frozen_utc']}）；程式 [forward/run_forward_se.py](../run_forward_se.py)；"
             "研究依據 [docs/self_earnings_report.md](../../docs/self_earnings_report.md)。研究記錄，非投資建議。", "",
             "CAR = 事件日 0 後第 +2 ~ +21 個交易日的累積異常報酬（個股含息 − β × 加權指數含息）；「前 − 後」= 同月份市值前 500 名中 "
             "ESUE 前三分之一 − 後三分之一的平均 CAR（至少 6 家才分組）。回測（2019 ~ 2026/04）每月平均 +1.19%（t 4.4）、金融股內部 +1.06%（t 4.9）。", "",
             f"已登錄事件 {len(ev)} 則；已結算月份 {len(rec)} 個。", "",
             "| 事件月份 | 類型 | 前 500 名事件數 | 金融股 | 前三分之一 | 後三分之一 | 前 − 後 | 金融股前 − 後 | 視窗結束 |", "|---|---|---|---|---|---|---|---|---|"]
    for _, r in rec.iterrows():
        lines.append(f"| {r['month']} | {r['mode']} | {int(r['n'])} | {int(r['n_fin'])} | {f(r['top'])} | {f(r['bottom'])} | "
                     f"{f(r['spread'])} | {f(r['fin_spread'])} | {r['last_exit']} |")
    for mode in ("backfill", "live"):
        sub = rec[rec["mode"] == mode] if not rec.empty else rec
        lines += ["", f"**{mode}**：前 − 後 {_t(pd.to_numeric(sub['spread'], errors='coerce'))}；"
                      f"金融股 {_t(pd.to_numeric(sub['fin_spread'], errors='coerce'))}。"]
    lines += ["", "檢定（事前寫下）：12 個 live 月份時平均 < 0 為失效警訊；24 個 live 月份時平均 > 0 且 t > 2 才算確認。"]
    if not ev.empty:
        pend = sorted(set(pd.to_datetime(ev["day0"]).dt.strftime("%Y-%m")) - set(rec["month"].astype(str)))
        if pend:
            lines.append(f"待結算（月份未結束或視窗未滿 21 個交易日）：{'、'.join(pend)}。")
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"已更新 {REPORT}")


def auto() -> bool:
    """每日：抓新公告、登錄事件、結算月份、更新報告；回傳是否有變動。"""
    if not SPEC_PATH.exists():
        return False
    before = REPORT.read_text(encoding="utf-8") if REPORT.exists() else ""
    n_ev = len(fv1.read_csv(EVENTS, EVENT_COLUMNS))
    try:
        cmd_update(None)
    except RuntimeError as exc:                                     # 公開資訊觀測站連線失敗：只結算既有事件
        print(f"[auto] se 抓取失敗，明天再試：{str(exc)[:200]}")
    cmd_resolve(None)
    cmd_report(None)
    return REPORT.read_text(encoding="utf-8") != before or len(fv1.read_csv(EVENTS, EVENT_COLUMNS)) != n_ev


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description="前瞻記錄 se")
    sub = p.add_subparsers(dest="cmd", required=True)
    for c in ("freeze", "update", "resolve", "report"):
        sub.add_parser(c)
    a = p.parse_args(argv)
    {"freeze": cmd_freeze, "update": cmd_update, "resolve": cmd_resolve, "report": cmd_report}[a.cmd](a)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
