"""前瞻驗證 fv5e：fv5 的金融股改用自結盈餘驚奇（ESUE）排序，與 fv5 平行記錄。

研究依據：docs/fin_esue_followup_report.md（點子卡 I018；1.51 / 1.88、全期 1.68 vs fv5 1.45 / 1.87、全期 1.64；事後設計、改善小）。
規格與紀錄在 forward/fv5e/。

規則（凍結於 forward/fv5e/spec.yaml）：
- 其餘與 fv5 完全相同：直接讀 fv5 同一預測日的成員資料（forward/fv5/predictions.csv 的產業、SUE 中性化分數、可借、借券費、β），
  所以 fv5e 必須在 fv5 預測之後執行，且不另外呼叫 FinMind。
- 唯一差異：預測日當天，金融股（產業「金融保險」「金融業」）若有已知的 ESUE（自結損益公告的事件日 0 + 1 ≤ 預測日、
  且距預測日不超過 45 個交易日，取最新一則；13:30 以後發言者事件日 0 為下一個交易日），把 ESUE 轉成這些金融股之間的百分位，
  取當日全體成員 fv5 分數的同一分位數值取代其分數；沒有 ESUE 的金融股維持原分數。ESUE 只用預測日以前發言的公告計算
  （analysis/self_earnings_parse.py，與 forward/se 同一份解析，檔案雜湊凍結）。
- 權重：ls_turnover.ew_ls_buffer（產業內前／後 1/3、只放空可借者、不含緩衝），β 與 fv5 相同算法；三份資金錯開、結算與成本同 fv5。

用法（於專案根目錄）：
    .venv/Scripts/python forward/run_forward_fv5e.py freeze
    .venv/Scripts/python forward/run_forward_fv5e.py backfill        # 補齊 fv5 已預測、fv5e 尚未預測的日期
    .venv/Scripts/python forward/run_forward_fv5e.py resolve
    .venv/Scripts/python forward/run_forward_fv5e.py report
    （每日由 forward/run_forward.py auto 在 fv5、se 之後呼叫 auto()）
研究記錄，非投資建議。
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import inspect
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "analysis"))

import leg_probe as lp  # noqa: E402
import ls_turnover as lt  # noqa: E402
import self_earnings_parse as sp  # noqa: E402
from data.fetch_financials import get_total_return_prices  # noqa: E402
from forward import run_forward as fv1  # noqa: E402
from forward import run_forward_fv2 as fv2  # noqa: E402
from forward import run_forward_fv5 as fv5  # noqa: E402
from forward import run_forward_se as se  # noqa: E402

DIR = ROOT / "forward" / "fv5e"
SPEC_PATH = DIR / "spec.yaml"
PREDICTIONS = DIR / "predictions.csv"
SEGMENTS = DIR / "segments.csv"
PERIODS = DIR / "periods.csv"
REPORT = DIR / "REPORT.md"
PUBLISH_FILES = [str(p.relative_to(ROOT)).replace("\\", "/") for p in (SPEC_PATH, PREDICTIONS, SEGMENTS, PERIODS, REPORT)]
FIN = ("金融保險", "金融業")
LOOKBACK = 45
N_TRANCHE = fv5.N_TRANCHE

PRED_COLUMNS = ["spec_version", "mode", "as_of_date", "tranche", "ticker", "sector", "score_fv5", "esue", "esue_day0", "score",
                "shortable", "fee", "beta", "weight", "tranche_beta", "run_utc", "git_commit"]
SEGMENT_COLUMNS = fv5.SEGMENT_COLUMNS
PERIOD_COLUMNS = ["seg_start", "seg_end", "mode", "n_active", "book_net", "fv5_net", "diff", "resolved_utc"]


# ---------------------------------------------------------------------------
# 規則（凍結）
# ---------------------------------------------------------------------------

def known_esue(e: pd.DataFrame, calendar: list[pd.Timestamp], as_of: pd.Timestamp) -> pd.DataFrame:
    """e：sp.esue 的輸出（只含預測日以前發言的公告）；回傳每檔最新一則已知 ESUE：[ticker, esue, day0]。"""
    days = pd.DatetimeIndex(calendar)
    kd = int(days.searchsorted(as_of))
    rows = []
    for r in e[e["esue"].notna()].itertuples():
        d0 = se.day0_of(days, pd.Timestamp(r.date), r.spoke_time)
        if d0 is None:
            continue
        k0 = int(days.searchsorted(d0))
        if k0 + 1 <= kd and kd - k0 <= LOOKBACK:
            rows.append({"ticker": r.stock_id + ".TW", "esue": float(r.esue), "day0": d0, "k0": k0})
    if not rows:
        return pd.DataFrame(columns=["ticker", "esue", "day0"])
    return pd.DataFrame(rows).sort_values("k0").drop_duplicates("ticker", keep="last")[["ticker", "esue", "day0"]]


def override_scores(g: pd.DataFrame, k: pd.DataFrame) -> pd.Series:
    """g：fv5 當日成員 [ticker, sector, score]；k：known_esue。金融股有 ESUE 者改用 ESUE 百分位對應的全體分數分位數。"""
    s = g.set_index("ticker")["score"].astype(float).copy()
    fin = set(g.loc[g["sector"].isin(FIN), "ticker"])
    k = k[k["ticker"].isin(fin) & k["ticker"].isin(s.index)]
    base = s.dropna()
    if len(k) >= 2 and len(base):
        p = k["esue"].rank(pct=True).to_numpy()
        s.loc[k["ticker"].to_numpy()] = np.nanquantile(base.to_numpy(), p)
    return s


def tranche_weights(g: pd.DataFrame, score: pd.Series) -> pd.Series:
    x = g.set_index("ticker")
    return lt.ew_ls_buffer(score, x["sector"], x["shortable"].astype(bool), q_keep=None)


def frozen_sources() -> dict[str, str]:
    return {"fv5e.known_esue": inspect.getsource(known_esue), "fv5e.override_scores": inspect.getsource(override_scores),
            "fv5e.tranche_weights": inspect.getsource(tranche_weights), "ls_turnover.ew_ls_buffer": inspect.getsource(lt.ew_ls_buffer),
            "fv5.segment_return": inspect.getsource(fv5.segment_return), "se.day0_of": inspect.getsource(se.day0_of),
            "self_earnings_parse.py": Path(sp.__file__).read_text(encoding="utf-8"),
            "fv5e.constants": repr((FIN, LOOKBACK, N_TRANCHE))}


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
        raise SystemExit("fv5e 規則程式碼已與凍結時不同：" + "、".join(changed) + "。修改規則請建立新版本。")
    return spec


# ---------------------------------------------------------------------------
# 指令
# ---------------------------------------------------------------------------

def cmd_freeze(args) -> None:
    if SPEC_PATH.exists():
        raise SystemExit(f"{SPEC_PATH} 已存在；凍結只做一次。")
    DIR.mkdir(parents=True, exist_ok=True)
    spec = {
        "spec_version": "fv5e",
        "frozen_utc": fv1.now_utc(),
        "frozen_git_commit": git_commit(),
        "rules": {
            "base": "與 fv5 完全相同，直接讀 forward/fv5/predictions.csv 同一預測日的成員資料（產業、分數、可借、借券費、β）",
            "override": f"金融股（{'、'.join(FIN)}）若有已知 ESUE（事件日 0 + 1 ≤ 預測日、{LOOKBACK} 個交易日內，取最新），"
                        "以 ESUE 在這些金融股間的百分位，取當日全體 fv5 分數同分位數值取代其分數",
            "esue": "analysis/self_earnings_parse.py（同 forward/se），只用預測日以前發言的公告",
            "portfolio": "ls_turnover.ew_ls_buffer（產業內前／後 1/3、只放空可借者、不含緩衝）；三份資金錯開、結算與成本同 fv5",
        },
        "preregistration": {
            "primary_metric": "組合每段淨報酬（同 fv5），以及同段 fv5e − fv5 的差",
            "hypothesis": "fv5e − fv5 每段差的長期平均 > 0",
            "backtest_expectation": {"sharpe_2019_2022": 1.51, "sharpe_2023_2026": 1.88, "sharpe_full": 1.68,
                                     "fv5_sharpe_full": 1.64, "source": "docs/fin_esue_followup_report.md"},
            "evaluation": ["只把 mode = live 的期數算入，backfill 另列",
                           "24 個 live 期數（約 2 年）時：fv5e − fv5 平均差 ≤ 0 則維持 fv5；平均差 > 0 且 fv5e 本身 t > 2 才考慮以 fv5e 取代 fv5",
                           "回測改善很小（全期 Sharpe +0.04），兩年的差預期不顯著；差的 t 值只作描述"],
            "notes": "事後設計（看過 I015 結果後才測），不得依前瞻結果回頭調整規則。",
        },
        "frozen_source_sha256": source_hashes(),
    }
    SPEC_PATH.write_text(yaml.safe_dump(spec, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(f"已凍結 fv5e 規格 → {SPEC_PATH}")


def _esue_before(as_of: pd.Timestamp) -> pd.DataFrame:
    h = pd.read_csv(se.HEADLINES, dtype={"stock_id": str, "seq": str, "spoke_time": str}, parse_dates=["date"])
    h = h[h["date"] < as_of]
    return sp.esue(sp.series(sp.parse_all(h)))


def predict(as_of: str, mode: str | None = None) -> bool:
    spec = load_spec()
    preds = fv1.read_csv(PREDICTIONS, PRED_COLUMNS)
    if (preds["as_of_date"] == as_of).any():
        return False
    p5 = fv1.read_csv(fv5.PREDICTIONS, fv5.PRED_COLUMNS)
    g = p5[p5["as_of_date"] == as_of].copy()
    if g.empty:
        print(f"[fv5e] {as_of}：fv5 尚未預測，略過")
        return False
    client = fv5.snapshot(dt.date.today().strftime("%Y-%m-%d"))
    calendar = fv1.trading_calendar(client, "2025-01-01")
    a = pd.Timestamp(as_of)
    k = known_esue(_esue_before(a), calendar, a)
    score = override_scores(g, k)
    w = tranche_weights(g, score)
    beta = g.set_index("ticker")["beta"]
    b = float((w * beta.reindex(w.index).fillna(1.0)).sum())
    km = k.set_index("ticker")
    mode = mode or ("backfill" if as_of < spec["frozen_utc"][:10] else g["mode"].iloc[0])     # 凍結日以前的預測日一律 backfill
    out = g.assign(spec_version=spec["spec_version"], mode=mode, score_fv5=g["score"],
                   esue=g["ticker"].map(km["esue"]) if len(km) else np.nan,
                   esue_day0=g["ticker"].map(km["day0"].dt.strftime("%Y-%m-%d")) if len(km) else "",
                   score=g["ticker"].map(score), weight=g["ticker"].map(w).fillna(0.0), tranche_beta=b,
                   run_utc=fv1.now_utc(), git_commit=git_commit())
    fin_rep = out["sector"].isin(FIN) & out["esue"].notna()
    DIR.mkdir(parents=True, exist_ok=True)
    fv1.append_csv(PREDICTIONS, out, PRED_COLUMNS)
    print(f"[fv5e {out['mode'].iloc[0]}] {as_of}：金融股改用 ESUE {int(fin_rep.sum())} 檔；多 {(w > 0).sum()}、空 {(w < 0).sum()}，β {b:+.2f}")
    return True


def cmd_backfill(args) -> int:
    load_spec()
    p5 = fv1.read_csv(fv5.PREDICTIONS, fv5.PRED_COLUMNS)
    return sum(predict(a) for a in sorted(p5["as_of_date"].unique()))


def cmd_resolve(args) -> int:
    """同 fv5：每段 = 相鄰兩個預測日之間，組合 = 在場各份淨報酬加總 ÷ 3；另記同段 fv5 的組合淨報酬。"""
    load_spec()
    preds = fv1.read_csv(PREDICTIONS, PRED_COLUMNS)
    if preds.empty:
        return 0
    per = fv1.read_csv(PERIODS, PERIOD_COLUMNS)
    p5per = fv1.read_csv(fv5.PERIODS, fv5.PERIOD_COLUMNS).set_index("seg_start")
    today = pd.Timestamp(dt.date.today())
    client = fv5.snapshot(today.strftime("%Y-%m-%d"))
    calendar = fv1.trading_calendar(client, "2025-01-01")
    entries = [e for _, e in fv5.scheduled(calendar)]
    done = set(per["seg_start"]) if len(per) else set()
    predicted = sorted(preds["as_of_date"].unique())
    todo = [(a, b) for a, b in zip(entries[:-1], entries[1:])
            if a.strftime("%Y-%m-%d") in predicted and a.strftime("%Y-%m-%d") not in done and b <= calendar[-1]]
    if not todo:
        return 0
    start, end = fv5.data_start(pd.Timestamp(predicted[0])), today.strftime("%Y-%m-%d")
    adj, _ = fv5.load_prices(client, sorted(set(preds["ticker"])), start, end)
    rets = adj.pct_change()
    tx = lp.tx_continuous(client, start, end)
    commit = git_commit()
    n = 0
    for a, b in todo:
        a_s = a.strftime("%Y-%m-%d")
        active = [e for e in entries if e <= a and e.strftime("%Y-%m-%d") in predicted][-N_TRANCHE:]
        seg_rows, daily = [], []
        for e in active:
            batch = preds[preds["as_of_date"] == e.strftime("%Y-%m-%d")]
            w = batch.set_index("ticker")["weight"]
            w = w[w != 0]
            k = int(batch["tranche"].iloc[0])
            earlier = preds[(preds["tranche"] == k) & (preds["as_of_date"] < e.strftime("%Y-%m-%d"))]
            if len(earlier):
                pb = earlier[earlier["as_of_date"] == earlier["as_of_date"].max()]
                prev_w, prev_b = pb.set_index("ticker")["weight"], float(pb["tranche_beta"].iloc[0])
                prev_w = prev_w[prev_w != 0]
            else:
                prev_w, prev_b = None, 0.0
            r = fv5.segment_return(w, float(batch["tranche_beta"].iloc[0]), batch.set_index("ticker")["fee"], rets, tx,
                                   a, b, first=(e == a), prev_weights=prev_w, prev_beta=prev_b)
            daily.append(r["daily"])
            seg_rows.append({"as_of_date": e.strftime("%Y-%m-%d"), "tranche": k, "seg_start": a_s, "seg_end": b.strftime("%Y-%m-%d"),
                             "first_segment": int(e == a), **{x: r[x] for x in ("gross", "hedge", "borrow", "cost", "net")},
                             "resolved_utc": fv1.now_utc(), "git_commit": commit})
        book = float((1 + pd.concat(daily, axis=1).sum(axis=1) / N_TRANCHE).prod() - 1) if daily else float("nan")
        f5 = float(p5per.loc[a_s, "book_net"]) if a_s in p5per.index else float("nan")
        mode = preds.loc[preds["as_of_date"] == a_s, "mode"].iloc[0]
        fv1.append_csv(SEGMENTS, pd.DataFrame(seg_rows), SEGMENT_COLUMNS)
        fv1.append_csv(PERIODS, pd.DataFrame([{"seg_start": a_s, "seg_end": b.strftime("%Y-%m-%d"), "mode": mode, "n_active": len(active),
                                                "book_net": book, "fv5_net": f5, "diff": book - f5, "resolved_utc": fv1.now_utc()}]), PERIOD_COLUMNS)
        n += 1
        print(f"fv5e {a_s} → {b:%Y-%m-%d}：組合 {book:+.2%}（fv5 {f5:+.2%}）")
    return n


def cmd_report(args) -> None:
    spec = load_spec()
    preds = fv1.read_csv(PREDICTIONS, PRED_COLUMNS)
    per = fv1.read_csv(PERIODS, PERIOD_COLUMNS)
    lines = ["# 前瞻驗證報告 fv5e：fv5 的金融股改用自結盈餘驚奇排序（自動產生）", "",
             f"- 規格：`fv5e`（凍結於 {spec['frozen_utc']}，git `{spec['frozen_git_commit'][:8]}`）；與 fv5 平行，研究依據 "
             "[docs/fin_esue_followup_report.md](../../docs/fin_esue_followup_report.md)。研究記錄，非投資建議。",
             f"- 預測日 {preds['as_of_date'].nunique()} 個，已結算段落 {len(per)} 個",
             "- 主要指標：組合每段淨報酬（扣交易成本、借券費，台指期對沖），以及同段 fv5e − fv5 的差。", "",
             "## 累積結果", "", "| 範圍 | fv5e 每段淨報酬 | fv5 每段淨報酬 | fv5e − fv5 |", "|---|---|---|---|"]
    for label, mode in (("live（正式）", "live"), ("backfill（凍結後回填）", "backfill")):
        sub = per[per["mode"] == mode] if len(per) else per
        if len(sub):
            lines.append(f"| {label} | {fv2.summary(sub['book_net'], True)} | {fv2.summary(sub['fv5_net'], True)} | {fv2.summary(sub['diff'], True)} |")
        else:
            lines.append(f"| {label} | 尚無資料 | | |")
    lines += ["", "## 各段", "", "| 段落 | mode | 在場資金份數 | fv5e | fv5 | 差 |", "|---|---|---|---|---|---|"]
    for r in per.itertuples():
        lines.append(f"| {r.seg_start} → {r.seg_end} | {r.mode} | {int(r.n_active)} | {r.book_net:+.2%} | {r.fv5_net:+.2%} | {r.diff:+.2%} |")
    lines += ["", "## 各預測日", "", "| 預測日 | mode | 資金份 | 金融股改用 ESUE 檔數（其中 fv5 原本無分數） | 持股方向與 fv5 不同的檔數 | 做多 | 放空 |", "|---|---|---|---|---|---|---|"]
    p5 = fv1.read_csv(fv5.PREDICTIONS, fv5.PRED_COLUMNS)
    for a, bt in preds.groupby("as_of_date"):
        w5 = p5[p5["as_of_date"] == a].set_index("ticker")["weight"]
        diff = int((np.sign(bt.set_index("ticker")["weight"]) != np.sign(w5.reindex(bt["ticker"]).fillna(0.0).to_numpy())).sum())
        rep = bt["sector"].isin(FIN) & bt["esue"].notna()
        n_rep, n_new = int(rep.sum()), int((rep & bt["score_fv5"].isna()).sum())
        lines.append(f"| {a} | {bt['mode'].iloc[0]} | {int(bt['tranche'].iloc[0]) + 1} | {n_rep}（{n_new}） | {diff} | {(bt['weight'] > 0).sum()} | {(bt['weight'] < 0).sum()} |")
    lines += ["", "## 事先登錄的評估方式", ""] + [f"- {e}" for e in spec["preregistration"]["evaluation"]]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"fv5e 報告 → {REPORT}")


def auto() -> bool:
    """排程用（fv5、se 之後）：補上 fv5 已預測的日期、結算已過的段落；有變動回傳 True。"""
    if not SPEC_PATH.exists():
        return False
    changed = cmd_backfill(None) > 0
    changed |= cmd_resolve(None) > 0
    if changed:
        cmd_report(None)
    return changed


def main(argv=None) -> None:
    import dotenv

    dotenv.load_dotenv(ROOT / ".env")
    p = argparse.ArgumentParser(description="前瞻驗證 fv5e")
    sub = p.add_subparsers(dest="cmd", required=True)
    for c in ("freeze", "backfill", "resolve", "report"):
        sub.add_parser(c)
    a = p.parse_args(argv)
    {"freeze": cmd_freeze, "backfill": cmd_backfill, "resolve": cmd_resolve, "report": cmd_report}[a.cmd](a)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
