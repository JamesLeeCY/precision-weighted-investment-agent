"""I080 台指期扣除預期股息後的超額逆價差（點子卡 research/ideas/I080-tx-dividend-adjusted-basis-carry.md，檢定計畫看結果前固定）。

用法（於專案根目錄；0050 借券費約 8 次請求，其餘已快取）：
    .venv/Scripts/python analysis/tx_basis_carry.py
輸出 docs/tx_basis_carry.md。

設計（依點子卡；補充以「補」標示）：
- 近月合約：每日成交量最大的 TX 月份（與 leg_probe.tx_continuous 相同）；結算日 T = 合約月份第三個星期三（遇休市取之後第一個交易日）。
- 預期股息點數 D̂(t, T)：前 1500 名名單中上市（twse）股票，AnnouncementDate ≤ t 且現金除息交易日落在 (t, T] 的
  （現金盈餘配息 + 公積配息）× 參與分派股數，加總後除以指數除數。
  補：沒有每日全市場總市值；除數 = 當年名單上市股票在名單換倉日的總市值 ÷ 當日加權指數，一年內固定（只忽略年內增資與新上市）。
  涵蓋率改報告名單上市股票檔數（前 1500 名已含幾乎全部上市普通股）。
- 調整後基差 EB_t = [F_t − S_t × (1 + r τ) + D̂] ÷ S_t，r = 1.5%／年，τ = 到 T 的日曆日 ÷ 365；EB < 0 = 期貨比公平價便宜。
- c_t = 台指期近月日報酬（換約不跳價）− 加權報酬指數日報酬 + r／252。
- 樣本 2018-07 ~ 2026-04，兩段 2018-07 ~ 2022 / 2023 ~ 2026/04。
- 主判定（兩項皆成立）：全期平均 c > 0、Newey-West（落後 5）t ≥ 2.58、兩段平均皆 > 0；前一日 EB 三分組中最便宜組的平均 c 大於最貴組。
- 只報告：(a) 結算日到結算日的月頻版本；(b) r = 0%、2.5%；(c) 多台指期、空 0050（比率 = 前 250 日 TX 對 0050 還原報酬的迴歸係數，
  每個結算日更新；扣 0050 借券費（無成交 1.5%）、股票單邊 0.29625%、期貨 0.005% 與每月轉倉；補：空單擔保品不計利息），
  全期與兩段 Sharpe、與 fv5 日報酬相關，以及只在前一日 EB < 0 時持有的條件版本；(d) fv5 的台指期對沖（每日淨 β）× c 的年化成本，
  與改放空 0050 時的借券費；(e) 0050 長期持有 vs 台指期加現金（r）的年化報酬差。
研究結果，非投資建議。
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "analysis"))
sys.path.insert(0, str(ROOT))
import borrow_capacity as bc  # noqa: E402
import hedge_construction as hc  # noqa: E402
import leg_probe as lp  # noqa: E402
import ls_turnover as lt  # noqa: E402
from data.fetch_financials import FinMindClient, get_total_return_prices  # noqa: E402
from sue_attention import nw_t  # noqa: E402

R_FIX = 0.015
START, END = pd.Timestamp("2018-07-01"), lp.HOLDOUT
SPLIT = lp.SPLIT


def third_wed(ym: str, days: pd.DatetimeIndex) -> pd.Timestamp:
    first = pd.Timestamp(f"{ym[:4]}-{ym[4:]}-01")
    wd = first + pd.Timedelta(days=(2 - first.weekday()) % 7 + 14)
    return days[min(days.searchsorted(wd), len(days) - 1)]


def futures(client, days):
    d = client.get("TaiwanFuturesDaily", "TX", "2018-06-01", "2026-05-31")
    d = d[(d["trading_session"] == "position") & d["contract_date"].astype(str).str.fullmatch(r"\d{6}") & (d["close"].astype(float) > 0)].copy()
    d["date"] = pd.to_datetime(d["date"])
    d["close"] = d["close"].astype(float)
    d["volume"] = d["volume"].astype(float)
    front = d.sort_values(["date", "volume"]).groupby("date").tail(1).set_index("date")["contract_date"].astype(str)
    px = d.pivot_table(index="date", columns="contract_date", values="close")
    px.columns = px.columns.astype(str)
    F, ret, T = {}, {}, {}
    dates = list(px.index)
    for k, dt in enumerate(dates):
        c = front[dt]
        F[dt], T[dt] = px.at[dt, c], third_wed(c, days)
        if k:
            p0 = px.at[dates[k - 1], c]
            ret[dt] = px.at[dt, c] / p0 - 1 if p0 == p0 and p0 > 0 else 0.0
    return pd.Series(F), pd.Series(ret), pd.Series(T)


def dividends(client, S: pd.Series) -> tuple[pd.DataFrame, pd.Series, dict]:
    """回傳（除息事件：date_ex、ann、amt、year）、各年除數、各年上市檔數。"""
    m = pd.read_csv(ROOT / "config" / "universe_mcap_membership_1500.csv", dtype={"stock_id": str})
    m = m[m["market_type"] == "twse"]
    div, nlist = {}, {}
    for y, g in m.groupby("year"):
        reb = pd.Timestamp(g["rebalance_date"].iloc[0])
        s0 = S.asof(reb) if reb >= S.index[0] else S.iloc[0]
        div[int(y)] = float(g["mcap"].sum()) / s0
        nlist[int(y)] = len(g)
    rows = []
    for sid, g in m.groupby("stock_id"):
        years = set(g["year"].astype(int))
        d = client.get("TaiwanStockDividend", sid, "2017-01-01")
        if d.empty:
            continue
        for r in d.itertuples():
            cash = float(r.CashEarningsDistribution or 0) + float(r.CashStatutorySurplus or 0)
            sh = float(r.ParticipateDistributionOfTotalShares or 0)
            x = pd.to_datetime(r.CashExDividendTradingDate, errors="coerce")
            a = pd.to_datetime(r.AnnouncementDate, errors="coerce")
            if cash <= 0 or sh <= 0 or x != x or x.year not in years:
                continue
            rows.append((x, a if a == a else x, cash * sh, x.year))
    ev = pd.DataFrame(rows, columns=["ex", "ann", "amt", "year"])
    return ev, pd.Series(div), nlist


def dhat(ev: pd.DataFrame, divisor: pd.Series, days, T: pd.Series) -> pd.Series:
    out = {}
    ex, ann, pts = ev["ex"].to_numpy(), ev["ann"].to_numpy(), (ev["amt"] / ev["year"].map(divisor)).to_numpy()
    for t in days:
        if t not in T.index:
            continue
        mk = (ann <= np.datetime64(t)) & (ex > np.datetime64(t)) & (ex <= np.datetime64(T[t]))
        out[t] = float(np.nansum(pts[mk]))
    return pd.Series(out)


def seg_mean(x):
    return [float(x[x.index < SPLIT].mean()), float(x[x.index >= SPLIT].mean())]


def main():
    import dotenv

    dotenv.load_dotenv(ROOT / ".env")
    client = FinMindClient()
    tp = client.get("TaiwanStockPrice", "TAIEX", "2018-06-01", "2026-05-31")
    S = pd.Series(tp["close"].astype(float).to_numpy(), index=pd.to_datetime(tp["date"])).sort_index()
    tri = lp.market_tri(client)
    rtri = tri.pct_change()
    days = S.index
    F, rtx, T = futures(client, days)
    ev, divisor, nlist = dividends(client, S)
    D = dhat(ev, divisor, days, T)
    idx = days[(days >= START) & (days < END)].intersection(F.index).intersection(D.index)

    def basis(r):
        tau = (T.reindex(idx) - idx.to_series()).dt.days / 365
        return (F.reindex(idx) - S.reindex(idx) * (1 + r * tau) + D.reindex(idx)) / S.reindex(idx)

    def carry(r):
        return (rtx.reindex(idx) - rtri.reindex(idx) + r / 252).dropna()

    EB, c = basis(R_FIX), carry(R_FIX)
    raw = ((F.reindex(idx) - S.reindex(idx)) / S.reindex(idx))
    t = nw_t(c, 5)
    s1, s2 = seg_mean(c)
    lagEB = EB.shift(1).reindex(c.index)
    q = pd.qcut(lagEB.rank(method="first"), 3, labels=["便宜", "中間", "昂貴"])
    qm = c.groupby(q, observed=True).mean()
    k1 = c.mean() > 0 and t >= 2.58 and s1 > 0 and s2 > 0
    k2 = qm["便宜"] > qm["昂貴"]
    print("main", c.mean() * 252, t, flush=True)
    # (a) 結算日到結算日
    settle = sorted(set(T.reindex(idx)))
    cyc = pd.Series(np.searchsorted(np.array(settle, dtype="datetime64[ns]"), c.index.to_numpy(), side="left"), index=c.index)
    mc = c.groupby(cyc).sum()
    mc_t = nw_t(mc, 2)
    # (b)
    sens = {r: (carry(r).mean() * 252, nw_t(carry(r), 5), basis(r).mean()) for r in (0.0, 0.025)}
    # (c) 多台指期、空 0050
    p50 = get_total_return_prices(client, "0050.TW", "2017-01-01", "2026-05-31")
    r50 = pd.Series(p50["adj_close"].astype(float).to_numpy(), index=pd.DatetimeIndex(p50["date"])).pct_change()
    fee50 = hc.lending_fees(client, ["0050.TW"], days)["0050.TW"].fillna(1.5)
    X = pd.DataFrame({"tx": rtx, "e": r50}).reindex(days)
    h = {}
    for s in settle:
        win = X.loc[:s].dropna().tail(250)
        h[s] = float(win.cov().iloc[0, 1] / win["e"].var()) if len(win) >= 120 else 1.0
    hs = pd.Series(h).reindex(idx, method="ffill").shift(1).bfill()
    roll = 2 * lp.FUT_COST * 12 / 252
    trade = rtx.reindex(idx) - hs * r50.reindex(idx) - hs * fee50.reindex(idx) / 100 / 252 - roll
    dh = hs.diff().abs().fillna(hs.abs())
    trade = (trade - dh * lp.STOCK_COST).dropna()
    cond = trade.where(lagEB.reindex(trade.index) < 0, 0.0)
    st_tr = hc.stats(trade) | {"full": lp.sharpe(trade)}
    st_cd = hc.stats(cond) | {"full": lp.sharpe(cond)}
    # (d) fv5 對沖
    c5 = lp.prepare(500)
    sue = lp.leg_scores(c5, "sue")
    fee = hc.lending_fees(c5.client, c5.tickers, c5.adj.index)
    quota, lend60 = bc.load_short_data(c5.client, c5.tickers, c5.adj.index)
    rawc = bc.raw_close(c5)

    def shortable_at(d):
        n_short = max(1, int(c5.member.loc[d].sum() / 3))
        need = lt.K_CAPITAL / n_short / rawc.loc[d]
        return (lend60.loc[d] > 0) & (quota.loc[d] >= need) & (need <= bc.DEPTH_FRAC * lend60.loc[d]) & (fee.loc[d] <= bc.FEE_MAX)

    sched = c5.schedule
    rets, betas = [], []
    for off in range(3):
        wd = {d: lt.ew_ls_buffer(sue[d], c5.sector, shortable_at(d), q_keep=None) for d in sched[off::3]}
        wd = {d: w for d, w in wd.items() if len(w)}
        sim = hc.simulate_weights(wd, c5.rets, c5.betas, c5.tx, list(wd), fee=fee)
        rets.append(sim["ret"])
        betas.append(sim["beta"])
    x5 = pd.concat(rets, axis=1).mean(axis=1)
    b5 = pd.concat(betas, axis=1).mean(axis=1)
    x5, b5 = x5[x5.index > sched[2]], b5[b5.index > sched[2]]
    cc = c.reindex(b5.index)
    hedge_cost = float((b5 * cc).mean() * 252)
    alt_fee = float((b5 * fee50.reindex(b5.index) / 100).mean())
    corr = float(pd.concat([x5, trade], axis=1).dropna().corr().iloc[0, 1])
    # (e)
    e_diff = float((r50.reindex(idx) - rtx.reindex(idx) - R_FIX / 252).mean() * 252)
    n_ev = int(((ev["ex"] >= START) & (ev["ex"] < END)).sum())
    ok = k1 and k2
    st_row = lambda nm, s: f"| {nm} | {s['sh_oos']:.2f} / {s['sh_is']:.2f} | {s['full']:.2f} | {s['ann']:+.2%} | {s['vol']:.1%} | {s['mdd']:.1%} |"  # noqa: E731
    L = ["# I080 台指期扣除預期股息後的超額逆價差（自動產生）", "",
         "由 [analysis/tx_basis_carry.py](../analysis/tx_basis_carry.py) 產生；設計見程式開頭（看結果前固定）。"
         "c = 台指期近月日報酬 − 加權報酬指數日報酬 + 1.5%／252（多期貨、空含息現貨的日報酬），以年化百分比表示；"
         "基差以占指數的百分比表示，負值 = 期貨比現貨便宜。兩段為 2018-07 ~ 2022 / 2023 ~ 2026/04。研究結果，非投資建議。", "",
         f"股息資料：名單上市股票每年 {min(nlist.values())}–{max(nlist.values())} 檔，期間內現金除息 {n_ev:,} 筆。", "",
         "## 基差", "",
         "| 項目 | 2018-07 ~ 2022 | 2023 ~ 2026/04 | 全期 |", "|---|---|---|---|",
         "| 原始基差（F − S）÷ S 平均 | " + " | ".join(f"{v:+.2%}" for v in (*seg_mean(raw), raw.mean())) + " |",
         "| 預期股息點數 ÷ S 平均 | " + " | ".join(f"{v:+.2%}" for v in (*seg_mean((D.reindex(idx) / S.reindex(idx))), (D.reindex(idx) / S.reindex(idx)).mean())) + " |",
         "| **調整後基差 EB 平均** | " + " | ".join(f"{v:+.2%}" for v in (*seg_mean(EB), EB.mean())) + " |",
         f"| EB < 0 的日數比例 | {(EB[EB.index < SPLIT] < 0).mean():.0%} | {(EB[EB.index >= SPLIT] < 0).mean():.0%} | {(EB < 0).mean():.0%} |", "",
         "## 主判定：c（多台指期、空含息現貨）", "",
         "| 項目 | 2018-07 ~ 2022 | 2023 ~ 2026/04 | 全期 |", "|---|---|---|---|",
         f"| **c 年化** | {s1 * 252:+.2%} | {s2 * 252:+.2%} | {c.mean() * 252:+.2%}（t {t:.2f}，{len(c)} 日） |",
         "| 前一日 EB 三分組 c 年化（便宜／中間／昂貴） | | | " + " / ".join(f"{qm[k] * 252:+.2%}" for k in ("便宜", "中間", "昂貴")) + " |", "",
         f"只報告 (a)：結算日到結算日每月 c 平均 {mc.mean():+.3%}（t {mc_t:.2f}，{len(mc)} 個月）。",
         "只報告 (b)：" + "；".join(f"r = {r:.1%} 時 c 年化 {v[0]:+.2%}（t {v[1]:.2f}）、EB 平均 {v[2]:+.2%}" for r, v in sens.items()) + "。", "",
         "只報告 (c)：可交易版本（Sharpe 為 2018-07 ~ 2022 / 2023 ~ 2026/04）", "",
         "| 版本 | Sharpe | 全期 | 年化 | 年化波動 | 最大回撤 |", "|---|---|---|---|---|---|",
         st_row("多台指期、空 0050（迴歸比率）", st_tr), st_row("只在前一日 EB < 0 時持有", st_cd), "",
         f"多台指期、空 0050 與 fv5 日報酬相關 {corr:+.2f}；0050 對台指期比率中位數 {hs.median():.2f}。", "",
         f"只報告 (d)：fv5 每日淨 β 平均 {b5.mean():.2f}（放空等量台指期）；以 c 計的對沖年化成本 {hedge_cost:+.2%}"
         f"（正值 = 放空便宜的期貨要付出的 carry）；若改放空 0050，借券費約 {alt_fee:.2%}／年（未計追蹤差與股票成本）。",
         f"只報告 (e)：0050 長期持有 − 台指期加現金（1.5%）年化 {e_diff:+.2%}（負值 = 台指期加現金較好）。", "",
         "## 判定", "",
         f"1. c 全期平均 > 0、Newey-West t ≥ 2.58、兩段皆 > 0（{c.mean() * 252:+.2%}，t {t:.2f}；{s1 * 252:+.2%} / {s2 * 252:+.2%}）→ {'✓' if k1 else '✗'}",
         f"2. EB 最便宜組 c > 最貴組（{qm['便宜'] * 252:+.2%} vs {qm['昂貴'] * 252:+.2%}）→ {'✓' if k2 else '✗'}", "",
         f"**結論：{'通過' if ok else '未通過'}**"]
    if ok:
        L.append("可交易版本兩段 Sharpe " + ("皆 > 0.5，依事前約定可另立點子卡（由使用者決定）。" if st_tr["sh_oos"] > 0.5 and st_tr["sh_is"] > 0.5 else "未皆 > 0.5，依事前約定只用於 fv5 對沖工具與 0050 部位的執行選擇，不另立策略。"))
    (ROOT / "docs" / "tx_basis_carry.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
