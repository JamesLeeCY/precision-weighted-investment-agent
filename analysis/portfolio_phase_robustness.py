"""合併策略（簡單平均）相對等權持有的超額報酬：21 種取樣起點 + 產業配置 / 選股拆解。

用法（於專案根目錄，輸入為 phase_robustness_agents.py 產生的每日輸出）：
    .venv/Scripts/python analysis/portfolio_phase_robustness.py daily_expanded.csv config/tickers_expanded.yaml

- 合併機率 = 各 Agent 看多機率的簡單平均（對應回測的 Baseline B，未含精度加權與校準）
- 組合：合併機率 > 0.55 的股票等權持有 20 個交易日，其餘持現金；不計交易成本
- 超額 = 組合報酬 − 等權持有全部股票的報酬（每期）
- 拆解（Brinson 式）：產業配置 = Σ(組合產業權重 − 股票池產業權重) × 股票池產業報酬；
  選股 = Σ 組合產業權重 × (組合在該產業的報酬 − 股票池該產業報酬)；現金部位的超額另列
"""
import math
import sys

import numpy as np
import pandas as pd
import yaml

STEP = 21
AGENTS = ["fundamentals_agent", "macro_agent", "supply_chain_agent"]


def period_stats(g, col, sectors, threshold=0.55):
    g = g.assign(sector=g["ticker"].map(sectors))
    held = g[g[col] > threshold]
    universe_ret = g["ret"].mean()
    if held.empty:
        return pd.Series({"excess": -universe_ret, "alloc": 0.0, "select": 0.0, "cash": -universe_ret, "n": 0})
    w_p = held["sector"].value_counts(normalize=True)
    w_u = g["sector"].value_counts(normalize=True)
    r_u = g.groupby("sector")["ret"].mean()
    r_p = held.groupby("sector")["ret"].mean()
    alloc = sum((w_p.get(s, 0.0) - w_u[s]) * (r_u[s] - universe_ret) for s in w_u.index)
    select = sum(w_p[s] * (r_p[s] - r_u[s]) for s in w_p.index)
    excess = held["ret"].mean() - universe_ret
    return pd.Series({"excess": excess, "alloc": alloc, "select": select, "cash": 0.0, "n": len(held)})


def main(daily_path, config_path):
    df = pd.read_csv(daily_path, parse_dates=["date"])
    cfg = yaml.safe_load(open(config_path, encoding="utf-8"))
    sectors = {u["ticker"]: u["segment"] for u in cfg["universe"]}
    for kind, label in (("p", "門檻模式"), ("pc", "連續模式")):
        df[f"merged_{kind}"] = df[[f"{kind}_{a}" for a in AGENTS]].mean(axis=1)
        per = df.groupby("i").apply(lambda g: period_stats(g, f"merged_{kind}", sectors))
        per["date"] = df.groupby("i")["date"].first()
        per["oos"] = per["date"] < "2024-01-01"
        print(f"\n## 簡單平均合併（{label}），相對等權持有，每期 20 個交易日、未扣成本")
        for name, mask in (("樣本外 2019–2023", per["oos"]), ("樣本內 2024–2026", ~per["oos"])):
            sub = per[mask]
            by_phase = sub.groupby(sub.index % STEP)[["excess", "alloc", "select", "n"]].mean()
            tstats = []
            for ph in range(STEP):
                x = sub[sub.index % STEP == ph]["excess"]
                tstats.append(x.mean() / (x.std(ddof=1) / math.sqrt(len(x))))
            print(f"  {name}：超額 中位 {by_phase['excess'].median() * 100:+.2f}%（21 起點 "
                  f"[{by_phase['excess'].min() * 100:+.2f}%, {by_phase['excess'].max() * 100:+.2f}%]，為正 "
                  f"{(by_phase['excess'] > 0).sum()}/21；t 中位 {np.median(tstats):+.2f}）")
            print(f"  {'':16s} 拆解（起點平均）：產業配置 {by_phase['alloc'].mean() * 100:+.2f}%、"
                  f"選股 {by_phase['select'].mean() * 100:+.2f}%；平均持股 {by_phase['n'].mean():.1f} 檔")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
