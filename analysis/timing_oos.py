"""0050 擇時規則的樣本內／樣本外驗證（2003 年起的含息 0050）。

用法（於專案根目錄）：
    .venv/Scripts/python analysis/timing_oos.py
輸出 docs/timing_oos.md 與 reports/timing_oos.csv。

設計（看結果前固定）：
- 資料：0050 含息還原價 2003-06-30 ~ 2026-04-30（FinMind，約 3 次呼叫）。
- 候選：買進持有；均線 n ∈ {60, 100, 120, 150, 200, 250} × 緩衝帶 b ∈ {0, 1, 2, 3%}（價格高於均線 ×(1+b) 才轉為持有、
  低於均線 ×(1−b) 才轉為空手，b = 0 即一般均線規則）；雙均線（50 日 > 200 日）。共 26 種。
- 時點與成本同 analysis/allocation_study.timing_series：以第 t−1 日收盤判斷、持有 t → t+1，切換一次扣單邊成本 COST；空手報酬 0。
- 方法 A（單一切割）：2004–2015 依 Sharpe 選最佳規則，看它在 2016 ~ 2026/04 的 Sharpe 與排名。
- 方法 B（滾動前進）：2009 年起每年 1 月，用 2004 年至前一年底的資料選 Sharpe 最佳規則，持有一整年；
  接起來的 2009 ~ 2026/04 報酬即為樣本外結果，與買進持有、固定「200 日 ±2%」比較。
- 額外：原研究在 2019–2026 選出的「200 日 ±2%」在 2004–2018（挑選時未使用）的表現。
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

WINDOWS = (60, 100, 120, 150, 200, 250)
BANDS = (0.0, 0.01, 0.02, 0.03)


def positions(adj: pd.Series, rule: tuple) -> pd.Series:
    """rule = ("bh",) / ("dual",) / ("ma", n, b)；回傳以前一日收盤決定的持有比例（同 allocation_study.timing_positions）。"""
    if rule[0] == "bh":
        return pd.Series(1.0, index=adj.index).shift(1)
    if rule[0] == "dual":
        m50, m200 = adj.rolling(50, min_periods=50).mean(), adj.rolling(200, min_periods=200).mean()
        return (m50 > m200).astype(float).where(m200.notna()).shift(1)
    _, n, b = rule
    ma = adj.rolling(n, min_periods=n).mean()
    vals, pos = [], np.nan
    for p, m in zip(adj.to_numpy(), ma.to_numpy()):
        if np.isnan(m):
            vals.append(np.nan)
            continue
        if np.isnan(pos):
            pos = 1.0 if p > m else 0.0
        elif pos == 0 and p > m * (1 + b):
            pos = 1.0
        elif pos == 1 and p < m * (1 - b):
            pos = 0.0
        vals.append(pos)
    return pd.Series(vals, index=adj.index).shift(1)


def net_returns(adj: pd.Series, rule: tuple) -> pd.Series:
    """同 timing_series 的淨報酬，索引放在實現日（t+1）。"""
    pos = positions(adj, rule).fillna(0.0)
    nxt = adj.pct_change().shift(-1).fillna(0.0)
    to = pos.diff().abs().fillna(pos.abs())
    net = pos * nxt - to * al.COST
    out = pd.Series(net.to_numpy()[:-1], index=adj.index[1:])
    return out


def sharpe(x: pd.Series) -> float:
    x = x.dropna()
    return float(x.mean() / x.std() * math.sqrt(252)) if len(x) > 20 and x.std() > 0 else float("nan")


def summary(x: pd.Series) -> dict:
    x = x.dropna()
    eq = (1 + x).cumprod()
    return {"sharpe": sharpe(x), "ann": float(eq.iloc[-1] ** (252 / len(x)) - 1), "mdd": float((eq / eq.cummax() - 1).min())}


def name(rule: tuple) -> str:
    if rule[0] == "bh":
        return "買進持有"
    if rule[0] == "dual":
        return "雙均線 50 > 200"
    return f"{rule[1]} 日線" + (f" ±{rule[2]:.0%}" if rule[2] else "")


def main():
    import dotenv

    dotenv.load_dotenv(ROOT / ".env")
    px = get_total_return_prices(FinMindClient(), "0050.TW", "2003-06-30", "2026-05-31")
    adj = px.set_index("date")["adj_close"].astype(float)
    adj = adj[adj.index <= pd.Timestamp("2026-04-30")]
    rules = [("bh",), ("dual",)] + [("ma", n, b) for n in WINDOWS for b in BANDS]
    R = pd.DataFrame({name(r): net_returns(adj, r) for r in rules})
    R = R[R.index >= pd.Timestamp("2004-01-01")]
    R.to_csv(ROOT / "reports" / "timing_oos.csv")

    # 方法 A
    is_, oos = R[R.index < "2016-01-01"], R[R.index >= "2016-01-01"]
    s_is = is_.apply(sharpe).sort_values(ascending=False)
    s_oos = oos.apply(sharpe)
    best = s_is.index[0]
    rank_oos = int(s_oos.rank(ascending=False)[best])

    # 方法 B
    wf, picks = [], []
    for y in range(2009, 2027):
        hist = R[R.index < f"{y}-01-01"]
        pick = hist.apply(sharpe).idxmax()
        seg = R.loc[(R.index >= f"{y}-01-01") & (R.index < f"{y + 1}-01-01"), pick]
        wf.append(seg)
        picks.append((y, pick))
    wf = pd.concat(wf)
    comp = pd.DataFrame({"滾動前進選規則": wf, "買進持有": R["買進持有"].reindex(wf.index),
                         "固定 200 日 ±2%": R["200 日線 ±2%"].reindex(wf.index)})
    d = (comp["滾動前進選規則"] - comp["買進持有"]).dropna()
    t_wf = d.mean() / (d.std() / math.sqrt(len(d)))

    pre = R[(R.index >= "2004-01-01") & (R.index < "2019-01-01")]
    post = R[R.index >= "2019-01-01"]

    lines = ["# 0050 擇時規則的樣本內／樣本外驗證（自動產生）", "",
             "由 [analysis/timing_oos.py](../analysis/timing_oos.py) 產生；設計見程式開頭。Sharpe = 年化報酬 ÷ 年化波動（無風險利率 0，空手報酬 0），已扣切換成本。研究結果，非投資建議。", "",
             "## 方法 A：2004–2015 選規則，2016 ~ 2026/04 驗證", "",
             f"共 {len(rules)} 種候選。樣本內最佳：**{best}**（樣本內 Sharpe {s_is[best]:.2f}）→ 樣本外 Sharpe {s_oos[best]:.2f}，"
             f"在 {len(rules)} 種中排第 {rank_oos}；買進持有樣本外 {s_oos['買進持有']:.2f}。", "",
             "| 規則 | 樣本內 2004–2015 | 樣本外 2016–2026/04 |", "|---|---|---|"]
    for k in list(dict.fromkeys(list(s_is.index[:5]) + ["200 日線 ±2%", "200 日線", "買進持有"])):
        lines.append(f"| {k}{'（樣本內前 5）' if k in s_is.index[:5] else ''} | {s_is[k]:.2f} | {s_oos[k]:.2f} |")
    lines += ["", f"樣本內與樣本外 Sharpe 的排名相關（{len(rules)} 種規則）：{s_is.rank().corr(s_oos.rank()):+.2f}。", "",
              "## 方法 B：滾動前進（每年 1 月用過去全部資料選規則，持有一年）", "",
              "| 策略（2009 ~ 2026/04） | Sharpe | 年化報酬 | 最大回撤 |", "|---|---|---|---|"]
    for k in comp.columns:
        s = summary(comp[k])
        lines.append(f"| {k} | {s['sharpe']:.2f} | {s['ann']:+.1%} | {s['mdd']:.1%} |")
    lines += ["", f"滾動前進相對買進持有：年化 {d.mean() * 252:+.1%}（t {t_wf:+.2f}）。", "",
              "每年選到的規則：" + "、".join(f"{y} {p}" for y, p in picks), "",
              "## 原研究選出的「200 日 ±2%」在挑選時未使用的 2004–2018", "",
              "| 規則 | 2004–2018（挑選時未用） | 2019 ~ 2026/04（挑選時用過） |", "|---|---|---|"]
    for k in ("200 日線 ±2%", "200 日線", "120 日線", "買進持有"):
        a, b = summary(pre[k]), summary(post[k])
        lines.append(f"| {k} | Sharpe {a['sharpe']:.2f}、年化 {a['ann']:+.1%}、回撤 {a['mdd']:.1%} | Sharpe {b['sharpe']:.2f}、年化 {b['ann']:+.1%}、回撤 {b['mdd']:.1%} |")
    (ROOT / "docs" / "timing_oos.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
