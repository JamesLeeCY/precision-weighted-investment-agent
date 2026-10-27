"""I076 fv5 改用平滑 SUE 排序以降低換手（點子卡 research/ideas/I076-fv5-smoothed-sue-low-turnover.md，檢定計畫看結果前固定）。

用法（於專案根目錄；資料皆已快取）：
    .venv/Scripts/python analysis/fv5_smoothed_sue.py
輸出 docs/fv5_smoothed_sue.md。

設計（依點子卡；補充以「補」標示）：
- SUE3 = 換倉日 d 時最近已公告 3 個月（m、m−1、m−2）SUE 的產業內百分位平均（只有 2 或 1 個月可用時取可用者平均）。
  補：每個月的 SUE 先照 fv5 處理（d 當日成員、產業內 z 分數、對產業與 d 當日 log 市值中性化，leg_probe.leg_scores 的步驟），再取產業內百分位。
- 建構：只把排序分數由 SUE 換成 SUE3，其餘照 fv5（產業內前／後 1/3 等權、三份錯開每 3 個換倉日、借券條件 D、台指期對沖、單邊 0.29625% + 借券費）。
- 通過（四項皆成立）：年換手（每份資金單邊權重變動合計，三份平均）相對 fv5 下降 ≥ 20%；年化淨報酬差 ≥ +0.10 個百分點且兩段差皆 > 0；
  兩段 Sharpe 皆不低於 fv5；配對日報酬差全期 Newey-West（落後 5）t ≥ 2.58。
- 只報告：扣成本前（股票成本 0、無借券費，期貨成本照計）的報酬差；0.5 / 0.3 / 0.2 加權版；fv5 緩衝版（新進前 1/3、續抱前／後 1/2，ls_turnover.Q_KEEP）；
  fv5x 換成 SUE3（以 SUE3 取代 fv5_family 的 SUE 分數）；第 501–1000 名與第 1001–1500 名 SUE3 相對 SUE 的 60 日產業內 IC 差（每個換倉日，Newey-West 落後 3）。
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
import fv5_family as ff  # noqa: E402
import hedge_construction as hc  # noqa: E402
import leg_probe as lp  # noqa: E402
import ls_turnover as lt  # noqa: E402
import smallcap_composite as sc  # noqa: E402
from sue_attention import nw_t  # noqa: E402

_ORIG_LEG_SCORES = lp.leg_scores


def month_score(c, d, mo):
    v = c.sue.loc[mo] if mo in c.sue.index else pd.Series(dtype=float)
    v = v.reindex(c.tickers).where(c.member.loc[d])
    z = v.groupby(c.sector.reindex(v.index)).transform(lambda x: (x - x.mean()) / x.std())
    return lp.neutralize(z, c.sector, c.logcap.loc[d])


def sue3_scores(c, weights=(1 / 3, 1 / 3, 1 / 3)) -> dict:
    out = {}
    for d in c.schedule:
        mo = d.to_period("M").to_timestamp()
        parts, ws = [], []
        for i, w in enumerate(weights):
            s = month_score(c, d, mo - pd.DateOffset(months=i))
            if len(s):
                parts.append(s.groupby(c.sector.reindex(s.index)).rank(pct=True) * w)
                ws.append(pd.Series(w, index=s.index))
        if not parts:
            out[d] = pd.Series(dtype=float)
            continue
        num = pd.concat(parts, axis=1).sum(axis=1, min_count=1)
        den = pd.concat(ws, axis=1).where(pd.concat(parts, axis=1).notna().to_numpy()).sum(axis=1)
        out[d] = (num / den.replace(0, np.nan)).dropna()
    return out


def ic_diff(S, sec, mem):
    days = S.days
    sched = [d for d in lp.event_dates(days) if pd.Timestamp("2019-01-01") <= d < lp.HOLDOUT]
    fwd = S.adj.shift(-60) / S.adj - 1
    out = {}
    for i in range(2, len(sched)):
        d = sched[i]
        kd = int(days.searchsorted(d))
        if kd + 60 >= S.limit:
            continue
        m = mem.loc[d]
        pc = []
        for dd in sched[i - 2:i + 1]:
            v = S.sue.iloc[int(days.searchsorted(dd))].where(m)
            pc.append(v.groupby(sec.reindex(v.index)).rank(pct=True))
        s1 = pc[-1].dropna()
        s3 = pd.concat(pc, axis=1).mean(axis=1).dropna()
        out[d] = lp.within_ic(s3, fwd.loc[d], sec) - lp.within_ic(s1, fwd.loc[d], sec)
    return pd.Series(out).sort_index()


def main():
    c = lp.prepare(500)
    days, sched, sector = c.adj.index, c.schedule, c.sector
    sue = lp.leg_scores(c, "sue")
    s3 = sue3_scores(c)
    s532 = sue3_scores(c, (0.5, 0.3, 0.2))
    fee = hc.lending_fees(c.client, c.tickers, days)
    quota, lend60 = bc.load_short_data(c.client, c.tickers, days)
    raw = bc.raw_close(c)

    def shortable_at(d):
        n_short = max(1, int(c.member.loc[d].sum() / 3))
        need = lt.K_CAPITAL / n_short / raw.loc[d]
        return (lend60.loc[d] > 0) & (quota.loc[d] >= need) & (need <= bc.DEPTH_FRAC * lend60.loc[d]) & (fee.loc[d] <= bc.FEE_MAX)

    def book(scores, buffer=False, gross=False):
        parts, tos = [], []
        sc0 = lp.STOCK_COST
        if gross:
            lp.STOCK_COST = 0.0
        try:
            for off in range(3):
                wd = lt.run_variant(scores, sector, sched, 3, buffer, shortable_at, off)
                sim = hc.simulate_weights(wd, c.rets, c.betas, c.tx, list(wd), fee=None if gross else fee)
                parts.append(sim["ret"])
                tos.append(sim["turnover"].sum() / (len(sim) / 252))
        finally:
            lp.STOCK_COST = sc0
        x = pd.concat(parts, axis=1).mean(axis=1)
        x = x[x.index > sched[2]]
        return x, hc.stats(x) | {"full": lp.sharpe(x.dropna()), "to": float(np.mean(tos))}

    x0, b0 = book(sue)
    x3, b3 = book(s3)
    g0, gb0 = book(sue, gross=True)
    g3, gb3 = book(s3, gross=True)
    _, b532 = book(s532)
    _, bbuf = book(sue, buffer=True)
    _, b3buf = book(s3, buffer=True)
    diff = (x3 - x0).dropna()
    seg = [float(diff[(diff.index < lp.SPLIT) == f].mean() * 252) for f in (True, False)]
    d_ann = b3["ann"] - b0["ann"]
    t = nw_t(diff, 5)
    to_drop = 1 - b3["to"] / b0["to"]
    k1 = to_drop >= 0.20
    k2 = d_ann >= 0.001 and seg[0] > 0 and seg[1] > 0
    k3 = b3["sh_oos"] >= b0["sh_oos"] and b3["sh_is"] >= b0["sh_is"]
    k4 = t >= 2.58
    print("main", b0["to"], b3["to"], d_ann, t, flush=True)
    # fv5x 換成 SUE3
    lp.leg_scores = lambda cc, name: sue3_scores(cc) if name == "sue" else _ORIG_LEG_SCORES(cc, name)
    try:
        Rx, _ = ff.run_backtests()
    finally:
        lp.leg_scores = _ORIG_LEG_SCORES
    R0, _ = ff.run_backtests()
    fx3 = Rx["fv5x（E+S+V）"]
    fx0 = R0["fv5x（E+S+V）"]
    sx3, sx0 = hc.stats(fx3) | {"full": lp.sharpe(fx3.dropna())}, hc.stats(fx0) | {"full": lp.sharpe(fx0.dropna())}
    # 中小型股 IC 差
    import dotenv
    dotenv.load_dotenv(ROOT / ".env")
    mkt, tx = lp.market_tri(c.client), lp.tx_continuous(c.client)
    ics = {}
    for lo, hi, path in ((501, 1000, ROOT / "config" / "universe_mcap_membership.csv"), (1001, 1500, sc.M1500)):
        ce.MEMBERSHIP = de.MEMBERSHIP = path
        S = ce.Sample(c.client, lo, hi, mkt, tx)
        ce.MEMBERSHIP = de.MEMBERSHIP = ROOT / "config" / "universe_mcap_membership.csv"
        sec = pd.Series({tk: S.sector.get(tk.split(".")[0], "NA") for tk in S.tickers})
        x = ic_diff(S, sec, S.member.astype(bool))
        ics[f"第 {lo}–{hi} 名"] = (float(x.mean()), nw_t(x, 3), len(x))
    ok = k1 and k2 and k3 and k4
    row = lambda nm, s: f"| {nm} | {s['sh_oos']:.2f} / {s['sh_is']:.2f} | {s['full']:.2f} | {s['ann']:+.2%} | {s['vol']:.1%} | {s['mdd']:.1%} | {s.get('to', float('nan')):.1f} |"  # noqa: E731
    L = ["# I076 fv5 改用平滑 SUE 排序（自動產生）", "",
         "由 [analysis/fv5_smoothed_sue.py](../analysis/fv5_smoothed_sue.py) 產生；設計見程式開頭（看結果前固定）。"
         "Sharpe 為年化、扣成本（單邊 0.29625% ＋ 借券費）與台指期對沖後，格式 2019–2022 / 2023–2026/04；"
         "年換手 = 每份資金每年單邊權重變動合計（多空兩邊合計，三份平均）。研究結果，非投資建議。", "",
         "| 版本 | Sharpe | 全期 | 年化淨報酬 | 年化波動 | 最大回撤 | 年換手 |", "|---|---|---|---|---|---|---|",
         row("fv5（SUE）", b0), row("**fv5-SUE3（主）**", b3), row("只報告：SUE3 加權 0.5 / 0.3 / 0.2", b532),
         row("只報告：fv5 緩衝（前 1/3 進、前／後 1/2 續抱）", bbuf), row("只報告：SUE3 ＋ 緩衝", b3buf),
         row("只報告：fv5x", sx0), row("只報告：fv5x 換成 SUE3", sx3), "",
         f"扣成本前（只報告）：fv5 年化 {gb0['ann']:+.2%}、SUE3 {gb3['ann']:+.2%}，差 {gb3['ann'] - gb0['ann']:+.2%}"
         f"（扣成本後差 {d_ann:+.2%}；兩者之差 = 成本節省 {(d_ann - (gb3['ann'] - gb0['ann'])):+.2%}）。", "",
         "只報告：SUE3 − SUE 的 60 日產業內 IC 差（平均，Newey-West t，換倉日數）：" + "；".join(f"{k} {v[0]:+.4f}（{v[1]:.2f}，{v[2]}）" for k, v in ics.items()) + "。", "",
         "## 判定", "",
         f"1. 年換手下降 ≥ 20%（{b0['to']:.1f} → {b3['to']:.1f}，下降 {to_drop:.0%}）→ {'✓' if k1 else '✗'}",
         f"2. 年化淨報酬差 ≥ +0.10 個百分點且兩段差 > 0（{d_ann:+.2%}；{seg[0]:+.2%} / {seg[1]:+.2%}）→ {'✓' if k2 else '✗'}",
         f"3. 兩段 Sharpe 不低於 fv5（{b3['sh_oos']:.2f} / {b3['sh_is']:.2f} vs {b0['sh_oos']:.2f} / {b0['sh_is']:.2f}）→ {'✓' if k3 else '✗'}",
         f"4. 配對日報酬差 Newey-West t ≥ 2.58（{t:.2f}）→ {'✓' if k4 else '✗'}", "",
         f"**結論：{'通過（是否另立前瞻規格由使用者決定）' if ok else '未通過'}**"]
    (ROOT / "docs" / "fv5_smoothed_sue.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
