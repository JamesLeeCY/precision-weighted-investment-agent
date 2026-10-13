"""前瞻驗證 fv3：月營收驚奇等權多空、三份資金錯開每 3 個月換倉、只放空可借股票、剩餘 β 以台指期對沖。

與 fv1、fv2 完全分開：規格與紀錄在 forward/fv3/，不影響 fv1 / fv2 的規格、紀錄與程式碼指紋。

規則（凍結於 forward/fv3/spec.yaml；研究依據 docs/borrow_capacity_report.md、ls_turnover_report.md、ls_offsets_top300.md）：
- 預測日：同 fv2，每月營收公告期限後的下一個交易日。
- 股票池：config/universe_mcap_membership.csv 當年市值前 300 名。
- 分數：SUE（只採 create_time ≤ 公告期限的營收）→ 產業內 z 分數 → 對產業虛擬變數與 log 市值迴歸取殘差。
- 每個預測日只重建一份資金（第 k 份 = 預測日序號 mod 3），持有到 3 個預測日後；組合由三份平均（每份 1/3 資金）。
- 每份：做多產業內前 1/3、放空產業內後 1/3（只放空可借者），產業內等權、產業權重 = 參與產業檔數占比、多空各 100%；
  剩餘 β（持股 250 日 β 加權）以台指期近月對沖。
- 可借：前 60 個交易日有借券成交、需借股數 ≤ 前一日借券賣出額度、≤ 前 60 日借券成交量 10%、60 日成交量加權借券費 ≤ 5%／年；
  需借股數 = 2 億 ÷（成員數 / 3）÷ 預測日收盤價。
- 成本：股票換手（相對同一份資金上一期）× 單邊 0.29625%、期貨 β 變動 × 0.005%、借券費逐日計。

用法（於專案根目錄）：
    .venv/Scripts/python forward/run_forward_fv3.py freeze
    .venv/Scripts/python forward/run_forward_fv3.py schedule
    .venv/Scripts/python forward/run_forward_fv3.py predict --as-of 2026-10-13
    .venv/Scripts/python forward/run_forward_fv3.py resolve
    .venv/Scripts/python forward/run_forward_fv3.py report
    （每日自動執行由 forward/run_forward.py auto 一併呼叫 auto()）
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

import leg_probe as lp  # noqa: E402
import ls_turnover as lt  # noqa: E402
from data import fetch_financials as ff  # noqa: E402
from data import revenue_signal as rsig  # noqa: E402
from data.fetch_financials import get_total_return_prices  # noqa: E402
from forward import run_forward as fv1  # noqa: E402
from forward import run_forward_fv2 as fv2  # noqa: E402

FV3_DIR = ROOT / "forward" / "fv3"
SPEC_PATH = FV3_DIR / "spec.yaml"
PREDICTIONS = FV3_DIR / "predictions.csv"
SEGMENTS = FV3_DIR / "segments.csv"
PERIODS = FV3_DIR / "periods.csv"
REPORT = FV3_DIR / "REPORT.md"
PUBLISH_FILES = [str(p.relative_to(ROOT)).replace("\\", "/") for p in (SPEC_PATH, PREDICTIONS, SEGMENTS, PERIODS, REPORT)]
MEMBERSHIP = ROOT / "config" / "universe_mcap_membership.csv"
TOP_N = 300
N_TRANCHE = 3
K_CAPITAL, DEPTH_FRAC, FEE_MAX, FEE_WINDOW = 2e8, 0.10, 5.0, 60
BETA_WIN, BETA_MIN = 250, 120
STOCK_COST, FUT_COST = lp.STOCK_COST, lp.FUT_COST
BACKFILL_START = "2026-05-01"  # 研究資料只到 2026-04 的換倉；之後的月份開發未使用

PRED_COLUMNS = ["spec_version", "mode", "as_of_date", "deadline_date", "tranche", "ticker", "sector", "revenue_month",
                "sue", "score", "shortable", "fee", "beta", "weight", "tranche_beta", "run_utc", "git_commit", "git_dirty"]
SEGMENT_COLUMNS = ["as_of_date", "tranche", "seg_start", "seg_end", "first_segment", "gross", "hedge", "borrow", "cost",
                   "net", "resolved_utc", "git_commit"]
PERIOD_COLUMNS = ["seg_start", "seg_end", "mode", "n_active", "book_net", "ic", "b0050", "resolved_utc"]


# ---------------------------------------------------------------------------
# 規則（以下函式與 data/revenue_signal.py、leg_probe.neutralize、ls_turnover.ew_ls_buffer 一起凍結）
# ---------------------------------------------------------------------------

def score_members(g: pd.DataFrame) -> pd.Series:
    """g：ticker、sector、sue、logcap → 中性化分數（產業內 z → 對產業與 log 市值迴歸取殘差）。"""
    x = g.set_index("ticker")
    z = x["sue"].groupby(x["sector"]).transform(lambda v: (v - v.mean()) / v.std())
    return lp.neutralize(z, x["sector"], x["logcap"])


def shortable_flags(g: pd.DataFrame) -> pd.Series:
    """g：ticker、close、quota（前一日借券賣出額度，股）、lend60（前 60 日借券成交，股）、fee（年化 %）。"""
    x = g.set_index("ticker")
    n_short = max(1, int(len(x) / 3))
    need = K_CAPITAL / n_short / x["close"]
    return (x["lend60"] > 0) & (x["quota"] >= need) & (need <= DEPTH_FRAC * x["lend60"]) & (x["fee"] <= FEE_MAX)


def tranche_weights(g: pd.DataFrame) -> pd.Series:
    score = score_members(g)
    sector = g.set_index("ticker")["sector"]
    return lt.ew_ls_buffer(score, sector, shortable_flags(g), q_keep=None)


def segment_return(weights: pd.Series, beta: float, fees: pd.Series, rets: pd.DataFrame, tx: pd.Series,
                   start, end, first: bool, prev_weights: pd.Series | None, prev_beta: float) -> dict:
    """一份資金在 (start, end] 的報酬（權重固定）：Σw·r − β·台指期 − 借券費；若為該份資金的第一段，另扣換倉成本。"""
    idx = rets.index[(rets.index > start) & (rets.index <= end)]
    R = rets.reindex(index=idx, columns=weights.index).fillna(0.0)
    gross = R.to_numpy() @ weights.to_numpy()
    hedge = beta * tx.reindex(idx).fillna(0.0).to_numpy()
    short = -weights[weights < 0]
    daily_fee = float((short * fees.reindex(short.index).fillna(FEE_MAX)).sum()) / 100 / 252
    borrow = np.full(len(idx), daily_fee)
    cost = 0.0
    if first:
        prev = prev_weights if prev_weights is not None else pd.Series(dtype=float)
        turnover = float(weights.sub(prev, fill_value=0.0).abs().sum())
        cost = turnover * STOCK_COST + abs(beta - prev_beta) * FUT_COST
    daily = gross - hedge - borrow
    if len(daily):
        daily[0] -= cost
    return {"daily": pd.Series(daily, index=idx), "gross": float(np.prod(1 + gross) - 1),
            "hedge": float(np.prod(1 + hedge) - 1), "borrow": float(borrow.sum()), "cost": cost,
            "net": float(np.prod(1 + daily) - 1)}


# ---------------------------------------------------------------------------
# 凍結與完整性
# ---------------------------------------------------------------------------

def frozen_sources() -> dict[str, str]:
    return {
        "data.revenue_signal": inspect.getsource(rsig),
        "leg_probe.neutralize": inspect.getsource(lp.neutralize),
        "leg_probe.tx_continuous": inspect.getsource(lp.tx_continuous),
        "ls_turnover.ew_ls_buffer": inspect.getsource(lt.ew_ls_buffer),
        "fetch_financials.total_return_index": inspect.getsource(ff.total_return_index),
        "fv3.score_members": inspect.getsource(score_members),
        "fv3.shortable_flags": inspect.getsource(shortable_flags),
        "fv3.tranche_weights": inspect.getsource(tranche_weights),
        "fv3.segment_return": inspect.getsource(segment_return),
        "fv3.member_frame": inspect.getsource(member_frame),
        "fv3.constants": repr((TOP_N, N_TRANCHE, K_CAPITAL, DEPTH_FRAC, FEE_MAX, FEE_WINDOW, BETA_WIN, BETA_MIN, STOCK_COST, FUT_COST)),
    }


def source_hashes() -> dict[str, str]:
    return {k: hashlib.sha256(v.encode("utf-8")).hexdigest() for k, v in frozen_sources().items()}


def git_state() -> tuple[str, bool]:
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
        excludes = [f":(exclude){p}" for p in PUBLISH_FILES[1:] + fv2.PUBLISH_FILES + fv1.PUBLISH_FILES + fv1.SITE_FILES]
        dirty = bool(subprocess.run(["git", "status", "--porcelain", "--untracked-files=no", "--", ".", *excludes],
                                    cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip())
        return commit, dirty
    except (OSError, subprocess.CalledProcessError):
        return "unknown", True


def load_spec() -> dict:
    if not SPEC_PATH.exists():
        raise SystemExit(f"找不到規格 {SPEC_PATH}；請先執行 freeze")
    return yaml.safe_load(SPEC_PATH.read_text(encoding="utf-8"))


def verify_frozen(spec: dict) -> None:
    current = source_hashes()
    changed = [k for k, h in spec["frozen_source_sha256"].items() if current.get(k) != h]
    if changed:
        raise SystemExit("fv3 規則程式碼已與凍結時不同，拒絕預測：" + "、".join(changed) + "。修改規則請建立新版本（fv4）。")


# ---------------------------------------------------------------------------
# 資料（一次抓取期間固定起點，同一個快照可涵蓋多個預測日）
# ---------------------------------------------------------------------------

def snapshot(fetch_date: str):
    """fv3 自己的快照快取（data_cache/forward/fv3/<日期>/），不和 fv1 / fv2 共用。"""
    import os

    fetch_date = os.environ.get("FV3_FETCH_DATE", fetch_date)  # 回填可固定抓取日，跨午夜重跑仍命中快取
    return ff.FinMindClient(cache_dir=fv1.SNAPSHOT_ROOT / "fv3" / fetch_date)


def data_start(as_of: pd.Timestamp) -> str:
    return f"{as_of.year - 1}-01-01"


def members(year: int) -> pd.DataFrame:
    m = pd.read_csv(MEMBERSHIP, dtype={"stock_id": str})
    m = m[(m["year"] == year) & (m["rank"] <= TOP_N)]
    if m.empty:
        raise SystemExit(f"{year} 年沒有市值股票池成員；請先執行 analysis/build_universe_mcap.py")
    return m.assign(ticker=m["stock_id"] + ".TW")


def load_prices(client, tickers, start: str, end: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    adj, close = {}, {}
    for t in tickers:
        px = get_total_return_prices(client, t, start, end)
        if not px.empty:
            px = px.set_index("date")
            adj[t], close[t] = px["adj_close"].astype(float), px["close"].astype(float)
    return pd.DataFrame(adj).sort_index(), pd.DataFrame(close).sort_index()


def member_frame(client, mem: pd.DataFrame, as_of: pd.Timestamp, deadline: pd.Timestamp, adj: pd.DataFrame,
                 close: pd.DataFrame, calendar: list[pd.Timestamp], start: str, end: str) -> pd.DataFrame:
    """預測日的成員資料：SUE（create_time ≤ 期限）、log 市值（前一日）、可借量、借券費、β（只用預測日前一日以前）。"""
    avail = as_of.to_period("M").to_timestamp()
    prior = [d for d in calendar if d < as_of]
    prev_day = prior[-1]
    window = prior[-FEE_WINDOW:]
    mkt = client.get("TaiwanStockTotalReturnIndex", "TAIEX", start, end)
    m = pd.Series(mkt["price"].astype(float).to_numpy(), index=pd.to_datetime(mkt["date"])).sort_index().pct_change()
    rows = []
    for r in mem.itertuples():
        sid, t = r.stock_id, r.ticker
        rev = client.get("TaiwanStockMonthRevenue", sid, "2017-01-01")
        sue = np.nan
        if not rev.empty:
            s = rsig.revenue_surprise(rev, cutoff=deadline).set_index("avail_month")
            if avail in s.index:
                sue = s.loc[avail, "sue"]
        sh = client.get("TaiwanStockShareholding", sid, start, end)
        shares = np.nan
        if not sh.empty:
            sh = sh.assign(date=pd.to_datetime(sh["date"]))
            sh = sh[sh["date"] <= prev_day]
            shares = float(sh["NumberOfSharesIssued"].astype(float).iloc[-1]) if len(sh) else np.nan
        c_prev = close[t].asof(prev_day) if t in close else np.nan
        sb = client.get("TaiwanDailyShortSaleBalances", sid, start, end)
        quota = np.nan
        if not sb.empty:
            sb = sb.assign(date=pd.to_datetime(sb["date"]))
            sb = sb[sb["date"] <= prev_day]
            quota = float(sb["SBLShortSalesQuota"].astype(float).iloc[-1]) if len(sb) else np.nan
        ld = client.get("TaiwanStockSecuritiesLending", sid, start, end)
        lend60, fee = 0.0, np.nan
        if not ld.empty:
            ld = ld.assign(date=pd.to_datetime(ld["date"]))
            ld = ld[ld["date"].isin(window)]
            v = ld["volume"].astype(float)
            if v.sum() > 0:
                lend60 = float(v.sum() * 1000)
                fee = float((v * ld["fee_rate"].astype(float)).sum() / v.sum())
        beta = np.nan
        if t in adj:
            rr = adj[t].pct_change()
            rr = rr[rr.index <= prev_day].iloc[-BETA_WIN:]
            mm = m.reindex(rr.index)
            ok = rr.notna() & mm.notna()
            if ok.sum() >= BETA_MIN:
                beta = float(np.cov(rr[ok], mm[ok])[0, 1] / mm[ok].var())
        rows.append({"ticker": t, "sector": r.sector, "sue": sue,
                     "logcap": math.log(c_prev * shares) if c_prev == c_prev and shares == shares and c_prev * shares > 0 else np.nan,
                     "close": close[t].asof(as_of) if t in close else np.nan, "quota": quota, "lend60": lend60, "fee": fee, "beta": beta})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 指令
# ---------------------------------------------------------------------------

def scheduled(calendar: list[pd.Timestamp], start: str = BACKFILL_START) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    return fv2.scheduled(calendar, start)


def tranche_of(as_of: pd.Timestamp, calendar: list[pd.Timestamp]) -> int:
    entries = [e for _, e in scheduled(calendar)]
    return entries.index(as_of) % N_TRANCHE


def cmd_freeze(args) -> None:
    if SPEC_PATH.exists():
        raise SystemExit(f"{SPEC_PATH} 已存在；凍結只做一次。")
    FV3_DIR.mkdir(parents=True, exist_ok=True)
    commit, dirty = git_state()
    spec = {
        "spec_version": "fv3",
        "frozen_utc": fv1.now_utc(),
        "frozen_git_commit": commit,
        "frozen_git_dirty": dirty,
        "rules": {
            "signal": "月營收驚奇 SUE（同 fv2，只採 create_time ≤ 公告期限的營收）→ 產業內 z → 對產業虛擬變數與 log 市值（前一日收盤 × 已發行股數）迴歸取殘差",
            "schedule": "每月營收公告期限後的下一個交易日（同 fv2）",
            "universe": f"config/universe_mcap_membership.csv 當年市值前 {TOP_N} 名",
            "tranches": f"資金分 {N_TRANCHE} 份；每個預測日只重建一份（預測日序號 mod 3），持有到 3 個預測日後",
            "portfolio": "每份：多產業內前 1/3、空產業內後 1/3（只空可借者），產業內等權，產業權重 = 參與產業檔數占比，多空各 100%；成員 < 3 檔或沒有可放空股票的產業不做",
            "shortable": f"前 {FEE_WINDOW} 個交易日有借券成交；需借股數 ≤ 前一日借券賣出額度；≤ 前 {FEE_WINDOW} 日借券成交量 × {DEPTH_FRAC}；"
                         f"成交量加權借券費 ≤ {FEE_MAX}%／年；需借股數 = {K_CAPITAL:.0f} ÷（成員數 / 3）÷ 預測日收盤價",
            "hedge": f"剩餘 β（持股 {BETA_WIN} 日 β 以權重加總，至少 {BETA_MIN} 日；缺值以 1 計）以台指期近月（一般交易時段成交量最大的月合約）對沖",
            "costs": f"股票換手（相對同一份資金上一期）× {STOCK_COST}、期貨 β 變動 × {FUT_COST}、借券費逐日（費率缺值以 {FEE_MAX}% 計）",
            "return": "預測日收盤後起算的含息每日報酬，權重在每段持有期間內固定",
            "backfill_start": BACKFILL_START,
        },
        "preregistration": {
            "primary_metric": "組合（三份平均）每段（相鄰兩個預測日之間）扣成本、扣借券費、台指期對沖後的淨報酬",
            "hypothesis": "每段淨報酬的長期平均 > 0",
            "backtest_expectation": {"mean_period_net": 0.0061, "sd_period_net": 0.0188, "t": 3.02, "n": 85,
                                     "sharpe_2019_2022": 0.93, "sharpe_2023_2026": 1.79,
                                     "source": "docs/ls_offsets_top300.md（三起點平均，2019-03 ~ 2026-04，市值前 300 檔）"},
            "evaluation": [
                "只把 mode = live 的期數算入正式檢定，backfill 另列；前兩個 live 期只有 1–2 份資金在場（其餘為現金）",
                "12 個 live 期數時檢查：平均淨報酬 < 0 視為失效警訊",
                "38 個 live 期數（約 3 年）時正式檢定：t > 2 才算確認（依回測平均與標準差估計所需期數）",
            ],
            "secondary_metrics": [
                "每個預測日 SUE 分數與下一段報酬的產業內 IC",
                "0050 同期報酬（對照，不作為檢定）",
            ],
            "notes": "此建構是看過多種組合建構（等權／市值加權、做多／多空、換倉頻率、緩衝）後選出的，回測數字已含選擇偏誤；前瞻結果才是乾淨的驗證，不得依前瞻結果回頭調整規則。"
                     "每年 1 月需先建立當年市值股票池（analysis/build_universe_mcap.py）。",
        },
        "frozen_source_sha256": source_hashes(),
    }
    SPEC_PATH.write_text(yaml.safe_dump(spec, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(f"已凍結 fv3 規格 → {SPEC_PATH}（git {commit[:8]}{'，工作區有未 commit 的修改' if dirty else ''}）")


def cmd_predict(args) -> None:
    spec = load_spec()
    verify_frozen(spec)
    as_of = pd.Timestamp(args.as_of)
    today = pd.Timestamp(dt.date.today())
    if as_of > today:
        raise SystemExit("不能預測未來日期")
    mode = args.mode or ("live" if as_of >= today - pd.Timedelta(days=3) else "backfill")
    preds = fv1.read_csv(PREDICTIONS, PRED_COLUMNS)
    if (preds["as_of_date"] == as_of.strftime("%Y-%m-%d")).any():
        raise SystemExit(f"{as_of:%Y-%m-%d} 已經預測過（紀錄只能新增）")
    client = snapshot(today.strftime("%Y-%m-%d"))
    calendar = fv1.trading_calendar(client, "2025-01-01")
    de = fv2.entry_for_month(calendar, as_of.year, as_of.month)
    if de is None or de[1] != as_of:
        raise SystemExit(f"{as_of:%Y-%m-%d} 不是 fv3 的預測日")
    start, end = data_start(as_of), today.strftime("%Y-%m-%d")
    mem = members(as_of.year)
    print(f"[fv3] {as_of:%Y-%m-%d}：載入 {len(mem)} 檔（FinMind 約 {len(mem) * 7} 次呼叫，額度不足會自動等待）", flush=True)
    adj, close = load_prices(client, mem["ticker"], start, end)
    g = member_frame(client, mem, as_of, de[0], adj, close, calendar, start, end)
    w = tranche_weights(g)
    b = float((w * g.set_index("ticker")["beta"].reindex(w.index).fillna(1.0)).sum())
    score = score_members(g)
    flags = shortable_flags(g)
    commit, dirty = git_state()
    out = g.assign(spec_version=spec["spec_version"], mode=mode, as_of_date=as_of.strftime("%Y-%m-%d"),
                   deadline_date=de[0].strftime("%Y-%m-%d"), tranche=tranche_of(as_of, calendar),
                   revenue_month=(as_of.to_period("M").to_timestamp() - pd.offsets.MonthBegin(1)).strftime("%Y-%m"),
                   score=g["ticker"].map(score), shortable=g["ticker"].map(flags).fillna(False).astype(int),
                   weight=g["ticker"].map(w).fillna(0.0), tranche_beta=b, run_utc=fv1.now_utc(), git_commit=commit, git_dirty=dirty)
    FV3_DIR.mkdir(parents=True, exist_ok=True)
    fv1.append_csv(PREDICTIONS, out, PRED_COLUMNS)
    print(f"[fv3 {mode}] {as_of:%Y-%m-%d}：第 {out['tranche'].iloc[0] + 1} 份資金，多 {(w > 0).sum()} 檔、空 {(w < 0).sum()} 檔，β {b:+.2f}")


def cmd_resolve(args) -> int:
    """結算已過的段落：每段 = 相鄰兩個預測日之間；所有在場的資金各記一筆，組合 = 各份淨報酬加總 ÷ 3。"""
    load_spec()
    preds = fv1.read_csv(PREDICTIONS, PRED_COLUMNS)
    if preds.empty:
        print("fv3：尚無預測")
        return 0
    segs = fv1.read_csv(SEGMENTS, SEGMENT_COLUMNS)
    today = pd.Timestamp(dt.date.today())
    client = snapshot(today.strftime("%Y-%m-%d"))
    calendar = fv1.trading_calendar(client, "2025-01-01")
    entries = [e for _, e in scheduled(calendar)]
    done = set(segs["seg_start"]) if len(segs) else set()
    predicted = sorted(preds["as_of_date"].unique())
    todo = []
    for a, b in zip(entries[:-1], entries[1:]):
        if a.strftime("%Y-%m-%d") in predicted and a.strftime("%Y-%m-%d") not in done and b <= calendar[-1]:
            todo.append((a, b))
    if not todo:
        print("fv3：沒有待結算的段落")
        return 0
    start = data_start(pd.Timestamp(predicted[0]))
    end = today.strftime("%Y-%m-%d")
    tickers = sorted(set(preds.loc[preds["weight"] != 0, "ticker"]) | set(preds["ticker"]))
    adj, _ = load_prices(client, tickers, start, end)
    rets = adj.pct_change()
    tx = lp.tx_continuous(client, start, end)
    b0050 = get_total_return_prices(client, "0050.TW", start, end).set_index("date")["adj_close"].astype(float)
    commit, _ = git_state()
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
            r = segment_return(w, float(batch["tranche_beta"].iloc[0]), batch.set_index("ticker")["fee"], rets, tx,
                               a, b, first=(e == a), prev_weights=prev_w, prev_beta=prev_b)
            daily.append(r["daily"])
            seg_rows.append({"as_of_date": e.strftime("%Y-%m-%d"), "tranche": k, "seg_start": a_s, "seg_end": b.strftime("%Y-%m-%d"),
                             "first_segment": int(e == a), **{x: r[x] for x in ("gross", "hedge", "borrow", "cost", "net")},
                             "resolved_utc": fv1.now_utc(), "git_commit": commit})
        book = (pd.concat(daily, axis=1).sum(axis=1) / N_TRANCHE) if daily else pd.Series(dtype=float)
        batch = preds[preds["as_of_date"] == a_s]
        fwd = adj.reindex(columns=batch["ticker"]).pipe(lambda x: x.asof(b) / x.loc[a] - 1 if a in x.index else pd.Series(dtype=float))
        g = batch.assign(fwd=batch["ticker"].map(fwd))
        ic = lp.within_ic(g.set_index("ticker")["score"], g.set_index("ticker")["fwd"], g.set_index("ticker")["sector"])
        fv1.append_csv(SEGMENTS, pd.DataFrame(seg_rows), SEGMENT_COLUMNS)
        fv1.append_csv(PERIODS, pd.DataFrame([{"seg_start": a_s, "seg_end": b.strftime("%Y-%m-%d"), "mode": batch["mode"].iloc[0],
                                                "n_active": len(active), "book_net": float((1 + book).prod() - 1), "ic": ic,
                                                "b0050": float(b0050.asof(b) / b0050.asof(a) - 1), "resolved_utc": fv1.now_utc()}]),
                       PERIOD_COLUMNS)
        n += 1
        print(f"fv3 {a_s} → {b:%Y-%m-%d}：{len(active)} 份資金在場，組合 {((1 + book).prod() - 1) * 100:+.2f}%")
    return n


def cmd_report(args) -> None:
    spec = load_spec()
    preds = fv1.read_csv(PREDICTIONS, PRED_COLUMNS)
    per = fv1.read_csv(PERIODS, PERIOD_COLUMNS)
    exp = spec["preregistration"]["backtest_expectation"]
    lines = ["# 前瞻驗證報告 fv3：月營收驚奇等權多空（自動產生）", "",
             f"- 規格：`fv3`（凍結於 {spec['frozen_utc']}，git `{spec['frozen_git_commit'][:8]}`）；產生時間 {fv1.now_utc()}",
             f"- 預測日 {preds['as_of_date'].nunique()} 個，已結算段落 {len(per)} 個",
             f"- 主要指標：組合（三份資金平均）每段淨報酬（扣交易成本、借券費，台指期對沖）；回測預期平均 {exp['mean_period_net'] * 100:+.2f}%、"
             f"每段標準差 {exp['sd_period_net'] * 100:.2f}%", "", "## 累積結果", "",
             "| 範圍 | 組合每段淨報酬 | 產業內 IC | 0050（每段，對照） |", "|---|---|---|---|"]
    for label, mode in (("live（正式）", "live"), ("backfill（凍結後回填）", "backfill")):
        sub = per[per["mode"] == mode] if len(per) else per
        if len(sub):
            lines.append(f"| {label} | {fv2.summary(sub['book_net'], True)} | {fv2.summary(sub['ic'])} | {fv2.summary(sub['b0050'], True)} |")
        else:
            lines.append(f"| {label} | 尚無資料 | | |")
    lines += ["", "## 各段", "", "| 段落 | mode | 在場資金份數 | 組合淨報酬 | 產業內 IC | 0050 |", "|---|---|---|---|---|---|"]
    for r in per.itertuples():
        lines.append(f"| {r.seg_start} → {r.seg_end} | {r.mode} | {int(r.n_active)} | {r.book_net * 100:+.2f}% | {r.ic:+.3f} | {r.b0050 * 100:+.2f}% |")
    lines += ["", "## 各預測日", "", "| 預測日 | mode | 資金份 | 做多檔數 | 放空檔數 | 可借比例（後 1/3 中） | β |", "|---|---|---|---|---|---|---|"]
    for a, bt in preds.groupby("as_of_date"):
        lines.append(f"| {a} | {bt['mode'].iloc[0]} | {int(bt['tranche'].iloc[0]) + 1} | {(bt['weight'] > 0).sum()} | {(bt['weight'] < 0).sum()} | "
                     f"{bt['shortable'].mean():.0%} | {bt['tranche_beta'].iloc[0]:+.2f} |")
    lines += ["", "## 事先登錄的評估方式", ""] + [f"- {e}" for e in spec["preregistration"]["evaluation"]]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"fv3 報告 → {REPORT}")


def cmd_schedule(args) -> None:
    client = snapshot(dt.date.today().strftime("%Y-%m-%d"))
    calendar = fv1.trading_calendar(client, "2025-01-01")
    preds = fv1.read_csv(PREDICTIONS, PRED_COLUMNS)
    done = set(preds["as_of_date"])
    for i, (deadline, entry) in enumerate(scheduled(calendar)):
        print(f"{entry:%Y-%m-%d}（期限 {deadline:%Y-%m-%d}，第 {i % N_TRANCHE + 1} 份資金）{'已預測' if entry.strftime('%Y-%m-%d') in done else '未預測'}")


def auto() -> bool:
    """排程用（由 forward/run_forward.py auto 呼叫）：預測當月（若已過預測日）、結算已過的段落；有變動回傳 True。"""
    if (FV3_DIR / "BACKFILL_PENDING").exists():
        print("[fv3] 回填進行中（forward/fv3/BACKFILL_PENDING），本次略過")
        return False
    today = pd.Timestamp(dt.date.today())
    client = snapshot(today.strftime("%Y-%m-%d"))
    calendar = fv1.trading_calendar(client, "2025-01-01")
    preds = fv1.read_csv(PREDICTIONS, PRED_COLUMNS)
    changed = False
    de = fv2.entry_for_month(calendar, today.year, today.month)
    if de is not None and de[1] <= today and de[1] in calendar and de[1].strftime("%Y-%m-%d") not in set(preds["as_of_date"]):
        cmd_predict(argparse.Namespace(as_of=de[1].strftime("%Y-%m-%d"), mode=None))
        changed = True
    changed |= cmd_resolve(argparse.Namespace()) > 0
    if changed:
        cmd_report(argparse.Namespace())
    return changed


def main(argv=None) -> None:
    import dotenv

    dotenv.load_dotenv(ROOT / ".env")
    ap = argparse.ArgumentParser(description="前瞻驗證 fv3（月營收驚奇等權多空）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("freeze")
    sub.add_parser("schedule")
    p = sub.add_parser("predict")
    p.add_argument("--as-of", required=True)
    p.add_argument("--mode", choices=["live", "backfill"], default=None)
    sub.add_parser("resolve")
    sub.add_parser("report")
    args = ap.parse_args(argv)
    {"freeze": cmd_freeze, "schedule": cmd_schedule, "predict": cmd_predict, "resolve": cmd_resolve,
     "report": cmd_report}[args.cmd](args)


if __name__ == "__main__":
    main()
