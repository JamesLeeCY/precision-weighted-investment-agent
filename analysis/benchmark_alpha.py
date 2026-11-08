"""fv5／fv5x 的基準比較：因子迴歸 alpha 與 Deflated Sharpe Ratio（使用者 2026-11-08 要求；非點子卡，沒有通過門檻，只報告）。

用法（於專案根目錄；資料皆已快取）：
    .venv/Scripts/python analysis/benchmark_alpha.py
輸出 docs/benchmark_alpha.md。

1. 因子迴歸：fv5、fv5x 的日淨報酬（analysis/fv5_family.run_backtests，與回測完全相同）對以下因子做 OLS，
   截距年化（× 252）為 alpha，標準誤用 Newey-West（落後 5）。
   - MKT：加權指數含息日報酬 − 1.5%／252。
   - 5 個多空因子（前 500 名、產業內前 1/3 − 後 1/3、各等權、前一日特徵）：SMB（市值小 − 大）、HML（帳面市值比）、
     MOM（12-1 動能）、STR（前 20 日報酬，正值 = 近期漲）、LVOL（60 日波動低 − 高）、BETA（250 日 β 高 − 低）。
     特徵與 I049（analysis/fv5_style_hedge.py）相同，另加 SMB；穩健性另做不分產業（前 500 名全體三分位）的版本與月報酬迴歸。
2. Deflated Sharpe Ratio（Bailey & López de Prado 2014）：
   PSR(SR*) = Φ((SR̂ − SR*)·√(T−1) / √(1 − γ3·SR̂ + (γ4 − 1)/4·SR̂²))，SR 為日頻；
   SR* = σ_SR·[(1 − γ)·Φ⁻¹(1 − 1/N) + γ·Φ⁻¹(1 − 1/(N·e))]，γ = 0.5772（試驗數 N 下、真實 Sharpe 皆為 0 時最大 Sharpe 的期望值）。
   σ_SR（試驗間 Sharpe 的標準差）以 docs/ 各報告表格中「兩段 / 全期」的全期 Sharpe 估計；N 做敏感度分析。
研究結果，非投資建議。
"""
import glob
import math
import re
import sys
from pathlib import Path
from statistics import NormalDist

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "analysis"))
sys.path.insert(0, str(ROOT))
import asset_growth as agm  # noqa: E402
import fv5_family as ff  # noqa: E402
import fv5_style_hedge as sh  # noqa: E402
import leg_probe as lp  # noqa: E402
import margin_surprise as msm  # noqa: E402

RF = 0.015
ND = NormalDist()
EULER = 0.5772156649


def plain_terciles(X: pd.DataFrame, member: pd.DataFrame) -> pd.DataFrame:
    return X.where(member).rank(axis=1, pct=True)


def ls(P: pd.DataFrame, rets: pd.DataFrame) -> pd.Series:
    P = P.shift(1)
    lw, sw = (P > 2 / 3).astype(float), (P <= 1 / 3).astype(float)
    return (rets * lw).sum(axis=1) / lw.sum(axis=1).replace(0, np.nan) - (rets * sw).sum(axis=1) / sw.sum(axis=1).replace(0, np.nan)


def build_factors(c) -> tuple[pd.DataFrame, pd.DataFrame]:
    days = c.adj.index
    eq = {}
    for t in c.tickers:
        e = msm.balance_equity(c.client, t.split(".")[0])
        if len(e):
            eq[t] = e[e.index.month.isin([3, 6, 9, 12])]
    equity = agm.to_daily(pd.DataFrame(eq).sort_index(), days).reindex(columns=c.tickers).astype(float)
    chars = {"SMB": -c.logcap, "HML": equity / np.exp(c.logcap), "MOM": c.adj.shift(21) / c.adj.shift(252) - 1,
             "STR": c.adj / c.adj.shift(20) - 1, "LVOL": -c.rets.rolling(60, min_periods=40).std(), "BETA": c.betas}
    tri = lp.market_tri(c.client).reindex(days)
    mkt = (tri.pct_change() - RF / 252).rename("MKT")
    sec = pd.DataFrame({k: ls(sh.sector_terciles(X, c.member, c.sector), c.rets) for k, X in chars.items()})
    pla = pd.DataFrame({k: ls(plain_terciles(X, c.member), c.rets) for k, X in chars.items()})
    return pd.concat([mkt, sec], axis=1), pd.concat([mkt, pla], axis=1)


def ols_nw(y: pd.Series, X: pd.DataFrame, lags: int = 5) -> dict:
    df = pd.concat([y.rename("y"), X], axis=1).dropna()
    Y = df["y"].to_numpy()
    Z = np.column_stack([np.ones(len(df)), df[X.columns].to_numpy()])
    b, *_ = np.linalg.lstsq(Z, Y, rcond=None)
    e = Y - Z @ b
    n = len(Y)
    ZtZi = np.linalg.inv(Z.T @ Z)
    u = Z * e[:, None]
    S = u.T @ u
    for k in range(1, lags + 1):
        g = u[k:].T @ u[:-k]
        S += (1 - k / (lags + 1)) * (g + g.T)
    V = ZtZi @ S @ ZtZi
    se = np.sqrt(np.diag(V))
    return {"n": n, "b": b, "t": b / se, "r2": 1 - e.var() / Y.var(), "resid_vol": e.std() * math.sqrt(252)}


def monthly(x: pd.Series) -> pd.Series:
    return (1 + x).groupby(x.index.to_period("M")).prod() - 1


def trial_sharpes() -> np.ndarray:
    vals = []
    for p in glob.glob(str(ROOT / "docs" / "*.md")):
        t = Path(p).read_text(encoding="utf-8")
        vals += [float(m[2]) for m in re.findall(r"\|\s*(-?\d+\.\d\d)\s*/\s*(-?\d+\.\d\d)\s*\|\s*(-?\d+\.\d\d)\s*\|", t)]
    return np.array(vals)


def sr_star(sd_annual: float, n: int) -> float:
    """N 個真實 Sharpe 為 0 的試驗中，最大年化 Sharpe 的期望值。"""
    if n <= 1:
        return 0.0
    z = (1 - EULER) * ND.inv_cdf(1 - 1 / n) + EULER * ND.inv_cdf(1 - 1 / (n * math.e))
    return sd_annual * z


def psr(x: pd.Series, sr_bench_annual: float) -> float:
    x = x.dropna()
    sr = x.mean() / x.std(ddof=1)
    g3 = float(((x - x.mean()) ** 3).mean() / x.std(ddof=0) ** 3)
    g4 = float(((x - x.mean()) ** 4).mean() / x.std(ddof=0) ** 4)
    sb = sr_bench_annual / math.sqrt(252)
    z = (sr - sb) * math.sqrt(len(x) - 1) / math.sqrt(1 - g3 * sr + (g4 - 1) / 4 * sr ** 2)
    return ND.cdf(z)


def min_trl(x: pd.Series, sr_bench_annual: float, conf: float = 0.95) -> float:
    """達到 conf 信心所需的最短紀錄長度（年）。"""
    x = x.dropna()
    sr = x.mean() / x.std(ddof=1)
    g3 = float(((x - x.mean()) ** 3).mean() / x.std(ddof=0) ** 3)
    g4 = float(((x - x.mean()) ** 4).mean() / x.std(ddof=0) ** 4)
    sb = sr_bench_annual / math.sqrt(252)
    if sr <= sb:
        return float("inf")
    n = 1 + (1 - g3 * sr + (g4 - 1) / 4 * sr ** 2) * (ND.inv_cdf(conf) / (sr - sb)) ** 2
    return n / 252


def main():
    R, _ = ff.run_backtests()
    c = ff.LAST["c"]
    series = {"fv5": R["fv5"], "fv5x": R["fv5x（E+S+V）"]}
    F_sec, F_pla = build_factors(c)
    names = list(F_sec.columns)
    periods = {"2019–2022": lambda s: s[s.index < lp.SPLIT], "2023–2026/04": lambda s: s[s.index >= lp.SPLIT], "全期": lambda s: s}
    L = ["# fv5／fv5x 基準比較：因子迴歸 alpha 與 Deflated Sharpe（analysis/benchmark_alpha.py 產生）", "",
         "研究結果，非投資建議。報酬為扣成本（單邊 0.29625% ＋ 借券費）與台指期對沖後的日淨報酬，與回測相同。", ""]

    def reg_table(F, title, freq="日"):
        L.extend([f"## {title}", "",
                  "| 策略 | 期間 | 樣本 | alpha（年化） | t | " + " | ".join(names) + " | R² |",
                  "|---|---|---|---|---|" + "---|" * len(names) + "---|"])
        out = {}
        for k, x in series.items():
            for pn, f in periods.items():
                if freq == "月":
                    y, X = monthly(f(x).dropna()), F.apply(lambda col: monthly(f(col).dropna()))
                    r = ols_nw(y, X, lags=2)
                    a = r["b"][0] * 12
                else:
                    r = ols_nw(f(x), F)
                    a = r["b"][0] * 252
                out[(k, pn)] = r | {"alpha": a}
                L.append(f"| {k} | {pn} | {r['n']} | {a:+.2%} | {r['t'][0]:.2f} | "
                         + " | ".join(f"{b:+.3f}（{t:.1f}）" for b, t in zip(r["b"][1:], r["t"][1:])) + f" | {r['r2']:.3f} |")
        L.append("")
        return out

    raw = {k: {pn: f(x).mean() * 252 for pn, f in periods.items()} for k, x in series.items()}
    L += ["## 原始年化平均報酬（迴歸前，算術平均 × 252）", "",
          "| 策略 | " + " | ".join(periods) + " |", "|---|" + "---|" * len(periods)]
    for k, v in raw.items():
        L.append(f"| {k} | " + " | ".join(f"{v[p]:+.2%}" for p in periods) + " |")
    L.append("")
    main_reg = reg_table(F_sec, "主要：日報酬對 7 因子（多空因子為產業內三分位）；係數括號為 Newey-West t")
    reg_table(F_pla, "穩健性：多空因子不分產業（前 500 名全體三分位）")
    reg_table(F_sec, "穩健性：月報酬（產業內因子；Newey-West 落後 2）", freq="月")
    fc = F_sec.dropna()
    L += ["## 因子本身（全期）", "", "| 因子 | 年化平均 | 年化波動 | Sharpe | 與 fv5 相關 |", "|---|---|---|---|---|"]
    for k in names:
        f = fc[k]
        L.append(f"| {k} | {f.mean() * 252:+.2%} | {f.std() * math.sqrt(252):.1%} | {lp.sharpe(f):.2f} | {f.corr(series['fv5'].reindex(f.index)):+.2f} |")
    L.append("")

    # Deflated Sharpe
    tr = trial_sharpes()
    sd_emp = float(tr.std(ddof=1))
    L += ["## Deflated Sharpe Ratio", "",
          f"- 試驗間 Sharpe 標準差：從 docs/ 報告表格收集到 {len(tr)} 個全期 Sharpe（各點子卡與 fv5 變體），標準差 {sd_emp:.2f}、"
          f"中位數 {np.median(tr):.2f}。這些多半是 fv5 的小修改，彼此高度相關，所以「有效試驗數」遠小於 {len(tr)}；下面以 N 做敏感度分析。",
          "- SR* = 在 N 個真實 Sharpe 都是 0 的試驗中，運氣最好的那個預期能有的年化 Sharpe；DSR = 實際 Sharpe 顯著高於 SR* 的機率（Bailey & López de Prado 2014，已考慮偏態與峰態）。", ""]
    for k, x in series.items():
        xx = x.dropna()
        g3 = float(((xx - xx.mean()) ** 3).mean() / xx.std(ddof=0) ** 3)
        g4 = float(((xx - xx.mean()) ** 4).mean() / xx.std(ddof=0) ** 4)
        L.append(f"- {k}：全期年化 Sharpe {lp.sharpe(xx):.2f}，{len(xx)} 個交易日（{len(xx) / 252:.1f} 年），偏態 {g3:+.2f}、峰態 {g4:.1f}；"
                 f"PSR（對 0）{psr(xx, 0.0):.4f}。")
    L += ["", "| 試驗間 Sharpe 標準差 | N | SR*（年化） | fv5 DSR | fv5x DSR | fv5 要達 95% 所需年數 |", "|---|---|---|---|---|---|"]
    for sd in (0.3, sd_emp, 0.8):
        for n in (10, 50, len(tr), 500, 1000):
            s0 = sr_star(sd, n)
            L.append(f"| {sd:.2f} | {n} | {s0:.2f} | {psr(series['fv5'], s0):.3f} | {psr(series['fv5x'], s0):.3f} | {min_trl(series['fv5'], s0):.1f} |")
    L.append("")
    (ROOT / "docs" / "benchmark_alpha.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))
    return main_reg


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
