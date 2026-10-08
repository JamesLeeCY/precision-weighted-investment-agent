"""供應鏈 Agent 橫斷面 IC 的分期穩定性分析。

用法（於專案根目錄）：
    .venv/Scripts/python analysis/ic_by_period.py reports/finmind_supply_chain_long_v1/backtest_results.csv
輸出：全期 / 樣本外（2019–2023）/ 樣本內（2024–2026）/ 逐年的橫斷面 IC 平均、t、
常態近似 p、IC > 0 的期數比例與符號檢定的精確二項 p（雙尾）。
"""
import math
import sys

import numpy as np
import pandas as pd


def spearman(x, y):
    rx, ry = x.rank(), y.rank()
    if rx.std() == 0 or ry.std() == 0:
        return np.nan
    return float(np.corrcoef(rx, ry)[0, 1])


def per_date_ic(df, score_col):
    out = {}
    for date, g in df.groupby("as_of_date"):
        if len(g) >= 3:
            ic = spearman(g[score_col], g["forward_return"])
            if not np.isnan(ic):
                out[date] = ic
    return pd.Series(out).sort_index()


def binom_two_sided(k, n):
    """符號檢定：H0 下 P(IC>0) = 0.5 的精確雙尾 p。"""
    if n == 0:
        return float("nan")
    probs = [math.comb(n, i) / 2**n for i in range(n + 1)]
    pk = probs[k]
    return min(1.0, sum(p for p in probs if p <= pk + 1e-12))


def summarize(ics, label):
    n = len(ics)
    if n < 2:
        return f"{label:24s} n={n}"
    mean, sd = ics.mean(), ics.std(ddof=1)
    t = mean / (sd / math.sqrt(n)) if sd > 0 else float("nan")
    p = math.erfc(abs(t) / math.sqrt(2))
    pos = int((ics > 0).sum())
    return (f"{label:24s} n={n:3d}  IC 平均 {mean:+.3f}  t {t:+.2f}  p≈{p:.3f}  "
            f"IC>0 {pos}/{n} ({pos / n:.0%}) 符號檢定 p={binom_two_sided(pos, n):.3f}")


for path in sys.argv[1:]:
    df = pd.read_csv(path)
    col = "p_supply_chain_agent"
    ics = per_date_ic(df, col)
    dates = pd.to_datetime(ics.index)
    print(f"\n### {path}  （{len(df)} 事件，{df['as_of_date'].min()} ~ {df['as_of_date'].max()}）")
    print(summarize(ics, "全期"))
    print(summarize(ics[dates < "2024-01-01"], "樣本外 2019–2023"))
    print(summarize(ics[dates >= "2024-01-01"], "樣本內 2024–2026"))
    for year in sorted(set(dates.year)):
        print(summarize(ics[dates.year == year], f"  {year}"))
    p = df[col]
    o = df["outcome"]
    dirn = p != 0.5
    hit = ((p > 0.5) & (o == 1)) | ((p < 0.5) & (o == 0))
    print(f"Brier {((p - o) ** 2).mean():.4f}（基準 0.25）  方向命中率 {hit[dirn].mean():.3f}（多 {(p > 0.5).sum()} / 空 {(p < 0.5).sum()}）  "
          f"基率 {o.mean():.3f}  期末校準係數 {df['slope_supply_chain_agent'].iloc[-1]:.2f}")
