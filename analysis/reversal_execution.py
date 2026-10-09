"""用短期反轉降低財報產業中性組合的交易成本：不另外交易，只改變原本換倉時的取捨。

用法（於專案根目錄；輸入為 technical_timing.py 產生的 daily_pit_val_tech.csv，需有 pc_fundamentals_agent、rev_1w）：
    .venv/Scripts/python analysis/reversal_execution.py daily_pit_val_tech.csv config/tickers_pit.yaml
輸出 docs/reversal_execution_data.md。

設計（看結果前固定）：
- 基準：財報 Agent 連續機率，每個產業內取前 1/3，產業權重 = 股票池產業權重；每 21 個交易日換倉、持有 20 日。
  另一個基準加緩衝（已持有者產業內百分位 > 50% 就續抱）。
- 反轉訊號 rev_1w = 過去 5 個交易日報酬的負值（預測日前一個交易日以前的資料）。
- B 延後賣出：原本要賣出的持股，若反轉訊號在產業內前 1/3（近 5 日跌最多），本期續抱。
- C 邊際偏好跌深：選股分數 = 財報產業內百分位 + 0.1 × 反轉產業內百分位，取前 1/3。
- 成本：換手量 × 單邊 0.29625%；超額 = 組合淨報酬 − 等權持有淨報酬。
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
import sector_neutral_portfolio as snp  # noqa: E402
from backtest.portfolio import max_drawdown  # noqa: E402

PPY = 252 / 21
COST = snp.COST_PER_SIDE
Q = 1 / 3
SPLIT = "2023-01-01"
SEGMENTS = [("2019–2022（樣本外）", lambda d: d < SPLIT), ("2023–2026/05", lambda d: d >= SPLIT)]
TILT = 0.1


def target_weights(g, held, keep=None, delay_sell=False, tilt=False):
    w_sector = g["sector"].value_counts(normalize=True)
    weights = {}
    for sector, sg in g.groupby("sector"):
        pf = sg["pc_fundamentals_agent"].rank(pct=True, method="average")
        pr = sg["rev_1w"].rank(pct=True, method="average")
        score = pf + TILT * pr.fillna(0.5) if tilt else pf
        ps = score.rank(pct=True, method="average")
        chosen = ps > 1 - Q
        is_held = sg["ticker"].isin(held)
        if keep is not None:
            chosen |= is_held & (pf > keep)
        if delay_sell:
            chosen |= is_held & (pr > 1 - Q)  # 原本要賣、但近 5 日跌最多 → 續抱
        names = sg.loc[chosen, "ticker"]
        if len(sg) < 3 or names.empty or len(names) == len(sg):
            names = sg["ticker"]
        for t in names:
            weights[t] = w_sector[sector] / len(names)
    return weights


def run_phase(df, phase, **kw):
    rows, prev, prev_ew = [], {}, {}
    for i in sorted(df["i"].unique()):
        if i % snp.STEP != phase:
            continue
        g = df[df["i"] == i]
        w = target_weights(g, set(prev), **kw)
        ew = {t: 1 / len(g) for t in g["ticker"]}
        r, r_ew = snp.portfolio_return(g, w), snp.portfolio_return(g, ew)
        to, to_ew = snp.turnover(w, prev), snp.turnover(ew, prev_ew)
        rows.append({"d": g["date"].iloc[0].strftime("%Y-%m-%d"), "net": r - to * COST, "gross": r,
                     "ew_net": r_ew - to_ew * COST, "to": to, "n": len(w)})
        prev, prev_ew = w, ew
    p = pd.DataFrame(rows)
    p["ex_net"] = p["net"] - p["ew_net"]
    return p


def stats(r):
    r = np.asarray(r, dtype=float)
    total = float(np.prod(1 + r) - 1)
    ann = (1 + total) ** (PPY / len(r)) - 1
    vol = r.std(ddof=1) * math.sqrt(PPY)
    return ann / vol if vol else float("nan"), max_drawdown(r)


def tstat(x):
    x = np.asarray(x, dtype=float)
    return x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))


def main(path, config):
    cols = ["i", "date", "ticker", "ret", "sector", "pc_fundamentals_agent", "rev_1w"]
    df = pd.read_csv(path, parse_dates=["date"], usecols=cols).dropna(subset=["pc_fundamentals_agent", "ret", "sector"])
    variants = [
        ("基準：產業中性做多", dict()),
        ("+ B 延後賣出", dict(delay_sell=True)),
        ("+ C 邊際偏好跌深", dict(tilt=True)),
        ("+ B + C", dict(delay_sell=True, tilt=True)),
        ("基準：產業中性 + 緩衝 50%", dict(keep=0.5)),
        ("緩衝 + B", dict(keep=0.5, delay_sell=True)),
        ("緩衝 + C", dict(keep=0.5, tilt=True)),
        ("緩衝 + B + C", dict(keep=0.5, delay_sell=True, tilt=True)),
    ]
    out = ["# 用短期反轉降低財報組合交易成本（自動產生）", "",
           "由 [analysis/reversal_execution.py](../analysis/reversal_execution.py) 產生；解讀見 "
           "[reversal_execution_report.md](reversal_execution_report.md)。21 種取樣起點中位數；每期 20 個交易日；"
           "超額 = 相對等權持有，扣成本。", "",
           "| 組合 | 期間 | 超額（扣成本，每期） | t | 為正起點 | 每期換手 | 平均持股 | Sharpe | 最大回撤 |",
           "|---|---|---|---|---|---|---|---|---|"]
    for label, kw in variants:
        phases = [run_phase(df, ph, **kw) for ph in range(snp.STEP)]
        for name, fn in SEGMENTS:
            seg = [p[p["d"].map(fn)] for p in phases]
            ex = [s["ex_net"].mean() for s in seg]
            ts = [tstat(s["ex_net"]) for s in seg]
            st = [stats(s["net"]) for s in seg]
            out.append(f"| {label} | {name} | {np.median(ex) * 100:+.2f}% | {np.median(ts):+.2f} | {sum(x > 0 for x in ex)}/21 | "
                       f"{np.median([s['to'].mean() for s in seg]):.2f} | {np.median([s['n'].mean() for s in seg]):.1f} | "
                       f"{np.median([x[0] for x in st]):.2f} | {np.median([x[1] for x in st]) * 100:.0f}% |")
            print(out[-1], flush=True)
    (ROOT / "docs" / "reversal_execution_data.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("DONE", flush=True)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
