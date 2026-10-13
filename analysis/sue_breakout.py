"""月營收驚奇 + 兩日連漲進場、連跌出場（使用者 2026-10-13 提出的技術面進出場規則）。

用法（於專案根目錄；資料同 leg_probe.py）：
    .venv/Scripts/python analysis/sue_breakout.py 300
輸出 docs/sue_breakout_top{N}.md 與 reports/legs/sue_breakout_top{N}.csv（每日報酬）。

規則（使用者決定；細節看結果前固定）：
- 股票池：每年市值前 N 名（config/universe_mcap_membership.csv）。
- 基本面轉好：最近一次月營收公告期限後，月營收驚奇（SUE，對產業與 log 市值中性化）在產業內前 1/3；
  每月公告期限後的下一個交易日更新，持續到下次更新。
- 買進：可買股票在第 t 日收盤出現「連續兩日上漲」（含息報酬 r_t > 0 且 r_{t−1} > 0），於 t+1 日收盤買進。
  每次加碼金額 = 總資產 × 5% × clip(兩日漲幅 / 4%, 0.25, 2.5) × clip(20 日平均成交金額 / 股票池中位數, 0.5, 2)，
  再限制在 1%～10% 之間（漲愈多、成交金額愈大買愈多）。之後每出現新的兩日連漲（與上次加碼至少隔 2 日）再加碼。
- 上限：單一個股買進後 ≤ 總資產 20%（之後隨股價上漲可略超過，不強制減碼）；總持股 ≤ 100%（現金不足時當日加碼等比例縮小）；現金報酬以 0 計。
- 賣出：持股連續兩日下跌且收盤跌破 20 日均線 → 隔日收盤賣出一半；連續三日下跌 → 隔日收盤全部賣出。
  基本面不再符合時不強制賣出（只依技術面出場）。
- 成本：每筆成交金額 × 單邊 0.29625%。2026-05 之後保留給前瞻驗證。
- 對照：0050 買進持有；月營收驚奇月換倉（產業內前 1/3 等權、單檔 ≤ 20%，不做技術面）；
  同一套買進規則但不做技術面出場（只在基本面不再符合時賣出）。
- 指標：年化 Sharpe（2019–2022 / 2023–2026/04）、年化報酬、最大回撤、平均持股水位、年換手、交易次數與勝率；
  另算 β 對沖版（每日 − Σw·β × 台指期）供主要指標參考。
"""
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "analysis"))
import leg_probe as lp  # noqa: E402

UNIT, G_REF = 0.05, 0.04
ADD_MIN, ADD_MAX, STOCK_MAX = 0.01, 0.10, 0.20
MA = 20


def eligibility(c, scores: dict) -> pd.DataFrame:
    """每日可買名單：換倉日的 SUE 在產業內前 1/3，延續到下一個換倉日（換倉日當天收盤即可用）。"""
    E = pd.DataFrame(False, index=c.adj.index, columns=c.tickers)
    sched = c.schedule
    for k, d in enumerate(sched):
        nxt = sched[k + 1] if k + 1 < len(sched) else lp.HOLDOUT
        top = list(lp.select(scores[d], c.sector).keys())
        E.loc[(E.index >= d) & (E.index < nxt), top] = True
    return E


def backtest(rets: pd.DataFrame, elig: pd.DataFrame, adv: pd.DataFrame, below_ma: pd.DataFrame,
             start: pd.Timestamp, end: pd.Timestamp, tech_exit: bool = True,
             betas: pd.DataFrame | None = None, timing: str = "breakout", adv_tilt: bool = True,
             gain_tilt: bool = True, size_pct: pd.DataFrame | None = None) -> tuple[pd.DataFrame, int]:
    """逐日模擬。訊號用第 t 日收盤（含）以前的資料，於 t+1 日收盤成交。
    timing="breakout"：兩日連漲才加碼；"any"：可買期間每隔 2 日就加碼（拆解用）。adv_tilt / gain_tilt：加碼金額是否乘上
    成交金額比、兩日漲幅比。回傳每日 [ret, exposure, turnover, beta_exp, n_hold, size]（beta_exp = 期初 Σw·β；
    size = 持股依權重平均的市值百分位）與完整出清次數。"""
    days = rets.index[(rets.index >= start) & (rets.index <= end)]
    cols = rets.columns
    up = (rets > 0).astype(int)
    dn = (rets < 0).astype(int)
    up2 = (up + up.shift(1)) == 2
    dn2 = (dn + dn.shift(1)) == 2
    dn3 = (dn + dn.shift(1) + dn.shift(2)) == 3
    g2 = (1 + rets) * (1 + rets.shift(1)) - 1
    adv_ratio = adv.div(adv.where(elig).median(axis=1), axis=0)

    w = pd.Series(0.0, index=cols)            # 期初持股市值 / 總資產
    last_add = pd.Series(-10, index=cols)
    exits = 0
    rows = []
    pending = None                            # 前一日收盤算好的委託
    for i, d in enumerate(days):
        r = rets.loc[d].fillna(0.0)
        bexp = float((w * betas.loc[d].reindex(cols).fillna(1.0)).sum()) if betas is not None else float(w.sum())
        # 1) 當日報酬
        port = float((w * r).sum())
        w = w * (1 + r) / (1 + port)
        cash = 1 - w.sum()
        # 2) 執行前一日收盤的委託（當日收盤成交）
        to = 0.0
        if pending is not None:
            sells, buys = pending
            for t, frac in sells.items():
                if w[t] > 0:
                    amt = w[t] * frac
                    w[t] -= amt
                    to += amt
                    if frac >= 1 or w[t] < 1e-9:
                        exits += 1
                        w[t] = 0.0
            cash = 1 - w.sum()
            if buys:
                room = pd.Series({t: max(0.0, STOCK_MAX - w[t]) for t in buys})
                want = pd.Series(buys).clip(upper=room)
                if want.sum() > cash:
                    want *= cash / want.sum() if want.sum() > 0 else 0.0
                for t, a in want.items():
                    if a > 1e-6:
                        w[t] += a
                        to += a
                        last_add[t] = i
            cost = to * lp.STOCK_COST
            w = w / (1 - cost)
        held_w = w[w > 1e-9]
        size = float((held_w * size_pct.loc[d, held_w.index]).sum() / held_w.sum()) if size_pct is not None and len(held_w) else float("nan")
        rows.append((d, (1 + port) * (1 - to * lp.STOCK_COST) - 1, float(w.sum()), to, bexp, len(held_w), size))
        # 3) 用當日收盤（含）以前的資料產生明日委託
        held = w[w > 0].index
        sells = {}
        if tech_exit:
            for t in held:
                if dn3.at[d, t]:
                    sells[t] = 1.0
                elif dn2.at[d, t] and below_ma.at[d, t]:
                    sells[t] = 0.5
        else:
            for t in held:
                if not elig.at[d, t]:
                    sells[t] = 1.0
        buys = {}
        trig = elig.loc[d] & up2.loc[d] if timing == "breakout" else elig.loc[d]
        cand = cols[trig.to_numpy()]
        for t in cand:
            if t in sells or i - last_add[t] < 2 or w[t] >= STOCK_MAX - 1e-9:
                continue
            a = UNIT
            if gain_tilt:
                a *= float(np.clip(g2.at[d, t] / G_REF, 0.25, 2.5))
            if adv_tilt:
                a *= float(np.clip(adv_ratio.at[d, t], 0.5, 2.0))
            buys[t] = float(np.clip(a, ADD_MIN, ADD_MAX))
        pending = (sells, buys)
    df = pd.DataFrame(rows, columns=["date", "ret", "exposure", "turnover", "beta_exp", "n_hold", "size"]).set_index("date")
    return df, exits


def hold_monthly(rets: pd.DataFrame, elig: pd.DataFrame, start, end) -> pd.Series:
    """對照：持有可買名單等權（單檔 ≤ 20%，其餘現金），名單變動日收盤換倉、隔日起生效，扣成本。"""
    days = rets.index[(rets.index >= start) & (rets.index <= end)]
    out, w_prev = [], pd.Series(0.0, index=rets.columns)
    for d in days:
        names = elig.columns[elig.loc[d].to_numpy()]
        w = pd.Series(0.0, index=rets.columns)
        if len(names):
            w[names] = min(1.0 / len(names), STOCK_MAX)
        out.append((d, w_prev))
        w_prev = w
    W = pd.DataFrame({d: v for d, v in out}).T
    ret = (W * rets.loc[days].fillna(0.0)).sum(axis=1)
    to = W.diff().abs().sum(axis=1).fillna(W.iloc[0].abs().sum())
    return ret - to * lp.STOCK_COST


def summarize(x: pd.Series) -> dict:
    x = x.dropna()
    eq = (1 + x).cumprod()
    return {"sh_oos": lp.sharpe(x[x.index < lp.SPLIT]), "sh_is": lp.sharpe(x[x.index >= lp.SPLIT]),
            "ann_oos": float((1 + x[x.index < lp.SPLIT]).prod() ** (252 / max(1, (x.index < lp.SPLIT).sum())) - 1),
            "ann_is": float((1 + x[x.index >= lp.SPLIT]).prod() ** (252 / max(1, (x.index >= lp.SPLIT).sum())) - 1),
            "mdd": float((eq / eq.cummax() - 1).min()),
            "yearly": {int(y): lp.sharpe(g) for y, g in x.groupby(x.index.year)}}


def main(top_n: int):
    c = lp.prepare(top_n)
    scores = lp.leg_scores(c, "sue")
    elig = eligibility(c, scores) & c.member
    rets = c.rets.where(c.adj.notna())
    adv = c.money.reindex(index=c.adj.index).rolling(20, min_periods=10).mean()
    ma = c.adj.rolling(MA, min_periods=MA).mean()
    below = c.adj < ma
    start, end = c.schedule[0], lp.HOLDOUT - pd.Timedelta(days=1)

    tech, exits = backtest(rets, elig, adv, below, start, end, tech_exit=True, betas=c.betas)
    notech, _ = backtest(rets, elig, adv, below, start, end, tech_exit=False, betas=c.betas)
    monthly = hold_monthly(rets, elig, start, end)

    from data.fetch_financials import get_total_return_prices
    e = get_total_return_prices(c.client, "0050.TW", "2018-06-01", "2026-05-31").set_index("date")["adj_close"]
    r0050 = e.pct_change().reindex(tech.index)

    # β 對沖版（主要指標參考）：每日 − 當日期初 Σw·β × 台指期，期貨部位變動另扣 0.005%
    txr = c.tx.reindex(tech.index).fillna(0.0)
    hedged = {}
    for k, df in (("breakout", tech), ("breakout_no_tech_exit", notech)):
        hedged[k] = df["ret"] - df["beta_exp"] * txr - df["beta_exp"].diff().abs().fillna(0.0) * lp.FUT_COST
    res = {"breakout": tech["ret"], "breakout_no_tech_exit": notech["ret"], "sue_monthly": monthly, "0050": r0050,
           "breakout_hedged": hedged["breakout"], "breakout_no_tech_exit_hedged": hedged["breakout_no_tech_exit"]}
    pd.DataFrame(res).to_csv(ROOT / "reports" / "legs" / f"sue_breakout_top{top_n}.csv")

    yrs = len(tech) / 252
    rows = [("月營收驚奇 + 兩日連漲進場、連跌出場", summarize(tech["ret"]), tech["exposure"].mean(), tech["turnover"].sum() / yrs),
            ("同一進場、不做技術面出場（基本面不符才賣）", summarize(notech["ret"]), notech["exposure"].mean(), notech["turnover"].sum() / yrs),
            ("月營收驚奇月換倉（產業內前 1/3 等權，不看技術面）", summarize(monthly), float("nan"), float("nan")),
            ("0050 買進持有", summarize(r0050), 1.0, 0.0),
            ("參考：連漲進場、連跌出場 − β × 台指期（純 alpha）", summarize(hedged["breakout"]), float("nan"), float("nan")),
            ("參考：同一進場、不做技術面出場 − β × 台指期", summarize(hedged["breakout_no_tech_exit"]), float("nan"), float("nan"))]
    lines = [f"# 月營收驚奇 + 兩日連漲進場、連跌出場（全市場市值前 {top_n} 檔，自動產生）", "",
             "由 [analysis/sue_breakout.py](../analysis/sue_breakout.py) 產生；規則見程式開頭。Sharpe 為年化（無風險利率 0、現金報酬 0），"
             "兩段為 2019–2022 / 2023–2026/04；已扣成本（單邊 0.29625%）。研究結果，非投資建議。", "",
             "| 策略 | Sharpe 2019–2022 | 2023–2026/04 | 年化報酬 2019–2022 | 2023–2026/04 | 最大回撤 | 平均持股水位 | 年換手（倍） | 逐年 Sharpe |",
             "|---|---|---|---|---|---|---|---|---|"]
    for name, s, expo, to in rows:
        yearly = "、".join(f"{y}:{v:+.1f}" for y, v in s["yearly"].items() if v == v)
        lines.append(f"| {name} | {s['sh_oos']:.2f} | {s['sh_is']:.2f} | {s['ann_oos']:+.1%} | {s['ann_is']:+.1%} | {s['mdd']:.1%} | "
                     f"{expo:.0%} | {to:.1f} | {yearly} |")
    lines += ["", f"交易：完整出清 {exits} 次；平均每日持股水位 {tech['exposure'].mean():.0%}（最高 {tech['exposure'].max():.0%}）；"
              f"可買名單平均每日 {elig.sum(axis=1).loc[start:end].mean():.0f} 檔，其中出現兩日連漲訊號平均每日 "
              f"{((elig & ((rets > 0) & (rets.shift(1) > 0))).sum(axis=1)).loc[start:end].mean():.1f} 檔。"]
    (ROOT / "docs" / f"sue_breakout_top{top_n}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print("DONE", flush=True)


if __name__ == "__main__":
    main(int(sys.argv[1]))
