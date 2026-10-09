"""各 Agent（與合併策略）的橫斷面 IC：全體排序與產業內排序，分期統計。

用法（於專案根目錄）：
    .venv/Scripts/python analysis/agent_ic.py reports/finmind_expanded/backtest_results.csv config/tickers_expanded.yaml

- 全體 IC：每個時點對所有股票做 Spearman(看多機率, 20 日含息報酬)，再對時點取平均。
  股票橫跨多個產業時，這主要反映「哪個產業表現好」。
- 產業內 IC：每個時點先在各產業內做 Spearman（產業內至少 3 檔且機率有差異），
  再以股票數加權平均；衡量的是同產業內的選股能力。
- 分期：樣本外 2019–2023 / 樣本內 2024–2026。p 值為常態近似，另附 IC>0 期數的符號檢定。
"""
import math
import sys

import numpy as np
import pandas as pd
import yaml


def spearman(x, y):
    if x.nunique() < 2 or y.nunique() < 2:
        return np.nan
    return float(x.rank().corr(y.rank()))


def binom_two_sided(k, n):
    if n == 0:
        return float("nan")
    probs = [math.comb(n, i) / 2**n for i in range(n + 1)]
    return min(1.0, sum(p for p in probs if p <= probs[k] + 1e-12))


def per_date(df, col, sectors=None):
    out = {}
    for date, g in df.groupby("as_of_date"):
        if sectors is None:
            if len(g) >= 3:
                out[date] = spearman(g[col], g["forward_return"])
        else:
            vals, weights = [], []
            for _, s in g.groupby(g["ticker"].map(sectors)):
                if len(s) >= 3:
                    ic = spearman(s[col], s["forward_return"])
                    if not np.isnan(ic):
                        vals.append(ic)
                        weights.append(len(s))
            if vals:
                out[date] = float(np.average(vals, weights=weights))
    return pd.Series(out).dropna().sort_index()


def summary(ics):
    n = len(ics)
    if n < 2:
        return f"n={n}"
    mean, sd = ics.mean(), ics.std(ddof=1)
    t = mean / (sd / math.sqrt(n)) if sd > 0 else float("nan")
    pos = int((ics > 0).sum())
    return (f"{mean:+.3f}（t {t:+.2f}，p≈{math.erfc(abs(t) / math.sqrt(2)):.3f}；"
            f"IC>0 {pos}/{n}，符號檢定 p={binom_two_sided(pos, n):.3f}）")


def main(results_path, config_path):
    df = pd.read_csv(results_path)
    cfg = yaml.safe_load(open(config_path, encoding="utf-8"))
    sectors = {u["ticker"]: u.get("segment", "?") for u in cfg["universe"]}
    cols = [c for c in df.columns if c.startswith("p_")] + [
        f"{s}_p" for s in ("baseline_b", "precision_weighted", "calibrated_average", "calibrated_precision_weighted")
        if f"{s}_p" in df
    ]
    dates = pd.to_datetime(df["as_of_date"])
    periods = [("樣本外 2019–2023", dates < "2024-01-01"), ("樣本內 2024–2026", dates >= "2024-01-01")]
    print(f"{results_path}：{len(df)} 事件，{df['ticker'].nunique()} 檔，{df['as_of_date'].nunique()} 個時點")
    for col in cols:
        print(f"\n## {col}")
        for label, mask in periods:
            sub = df[mask]
            print(f"  {label}  全體 {summary(per_date(sub, col))}")
            print(f"  {'':16s}  產業內 {summary(per_date(sub, col, sectors))}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
