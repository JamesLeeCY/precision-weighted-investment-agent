"""取樣起點穩健性（所有 Agent）：每個交易日計算每檔股票各 Agent 的看多機率與
20 日含息報酬，再依「每 21 個交易日取一次」的 21 種起點分別算橫斷面 IC 平均
（全體排序與產業內排序），分樣本外 2019–2023 / 樣本內 2024–2026。

用法（於專案根目錄）：
    .venv/Scripts/python analysis/phase_robustness_agents.py config/tickers_expanded.yaml daily_outputs.csv

只用規則式判斷（不呼叫 LLM）；資料全部來自 data_cache/。
輸出三種：p = 門檻模式的看多機率、pc = 連續模式的看多機率、score = 規則分數。
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from agents.base import continuous_judgement  # noqa: E402
from agents.fundamentals_agent import FundamentalsAgent  # noqa: E402
from agents.macro_agent import MacroAgent  # noqa: E402
from agents.supply_chain_agent import SupplyChainAgent  # noqa: E402
from backtest.metrics import signal_to_probability  # noqa: E402
from data.fetch_financials import FinMindClient, FinMindFundamentalsProvider, get_total_return_prices  # noqa: E402
from data.fetch_macro import FinMindMacroProvider  # noqa: E402
from data.fetch_supply_chain import FinMindSupplyChainProvider, load_graph  # noqa: E402

HORIZON, STEP = 20, 21


class MemoClient(FinMindClient):
    """同一組參數只讀一次快取檔（財報 provider 每次呼叫都會重新讀檔）。"""

    def __init__(self):
        super().__init__()
        self._memo = {}

    def get(self, dataset, data_id, start_date, end_date=None):
        key = (dataset, data_id, start_date, end_date)
        if key not in self._memo:
            self._memo[key] = super().get(dataset, data_id, start_date, end_date)
        return self._memo[key].copy()


def spearman(x, y):
    if x.nunique() < 2 or y.nunique() < 2:
        return np.nan
    return float(x.rank().corr(y.rank()))


def daily_ic(df, col, sectors=None):
    out = {}
    for i, g in df.groupby("i"):
        if sectors is None:
            out[i] = spearman(g[col], g["ret"])
        else:
            vals, w = [], []
            for _, s in g.groupby(g["ticker"].map(sectors)):
                if len(s) >= 3:
                    ic = spearman(s[col], s["ret"])
                    if not np.isnan(ic):
                        vals.append(ic)
                        w.append(len(s))
            out[i] = float(np.average(vals, weights=w)) if vals else np.nan
    return pd.Series(out)


def main(config_path, out_path):
    cfg = yaml.safe_load(open(config_path, encoding="utf-8"))
    tickers = [u["ticker"] for u in cfg["universe"]]
    sectors = {u["ticker"]: u.get("segment", "?") for u in cfg["universe"]}
    client = MemoClient()
    start, end = cfg["backtest"]["start_date"], cfg["backtest"]["end_date"]
    agents = {
        "fundamentals_agent": FundamentalsAgent(FinMindFundamentalsProvider(client, history_start=cfg["fundamentals"]["history_start"])),
        "macro_agent": MacroAgent(FinMindMacroProvider(client, history_start=cfg["macro"]["history_start"])),
        "supply_chain_agent": SupplyChainAgent(
            FinMindSupplyChainProvider(client, history_start=cfg["supply_chain"]["history_start"]),
            graph=load_graph(Path(config_path).resolve().parent.parent / cfg["supply_chain"]["graph"]),
        ),
    }
    membership = None
    if cfg.get("universe_membership"):
        from data.universe import load_membership

        membership = load_membership(Path(config_path).resolve().parent.parent / cfg["universe_membership"])
    prices = {t: get_total_return_prices(client, t, start, end).set_index("date")["adj_close"] for t in tickers}
    calendar = sorted(set().union(*(p.index for p in prices.values())))
    rows = []
    for i in range(len(calendar) - HORIZON):
        d0, d1 = calendar[i], calendar[i + HORIZON]
        for t in tickers:
            s = prices[t]
            if d0 not in s.index:
                continue
            if membership is not None and t not in membership.get(d0.year, set()):
                continue  # 無選股偏誤股票池：只用當年成員
            row = {"i": i, "date": d0, "ticker": t, "ret": float(s.asof(d1) / s.asof(d0) - 1.0)}
            for name, agent in agents.items():
                o = agent.analyze(t, d0.strftime("%Y-%m-%d"))
                row[f"p_{name}"] = signal_to_probability(o.signal, o.confidence)
                row[f"score_{name}"] = o.raw_features.get("rule_score", 0.0)
                # 連續輸出模式的看多機率（由同一次判斷的分數與證據強度換算）
                row[f"pc_{name}"] = continuous_judgement(row[f"score_{name}"], o.raw_features.get("evidence", 1.0))[2]
            rows.append(row)
        if i % 200 == 0:
            print(f"  {d0:%Y-%m-%d}（{i}/{len(calendar) - HORIZON}）", flush=True)
    df = pd.DataFrame(rows)
    df.to_csv(out_path, index=False)

    dates = df.groupby("i")["date"].first()
    oos = pd.to_datetime(dates) < "2024-01-01"
    print(f"\n{len(df)} 筆，{df['ticker'].nunique()} 檔，{df['date'].min():%Y-%m-%d} ~ {df['date'].max():%Y-%m-%d}")
    for name in agents:
        for kind in ("p", "pc", "score"):
            col = f"{kind}_{name}"
            for scope, sec in (("全體", None), ("產業內", sectors)):
                ic = daily_ic(df, col, sec)
                for label, mask in (("樣本外", oos), ("樣本內", ~oos)):
                    sub = ic[mask[ic.index].values] if len(ic) else ic
                    by_phase = sub.groupby(sub.index % STEP).mean()
                    print(f"{name:20s} {kind:5s} {scope:3s} {label}：每日 IC {sub.mean():+.3f}；21 起點 "
                          f"[{by_phase.min():+.3f}, 中位 {by_phase.median():+.3f}, {by_phase.max():+.3f}]，"
                          f"為正 {(by_phase > 0).sum()}/21")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
