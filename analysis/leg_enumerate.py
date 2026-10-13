"""本機枚舉「主腿 + 1–3 條稀釋腿」（參考使用者 WorldQuant 流程第 5 步）。

用法（於專案根目錄；輸入為 leg_probe.py 產生的 reports/legs/pnl_top{N}.csv）：
    .venv/Scripts/python analysis/leg_enumerate.py 300
輸出 docs/leg_enumerate_top{N}.md。

設計（看結果前固定）：
- 主腿 sue；稀釋腿為其他各腿，方向不翻轉（事先固定，避免依結果翻號）。
- 組合每日報酬 = Σ 權重 × 各腿每日純 alpha（訊號組合的近似；最後選出的組合需以合成訊號實際建倉驗證）。
- 權重：主腿 40 / 50 / 60 / 70%，其餘由稀釋腿平分。
- 篩選：2019–2022 與 2023–2026/04 的 Sharpe 都高於主腿單獨；逐年 Sharpe 最差一年 ≥ −0.5 且至少 6 年為正；與 0050 日報酬相關 |ρ| ≤ 0.3。
- 排序：兩段 Sharpe 的較小值。輸出前 15 組與總測試組數。
"""
import itertools
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SPLIT = pd.Timestamp("2023-01-01")
MAIN_WEIGHTS = (0.4, 0.5, 0.6, 0.7)


def sharpe(x: pd.Series) -> float:
    return float(x.mean() / x.std(ddof=1) * math.sqrt(252)) if len(x) > 20 and x.std(ddof=1) > 0 else float("nan")


def evaluate(series: pd.Series, bench: pd.Series | None) -> dict:
    yearly = series.groupby(series.index.year).apply(sharpe)
    return {"sh_oos": sharpe(series[series.index < SPLIT]), "sh_is": sharpe(series[series.index >= SPLIT]),
            "worst_year": float(yearly.min()), "pos_years": int((yearly > 0).sum()), "n_years": int(len(yearly)),
            "corr_0050": float(series.corr(bench)) if bench is not None else float("nan")}


def enumerate_combos(P: pd.DataFrame, main: str = "sue", bench: pd.Series | None = None) -> tuple[pd.DataFrame, dict]:
    legs = [c for c in P.columns if c != main]
    base = evaluate(P[main], bench)
    rows = []
    for k in (1, 2, 3):
        for combo in itertools.combinations(legs, k):
            for wm in MAIN_WEIGHTS:
                w = {main: wm, **{c: (1 - wm) / k for c in combo}}
                s = sum(P[c] * x for c, x in w.items())
                e = evaluate(s, bench)
                rows.append({"legs": " + ".join(combo), "w_main": wm, **e})
    df = pd.DataFrame(rows)
    ok = ((df["sh_oos"] > base["sh_oos"]) & (df["sh_is"] > base["sh_is"]) & (df["worst_year"] >= -0.5)
          & (df["pos_years"] >= 6) & (df["corr_0050"].abs().fillna(0) <= 0.3))
    df["passed"] = ok
    df["score"] = df[["sh_oos", "sh_is"]].min(axis=1)
    return df.sort_values(["passed", "score"], ascending=False), base


def main(top_n: int):
    P = pd.read_csv(ROOT / "reports" / "legs" / f"pnl_top{top_n}.csv", index_col=0, parse_dates=True).dropna(how="all")
    bench = None
    try:
        sys.path.insert(0, str(ROOT))
        from data.fetch_financials import FinMindClient, get_total_return_prices

        e = get_total_return_prices(FinMindClient(), "0050.TW", "2019-01-01", "2026-05-31").set_index("date")["adj_close"]
        bench = e.pct_change().reindex(P.index)
    except Exception:  # noqa: BLE001
        pass
    universe = P.pop("universe").fillna(0.0) if "universe" in P.columns else None
    lines = [f"# 本機枚舉：主腿 + 稀釋腿（全市場市值前 {top_n} 檔，自動產生）", "",
             "由 [analysis/leg_enumerate.py](../analysis/leg_enumerate.py) 產生。組合報酬 = 各腿每日純 alpha（產業中性做多 − β × 台指期，扣成本）的加權和；"
             "Sharpe 為年化（無風險利率 0）。篩選條件看結果前固定：兩段 Sharpe 都高於主腿單獨、最差一年 ≥ −0.5、至少 6 年為正、與 0050 日報酬相關 |ρ| ≤ 0.3。"]
    modes = [("純 alpha（原定指標）", P)]
    if universe is not None:
        modes.append(("超額（純 alpha 減股票池基準；看完第一版結果後加的診斷）", P.sub(universe, axis=0)))
    for title, X in modes:
        df, base = enumerate_combos(X.fillna(0.0), bench=bench)
        lines += ["", f"## {title}", "",
                  f"- 主腿 sue 單獨：Sharpe 2019–2022 {base['sh_oos']:.2f}、2023–2026/04 {base['sh_is']:.2f}；最差一年 {base['worst_year']:+.2f}；"
                  f"為正 {base['pos_years']}/{base['n_years']} 年",
                  f"- 共測試 {len(df)} 組（{len(X.columns) - 1} 條稀釋腿取 1–3 條 × 主腿權重 {len(MAIN_WEIGHTS)} 種）；通過篩選 {int(df['passed'].sum())} 組", "",
                  "| 稀釋腿 | 主腿權重 | Sharpe 2019–2022 | 2023–2026/04 | 最差一年 | 為正年數 | 與 0050 相關 | 通過 |", "|---|---|---|---|---|---|---|---|"]
        for r in df.head(15).itertuples():
            lines.append(f"| {r.legs} | {r.w_main:.0%} | {r.sh_oos:.2f} | {r.sh_is:.2f} | {r.worst_year:+.2f} | {r.pos_years}/{r.n_years} | "
                         f"{r.corr_0050:+.2f} | {'✓' if r.passed else '—'} |")
    (ROOT / "docs" / f"leg_enumerate_top{top_n}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main(int(sys.argv[1]))
