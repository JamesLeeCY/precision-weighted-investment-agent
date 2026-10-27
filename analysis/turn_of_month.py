"""I071 月底月初效應以台指期執行（點子卡 research/ideas/I071-turn-of-month-tx-futures.md，檢定計畫看結果前固定）。

用法（於專案根目錄；資料皆已快取）：
    .venv/Scripts/python analysis/turn_of_month.py
輸出 docs/turn_of_month.md。

設計（依點子卡；補充以「補」標示）：
- 交易日以加權報酬指數（TaiwanStockTotalReturnIndex）的日期為準；日序 −1 = 每月最後 1 個交易日，+1、+2、+3 = 次月前 3 個交易日。
- TOM 日 = 日序 −1 ~ +3（每月 4 個交易日）。
- T1：加權報酬指數日報酬 = a + b·TOM + e，Newey-West 落後 5；2007–2018 b 的 t ≥ 2.58；2019–2022、2023–2026/04 b 皆 > 0。
- T2：日序 −2 收盤買 1 倍名目台指期（近月連續，同 timing_futures.tx_returns）、日序 +3 收盤平倉，其餘空手；每次進出各扣 0.005% 單邊
  ＋ 1 點滑價（以前一日近月收盤價換算）；保證金閒置資金不計利息。對照：同平均曝險的固定持有台指期（每月轉倉 2 × 曝險 × 0.005%）。
  通過：2019–2022 與 2023–2026/04 兩段 TOM 的 Sharpe 都高於對照、且年化報酬差 > 0。
- T3（只報告）：fv5 + 0.5 倍名目 TOM 部位的 Sharpe；TOM 策略與 fv5 日報酬相關。
- 只報告：[−3, +3]、[−1, +1] 視窗的 T1 係數；日序 −5 ~ +5 逐日平均報酬；剔除大跌月份的版本（補：2008、2020、2022 年中
  加權報酬指數月報酬 ≤ −5% 的月份，剔除以該月最後交易日為日序 −1 的 TOM 視窗）；夜盤（2017-05 起）：補：台指期日盤收盤到收盤
  報酬已含夜盤期間的價格變動，以 2017-05 起 TOM 日的台指期與報酬指數平均報酬對照。
研究結果，非投資建議。
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "analysis"))
sys.path.insert(0, str(ROOT))
import timing_futures as tf  # noqa: E402
from data.fetch_financials import FinMindClient  # noqa: E402
from dividend_reinvest import ols_nw  # noqa: E402

SEGS = (("2007–2018", "2007-01-01", "2019-01-01"), ("2019–2022", "2019-01-01", "2023-01-01"), ("2023–2026/04", "2023-01-01", "2026-05-01"))
COST = 0.00005


def day_offset(days: pd.DatetimeIndex) -> pd.Series:
    """每個交易日相對月界的日序：月底前為 −1, −2, …；月初起為 +1, +2, …（取絕對值較小者，月中兩者相等時取負）。"""
    s = pd.Series(days, index=days)
    per = days.to_period("M")
    fwd = s.groupby(per).cumcount() + 1
    back = -(s.groupby(per).cumcount(ascending=False) + 1)
    return pd.Series(np.where(fwd.to_numpy() < -back.to_numpy(), fwd, back), index=days)


def front_close(client) -> pd.Series:
    parts = [client.get("TaiwanFuturesDaily", "TX", f"{y}-01-01", f"{y}-12-31") for y in range(2007, 2027)]
    d = pd.concat([p for p in parts if not p.empty])
    d = d[(d["trading_session"] == "position") & d["contract_date"].astype(str).str.fullmatch(r"\d{6}") & (d["close"].astype(float) > 0)].copy()
    d["date"] = pd.to_datetime(d["date"])
    d["close"] = d["close"].astype(float)
    return d.sort_values(["date", "volume"]).groupby("date").tail(1).set_index("date")["close"]


def sharpe(x):
    x = x.dropna()
    return float(x.mean() / x.std() * np.sqrt(252)) if x.std() > 0 else float("nan")


def seg(x, a, b):
    return x[(x.index >= a) & (x.index < b)]


def main():
    import dotenv

    dotenv.load_dotenv(ROOT / ".env")
    client = FinMindClient()
    tri = client.get("TaiwanStockTotalReturnIndex", "TAIEX", "2006-06-01", "2026-05-31")
    lvl = pd.Series(tri["price"].astype(float).to_numpy(), index=pd.to_datetime(tri["date"])).sort_index()
    r = lvl.pct_change()
    days = lvl.index
    off = day_offset(days)
    tom = off.between(-1, 3) & (off != 0)
    rtx = tf.tx_returns(client).reindex(days)
    fc = front_close(client).reindex(days).ffill()

    def reg(lo, hi, a, b):
        flag = (off >= lo) & (off <= hi) & (off != 0)
        df = pd.DataFrame({"r": r, "f": flag.astype(float)}).dropna()
        df = seg(df, a, b)
        X = np.column_stack([np.ones(len(df)), df["f"].to_numpy()])
        bb, se = ols_nw(df["r"].to_numpy(float), X, 5)
        return float(bb[1]), float(bb[1] / se[1]), int(df["f"].sum())
    t1 = {nm: reg(-1, 3, a, b) for nm, a, b in SEGS}
    k1 = t1["2007–2018"][1] >= 2.58 and t1["2019–2022"][0] > 0 and t1["2023–2026/04"][0] > 0
    alt = {f"[{lo:+d}, {hi:+d}]": {nm: reg(lo, hi, a, b) for nm, a, b in SEGS} for lo, hi in ((-3, 3), (-1, 1))}
    # T2
    slip = 1.0 / fc.shift(1)
    strat = tom.astype(float) * rtx.fillna(0.0)  # 進場於日序 −2 收盤：持有日序 −1 ~ +3 的報酬
    cost = pd.Series(0.0, index=days)
    first_tom = tom & ~tom.shift(1, fill_value=False)
    last_tom = tom & ~tom.shift(-1, fill_value=False)
    cost[first_tom] += COST + slip[first_tom].fillna(0.0)
    cost[last_tom] += COST + slip[last_tom].fillna(0.0)
    strat = strat - cost
    strat = strat[strat.index >= "2007-01-01"]
    expo = float(tom[(days >= "2007-01-01") & (days < "2026-05-01")].mean())
    roll = tf.roll_days(days).astype(float)
    const = expo * rtx.fillna(0.0) - roll * 2 * expo * COST
    t2 = {}
    for nm, a, b in SEGS:
        s, c_ = seg(strat, a, b), seg(const, a, b)
        t2[nm] = (sharpe(s), float(s.mean() * 252), sharpe(c_), float(c_.mean() * 252), int(seg(first_tom, a, b).sum()))
    k2 = all(t2[nm][0] > t2[nm][2] and t2[nm][1] - t2[nm][3] > 0 for nm in ("2019–2022", "2023–2026/04"))
    # 只報告
    by_off = {k: [float(seg(r[off == k], a, b).mean()) for _, a, b in SEGS] for k in list(range(-5, 0)) + list(range(1, 6))}
    mret = (1 + r).groupby(days.to_period("M")).prod() - 1
    bad = mret[(mret.index.year.isin([2008, 2020, 2022])) & (mret <= -0.05)].index
    # TOM 視窗以日序 −1 所在月份歸屬
    win_month = pd.Series(days.to_period("M"), index=days)
    win_month[off > 0] = (days[off > 0].to_period("M") - 1)
    keep = ~win_month.isin(bad)
    ex = {}
    for nm, a, b in SEGS:
        df = pd.DataFrame({"r": r, "f": tom.astype(float)})[keep].dropna()
        df = seg(df, a, b)
        X = np.column_stack([np.ones(len(df)), df["f"].to_numpy()])
        bb, se = ols_nw(df["r"].to_numpy(float), X, 5)
        ex[nm] = (float(bb[1]), float(bb[1] / se[1]))
    ng = (days >= "2017-05-15") & (days < "2026-05-01")
    night = (float(rtx[tom & ng].mean()), float(r[tom & ng].mean()), float(rtx[~tom & ng].mean()), float(r[~tom & ng].mean()))
    # T3
    import fv5_family as ff
    R5, sched = ff.run_backtests()
    fv5 = R5["fv5"]
    fv5 = fv5[fv5.index > sched[2]]
    comb = fv5 + 0.5 * strat.reindex(fv5.index).fillna(0.0)
    t3 = {nm: (sharpe(seg(fv5, a, b)), sharpe(seg(comb, a, b))) for nm, a, b in SEGS[1:]}
    t3["全期"] = (sharpe(fv5), sharpe(comb))
    corr = float(pd.concat([fv5, strat.reindex(fv5.index)], axis=1).dropna().corr().iloc[0, 1])
    L = ["# I071 月底月初效應以台指期執行（自動產生）", "",
         "由 [analysis/turn_of_month.py](../analysis/turn_of_month.py) 產生；設計見程式開頭（看結果前固定）。"
         "TOM 日 = 每月最後 1 個交易日到次月第 3 個交易日；b = TOM 日相對其他日的加權報酬指數日報酬差，括號為（Newey-West t，TOM 日數）。"
         "Sharpe 為日報酬年化，空手日報酬為 0。研究結果，非投資建議。", "",
         "## T1 統計", "", "| 期間 | b（t，日數） | 只報告：[−3, +3] | 只報告：[−1, +1] | 只報告：剔除大跌月份 |", "|---|---|---|---|---|"]
    for nm, _, _ in SEGS:
        v = t1[nm]
        L.append(f"| {nm} | {v[0]:+.3%}（{v[1]:.2f}，{v[2]}） | " + " | ".join(f"{alt[k][nm][0]:+.3%}（{alt[k][nm][1]:.2f}）" for k in alt)
                 + f" | {ex[nm][0]:+.3%}（{ex[nm][1]:.2f}） |")
    L += ["", f"剔除的大跌月份（2008、2020、2022 年月報酬 ≤ −5%）：{'、'.join(str(p) for p in bad)}。", "",
          "只報告：日序 −5 ~ +5 的平均日報酬（2007–2018 / 2019–2022 / 2023–2026/04）：", "",
          "| 日序 | " + " | ".join(str(k) for k in by_off) + " |", "|---|" + "---|" * len(by_off)]
    for i, (nm, _, _) in enumerate(SEGS):
        L.append(f"| {nm} | " + " | ".join(f"{v[i]:+.2%}" for v in by_off.values()) + " |")
    L += ["", "## T2 可交易（台指期，扣 0.005% 單邊與 1 點滑價）", "",
          f"對照為固定持有 {expo:.1%} 名目台指期（與 TOM 策略平均曝險相同）。", "",
          "| 期間 | TOM Sharpe | TOM 年化報酬 | 對照 Sharpe | 對照年化報酬 | 交易次數 |", "|---|---|---|---|---|---|"]
    for nm, v in t2.items():
        L.append(f"| {nm} | {v[0]:.2f} | {v[1]:+.2%} | {v[2]:.2f} | {v[3]:+.2%} | {v[4]} |")
    L += ["", "## T3 與 fv5 組合（只報告）", "",
          f"TOM 策略與 fv5 日淨報酬相關 {corr:+.2f}。", "", "| 期間 | fv5 Sharpe | fv5 + 0.5 倍 TOM Sharpe |", "|---|---|---|"]
    L += [f"| {k} | {v[0]:.2f} | {v[1]:.2f} |" for k, v in t3.items()]
    L += ["", f"只報告（夜盤，2017-05 起）：TOM 日平均報酬 台指期 {night[0]:+.3%}、報酬指數 {night[1]:+.3%}；非 TOM 日 台指期 {night[2]:+.3%}、報酬指數 {night[3]:+.3%}。", "",
          "## 判定", "",
          f"- T1：2007–2018 t ≥ 2.58 且兩段報告期 b > 0（t {t1['2007–2018'][1]:.2f}；{t1['2019–2022'][0]:+.3%} / {t1['2023–2026/04'][0]:+.3%}）→ {'✓' if k1 else '✗'}",
          f"- T2：兩段報告期 Sharpe 高於對照且年化報酬差 > 0 → {'✓' if k2 else '✗'}", "",
          f"**結論：{'通過' if k1 and k2 else '未通過'}**"]
    (ROOT / "docs" / "turn_of_month.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
