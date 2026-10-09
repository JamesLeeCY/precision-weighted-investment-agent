"""以財報 Agent 為核心的產業中性組合：產業內排序、產業內多空，21 種取樣起點穩健性。

用法（於專案根目錄，輸入為 phase_robustness_agents.py 產生的每日輸出）：
    .venv/Scripts/python analysis/sector_neutral_portfolio.py daily_pit.csv config/tickers_pit.yaml
    .venv/Scripts/python analysis/sector_neutral_portfolio.py daily_pit.csv config/tickers_pit.yaml --signal score_fundamentals_agent --quantile 0.2

組合（每期 20 個交易日，每 21 個交易日換一次；同一起點的各期不重疊）：
- 產業中性做多（long-only）：每個產業內依訊號取前 quantile，產業權重 = 股票池的產業權重
  （產業配置與等權持有完全相同，超額只來自產業內選股）；不足 min_sector 檔或訊號全相同的產業整個持有。
- 產業內多空（long-short）：每個產業內前 quantile 做多、後 quantile 做空，產業權重同上（只計有效產業並重新正規化）；
  市場與產業皆中性。台股放空受限（融券／借券成本未計），只作為訊號強度的分析指標。
- 對照：等權持有全部股票、不分產業取前 quantile、看多機率 > 0.5 全部持有（現行回測的 long/neutral 做法）。
成本：換手量 × 單邊成本（同 backtest/portfolio.py）；超額 = 組合淨報酬 − 等權持有淨報酬。
"""
import argparse
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

STEP = 21
COST_PER_SIDE = 0.0029625


def sector_neutral_weights(g: pd.DataFrame, col: str, q: float, min_n: int, side: int,
                           held: set | None = None, keep: float | None = None) -> dict:
    """side=+1 取產業內前 q、-1 取後 q；產業權重 = 股票池產業權重。

    side=+1 時，無法排序的產業（檔數不足或訊號相同）整個持有（中性）；side=-1 時同樣整個持有，
    多空相減後該產業貢獻為 0。
    keep：緩衝規則，已持有（held）的股票只要產業內百分位仍 > keep（做空側為 ≤ 1 − keep）就續抱，降低換手。
    """
    w_sector = g["sector"].value_counts(normalize=True)
    weights = {}
    for sector, sg in g.groupby("sector"):
        pct = sg[col].rank(pct=True, method="average")
        chosen = sg[pct > 1 - q] if side > 0 else sg[pct <= q]
        if keep is not None and held:
            stay = sg["ticker"].isin(held) & ((pct > keep) if side > 0 else (pct <= 1 - keep))
            chosen = sg[sg.index.isin(chosen.index) | stay]
        if len(sg) < min_n or chosen.empty or len(chosen) == len(sg):
            chosen = sg
        for t in chosen["ticker"]:
            weights[t] = w_sector[sector] / len(chosen)
    return weights


def ranked_sectors(g: pd.DataFrame, col: str, q: float, min_n: int) -> pd.Series:
    """可做產業內多空的產業（檔數足夠、前後 q 都選得出且不重疊）及其股票池權重（重新正規化）。"""
    ok = {}
    for sector, sg in g.groupby("sector"):
        pct = sg[col].rank(pct=True, method="average")
        if len(sg) >= min_n and (pct > 1 - q).any() and (pct <= q).any():
            ok[sector] = len(sg)
    s = pd.Series(ok, dtype=float)
    return s / s.sum() if len(s) else s


def long_short_weights(g, col, q, min_n, held_l=None, held_s=None, keep=None):
    w_s = ranked_sectors(g, col, q, min_n)
    long_w, short_w = {}, {}
    for sector, w in w_s.items():
        sg = g[g["sector"] == sector]
        pct = sg[col].rank(pct=True, method="average")
        top, bottom = sg[pct > 1 - q], sg[pct <= q]
        if keep is not None:
            top = sg[(pct > 1 - q) | (sg["ticker"].isin(held_l or set()) & (pct > keep))]
            bottom = sg[(pct <= q) | (sg["ticker"].isin(held_s or set()) & (pct <= 1 - keep))]
        long_w.update({t: w / len(top) for t in top["ticker"]})
        short_w.update({t: w / len(bottom) for t in bottom["ticker"]})
    return long_w, short_w


def turnover(w, prev):
    return sum(abs(w.get(t, 0.0) - prev.get(t, 0.0)) for t in set(w) | set(prev))


def portfolio_return(g, w):
    r = g.set_index("ticker")["ret"]
    return float(sum(wt * r[t] for t, wt in w.items()))


def phase_series(df: pd.DataFrame, col: str, q: float, min_n: int, phase: int, keep: float | None = None) -> pd.DataFrame:
    """單一取樣起點的逐期報酬（毛、淨）與換手量。"""
    rows = []
    prev = {k: {} for k in ("ew", "sn", "gl", "p50", "ls_l", "ls_s")}
    for i in sorted(df["i"].unique()):
        if i % STEP != phase:
            continue
        g = df[df["i"] == i]
        n = len(g)
        w = {"ew": {t: 1 / n for t in g["ticker"]},
             "sn": sector_neutral_weights(g, col, q, min_n, +1, set(prev["sn"]), keep)}
        pct = g[col].rank(pct=True, method="average")
        top = g[pct > 1 - q]
        w["gl"] = {t: 1 / len(top) for t in top["ticker"]} if len(top) else w["ew"]
        held = g[g[col] > 0.5]
        w["p50"] = {t: 1 / len(held) for t in held["ticker"]}  # 空集合 = 全現金
        w["ls_l"], w["ls_s"] = long_short_weights(g, col, q, min_n, set(prev["ls_l"]), set(prev["ls_s"]), keep)
        row = {"i": i, "date": g["date"].iloc[0], "n": n, "n_sn": len(w["sn"]), "n_ls": len(w["ls_l"]) + len(w["ls_s"])}
        for k in ("ew", "sn", "gl", "p50"):
            gross = portfolio_return(g, w[k])
            to = turnover(w[k], prev[k])
            row[f"{k}_gross"], row[f"{k}_to"], row[f"{k}_net"] = gross, to, gross - to * COST_PER_SIDE
        ls_gross = portfolio_return(g, w["ls_l"]) - portfolio_return(g, w["ls_s"])
        ls_to = turnover(w["ls_l"], prev["ls_l"]) + turnover(w["ls_s"], prev["ls_s"])
        row["ls_gross"], row["ls_to"], row["ls_net"] = ls_gross, ls_to, ls_gross - ls_to * COST_PER_SIDE
        prev = w
        rows.append(row)
    out = pd.DataFrame(rows)
    for k in ("sn", "gl", "p50"):
        out[f"{k}_excess_net"] = out[f"{k}_net"] - out["ew_net"]
        out[f"{k}_excess_gross"] = out[f"{k}_gross"] - out["ew_gross"]
    return out


def tstat(x: pd.Series) -> float:
    x = x.dropna()
    return x.mean() / (x.std(ddof=1) / math.sqrt(len(x))) if len(x) > 2 and x.std(ddof=1) > 0 else float("nan")


def summarize(phases: list[pd.DataFrame], metric: str, mask_fn=None) -> str:
    means, ts = [], []
    for p in phases:
        s = p[mask_fn(p)] if mask_fn else p
        means.append(s[metric].mean())
        ts.append(tstat(s[metric]))
    means, ts = np.array(means), np.array(ts)
    return (f"{np.median(means) * 100:+.2f}%（21 起點 [{means.min() * 100:+.2f}%, {means.max() * 100:+.2f}%]，"
            f"為正 {(means > 0).sum()}/21；t 中位 {np.nanmedian(ts):+.2f}）")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("daily_csv")
    ap.add_argument("config")
    ap.add_argument("--signal", default="pc_fundamentals_agent", help="排序用的欄位（預設財報 Agent 連續輸出機率）")
    ap.add_argument("--quantile", type=float, default=1 / 3, help="產業內做多 / 做空的比例（預設前後三分之一）")
    ap.add_argument("--min-sector", type=int, default=3, help="產業至少幾檔才做產業內排序")
    ap.add_argument("--keep", type=float, default=None,
                    help="緩衝：已持有的股票產業內百分位仍高於此值就續抱（例如 0.5）；預設不用")
    ap.add_argument("--out", default=None, help="起點 0 的逐期結果 CSV")
    args = ap.parse_args(argv)

    df = pd.read_csv(args.daily_csv, parse_dates=["date"])
    cfg = yaml.safe_load(open(args.config, encoding="utf-8"))
    df["sector"] = df["ticker"].map({u["ticker"]: u["segment"] for u in cfg["universe"]})
    df = df.dropna(subset=["sector", args.signal, "ret"])

    phases = [phase_series(df, args.signal, args.quantile, args.min_sector, ph, args.keep) for ph in range(STEP)]
    if args.out:
        phases[0].to_csv(args.out, index=False)
    p0 = phases[0]
    early = lambda p: p["date"] < "2024-01-01"  # noqa: E731
    late = lambda p: p["date"] >= "2024-01-01"  # noqa: E731

    print(f"訊號 {args.signal}，產業內前後 {args.quantile:.0%}，產業至少 {args.min_sector} 檔，"
          f"緩衝 {'無' if args.keep is None else f'續抱至百分位 {args.keep:.0%}'}；"
          f"{df['date'].min():%Y-%m-%d} ~ {df['date'].max():%Y-%m-%d}，每起點約 {len(p0)} 期")
    print(f"平均持股：產業中性做多 {p0['n_sn'].mean():.1f} 檔 / 股票池 {p0['n'].mean():.0f} 檔；多空合計 {p0['n_ls'].mean():.1f} 檔")
    print(f"平均換手（每期，權重變動合計）：等權 {p0['ew_to'].mean():.2f}、產業中性做多 {p0['sn_to'].mean():.2f}、"
          f"不分產業前段 {p0['gl_to'].mean():.2f}、p>0.5 {p0['p50_to'].mean():.2f}、多空 {p0['ls_to'].mean():.2f}")
    print("\n每期（20 個交易日）平均，21 個取樣起點的中位數：")
    rows = [
        ("產業中性做多 − 等權（扣成本）", "sn_excess_net"),
        ("產業中性做多 − 等權（未扣成本）", "sn_excess_gross"),
        ("產業內多空（扣成本）", "ls_net"),
        ("產業內多空（未扣成本）", "ls_gross"),
        ("不分產業前段 − 等權（扣成本）", "gl_excess_net"),
        ("p > 0.5 全持有 − 等權（扣成本）", "p50_excess_net"),
    ]
    for label, metric in rows:
        print(f"- {label}")
        for name, fn in (("全期 2019–2026", None), ("2019–2023", early), ("2024–2026", late)):
            print(f"    {name:14s} {summarize(phases, metric, fn)}")

    print("\n逐年（21 起點平均，扣成本）：")
    allp = pd.concat([p.assign(phase=k) for k, p in enumerate(phases)])
    allp["year"] = allp["date"].dt.year
    by_year = allp.groupby("year")[["sn_excess_net", "ls_net", "gl_excess_net"]].mean() * 100
    print("| 年 | 產業中性做多 − 等權 | 產業內多空 | 不分產業前段 − 等權 |")
    print("|---|---|---|---|")
    for y, r in by_year.iterrows():
        print(f"| {y} | {r['sn_excess_net']:+.2f}% | {r['ls_net']:+.2f}% | {r['gl_excess_net']:+.2f}% |")

    cum = (1 + p0["sn_net"]).prod() - 1, (1 + p0["ew_net"]).prod() - 1, (1 + p0["ls_net"]).prod() - 1
    ls_curve = (1 + p0["ls_net"]).cumprod()
    mdd = float((ls_curve / ls_curve.cummax() - 1).min())
    print(f"\n起點 0 累積（扣成本）：產業中性做多 {cum[0] * 100:+.0f}%、等權 {cum[1] * 100:+.0f}%、"
          f"產業內多空 {cum[2] * 100:+.1f}%（最大回撤 {mdd * 100:.1f}%）；"
          f"多空每期勝率 {(p0['ls_net'] > 0).mean():.0%}")


if __name__ == "__main__":
    main()
