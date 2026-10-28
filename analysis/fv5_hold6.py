"""I078 fv5 延長持有期：六份資金、每份持有 6 個月（點子卡 research/ideas/I078-fv5-six-month-hold-six-tranches.md，檢定計畫看結果前固定）。

用法（於專案根目錄；資料皆已快取）：
    .venv/Scripts/python analysis/fv5_hold6.py
輸出 docs/fv5_hold6.md。

設計（依點子卡；補充以「補」標示）：
- 每個月營收換倉日 d 的目標權重與 fv5 完全相同（當月 SUE、產業內前／後 1/3 等權、借券條件 D、K_CAPITAL 不變）。
- fv5-Hk：資金分 k 份，第 j 份在 sched[j::k] 換倉；組合日報酬 = 各份日報酬平均（hedge_construction.simulate_weights，台指期對沖、單邊 0.29625%、借券費）。
  fv5 = H3。補：條件 D 的 K_CAPITAL 照 fv5 不變（點子卡「全部照 fv5」），不因每份資金變小而放寬。
- 比較期間：所有版本都從第 6 個換倉日（sched[5]）之後起算，2019–2022 / 2023–2026/04 兩段。
- 通過（四項皆成立）：年換手下降 ≥ 30%；年化淨報酬差 ≥ +0.10 個百分點且兩段差皆 > 0；兩段 Sharpe 皆不低於 fv5（同期間）；
  配對日報酬差全期 Newey-West（落後 5）t ≥ 2.58。
- 只報告：H4；fv5x 改為 H6（fv5_family 的 fv5x 每個換倉日權重，重新分成六份）；扣成本前（單邊成本 0、不計借券費）的報酬差；
  SUE 對第 1–60、61–120、121–180 日產業調整報酬的產業內 IC（前 500 名、第 1001–1500 名）；空單持有期間遇到停券窗
  （TaiwanStockMarginPurchaseShortSale Note「X」首日，analysis/forced_covering.events_for）的次數。
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
import corp_event_study as ce  # noqa: E402
import dividend_events as de  # noqa: E402
import forced_covering as fc  # noqa: E402
import fv5_family as ff  # noqa: E402
import hedge_construction as hc  # noqa: E402
import leg_probe as lp  # noqa: E402
import ls_turnover as lt  # noqa: E402
import smallcap_composite as sc  # noqa: E402
from revenue_ear import sector_mean_adj  # noqa: E402
from sue_attention import nw_t  # noqa: E402

WINDOWS = ((1, 60), (61, 120), (121, 180))


def book(W: dict, sched, c, fee, k: int, start, gross=False):
    """W：{換倉日: 目標權重}；k 份資金錯開換倉。回傳（日報酬, 統計, 各份權重排程）。"""
    parts, tos, wds = [], [], []
    sc0 = lp.STOCK_COST
    if gross:
        lp.STOCK_COST = 0.0
    try:
        for off in range(k):
            wd = {d: W[d] for d in sched[off::k] if d in W and len(W[d])}
            sim = hc.simulate_weights(wd, c.rets, c.betas, c.tx, list(wd), fee=None if gross else fee)
            parts.append(sim["ret"])
            s2 = sim[sim.index > start]
            tos.append(s2["turnover"].sum() / (len(s2) / 252))
            wds.append(wd)
    finally:
        lp.STOCK_COST = sc0
    x = pd.concat(parts, axis=1).mean(axis=1)
    x = x[x.index > start]
    return x, hc.stats(x) | {"full": lp.sharpe(x.dropna()), "to": float(np.mean(tos))}, wds


def horizon_ic(S, sec, mem) -> dict:
    """SUE 對各持有窗產業調整報酬的產業內 IC：{窗: (平均, NW t, 換倉日數)}。"""
    days = S.days
    sched = [d for d in lp.event_dates(days) if pd.Timestamp("2019-01-01") <= d < lp.HOLDOUT]
    out = {}
    for a, b in WINDOWS:
        fwd = S.adj.shift(-b) / S.adj.shift(-(a - 1)) - 1
        ic = {}
        for d in sched:
            kd = int(days.searchsorted(d))
            if kd + b >= S.limit:
                continue
            m = mem.loc[d]
            s = S.sue.iloc[kd].where(m).dropna()
            r = sector_mean_adj(fwd.loc[d], m, sec)
            ic[d] = lp.within_ic(s, r, sec)
        x = pd.Series(ic).dropna().sort_index()
        out[(a, b)] = (float(x.mean()), nw_t(x, max(1, b // 21)), len(x))
    return out


def stop_hits(wds, ev: pd.DataFrame, days) -> tuple[float, int]:
    """空單持有期間遇到停券窗首日的次數：（每個空單持有檔次平均次數, 空單持有檔次）。"""
    s_by = ev.groupby("ticker")["s"].apply(lambda v: pd.DatetimeIndex(sorted(pd.to_datetime(v)))).to_dict()
    hits, n = 0, 0
    for wd in wds:
        reb = list(wd)
        for i, d in enumerate(reb):
            nxt = reb[i + 1] if i + 1 < len(reb) else lp.HOLDOUT
            for t in wd[d][wd[d] < 0].index:
                s = s_by.get(t)
                n += 1
                if s is not None:
                    hits += int(((s > d) & (s <= nxt)).sum())
    return hits / max(n, 1), n


def main():
    import dotenv

    dotenv.load_dotenv(ROOT / ".env")
    c = lp.prepare(500)
    days, sched, sector = c.adj.index, c.schedule, c.sector
    sue = lp.leg_scores(c, "sue")
    fee = hc.lending_fees(c.client, c.tickers, days)
    quota, lend60 = bc.load_short_data(c.client, c.tickers, days)
    raw = bc.raw_close(c)

    def shortable_at(d):
        n_short = max(1, int(c.member.loc[d].sum() / 3))
        need = lt.K_CAPITAL / n_short / raw.loc[d]
        return (lend60.loc[d] > 0) & (quota.loc[d] >= need) & (need <= bc.DEPTH_FRAC * lend60.loc[d]) & (fee.loc[d] <= bc.FEE_MAX)

    start = sched[5]
    W = {d: lt.ew_ls_buffer(sue[d], sector, shortable_at(d), q_keep=None) for d in sched}
    x3, b3, w3 = book(W, sched, c, fee, 3, start)
    x6, b6, w6 = book(W, sched, c, fee, 6, start)
    _, b4, _ = book(W, sched, c, fee, 4, start)
    _, g3, _ = book(W, sched, c, fee, 3, start, gross=True)
    _, g6, _ = book(W, sched, c, fee, 6, start, gross=True)
    print("main", b3["to"], b6["to"], b6["ann"] - b3["ann"], flush=True)
    diff = (x6 - x3).dropna()
    seg = [float(diff[(diff.index < lp.SPLIT) == f].mean() * 252) for f in (True, False)]
    d_ann = b6["ann"] - b3["ann"]
    t = nw_t(diff, 5)
    to_drop = 1 - b6["to"] / b3["to"]
    k1 = to_drop >= 0.30
    k2 = d_ann >= 0.001 and seg[0] > 0 and seg[1] > 0
    k3 = b6["sh_oos"] >= b3["sh_oos"] and b6["sh_is"] >= b3["sh_is"]
    k4 = t >= 2.58
    # fv5x：同一組每日權重，重分成六份
    ff.run_backtests()
    WX = {d: w for wd in ff.LAST["wd"][(True, True, True)] for d, w in wd.items()}
    _, bx3, _ = book(WX, sched, c, fee, 3, start)
    _, bx6, _ = book(WX, sched, c, fee, 6, start)
    # 停券窗
    mkt, tx = lp.market_tri(c.client), lp.tx_continuous(c.client)
    S5 = ce.Sample(c.client, 1, 500, mkt, tx)
    ev = fc.events_for(S5, c.client)
    h3, n3 = stop_hits(w3, ev, days)
    h6, n6 = stop_hits(w6, ev, days)
    # 各持有窗的 SUE IC
    ics = {}
    for lo, hi, path in ((1, 500, ROOT / "config" / "universe_mcap_membership.csv"), (1001, 1500, sc.M1500)):
        ce.MEMBERSHIP = de.MEMBERSHIP = path
        S = S5 if lo == 1 else ce.Sample(c.client, lo, hi, mkt, tx)
        ce.MEMBERSHIP = de.MEMBERSHIP = ROOT / "config" / "universe_mcap_membership.csv"
        sec = pd.Series({tk: S.sector.get(tk.split(".")[0], "NA") for tk in S.tickers})
        ics["前 500 名" if lo == 1 else f"第 {lo}–{hi} 名"] = horizon_ic(S, sec, S.member.astype(bool))
    ok = k1 and k2 and k3 and k4
    row = lambda nm, s: f"| {nm} | {s['sh_oos']:.2f} / {s['sh_is']:.2f} | {s['full']:.2f} | {s['ann']:+.2%} | {s['vol']:.1%} | {s['mdd']:.1%} | {s['to']:.1f} |"  # noqa: E731
    L = ["# I078 fv5 延長持有期：六份資金、每份持有 6 個月（自動產生）", "",
         "由 [analysis/fv5_hold6.py](../analysis/fv5_hold6.py) 產生；設計見程式開頭（看結果前固定）。"
         f"所有版本都從 {start.date()} 之後起算（六份資金建倉完成），所以 fv5 數字與全期報告（1.45 / 1.87）略有不同。"
         "Sharpe 為年化、扣成本（單邊 0.29625% ＋ 借券費）與台指期對沖後，格式 2019–2022 / 2023–2026/04；"
         "年換手 = 每份資金每年單邊權重變動合計（多空兩邊合計，各份平均）。研究結果，非投資建議。", "",
         "| 版本 | Sharpe | 全期 | 年化淨報酬 | 年化波動 | 最大回撤 | 年換手 |", "|---|---|---|---|---|---|---|",
         row("fv5（三份、3 個月）", b3), row("**fv5-H6（六份、6 個月）**", b6), row("只報告：fv5-H4（四份、4 個月）", b4),
         row("只報告：fv5x", bx3), row("只報告：fv5x-H6", bx6), "",
         f"扣成本前（只報告；單邊成本 0、不計借券費）：fv5 年化 {g3['ann']:+.2%}、H6 {g6['ann']:+.2%}，差 {g6['ann'] - g3['ann']:+.2%}"
         f"（訊號衰減）；扣成本後差 {d_ann:+.2%}，兩者之差 {d_ann - (g6['ann'] - g3['ann']):+.2%} 為省下的成本與借券費。", "",
         "只報告：SUE 對各持有窗產業調整報酬的產業內 IC（平均，Newey-West t，換倉日數）：", "",
         "| 樣本 | 第 1–60 日 | 第 61–120 日 | 第 121–180 日 |", "|---|---|---|---|"]
    for nm, v in ics.items():
        L.append(f"| {nm} | " + " | ".join(f"{v[w][0]:+.4f}（{v[w][1]:.2f}，{v[w][2]}）" for w in WINDOWS) + " |")
    L += ["", f"只報告：空單每個持有檔次遇到停券窗首日的平均次數：fv5 {h3:.3f}（{n3:,} 檔次）、H6 {h6:.3f}（{n6:,} 檔次）。", "",
          "## 判定", "",
          f"1. 年換手下降 ≥ 30%（{b3['to']:.1f} → {b6['to']:.1f}，下降 {to_drop:.0%}）→ {'✓' if k1 else '✗'}",
          f"2. 年化淨報酬差 ≥ +0.10 個百分點且兩段差 > 0（{d_ann:+.2%}；{seg[0]:+.2%} / {seg[1]:+.2%}）→ {'✓' if k2 else '✗'}",
          f"3. 兩段 Sharpe 不低於 fv5（{b6['sh_oos']:.2f} / {b6['sh_is']:.2f} vs {b3['sh_oos']:.2f} / {b3['sh_is']:.2f}）→ {'✓' if k3 else '✗'}",
          f"4. 配對日報酬差 Newey-West t ≥ 2.58（{t:.2f}）→ {'✓' if k4 else '✗'}", "",
          f"**結論：{'通過（是否另立前瞻規格由使用者決定）' if ok else '未通過'}**"]
    (ROOT / "docs" / "fv5_hold6.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
