"""前瞻驗證 fv5s：fv5 的分數改為 0.75 × SUE ＋ 0.25 × 借券賣出餘額比相對自身歷史排名（S1），與 fv5 平行記錄。

研究依據：docs/ts_rank_report.md（點子卡 I040；合成 1.48 / 2.15、全期 1.78 vs fv5 1.45 / 1.87、全期 1.64；S1 單獨多空為負）。
規格與紀錄在 forward/fv5s/。

規則（凍結於 forward/fv5s/spec.yaml）：
- 其餘與 fv5 完全相同：直接讀 fv5 同一預測日的成員資料（forward/fv5/predictions.csv 的產業、SUE 中性化分數、可借、借券費、β），
  所以 fv5s 必須在 fv5 預測之後執行。
- S1：借券賣出餘額 ÷ 已發行股數，在自身過去 250 個交易日（至少 120 日）中的平均名次百分位，往後移一日，取負號；
  視窗內借券賣出餘額全為 0 者缺值；再做 leg_probe.wrap（產業內 z → 20 日平均）與 leg_probe.neutralize（產業與 log 市值）。
  資料用 fv5 同一天的快照快取（data_cache/forward/fv3/<日期>/，同樣的資料起訖），預測日當天通常不需新的 FinMind 請求。
- 分數 = 0.75 × SUE 分數的產業內百分位 ＋ 0.25 × S1 的產業內百分位（S1 缺值以 0.5 計）；只對有 SUE 分數的股票。
- 權重：ls_turnover.ew_ls_buffer（產業內前／後 1/3、只放空可借者、不含緩衝），β 與 fv5 相同算法；三份資金錯開、結算與成本同 fv5。

用法（於專案根目錄）：
    .venv/Scripts/python forward/run_forward_fv5s.py freeze
    .venv/Scripts/python forward/run_forward_fv5s.py backfill        # 補齊 fv5 已預測、fv5s 尚未預測的日期
    .venv/Scripts/python forward/run_forward_fv5s.py resolve
    .venv/Scripts/python forward/run_forward_fv5s.py report
    （每日由 forward/run_forward.py auto 在 fv5 之後呼叫 auto()）
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
from data.fetch_financials import get_total_return_prices  # noqa: E402
from forward import run_forward as fv1  # noqa: E402
from forward import run_forward_fv2 as fv2  # noqa: E402
from forward import run_forward_fv5 as fv5  # noqa: E402

DIR = ROOT / "forward" / "fv5s"
SPEC_PATH = DIR / "spec.yaml"
PREDICTIONS = DIR / "predictions.csv"
SEGMENTS = DIR / "segments.csv"
PERIODS = DIR / "periods.csv"
REPORT = DIR / "REPORT.md"
PUBLISH_FILES = [str(p.relative_to(ROOT)).replace("\\", "/") for p in (SPEC_PATH, PREDICTIONS, SEGMENTS, PERIODS, REPORT)]
WIN, MINP, W_SUE = 250, 120, 0.75
N_TRANCHE = fv5.N_TRANCHE

PRED_COLUMNS = ["spec_version", "mode", "as_of_date", "tranche", "ticker", "sector", "score_fv5", "s1", "score",
                "shortable", "fee", "beta", "weight", "tranche_beta", "run_utc", "git_commit"]
SEGMENT_COLUMNS = fv5.SEGMENT_COLUMNS
PERIOD_COLUMNS = ["seg_start", "seg_end", "mode", "n_active", "book_net", "fv5_net", "diff", "resolved_utc"]


# ---------------------------------------------------------------------------
# 規則（凍結）
# ---------------------------------------------------------------------------

def s1_raw(sbl: pd.DataFrame, shares: pd.DataFrame) -> pd.DataFrame:
    """sbl、shares：每日 [日期 × 代號]（已向前填補）；回傳 −ts_rank(借券賣出餘額比)，已往後移一日。"""
    x = sbl / shares
    r = x.rolling(WIN, min_periods=MINP).rank(method="average")
    n = x.rolling(WIN, min_periods=MINP).count()
    ts = ((r - 1) / (n - 1)).where(n > 1).where(x.rolling(WIN, min_periods=MINP).max() > 0)
    return -ts.shift(1)


def s1_score(raw: pd.DataFrame, sector: pd.Series, logcap: pd.Series, as_of: pd.Timestamp) -> pd.Series:
    member = pd.DataFrame(True, index=raw.index, columns=raw.columns)
    wz = lp.wrap(raw.replace([np.inf, -np.inf], np.nan), member, sector)
    return lp.neutralize(wz.loc[as_of], sector, logcap)


def composite(g: pd.DataFrame, s1: pd.Series) -> pd.Series:
    """g：fv5 當日成員 [ticker, sector, score]；回傳 0.75 × SUE 產業內百分位 ＋ 0.25 × S1 產業內百分位（S1 缺值 0.5）。"""
    x = g.set_index("ticker")
    s = x["score"].astype(float).dropna()
    grp = x["sector"].reindex(s.index)
    a = s.groupby(grp).rank(pct=True)
    b = s1.reindex(s.index).groupby(grp).rank(pct=True).fillna(0.5)
    return W_SUE * a + (1 - W_SUE) * b


def tranche_weights(g: pd.DataFrame, score: pd.Series) -> pd.Series:
    x = g.set_index("ticker")
    return lt.ew_ls_buffer(score, x["sector"], x["shortable"].astype(bool), q_keep=None)


def frozen_sources() -> dict[str, str]:
    return {"fv5s.s1_raw": inspect.getsource(s1_raw), "fv5s.s1_score": inspect.getsource(s1_score),
            "fv5s.composite": inspect.getsource(composite), "fv5s.tranche_weights": inspect.getsource(tranche_weights),
            "leg_probe.wrap": inspect.getsource(lp.wrap), "leg_probe.neutralize": inspect.getsource(lp.neutralize),
            "ls_turnover.ew_ls_buffer": inspect.getsource(lt.ew_ls_buffer), "fv5.segment_return": inspect.getsource(fv5.segment_return),
            "fv5s.constants": repr((WIN, MINP, W_SUE, N_TRANCHE))}


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
        raise SystemExit("fv5s 規則程式碼已與凍結時不同：" + "、".join(changed) + "。修改規則請建立新版本。")
    return spec


# ---------------------------------------------------------------------------
# 指令
# ---------------------------------------------------------------------------

def cmd_freeze(args) -> None:
    if SPEC_PATH.exists():
        raise SystemExit(f"{SPEC_PATH} 已存在；凍結只做一次。")
    DIR.mkdir(parents=True, exist_ok=True)
    spec = {
        "spec_version": "fv5s",
        "frozen_utc": fv1.now_utc(),
        "frozen_git_commit": git_commit(),
        "rules": {
            "base": "與 fv5 完全相同，直接讀 forward/fv5/predictions.csv 同一預測日的成員資料（產業、分數、可借、借券費、β）",
            "s1": f"借券賣出餘額 ÷ 已發行股數在自身過去 {WIN} 個交易日（至少 {MINP} 日）中的百分位，往後移一日、取負號；wrap 與 neutralize 同 leg_probe",
            "score": f"{W_SUE} × SUE 分數產業內百分位 ＋ {1 - W_SUE:.2f} × S1 產業內百分位（S1 缺值 0.5）",
            "portfolio": "ls_turnover.ew_ls_buffer（產業內前／後 1/3、只放空可借者、不含緩衝）；三份資金錯開、結算與成本同 fv5",
        },
        "preregistration": {
            "primary_metric": "組合每段淨報酬（同 fv5），以及同段 fv5s − fv5 的差",
            "hypothesis": "fv5s − fv5 每段差的長期平均 > 0",
            "backtest_expectation": {"sharpe_2019_2022": 1.48, "sharpe_2023_2026": 2.15, "sharpe_full": 1.78,
                                     "fv5_sharpe_full": 1.64, "source": "docs/ts_rank_report.md"},
            "evaluation": ["只把 mode = live 的期數算入，backfill 另列",
                           "24 個 live 期數（約 2 年）時：fv5s − fv5 平均差 ≤ 0 則維持 fv5；平均差 > 0 且 fv5s 本身 t > 2 才考慮以 fv5s 取代 fv5",
                           "回測改善集中在 2023 年後（2019–2022 只多 0.03）；差的 t 值只作描述"],
            "notes": "點子卡 I040 事前固定權重 0.75 / 0.25；這是第 40 張點子卡，仍可能有多重測試的運氣成分，不得依前瞻結果回頭調整規則。",
        },
        "frozen_source_sha256": source_hashes(),
    }
    SPEC_PATH.write_text(yaml.safe_dump(spec, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(f"已凍結 fv5s 規格 → {SPEC_PATH}")


def _s1_at(g: pd.DataFrame, as_of: pd.Timestamp) -> pd.Series:
    client = fv5.snapshot(dt.date.today().strftime("%Y-%m-%d"))
    calendar = pd.DatetimeIndex(fv1.trading_calendar(client, "2025-01-01"))
    start, end = fv5.data_start(as_of), dt.date.today().strftime("%Y-%m-%d")
    tickers = list(g["ticker"])
    sbl, sh = {}, {}
    for t in tickers:
        sid = t.split(".")[0]
        d = client.get("TaiwanDailyShortSaleBalances", sid, start, end)
        if not d.empty:
            sbl[t] = pd.Series(d["SBLShortSalesCurrentDayBalance"].astype(float).to_numpy(), index=pd.to_datetime(d["date"]))
        s = client.get("TaiwanStockShareholding", sid, start, end)
        if not s.empty:
            sh[t] = pd.Series(s["NumberOfSharesIssued"].astype(float).to_numpy(), index=pd.to_datetime(s["date"]))
    _, close = fv5.load_prices(client, tickers, start, end)
    idx = calendar[(calendar >= pd.Timestamp(start)) & (calendar <= as_of)]
    f = lambda m: pd.DataFrame(m).reindex(index=idx, columns=tickers).ffill()  # noqa: E731
    shares = f(sh)
    sector = g.set_index("ticker")["sector"]
    prev = idx[idx < as_of][-1]
    logcap = np.log((close.reindex(index=idx, columns=tickers).ffill() * shares).loc[prev])
    return s1_score(s1_raw(f(sbl), shares), sector, logcap, as_of)


def predict(as_of: str, mode: str | None = None) -> bool:
    spec = load_spec()
    preds = fv1.read_csv(PREDICTIONS, PRED_COLUMNS)
    if (preds["as_of_date"] == as_of).any():
        return False
    p5 = fv1.read_csv(fv5.PREDICTIONS, fv5.PRED_COLUMNS)
    g = p5[p5["as_of_date"] == as_of].copy()
    if g.empty:
        print(f"[fv5s] {as_of}：fv5 尚未預測，略過")
        return False
    a = pd.Timestamp(as_of)
    s1 = _s1_at(g, a)
    score = composite(g, s1)
    w = tranche_weights(g, score)
    beta = g.set_index("ticker")["beta"]
    b = float((w * beta.reindex(w.index).fillna(1.0)).sum())
    mode = mode or ("backfill" if as_of < spec["frozen_utc"][:10] else g["mode"].iloc[0])     # 凍結日以前的預測日一律 backfill
    out = g.assign(spec_version=spec["spec_version"], mode=mode, score_fv5=g["score"], s1=g["ticker"].map(s1),
                   score=g["ticker"].map(score), weight=g["ticker"].map(w).fillna(0.0), tranche_beta=b,
                   run_utc=fv1.now_utc(), git_commit=git_commit())
    DIR.mkdir(parents=True, exist_ok=True)
    fv1.append_csv(PREDICTIONS, out, PRED_COLUMNS)
    print(f"[fv5s {out['mode'].iloc[0]}] {as_of}：S1 有值 {int(out['s1'].notna().sum())} 檔；多 {(w > 0).sum()}、空 {(w < 0).sum()}，β {b:+.2f}")
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
        print(f"fv5s {a_s} → {b:%Y-%m-%d}：組合 {book:+.2%}（fv5 {f5:+.2%}）")
    return n


def cmd_report(args) -> None:
    spec = load_spec()
    preds = fv1.read_csv(PREDICTIONS, PRED_COLUMNS)
    per = fv1.read_csv(PERIODS, PERIOD_COLUMNS)
    lines = ["# 前瞻驗證報告 fv5s：fv5 加入借券賣出餘額比相對自身歷史排名（自動產生）", "",
             f"- 規格：`fv5s`（凍結於 {spec['frozen_utc']}，git `{spec['frozen_git_commit'][:8]}`）；與 fv5 平行，研究依據 "
             "[docs/ts_rank_report.md](../../docs/ts_rank_report.md)。研究記錄，非投資建議。",
             f"- 預測日 {preds['as_of_date'].nunique()} 個，已結算段落 {len(per)} 個",
             "- 主要指標：組合每段淨報酬（扣交易成本、借券費，台指期對沖），以及同段 fv5s − fv5 的差。", "",
             "## 累積結果", "", "| 範圍 | fv5s 每段淨報酬 | fv5 每段淨報酬 | fv5s − fv5 |", "|---|---|---|---|"]
    for label, mode in (("live（正式）", "live"), ("backfill（凍結後回填）", "backfill")):
        sub = per[per["mode"] == mode] if len(per) else per
        if len(sub):
            lines.append(f"| {label} | {fv2.summary(sub['book_net'], True)} | {fv2.summary(sub['fv5_net'], True)} | {fv2.summary(sub['diff'], True)} |")
        else:
            lines.append(f"| {label} | 尚無資料 | | |")
    lines += ["", "## 各段", "", "| 段落 | mode | 在場資金份數 | fv5s | fv5 | 差 |", "|---|---|---|---|---|---|"]
    for r in per.itertuples():
        lines.append(f"| {r.seg_start} → {r.seg_end} | {r.mode} | {int(r.n_active)} | {r.book_net:+.2%} | {r.fv5_net:+.2%} | {r.diff:+.2%} |")
    lines += ["", "## 各預測日", "", "| 預測日 | mode | 資金份 | S1 有值檔數 | 持股方向與 fv5 不同的檔數 | 做多 | 放空 |", "|---|---|---|---|---|---|---|"]
    p5 = fv1.read_csv(fv5.PREDICTIONS, fv5.PRED_COLUMNS)
    for a, bt in preds.groupby("as_of_date"):
        w5 = p5[p5["as_of_date"] == a].set_index("ticker")["weight"]
        diff = int((np.sign(bt.set_index("ticker")["weight"]) != np.sign(w5.reindex(bt["ticker"]).fillna(0.0).to_numpy())).sum())
        n_s1 = int(bt["s1"].notna().sum())
        lines.append(f"| {a} | {bt['mode'].iloc[0]} | {int(bt['tranche'].iloc[0]) + 1} | {n_s1} | {diff} | {(bt['weight'] > 0).sum()} | {(bt['weight'] < 0).sum()} |")
    lines += ["", "## 事先登錄的評估方式", ""] + [f"- {e}" for e in spec["preregistration"]["evaluation"]]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"fv5s 報告 → {REPORT}")


def auto() -> bool:
    """排程用（fv5 之後）：補上 fv5 已預測的日期、結算已過的段落；有變動回傳 True。"""
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
    p = argparse.ArgumentParser(description="前瞻驗證 fv5s")
    sub = p.add_subparsers(dest="cmd", required=True)
    for c in ("freeze", "backfill", "resolve", "report"):
        sub.add_parser(c)
    a = p.parse_args(argv)
    {"freeze": cmd_freeze, "backfill": cmd_backfill, "resolve": cmd_resolve, "report": cmd_report}[a.cmd](a)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
