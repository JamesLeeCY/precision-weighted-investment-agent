"""供應鏈訊號的取樣相位穩健性：每個交易日都計算 5 檔的看多機率與 20 日含息報酬，
再依「每 21 個交易日取一次」的 21 種起點分別算橫斷面 IC 平均。

用法（於專案根目錄）：
    .venv/Scripts/python analysis/phase_robustness.py config/supply_chain_graph.json phase_v2.csv
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from agents.supply_chain_agent import SupplyChainAgent  # noqa: E402
from backtest.metrics import signal_to_probability  # noqa: E402
from data.fetch_financials import FinMindClient, get_total_return_prices  # noqa: E402
from data.fetch_supply_chain import FinMindSupplyChainProvider, load_graph  # noqa: E402

TICKERS = ["2327.TW", "2492.TW", "3026.TW", "2375.TW", "2478.TW"]
HORIZON, STEP = 20, 21
graph_path, out_path = sys.argv[1], sys.argv[2]

client = FinMindClient()
agent = SupplyChainAgent(FinMindSupplyChainProvider(client, history_start="2017-01-01"), graph=load_graph(graph_path))
prices = {t: get_total_return_prices(client, t, "2019-01-01", "2026-05-31").set_index("date")["adj_close"] for t in TICKERS}
calendar = sorted(set().union(*(p.index for p in prices.values())))

rows = []
for i in range(len(calendar) - HORIZON):
    start, end = calendar[i], calendar[i + HORIZON]
    for t in TICKERS:
        s = prices[t]
        if start not in s.index:
            continue
        o = agent.analyze(t, start.strftime("%Y-%m-%d"))
        rows.append({
            "i": i, "date": start, "ticker": t,
            "p": signal_to_probability(o.signal, o.confidence),
            "score": o.raw_features.get("rule_score", 0.0),
            "ret": float(s.asof(end) / s.asof(start) - 1.0),
        })
df = pd.DataFrame(rows)
df.to_csv(out_path, index=False)


def cs_ic(g, col):
    if g[col].nunique() < 2 or len(g) < 3:
        return np.nan
    return g[col].rank().corr(g["ret"].rank())


daily = df.groupby("i").apply(lambda g: pd.Series({
    "date": g["date"].iloc[0], "ic_p": cs_ic(g, "p"), "ic_score": cs_ic(g, "score")}))
daily["oos"] = pd.to_datetime(daily["date"]) < "2024-01-01"
daily["phase"] = daily.index % STEP
print(f"{graph_path}: {len(df)} 筆（{df['date'].min():%Y-%m-%d} ~ {df['date'].max():%Y-%m-%d}）")
for label, sub in [("樣本外 2019–2023", daily[daily.oos]), ("樣本內 2024–2026", daily[~daily.oos])]:
    for col, name in [("ic_p", "看多機率 p"), ("ic_score", "連續分數")]:
        by_phase = sub.groupby("phase")[col].mean()
        print(f"  {label} [{name}] 每日 IC 平均 {sub[col].mean():+.3f}（{sub[col].notna().sum()} 天）| "
              f"21 種取樣起點的 IC 平均：最小 {by_phase.min():+.3f}、中位 {by_phase.median():+.3f}、最大 {by_phase.max():+.3f}，"
              f"為正的起點 {(by_phase > 0).sum()}/21")
