"""台指 VIX（自算）用於 0050 持股調整與月營收驚奇多空的波動率管理。

用法（於專案根目錄；先執行 analysis/txo_vix.py 產生 reports/txo_vix.csv）：
    .venv/Scripts/python analysis/vix_timing.py
輸出 docs/vix_timing.md 與 reports/vix_timing.csv。

設計（看結果前固定）：
- VIX：用台指選擇權結算價自行計算（analysis/txo_vix.py）；第 t 日只用 t−1 日收盤的 VIX。
  以期交所官方 2026-07 ~ 10 每日收盤值驗證（data_cache/taifex_vix/，官方只免費提供近 3 個月）。
- 0050 持股規則（成本：持股變動 × allocation_study.COST；空手報酬 0）：
  A1 恐慌時加碼：VIX 在過去 252 日的百分位 ≥ 80% → 100%，≤ 20% → 60%，其餘 80%；
  A2 波動率風險溢酬：VRP = (VIX/100)² − 0050 過去 21 日實際變異數（年化）；VRP 高於過去 252 日中位數 → 100%，否則 70%；
  B  波動率管理（Moreira & Muir 2017，不加槓桿）：持股 = min(1, k ÷ VIX)，k = 過去 756 日 VIX 中位數；
  B′ 同 B，但用 0050 過去 21 日實際波動（年化 %）取代 VIX，檢驗隱含波動率是否有額外資訊。
- 對照：0050 長期持有；固定持股（比例 = 該規則平均持股）。
- 期間：2008 ~ 2026/04（VIX 自 2007 起，需一年暖身），兩段 2008–2015 / 2016 ~ 2026/04。
- 補充：B、B′ 套用在月營收驚奇多空（市值前 500 檔、fv3 建構，2019-03 ~ 2026-04），與同平均部位比較。
"""
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "analysis"))
import allocation_study as al  # noqa: E402
from data.fetch_financials import FinMindClient, get_total_return_prices  # noqa: E402


def official_vix() -> pd.Series:
    rows = []
    for f in sorted((ROOT / "data_cache" / "taifex_vix").glob("*new.txt")):
        for line in f.read_text(encoding="big5", errors="ignore").splitlines():
            parts = line.split()
            if len(parts) >= 3 and parts[0].isdigit() and len(parts[0]) == 8:
                rows.append((pd.Timestamp(parts[0]), float(parts[2])))
    return pd.Series(dict(rows)).sort_index()


def run(expo: pd.Series, r: pd.Series) -> pd.Series:
    e = expo.reindex(r.index)
    return e * r - e.diff().abs().fillna(0.0) * al.COST


def summary(x: pd.Series) -> dict:
    x = x.dropna()
    eq = (1 + x).cumprod()
    return {"sharpe": float(x.mean() / x.std() * math.sqrt(252)), "ann": float(eq.iloc[-1] ** (252 / len(x)) - 1),
            "vol": float(x.std() * math.sqrt(252)), "mdd": float((eq / eq.cummax() - 1).min())}


def rules(vix: pd.Series, r: pd.Series) -> dict:
    v = vix.reindex(r.index).ffill()
    pct = v.rolling(252, min_periods=200).apply(lambda w: (w[:-1] < w[-1]).mean(), raw=True)
    a1 = pd.Series(np.where(pct >= 0.8, 1.0, np.where(pct <= 0.2, 0.6, 0.8)), index=r.index).where(pct.notna())
    rv = r.rolling(21, min_periods=15).var() * 252
    vrp = (v / 100) ** 2 - rv
    a2 = pd.Series(np.where(vrp > vrp.rolling(252, min_periods=200).median(), 1.0, 0.7), index=r.index).where(vrp.rolling(252, min_periods=200).median().notna())
    k = v.rolling(756, min_periods=250).median()
    b = (k / v).clip(upper=1.0)
    rvol = np.sqrt(rv) * 100
    kr = rvol.rolling(756, min_periods=250).median()
    b2 = (kr / rvol).clip(upper=1.0)
    # 第 t 日只用 t−1 日收盤的資訊
    return {k_: s.shift(1) for k_, s in {"A1 恐慌時加碼": a1, "A2 波動率風險溢酬": a2, "B 波動率管理（VIX）": b, "B′ 波動率管理（實際波動）": b2}.items()}


def main():
    import dotenv

    dotenv.load_dotenv(ROOT / ".env")
    vix = pd.read_csv(ROOT / "reports" / "txo_vix.csv", index_col=0, parse_dates=True)["vix"]
    off = official_vix()
    both = pd.concat([vix.rename("自算"), off.rename("官方")], axis=1).dropna()
    px = get_total_return_prices(FinMindClient(), "0050.TW", "2003-06-30", "2026-05-31").set_index("date")["adj_close"].astype(float)
    r_all = px.pct_change()
    R = rules(vix, r_all)
    r = r_all[(r_all.index >= "2008-01-01") & (r_all.index <= "2026-04-30")]
    S = {"0050 長期持有": r}
    avg = {}
    for k, e in R.items():
        e = e.reindex(r.index)
        S[k] = run(e, r)
        avg[k] = float(e.mean())
        S[f"固定 {avg[k]:.0%}（對照 {k.split()[0]}）"] = run(pd.Series(avg[k], index=r.index), r)
    P = pd.DataFrame(S)
    P.to_csv(ROOT / "reports" / "vix_timing.csv")

    lines = ["# 台指 VIX（自算）：0050 持股調整與波動率管理（自動產生）", "",
             "由 [analysis/vix_timing.py](../analysis/vix_timing.py) 產生；設計見程式開頭。Sharpe = 年化報酬 ÷ 年化波動（無風險利率 0，空手報酬 0），已扣調整成本。研究結果，非投資建議。", "",
             "## 自算 VIX 與期交所官方值比較", "",
             f"共 {len(both)} 個交易日（{both.index.min():%Y-%m-%d} ~ {both.index.max():%Y-%m-%d}）：相關 {both.corr().iloc[0, 1]:+.3f}；"
             f"平均差（自算 − 官方）{(both['自算'] - both['官方']).mean():+.2f}；平均絕對差 {(both['自算'] - both['官方']).abs().mean():.2f} 點；"
             f"官方平均 {both['官方'].mean():.2f}。", "",
             f"自算 VIX（2007 ~ 2026/04）：平均 {vix[:'2026-04-30'].mean():.1f}、中位數 {vix[:'2026-04-30'].median():.1f}、最高 {vix.max():.1f}（{vix.idxmax():%Y-%m-%d}）。", ""]
    for seg, m in (("2008–2015", P.index < "2016-01-01"), ("2016 ~ 2026/04", P.index >= "2016-01-01"), ("全期 2008 ~ 2026/04", P.index == P.index)):
        lines += [f"## {seg}", "", "| 策略 | 平均持股 | Sharpe | 年化報酬 | 年化波動 | 最大回撤 |", "|---|---|---|---|---|---|"]
        for k in P.columns:
            if k.startswith("0050"):
                e_avg = 1.0
            elif k.startswith("固定"):
                e_avg = float(k.split()[1].split("%")[0]) / 100
            else:
                e_avg = float(R[k].reindex(r.index)[m].mean())
            s = summary(P.loc[m, k])
            lines.append(f"| {k} | {e_avg:.0%} | {s['sharpe']:.2f} | {s['ann']:+.1%} | {s['vol']:.1%} | {s['mdd']:.1%} |")
        lines.append("")
    lines.append("相對同平均持股的固定比例（全期，年化報酬差，括號 t 值）：")
    for k in R:
        d = (P[k] - P[f"固定 {avg[k]:.0%}（對照 {k.split()[0]}）"]).dropna()
        lines.append(f"- {k}：{d.mean() * 252:+.2%}（{d.mean() / (d.std() / math.sqrt(len(d))):+.2f}）")

    bl = ROOT / "reports" / "legs" / "blend_longonly_top500.csv"
    if bl.exists():
        L = pd.read_csv(bl, index_col=0, parse_dates=True)["月營收驚奇多空（fv3 建構）"].dropna()
        lines += ["", "## 補充：月營收驚奇多空（市值前 500 檔，2019-03 ~ 2026-04）的波動率管理", "",
                  "| 策略 | 平均部位 | Sharpe 2019–2022 | 2023–2026/04 | 年化報酬 | 最大回撤 |", "|---|---|---|---|---|---|"]
        rows = {"多空（100%）": (L, 1.0)}
        for k in ("B 波動率管理（VIX）", "B′ 波動率管理（實際波動）"):
            e = R[k].reindex(L.index)
            rows[f"多空 × {k[:2]}"] = (run(e, L), float(e.mean()))
            rows[f"多空 × 固定 {e.mean():.0%}"] = (run(pd.Series(e.mean(), index=L.index), L), float(e.mean()))
        for k, (x, ea) in rows.items():
            a, b = summary(x[x.index < "2023-01-01"]), summary(x[x.index >= "2023-01-01"])
            s = summary(x)
            lines.append(f"| {k} | {ea:.0%} | {a['sharpe']:.2f} | {b['sharpe']:.2f} | {s['ann']:+.1%} | {s['mdd']:.1%} |")
    (ROOT / "docs" / "vix_timing.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
