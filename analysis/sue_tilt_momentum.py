"""檢驗「依兩日漲幅加碼」是不是就是動能。

用法（於專案根目錄）：
    .venv/Scripts/python analysis/sue_tilt_momentum.py 300
輸出 docs/sue_tilt_momentum_top{N}.md 與 reports/legs/sue_tilt_momentum_top{N}.csv。

設計（看結果前固定）：
- 引擎同 docs/sue_breakout_decompose_report.md：月營收驚奇產業內前 1/3 可買、每隔 2 日加碼 5%（1%–10%）、
  單檔買進後 ≤ 20%、總持股 ≤ 100%、只在掉出前 1/3 時賣出、扣成本；不做成交金額加權。
- 只換加碼的傾斜倍數；為了可比，所有傾斜都用同一個對應：倍數 = 0.25 + 2.25 × 當日在可買名單內的百分位排名（0.25–2.5 倍）。
  傾斜：兩日報酬、1 個月（21 日）報酬、3 個月（63 日）報酬、12-1 動能（252 日前到 21 日前）；
  另列原版的兩日漲幅比值（兩日漲幅 ÷ 4%，0.25–2.5）與不加權。
- 檢定：
  1) 各版本 Sharpe（2019–2022 / 2023–2026/04）、相對不加權的年化報酬差與 t 值；
  2) 涵蓋迴歸：兩日報酬傾斜的超額（減不加權）對各動能傾斜的超額迴歸，截距（年化）與 t 值——截距消失表示兩日報酬傾斜就是動能；
  3) 可買名單內兩日報酬與各動能的橫斷面 Spearman 相關（每日平均）。
- 看完第一版結果後加的診斷（標示「診斷」）：原版比值拆成只留同日橫斷面（減當日可買名單中位數）、
  只留整體行情（當日中位數，全體同倍數），以及 60 日波動度排名。
"""
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "analysis"))
import leg_probe as lp  # noqa: E402
import sue_breakout as sb  # noqa: E402

SPLIT = lp.SPLIT


def rank_tilt(x: pd.DataFrame, elig: pd.DataFrame) -> pd.DataFrame:
    return 0.25 + 2.25 * x.where(elig).rank(axis=1, pct=True)


def diff_stats(a: pd.Series, b: pd.Series) -> dict:
    d = (a - b).dropna()
    out = {}
    for seg, x in (("oos", d[d.index < SPLIT]), ("is", d[d.index >= SPLIT]), ("all", d)):
        out[seg] = (x.mean() * 252, x.mean() / (x.std() / math.sqrt(len(x))))
    return out


def spanning(y: pd.Series, x: pd.Series) -> tuple[float, float, float]:
    df = pd.concat([y, x], axis=1).dropna()
    X = np.column_stack([np.ones(len(df)), df.iloc[:, 1].to_numpy()])
    coef, *_ = np.linalg.lstsq(X, df.iloc[:, 0].to_numpy(), rcond=None)
    res = df.iloc[:, 0].to_numpy() - X @ coef
    cov = res.var(ddof=2) * np.linalg.inv(X.T @ X)
    return coef[0] * 252, coef[0] / math.sqrt(cov[0, 0]), coef[1]


def main(top_n: int):
    c = lp.prepare(top_n)
    scores = lp.leg_scores(c, "sue")
    elig = sb.eligibility(c, scores) & c.member
    rets = c.rets.where(c.adj.notna())
    adv = c.money.reindex(index=c.adj.index).rolling(20, min_periods=10).mean()
    below = c.adj < c.adj.rolling(sb.MA, min_periods=sb.MA).mean()
    start, end = c.schedule[0], lp.HOLDOUT - pd.Timedelta(days=1)

    adj = c.adj
    measures = {
        "兩日報酬": adj / adj.shift(2) - 1,
        "1 個月報酬": adj / adj.shift(21) - 1,
        "3 個月報酬": adj / adj.shift(63) - 1,
        "12-1 動能": adj.shift(21) / adj.shift(252) - 1,
    }
    tilts = {f"{k}（排名）": rank_tilt(v, elig) for k, v in measures.items()}
    runs = {"不加權": dict(gain_tilt=False), "兩日漲幅比值（原版）": dict(gain_tilt=True)}
    runs.update({k: dict(gain_tilt=False, tilt=v) for k, v in tilts.items()})
    runs["兩日報酬 + 3 個月報酬（排名平均）"] = dict(gain_tilt=False, tilt=(tilts["兩日報酬（排名）"] + tilts["3 個月報酬（排名）"]) / 2)
    # 看完上面結果後加的診斷：原版比值的效果來自「同日橫斷面」、「整體行情」還是「波動度」？
    g2 = measures["兩日報酬"]
    med = g2.where(elig).median(axis=1)
    post = {
        "診斷：比值只留橫斷面（減當日中位數）": (1 + g2.sub(med, axis=0) / sb.G_REF).clip(0.25, 2.5),
        "診斷：比值只留整體行情（當日中位數，全體相同）": pd.DataFrame(np.repeat((med / sb.G_REF).clip(0.25, 2.5).to_numpy()[:, None], len(g2.columns), axis=1),
                                                       index=g2.index, columns=g2.columns),
        "診斷：60 日波動度（排名）": rank_tilt(c.rets.rolling(60, min_periods=40).std(), elig),
    }
    runs.update({k: dict(gain_tilt=False, tilt=v) for k, v in post.items()})

    series, rows = {}, []
    for name, kw in runs.items():
        df, _ = sb.backtest(rets, elig, adv, below, start, end, tech_exit=False, betas=c.betas,
                            timing="any", adv_tilt=False, **kw)
        series[name] = df["ret"]
        s = sb.summarize(df["ret"])
        rows.append((name, s, df["ret"].std() * math.sqrt(252)))
        print(f"  {name}: {s['sh_oos']:.2f} / {s['sh_is']:.2f}", flush=True)
    pd.DataFrame(series).to_csv(ROOT / "reports" / "legs" / f"sue_tilt_momentum_top{top_n}.csv")

    base = series["不加權"]
    ex = {k: v - base for k, v in series.items() if k != "不加權"}
    corr = {}
    for k in ("1 個月報酬", "3 個月報酬", "12-1 動能"):
        a, b = measures["兩日報酬"].where(elig).loc[start:end], measures[k].where(elig).loc[start:end]
        corr[k] = float(a.rank(axis=1).corrwith(b.rank(axis=1), axis=1).mean())

    lines = [f"# 依兩日漲幅加碼是不是動能？（全市場市值前 {top_n} 檔，自動產生）", "",
             "由 [analysis/sue_tilt_momentum.py](../analysis/sue_tilt_momentum.py) 產生；設計見程式開頭。"
             "Sharpe 為年化（無風險利率 0），兩段為 2019–2022 / 2023–2026/04；報酬差 = 相對「不加權」的年化每日報酬差，括號為 t 值；已扣成本。", "",
             "| 傾斜 | Sharpe 2019–2022 | 2023–2026/04 | 年化波動 | 報酬差 2019–2022 | 2023–2026/04 | 全期 |", "|---|---|---|---|---|---|---|"]
    for name, s, vol in rows:
        if name == "不加權":
            lines.append(f"| {name} | {s['sh_oos']:.2f} | {s['sh_is']:.2f} | {vol:.1%} | — | — | — |")
            continue
        dsm = diff_stats(series[name], base)
        lines.append(f"| {name} | {s['sh_oos']:.2f} | {s['sh_is']:.2f} | {vol:.1%} | "
                     + " | ".join(f"{dsm[g][0]:+.1%}（{dsm[g][1]:+.1f}）" for g in ("oos", "is", "all")) + " |")
    lines += ["", "## 涵蓋迴歸：兩日報酬傾斜的超額 = α + b × 動能傾斜的超額", "",
              "| 控制的動能傾斜 | α（年化） | α 的 t | b | 兩日報酬與該動能的橫斷面相關 |", "|---|---|---|---|---|"]
    y = ex["兩日報酬（排名）"]
    for k in ("1 個月報酬", "3 個月報酬", "12-1 動能"):
        a, t, b = spanning(y, ex[f"{k}（排名）"])
        lines.append(f"| {k} | {a:+.1%} | {t:+.1f} | {b:+.2f} | {corr[k]:+.2f} |")
    yd = y.dropna()
    lines.append(f"| （不控制） | {yd.mean() * 252:+.1%} | {yd.mean() / (yd.std() / math.sqrt(len(yd))):+.1f} | — | — |")
    (ROOT / "docs" / f"sue_tilt_momentum_top{top_n}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print("DONE", flush=True)


if __name__ == "__main__":
    main(int(sys.argv[1]))
