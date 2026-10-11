"""配置研究（使用者 2026-10-12 指定順序）：2 擇時規則比較 → 1 0050 擇時與財報選股的混合比例 → 3 個股權重方法。

用法（於專案根目錄）：
    .venv/Scripts/python analysis/allocation_study.py daily_pit_val_tech.csv config/tickers_pit.yaml
輸出 docs/allocation_study_data.md。

設計（看結果前固定）：
2. 擇時規則（標的 0050，含息還原價；第 t 日部位只用 t−1 日收盤以前資料，t 日收盤成交，賺 t → t+1；空手現金報酬 0）：
   買進持有、120 / 200 / 250 日線、雙均線（50 日 > 200 日）、200 日線 ±2% 緩衝帶、200 日線每週判斷（每週第一個交易日）。
1. 混合比例：a ×「0050 + 每日 200 日線濾網」+（1 − a）× 財報產業中性 + 緩衝，a = 0 / 25 / 50 / 75 / 100%，每日固定比例
   （兩個部位之間的再平衡成本忽略）；對照組把前者換成 0050 買進持有。用 200 日線而不是第 2 項事後最佳的規則。
3. 個股權重：選股固定為財報產業中性 + 緩衝；產業內權重 = 等權 / 財報百分位 / 60 日波動度倒數 / 市值（產業總權重不變）。
所有組合：每日回測、扣成本（換手 × 單邊 0.29625%）、21 種換倉起點中位數（0050 擇時只有一條路徑）。
"""
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "analysis"))
import fund_tech_daily as ftd  # noqa: E402
from data.fetch_financials import FinMindClient, get_total_return_prices  # noqa: E402

COST = ftd.COST
SPLIT = pd.Timestamp("2023-01-01")
SEGS = [("2019–2022（樣本外）", lambda d: d < SPLIT), ("2023–2026/05", lambda d: d >= SPLIT)]


def timing_positions(adj: pd.Series, rule: str) -> pd.Series:
    """回傳每日「以前一日收盤決定」的持有比例（0/1），索引同 adj。"""
    ma = {n: adj.rolling(n, min_periods=n).mean() for n in (50, 120, 200, 250)}
    if rule == "bh":
        sig = pd.Series(1.0, index=adj.index)
    elif rule.startswith("ma"):
        n = int(rule[2:])
        sig = (adj > ma[n]).astype(float).where(ma[n].notna())
    elif rule == "dual":
        sig = (ma[50] > ma[200]).astype(float).where(ma[200].notna())
    elif rule == "band":
        vals, pos = [], np.nan
        for p, m in zip(adj, ma[200]):
            if np.isnan(m):
                vals.append(np.nan)
                continue
            if np.isnan(pos):
                pos = 1.0 if p > m else 0.0
            elif pos == 0 and p > m * 1.02:
                pos = 1.0
            elif pos == 1 and p < m * 0.98:
                pos = 0.0
            vals.append(pos)
        sig = pd.Series(vals, index=adj.index)
    elif rule == "weekly":
        daily = (adj > ma[200]).astype(float).where(ma[200].notna())
        week = adj.index.to_period("W")
        first = ~pd.Series(week, index=adj.index).duplicated()
        sig = daily.where(first).ffill()
    else:
        raise ValueError(rule)
    return sig.shift(1)  # 第 t 日只能用 t−1 日收盤的判斷


def timing_series(adj: pd.Series, rule: str, start="2019-01-01", end="2026-05-29") -> pd.DataFrame:
    pos = timing_positions(adj, rule).fillna(0.0)
    nxt = adj.pct_change().shift(-1).fillna(0.0)  # t → t+1 報酬
    to = pos.diff().abs().fillna(pos.abs())
    s = pd.DataFrame({"d": adj.index, "net": (pos * nxt - to * COST).to_numpy(), "expo": pos.to_numpy(), "to": to.to_numpy()})
    return s[(s["d"] >= start) & (s["d"] <= end)].reset_index(drop=True)


def seg_stats(series_list):
    out = {}
    for name, fn in SEGS:
        st = [ftd.stats(s[fn(s["d"])]) for s in series_list]
        out[name] = {k: float(np.median([x[k] for x in st])) for k in st[0]}
    return out


def fmt(m, extra=""):
    return (f"{m['ann'] * 100:+.1f}% / {m['sharpe']:.2f} / {m['mdd'] * 100:.0f}% / {m['expo']:.0%}" + extra)


def main(path, config):
    import dotenv

    dotenv.load_dotenv(ROOT / ".env")
    out = ["# 配置研究：擇時規則、混合比例、個股權重（自動產生）", "",
           "由 [analysis/allocation_study.py](../analysis/allocation_study.py) 產生；解讀見 "
           "[allocation_study_report.md](allocation_study_report.md)。每日回測、扣成本；欄位為 年化報酬 / Sharpe / 最大回撤 / 平均持股比例。", ""]

    # ---- 2. 擇時規則 ----
    px = get_total_return_prices(FinMindClient(), "0050.TW", "2017-06-01", "2026-05-31")
    adj = pd.Series(px["adj_close"].astype(float).to_numpy(), index=pd.DatetimeIndex(px["date"]))
    rules = [("bh", "買進持有"), ("ma120", "120 日線"), ("ma200", "200 日線（已看過）"), ("ma250", "250 日線"),
             ("dual", "雙均線 50 > 200"), ("band", "200 日線 ±2% 緩衝帶"), ("weekly", "200 日線每週判斷")]
    out += ["## 2. 0050 擇時規則", "", "| 規則 | 2019–2022（樣本外） | 2023–2026/05 | 每年進出次數 |", "|---|---|---|---|"]
    for rule, label in rules:
        s = timing_series(adj, rule)
        m = seg_stats([s])
        switches = (s["to"] > 0).sum() / (len(s) / 252)
        out.append(f"| {label} | {fmt(m[SEGS[0][0]])} | {fmt(m[SEGS[1][0]])} | {switches:.1f} |")
        print(out[-1], flush=True)

    # ---- 共用資料 ----
    cfg = yaml.safe_load(open(config, encoding="utf-8"))
    tickers = [u["ticker"] for u in cfg["universe"]]
    daily = pd.read_csv(path, parse_dates=["date"], usecols=["i", "date", "ticker", "sector", "pc_fundamentals_agent", "pc_technical"])
    daily = daily.dropna(subset=["sector"])
    close, ma20, ma60 = ftd.load_prices(tickers)
    close = close.loc["2019-01-01":"2026-05-29"]
    ma20, ma60 = ma20.reindex(close.index), ma60.reindex(close.index)
    on, bench = ftd.market_on(close.index)
    phases = range(ftd.STEP)

    # ---- 1. 混合比例 ----
    timed = ftd.run(daily, close, ma20, ma60, on, bench, 0, kind="0050", mkt=True).set_index("d")
    bh = ftd.run(daily, close, ma20, ma60, on, bench, 0, kind="0050").set_index("d")
    stock = [ftd.run(daily, close, ma20, ma60, on, bench, ph).set_index("d") for ph in phases]
    out += ["", "## 1. 混合比例：0050 部位 a ＋ 財報選股（1 − a）", "",
            "| 0050 部位 | 0050 比例 a | 2019–2022（樣本外） | 2023–2026/05 |", "|---|---|---|---|"]
    for sleeve, sname in ((timed, "0050 + 200 日線濾網"), (bh, "0050 買進持有")):
        for a in (1.0, 0.75, 0.5, 0.25, 0.0):
            if sname == "0050 買進持有" and a in (1.0, 0.0):
                continue  # 與上面重複
            series = []
            for st in stock:
                j = st.join(sleeve, lsuffix="_s", rsuffix="_m", how="inner")
                series.append(pd.DataFrame({"d": j.index, "net": a * j["net_m"] + (1 - a) * j["net_s"],
                                            "expo": a * j["expo_m"] + (1 - a) * j["expo_s"], "to": a * j["to_m"] + (1 - a) * j["to_s"]}))
            m = seg_stats(series)
            out.append(f"| {sname} | {a:.0%} | {fmt(m[SEGS[0][0]])} | {fmt(m[SEGS[1][0]])} |")
            print(out[-1], flush=True)

    # ---- 3. 個股權重 ----
    vol = close.pct_change().rolling(60, min_periods=40).std().shift(1)  # 換倉日只用前一日以前的波動度
    vol_long = vol.stack().rename("vol60").reset_index().rename(columns={"level_0": "date", "level_1": "ticker"})
    from valuation_signal import load_panel

    cap = load_panel(tickers)[["date", "ticker", "cap"]]
    d3 = daily.merge(vol_long, on=["date", "ticker"], how="left").merge(cap, on=["date", "ticker"], how="left")
    out += ["", "## 3. 個股權重方法（選股：財報產業中性 + 緩衝）", "",
            "| 權重 | 2019–2022（樣本外） | 2023–2026/05 | 年換手（樣本外） |", "|---|---|---|---|"]
    for w, label in (("equal", "等權"), ("score", "財報百分位加權"), ("invvol", "60 日波動度倒數"), ("cap", "市值加權")):
        series = [ftd.run(d3, close, ma20, ma60, on, bench, ph, weight=w) for ph in phases]
        m = seg_stats(series)
        out.append(f"| {label} | {fmt(m[SEGS[0][0]])} | {fmt(m[SEGS[1][0]])} | {m[SEGS[0][0]]['to_yr']:.1f} |")
        print(out[-1], flush=True)
    (ROOT / "docs" / "allocation_study_data.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("DONE", flush=True)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
