"""拆解「月營收驚奇 + 兩日連漲進場」（不做技術面出場）的超額來源。

用法（於專案根目錄）：
    .venv/Scripts/python analysis/sue_breakout_decompose.py 300
輸出 docs/sue_breakout_decompose_top{N}.md 與 reports/legs/sue_breakout_decompose_top{N}.csv。

設計（看結果前固定）：
- 起點：docs/sue_breakout_report.md 中勝出的版本——兩日連漲進場、依兩日漲幅 × 成交金額加碼、單檔買進後 ≤ 20%，
  只在月營收驚奇掉出產業內前 1/3 時賣出。
- 三個因素各開／關，共 2 × 2 × 2 = 8 個版本：
  時點（兩日連漲才加碼 / 可買期間每隔 2 日就加碼）、成交金額加權（有 / 無）、漲幅加權（有 / 無）。
  其他規則（每次 5% 基本單位、1%–10%、單檔 20%、總持股 100%、賣出條件、成本）都相同。
- 對照：月營收驚奇月換倉（產業內前 1/3 等權）、0050 買進持有。
- 主效果 = 該因素「開」的 4 個版本平均 Sharpe − 「關」的 4 個版本平均（兩段各算）。
- 另記錄平均持股檔數與持股的市值百分位（股票池內，1 = 最大），檢查是否只是偏向大型股。
"""
import itertools
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "analysis"))
import leg_probe as lp  # noqa: E402
import sue_breakout as sb  # noqa: E402

FACTORS = [("timing", ("breakout", "any")), ("adv_tilt", (True, False)), ("gain_tilt", (True, False))]
LABEL = {("timing", "breakout"): "兩日連漲", ("timing", "any"): "每隔 2 日",
         ("adv_tilt", True): "成交金額加權", ("adv_tilt", False): "—", ("gain_tilt", True): "漲幅加權", ("gain_tilt", False): "—"}


def main(top_n: int):
    c = lp.prepare(top_n)
    scores = lp.leg_scores(c, "sue")
    elig = sb.eligibility(c, scores) & c.member
    rets = c.rets.where(c.adj.notna())
    adv = c.money.reindex(index=c.adj.index).rolling(20, min_periods=10).mean()
    below = c.adj < c.adj.rolling(sb.MA, min_periods=sb.MA).mean()
    size_pct = np.exp(c.logcap).where(c.member).rank(axis=1, pct=True)
    start, end = c.schedule[0], lp.HOLDOUT - pd.Timedelta(days=1)

    rows, series = [], {}
    for combo in itertools.product(*[v for _, v in FACTORS]):
        kw = dict(zip([k for k, _ in FACTORS], combo))
        df, _ = sb.backtest(rets, elig, adv, below, start, end, tech_exit=False, betas=c.betas, size_pct=size_pct, **kw)
        s = sb.summarize(df["ret"])
        name = " + ".join(LABEL[(k, v)] for k, v in kw.items() if LABEL[(k, v)] != "—") or "每隔 2 日（無加權）"
        yrs = len(df) / 252
        rows.append({**kw, "name": name, **{k: s[k] for k in ("sh_oos", "sh_is", "ann_oos", "ann_is", "mdd")},
                     "yearly": s["yearly"], "turnover": df["turnover"].sum() / yrs, "exposure": df["exposure"].mean(),
                     "n_hold": df["n_hold"].mean(), "size": df["size"].mean()})
        series[name] = df["ret"]
        print(f"  {name}: {s['sh_oos']:.2f} / {s['sh_is']:.2f}", flush=True)

    monthly = sb.hold_monthly(rets, elig, start, end)
    from data.fetch_financials import get_total_return_prices
    e = get_total_return_prices(c.client, "0050.TW", "2018-06-01", "2026-05-31").set_index("date")["adj_close"]
    r0050 = e.pct_change().reindex(monthly.index)
    series["月營收驚奇月換倉"], series["0050"] = monthly, r0050
    pd.DataFrame(series).to_csv(ROOT / "reports" / "legs" / f"sue_breakout_decompose_top{top_n}.csv")

    R = pd.DataFrame(rows)
    effects = []
    for k, (on, off) in FACTORS:
        effects.append((k, on, off,
                        R.loc[R[k] == on, "sh_oos"].mean() - R.loc[R[k] == off, "sh_oos"].mean(),
                        R.loc[R[k] == on, "sh_is"].mean() - R.loc[R[k] == off, "sh_is"].mean()))
    el = elig.loc[start:end]
    m_n = float(el.sum(axis=1).clip(lower=1).mean())
    m_size = float(size_pct.where(el).loc[start:end].mean(axis=1).mean())

    lines = [f"# 拆解「月營收驚奇 + 兩日連漲進場」的超額來源（全市場市值前 {top_n} 檔，自動產生）", "",
             "由 [analysis/sue_breakout_decompose.py](../analysis/sue_breakout_decompose.py) 產生；設計見程式開頭。"
             "所有版本只在月營收驚奇掉出產業內前 1/3 時賣出（不做技術面出場）。Sharpe 為年化（無風險利率 0），"
             "兩段為 2019–2022 / 2023–2026/04；已扣成本。持股市值百分位：股票池內依市值排序，1 = 最大、0.5 = 中位數。", "",
             "| 版本 | Sharpe 2019–2022 | 2023–2026/04 | 年化報酬 2019–2022 | 2023–2026/04 | 最大回撤 | 年換手（倍） | 平均持股檔數 | 持股市值百分位 |",
             "|---|---|---|---|---|---|---|---|---|"]
    for r in sorted(rows, key=lambda r: -min(r["sh_oos"], r["sh_is"])):
        lines.append(f"| {r['name']} | {r['sh_oos']:.2f} | {r['sh_is']:.2f} | {r['ann_oos']:+.1%} | {r['ann_is']:+.1%} | {r['mdd']:.1%} | "
                     f"{r['turnover']:.1f} | {r['n_hold']:.0f} | {r['size']:.2f} |")
    sm, s0 = sb.summarize(monthly), sb.summarize(r0050)
    lines.append(f"| 對照：月營收驚奇月換倉（等權） | {sm['sh_oos']:.2f} | {sm['sh_is']:.2f} | {sm['ann_oos']:+.1%} | {sm['ann_is']:+.1%} | "
                 f"{sm['mdd']:.1%} | — | {m_n:.0f} | {m_size:.2f} |")
    lines.append(f"| 對照：0050 買進持有 | {s0['sh_oos']:.2f} | {s0['sh_is']:.2f} | {s0['ann_oos']:+.1%} | {s0['ann_is']:+.1%} | {s0['mdd']:.1%} | 0 | — | — |")
    lines += ["", "## 主效果（該因素開的 4 個版本平均 Sharpe − 關的 4 個版本平均）", "",
              "| 因素 | 2019–2022 | 2023–2026/04 |", "|---|---|---|"]
    names = {"timing": "時點：兩日連漲（vs 每隔 2 日）", "adv_tilt": "成交金額加權（vs 無）", "gain_tilt": "漲幅加權（vs 無）"}
    for k, on, off, eo, ei in effects:
        lines.append(f"| {names[k]} | {eo:+.2f} | {ei:+.2f} |")
    lines += ["", "## 逐年 Sharpe", "", "| 版本 | " + " | ".join(str(y) for y in rows[0]["yearly"]) + " |",
              "|---|" + "---|" * len(rows[0]["yearly"])]
    for r in rows:
        lines.append(f"| {r['name']} | " + " | ".join(f"{v:+.1f}" for v in r["yearly"].values()) + " |")
    (ROOT / "docs" / f"sue_breakout_decompose_top{top_n}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print("DONE", flush=True)


if __name__ == "__main__":
    main(int(sys.argv[1]))
