"""前瞻記錄 msci：MSCI 臺灣指數（標準型）季度調整，公告到生效期間納入股與刪除股的報酬。

研究依據：docs/index_rebalance_report.md（2019 ~ 2026/04，23 次審核：公告到生效的納入 − 刪除 +5.5%，t 2.1，兩段同號但各自不顯著）。
樣本太少，回測只能算勉強通過；這裡把規則凍結，逐季記錄，2–3 年後再判斷。紀錄在 forward/msci/。

規則（凍結於 forward/msci/spec.yaml）：
- 事件：每次 MSCI 季度審核（2／5／8／11 月）中，MSCI 臺灣指數（標準型）的新增與刪除名單（來源：MSCI 官方 Index Review
  公告的 STPublicList PDF，研究資料 config/index_changes/msci_tw_changes.csv 用同一來源）。
- 進場：公布日（台灣時間清晨公布）的收盤；公布日非交易日時取下一個交易日收盤。
- 出場：生效日（MSCI 公告的 as of the close of，遇台灣休市取之前最後一個交易日）的收盤。
- 報酬：每檔含息報酬 − 加權指數含息報酬（β = 1，不估計 β）；納入組與刪除組各自等權平均。
- 主要指標：每次審核的「納入 − 刪除」超額報酬（只有一邊時取該邊，刪除取負號），以及扣成本後的版本
  （每邊一買一賣 2 × 0.29625%；不計借券費）。
- 檢定（事前寫下）：8 次 live 審核（約 2 年）時，平均淨報酬 < 0 視為失效警訊；12 次 live 審核（約 3 年）時正式檢定，
  平均淨報酬 > 0 且 t > 2 才算確認。2026-05、2026-08 兩次審核在研究期間之後，作為 backfill 另列。

用法（於專案根目錄）：
    .venv/Scripts/python forward/run_forward_msci.py freeze
    .venv/Scripts/python forward/run_forward_msci.py backfill            # 從 config/index_changes/msci_tw_changes.csv 匯入 2026-05 起的審核
    .venv/Scripts/python forward/run_forward_msci.py fetch --review 2026-11   # 下載 MSCI PDF，印出臺灣段落（新增／刪除的英文名稱）
    .venv/Scripts/python forward/run_forward_msci.py add --review 2026-11 --announce 2026-11-11 --effective 2026-11-30 \\
        --add 2330,2317 --delete 1101     # 人工確認代號後登錄（只能新增，不得修改已登錄的審核）
    .venv/Scripts/python forward/run_forward_msci.py resolve             # 生效日已過的審核計算報酬
    .venv/Scripts/python forward/run_forward_msci.py report
    （forward/run_forward.py auto 每天呼叫 auto()：resolve + report）
研究記錄，非投資建議。
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import inspect
import io
import math
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from data import fetch_financials as ff  # noqa: E402
from forward import run_forward as fv1  # noqa: E402

MSCI_DIR = ROOT / "forward" / "msci"
SPEC_PATH = MSCI_DIR / "spec.yaml"
EVENTS = MSCI_DIR / "events.csv"
RECORDS = MSCI_DIR / "records.csv"
REPORT = MSCI_DIR / "REPORT.md"
PUBLISH_FILES = [str(p.relative_to(ROOT)).replace("\\", "/") for p in (SPEC_PATH, EVENTS, RECORDS, REPORT)]
RESEARCH_CSV = ROOT / "config" / "index_changes" / "msci_tw_changes.csv"
BACKFILL_START = "2026-05"
STOCK_COST = 0.0029625
EVENT_COLUMNS = ["review", "mode", "announce_date", "effective_date", "action", "stock_id", "name", "source", "recorded_utc", "git_commit"]
RECORD_COLUMNS = ["review", "mode", "entry_date", "exit_date", "n_add", "n_del", "add_excess", "del_excess", "spread", "net",
                  "market_ret", "detail", "resolved_utc"]
PDF_URL = "https://app2.msci.com/eqb/gimi/stdindex/MSCI_{mon}{yy}_STPublicList.pdf"


# ---------------------------------------------------------------------------
# 規則（凍結）
# ---------------------------------------------------------------------------

def trade_dates(days: pd.DatetimeIndex, announce: pd.Timestamp, effective: pd.Timestamp) -> tuple[pd.Timestamp, pd.Timestamp] | None:
    """進場 = 公布日當天或之後第一個交易日；出場 = 生效日當天或之前最後一個交易日。"""
    k_in = int(days.searchsorted(announce, side="left"))
    k_out = int(days.searchsorted(effective, side="right")) - 1
    if k_in >= len(days) or k_out < 0 or k_out <= k_in:
        return None
    return days[k_in], days[k_out]


def review_return(adds: dict[str, float], dels: dict[str, float], market: float) -> dict:
    """adds / dels：{代號: 期間含息報酬}；回傳納入、刪除的平均超額報酬與「納入 − 刪除」（扣成本前後）。"""
    a = np.mean([r - market for r in adds.values()]) if adds else np.nan
    d = np.mean([r - market for r in dels.values()]) if dels else np.nan
    round_trip = 2 * STOCK_COST
    if adds and dels:
        spread, net = a - d, (a - round_trip) - (d + round_trip)
    elif adds:
        spread, net = a, a - round_trip
    elif dels:
        spread, net = -d, -d - round_trip
    else:
        spread = net = np.nan
    return {"add_excess": a, "del_excess": d, "spread": spread, "net": net}


def frozen_sources() -> dict[str, str]:
    return {"msci.trade_dates": inspect.getsource(trade_dates), "msci.review_return": inspect.getsource(review_return),
            "fetch_financials.total_return_index": inspect.getsource(ff.total_return_index),
            "msci.constants": repr((STOCK_COST, BACKFILL_START))}


def source_hashes() -> dict[str, str]:
    return {k: hashlib.sha256(v.encode("utf-8")).hexdigest() for k, v in frozen_sources().items()}


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
        raise SystemExit("msci 規則程式碼已與凍結時不同：" + "、".join(changed) + "。修改規則請建立新版本。")
    return spec


# ---------------------------------------------------------------------------
# 指令
# ---------------------------------------------------------------------------

def cmd_freeze(args) -> None:
    if SPEC_PATH.exists():
        raise SystemExit(f"{SPEC_PATH} 已存在；凍結只做一次。")
    MSCI_DIR.mkdir(parents=True, exist_ok=True)
    spec = {
        "spec_version": "msci-v1",
        "frozen_utc": fv1.now_utc(),
        "frozen_git_commit": git_commit(),
        "rules": {
            "events": "MSCI 季度審核（2／5／8／11 月）MSCI 臺灣指數（標準型）的新增與刪除名單，來源為 MSCI 官方 STPublicList PDF",
            "entry": "公布日（台灣時間清晨公布）收盤；非交易日取下一個交易日",
            "exit": "生效日（as of the close of；遇台灣休市取之前最後交易日）收盤",
            "return": "每檔含息報酬 − 加權指數含息報酬（β = 1）；納入、刪除各自等權平均",
            "metric": "每次審核的納入 − 刪除（只有一邊時取該邊，刪除取負號）；淨值另扣每邊一買一賣 2 × 0.29625%，不計借券費",
            "backfill_start": BACKFILL_START,
        },
        "preregistration": {
            "hypothesis": "每次審核的淨報酬長期平均 > 0",
            "backtest_expectation": {"mean_spread": 0.0545, "t": 2.1, "n_reviews": 23, "source": "docs/index_rebalance_report.md"},
            "evaluation": ["只把 mode = live 算入正式檢定，backfill 另列",
                           "8 次 live 審核時：平均淨報酬 < 0 視為失效警訊",
                           "12 次 live 審核（約 3 年）時正式檢定：平均淨報酬 > 0 且 t > 2 才算確認"],
            "notes": "名單需在公布當天由人工（或排程中的 Claude）從 MSCI PDF 對應代號後以 add 登錄；登錄後不得修改，錯誤只能在 REPORT 註記。",
        },
        "frozen_source_sha256": source_hashes(),
    }
    SPEC_PATH.write_text(yaml.safe_dump(spec, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(f"已凍結 msci 前瞻規格 → {SPEC_PATH}")


def _append_events(rows: list[dict]) -> None:
    ev = fv1.read_csv(EVENTS, EVENT_COLUMNS)
    have = set(ev["review"].astype(str)) if not ev.empty else set()
    reviews = {r["review"] for r in rows}
    dup = reviews & have
    if dup:
        raise SystemExit(f"審核 {'、'.join(sorted(dup))} 已登錄，不得重複或修改。")
    fv1.append_csv(EVENTS, pd.DataFrame(rows), EVENT_COLUMNS)


def cmd_backfill(args) -> None:
    load_spec()
    src = pd.read_csv(RESEARCH_CSV, dtype={"stock_id": str})
    src = src[src["review"] >= BACKFILL_START]
    ev = fv1.read_csv(EVENTS, EVENT_COLUMNS)
    have = set(ev["review"].astype(str)) if not ev.empty else set()
    src = src[~src["review"].isin(have)]
    if src.empty:
        print("沒有需要回填的審核")
        return
    now, commit = fv1.now_utc(), git_commit()
    rows = [{"review": r["review"], "mode": "backfill", "announce_date": r["announce_date"], "effective_date": r["effective_date"],
             "action": r["action"], "stock_id": r["stock_id"] if isinstance(r["stock_id"], str) else "", "name": r["name"] if isinstance(r["name"], str) else "",
             "source": r["source"], "recorded_utc": now, "git_commit": commit} for _, r in src.iterrows()]
    _append_events(rows)
    print(f"回填 {src['review'].nunique()} 次審核、{len(rows)} 列")


def cmd_add(args) -> None:
    load_spec()
    now, commit = fv1.now_utc(), git_commit()
    src = args.source or PDF_URL.format(mon=pd.Timestamp(args.review + "-01").strftime("%b"), yy=args.review[2:4])
    rows = []
    for action, codes in (("add", args.add), ("del", args.delete)):
        for c in [x.strip() for x in (codes or "").split(",") if x.strip()]:
            if not re.fullmatch(r"\d{4}", c):
                raise SystemExit(f"代號格式錯誤：{c}")
            rows.append({"review": args.review, "mode": "live", "announce_date": args.announce, "effective_date": args.effective,
                         "action": action, "stock_id": c, "name": "", "source": src, "recorded_utc": now, "git_commit": commit})
    if not rows:
        rows.append({"review": args.review, "mode": "live", "announce_date": args.announce, "effective_date": args.effective,
                     "action": "none", "stock_id": "", "name": "", "source": src, "recorded_utc": now, "git_commit": commit})
    _append_events(rows)
    print(f"已登錄 {args.review}：{len(rows)} 列")


def cmd_fetch(args) -> None:
    import pdfplumber
    import requests

    url = PDF_URL.format(mon=pd.Timestamp(args.review + "-01").strftime("%b"), yy=args.review[2:4])
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=120)
    if r.status_code != 200 or not r.content.startswith(b"%PDF"):
        raise SystemExit(f"尚未取得 {url}（HTTP {r.status_code}）")
    with pdfplumber.open(io.BytesIO(r.content)) as pdf:
        text = "\n".join(p.extract_text() or "" for p in pdf.pages)
    m = re.search(r"MSCI TAIWAN INDEX(.*?)(?:\nMSCI [A-Z ]+INDEX|\Z)", text, flags=re.S)
    print(url)
    print(m.group(0) if m else "PDF 中沒有 MSCI TAIWAN INDEX 段落（本次可能無變動）")


def _prices(client, sid: str) -> pd.Series:
    px = client.get("TaiwanStockPrice", sid, "2025-06-01")
    if px.empty:
        return pd.Series(dtype=float)
    px = px[px["close"].astype(float) > 0].copy()
    px["date"] = pd.to_datetime(px["date"])
    ev = ff.get_adjustment_events(client, sid + ".TW", "2025-06-01", dt.date.today().isoformat())
    return pd.Series(ff.total_return_index(px[["date", "close"]], ev).to_numpy(), index=px["date"]).sort_index()


def cmd_resolve(args) -> int:
    load_spec()
    ev = fv1.read_csv(EVENTS, EVENT_COLUMNS)
    if ev.empty:
        print("沒有登錄的審核")
        return 0
    ev["stock_id"] = ev["stock_id"].fillna("").astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(4).where(ev["stock_id"].notna() & (ev["stock_id"].astype(str) != ""), "")
    done = set(fv1.read_csv(RECORDS, RECORD_COLUMNS)["review"].astype(str))
    today = pd.Timestamp(dt.date.today())
    todo = [r for r in ev["review"].astype(str).unique() if r not in done]
    if not todo:
        return 0
    import dotenv

    dotenv.load_dotenv(ROOT / ".env")
    client = ff.FinMindClient(cache_dir=fv1.SNAPSHOT_ROOT / "msci" / dt.date.today().isoformat())
    tri = client.get("TaiwanStockTotalReturnIndex", "TAIEX", "2025-06-01")
    mkt = pd.Series(tri["price"].astype(float).to_numpy(), index=pd.to_datetime(tri["date"])).sort_index()
    rows = []
    for rv in sorted(todo):
        g = ev[ev["review"].astype(str) == rv]
        ann, eff = pd.Timestamp(g["announce_date"].iloc[0]), pd.Timestamp(g["effective_date"].iloc[0])
        if eff >= today:
            continue
        td = trade_dates(mkt.index, ann, eff)
        if td is None or td[1] > mkt.index[-1]:
            continue
        k_in, k_out = td
        mret = float(mkt.loc[k_out] / mkt.loc[k_in] - 1)
        rets = {"add": {}, "del": {}}
        for _, r in g[g["action"].isin(["add", "del"])].iterrows():
            p = _prices(client, r["stock_id"])
            if k_in in p.index and k_out in p.index:
                rets[r["action"]][r["stock_id"]] = float(p.loc[k_out] / p.loc[k_in] - 1)
        res = review_return(rets["add"], rets["del"], mret)
        detail = ";".join(f"{a}:{s}:{v - mret:+.4f}" for a in ("add", "del") for s, v in rets[a].items())
        rows.append({"review": rv, "mode": g["mode"].iloc[0], "entry_date": k_in.date().isoformat(), "exit_date": k_out.date().isoformat(),
                     "n_add": len(rets["add"]), "n_del": len(rets["del"]), **res, "market_ret": mret, "detail": detail,
                     "resolved_utc": fv1.now_utc()})
    if rows:
        fv1.append_csv(RECORDS, pd.DataFrame(rows), RECORD_COLUMNS)
        print(f"結算 {len(rows)} 次審核")
    return len(rows)


def cmd_report(args) -> None:
    spec = load_spec()
    rec = fv1.read_csv(RECORDS, RECORD_COLUMNS)
    ev = fv1.read_csv(EVENTS, EVENT_COLUMNS)
    lines = ["# 前瞻記錄 msci：MSCI 臺灣指數季度調整（自動產生）", "",
             f"規格：[spec.yaml](spec.yaml)（凍結於 {spec['frozen_utc']}）；程式 [forward/run_forward_msci.py](../run_forward_msci.py)；"
             "研究依據 [docs/index_rebalance_report.md](../../docs/index_rebalance_report.md)。研究記錄，非投資建議。", "",
             "超額報酬 = 公布日收盤到生效日收盤的含息報酬 − 加權指數含息報酬；淨報酬另扣每邊一買一賣 2 × 0.29625%（不計借券費）。", "",
             f"已登錄審核 {ev['review'].nunique() if not ev.empty else 0} 次；已結算 {len(rec)} 次。", "",
             "| 審核 | 類型 | 進場 | 出場 | 納入檔數 | 刪除檔數 | 納入超額 | 刪除超額 | 納入 − 刪除 | 淨報酬 |", "|---|---|---|---|---|---|---|---|---|---|"]
    f = lambda x: "—" if pd.isna(x) else f"{x:+.2%}"  # noqa: E731
    for _, r in rec.iterrows():
        lines.append(f"| {r['review']} | {r['mode']} | {r['entry_date']} | {r['exit_date']} | {int(r['n_add'])} | {int(r['n_del'])} | "
                     f"{f(r['add_excess'])} | {f(r['del_excess'])} | {f(r['spread'])} | {f(r['net'])} |")
    live = rec[rec["mode"] == "live"]["net"].dropna() if not rec.empty else pd.Series(dtype=float)
    if len(live) >= 2:
        t = live.mean() / live.std(ddof=1) * math.sqrt(len(live)) if live.std(ddof=1) > 0 else float("nan")
        lines += ["", f"live 審核 {len(live)} 次：平均淨報酬 {live.mean():+.2%}、t {t:.2f}（8 次時警訊檢查，12 次時正式檢定）。"]
    else:
        lines += ["", f"live 審核 {len(live)} 次：樣本不足，尚不檢定（8 次時警訊檢查，12 次時正式檢定）。"]
    pending = sorted(set(ev["review"].astype(str)) - set(rec["review"].astype(str))) if not ev.empty else []
    if pending:
        lines.append(f"待結算（生效日未到或資料未更新）：{'、'.join(pending)}。")
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"已更新 {REPORT}")


def auto() -> bool:
    """每日：結算生效日已過的審核並更新報告；回傳是否有變動。"""
    if not SPEC_PATH.exists():
        return False
    before = REPORT.read_text(encoding="utf-8") if REPORT.exists() else ""
    cmd_resolve(None)
    cmd_report(None)
    return REPORT.read_text(encoding="utf-8") != before


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description="前瞻記錄 msci")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("freeze")
    sub.add_parser("backfill")
    s = sub.add_parser("fetch"); s.add_argument("--review", required=True)
    s = sub.add_parser("add")
    s.add_argument("--review", required=True); s.add_argument("--announce", required=True); s.add_argument("--effective", required=True)
    s.add_argument("--add", default=""); s.add_argument("--delete", default=""); s.add_argument("--source", default="")
    sub.add_parser("resolve")
    sub.add_parser("report")
    a = p.parse_args(argv)
    {"freeze": cmd_freeze, "backfill": cmd_backfill, "fetch": cmd_fetch, "add": cmd_add, "resolve": cmd_resolve, "report": cmd_report}[a.cmd](a)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
