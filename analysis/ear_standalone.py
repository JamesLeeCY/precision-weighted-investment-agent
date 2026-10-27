"""I068 月營收公告期報酬（EAR）的獨立多空與 fv5 各半組合（點子卡 research/ideas/I068-ear-standalone-ls-fv5-blend.md，檢定計畫看結果前固定）。

用法（於專案根目錄；資料皆已快取）：
    .venv/Scripts/python analysis/ear_standalone.py
輸出 docs/ear_standalone.md。

設計（依點子卡；補充以「補」標示）：
- EAR：與 I063 相同（換倉日 d 所在月第一個交易日的前一交易日收盤 → d 前一交易日收盤，減同產業成員等權平均），方向 +。
- EAR 多空：分數 = EAR，其餘照 fv5（產業內前／後 1/3 等權、借券條件 D、三份錯開每 3 個換倉日換倉、單邊 0.29625% + 借券費、台指期對沖）。
- P1：EAR 多空兩段淨 Sharpe 皆 > 0。
- P2（主判定）：EAR 多空日淨報酬 = a + b·fv5 日淨報酬 + 5 個 I049 風格因子 + e，Newey-West 落後 5；全期 a 的 t ≥ 2.58，兩段 a 皆 > 0（補：兩段各自迴歸）。
- P3：0.5 × fv5 + 0.5 × EAR 多空（每日合併淨報酬）；兩段 Sharpe ≥ fv5 且全期 ≥ 1.79。
- 確認：第 1001–1500 名，同一建構但不限可借、只扣交易成本（仍以台指期對沖 β）；EAR 多空月報酬（日報酬按月加總）對同樣本 SUE 多空
  與同樣本 5 個風格因子迴歸，截距 > 0 且 t ≥ 2.0（補：Newey-West 落後 3）。
- 只報告：EAR 多空與 fv5 日報酬相關；fv5 多方名單中 EAR 產業內前 1/3 的比例；I063 的 0.75/0.25 合成相對 fv5 被換掉／換入的股票之 SUE 分位
  與之後 60 日產業調整報酬；EAR 多空多方腿、空方腿相對產業平均的年化報酬；EAR 與 SUE 後 1/3 的可借比例；第 501–1000 名同一確認；fv5x 與 EAR 多空各半。
研究結果，非投資建議。
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "analysis"))
sys.path.insert(0, str(ROOT))
import asset_growth as agm  # noqa: E402
import borrow_capacity as bc  # noqa: E402
import corp_event_study as ce  # noqa: E402
import dividend_events as de  # noqa: E402
import fv5_family as ff  # noqa: E402
import fv5_style_hedge as sh  # noqa: E402
import hedge_construction as hc  # noqa: E402
import leg_probe as lp  # noqa: E402
import ls_turnover as lt  # noqa: E402
import margin_surprise as msm  # noqa: E402
import smallcap_composite as scm  # noqa: E402
from dividend_reinvest import ols_nw  # noqa: E402
from revenue_ear import sector_mean_adj  # noqa: E402

F_NAMES = sh.FACTORS


def ear_scores(adj, member, sector, sched) -> dict:
    days = adj.index
    out = {}
    for d in sched:
        kd = int(days.searchsorted(d))
        k_first = int(days.searchsorted(d.to_period("M").to_timestamp()))
        a, b = k_first - 1, kd - 1
        if a < 1 or b <= a:
            continue
        mem = member.iloc[kd]
        e = sector_mean_adj(adj.iloc[b] / adj.iloc[a] - 1, mem, sector)
        out[d] = e[mem.reindex(e.index).fillna(False).to_numpy(bool)].dropna()
    return out


def style_factors(adj, rets, betas, member, sector, logcap, client, tickers):
    days = adj.index
    eq = {}
    for t in tickers:
        e = msm.balance_equity(client, t.split(".")[0])
        if len(e):
            eq[t] = e[e.index.month.isin([3, 6, 9, 12])]
    equity = agm.to_daily(pd.DataFrame(eq).sort_index(), days).reindex(columns=tickers).astype(float)
    chars = {"12-1 動能": adj.shift(21) / adj.shift(252) - 1, "60 日波動": rets.rolling(60, min_periods=40).std(),
             "帳面市值比": equity / np.exp(logcap), "前 20 日報酬": adj / adj.shift(20) - 1, "250 日 β": betas}
    return sh.factor_returns(chars, member, sector, rets)


def span(y: pd.Series, X: pd.DataFrame, lag: int):
    df = pd.concat([y.rename("y"), X], axis=1).dropna()
    M = np.column_stack([np.ones(len(df)), df.drop(columns="y").to_numpy(float)])
    b, se = ols_nw(df["y"].to_numpy(float), M, lag)
    return float(b[0]), float(b[0] / se[0]), len(df), b[1:]


def book(score_at, sched, rets, betas, tx, sector, shortable_at, fee):
    parts, wds = [], []
    for off in range(3):
        wd = {d: lt.ew_ls_buffer(score_at(d), sector, shortable_at(d), q_keep=None) for d in sched[off::3]}
        wd = {d: w for d, w in wd.items() if len(w)}
        sim = hc.simulate_weights(wd, rets, betas, tx, list(wd), fee=fee)
        parts.append(sim["ret"])
        wds.append(wd)
    x = pd.concat(parts, axis=1).mean(axis=1)
    return x[x.index > sched[2]], wds


def st(x):
    return hc.stats(x) | {"full": lp.sharpe(x.dropna())}


def confirm(client, lo, hi, membership, mkt, tx):
    ce.MEMBERSHIP = de.MEMBERSHIP = membership
    S = ce.Sample(client, lo, hi, mkt, tx)
    ce.MEMBERSHIP = de.MEMBERSHIP = ROOT / "config" / "universe_mcap_membership.csv"
    sec = pd.Series({t: S.sector.get(t.split(".")[0], "NA") for t in S.tickers})
    sched = [d for d in lp.event_dates(S.days) if pd.Timestamp("2019-01-01") <= d < lp.HOLDOUT]
    ear = ear_scores(S.adj, S.member, sec, sched)
    sched = [d for d in sched if d in ear]
    mem = S.member.astype(bool)
    sue_at = lambda d: S.sue.iloc[int(S.days.searchsorted(d))][mem.loc[d]]  # noqa: E731
    allok = lambda d: pd.Series(True, index=S.tickers)  # noqa: E731
    xe, _ = book(lambda d: ear[d], sched, S.rets, S.betas, tx, sec, allok, None)
    xs, _ = book(sue_at, sched, S.rets, S.betas, tx, sec, allok, None)
    F = style_factors(S.adj, S.rets, S.betas, mem, sec, S.lmcap.shift(-1), client, S.tickers)
    mon = lambda x: x.groupby(x.index.to_period("M")).sum()  # noqa: E731
    X = pd.concat([mon(xs).rename("sue"), mon(F.reindex(xe.index))], axis=1)
    a, t, n, _ = span(mon(xe), X, 3)
    return {"a": a, "t": t, "n": n, "ear": st(xe), "sue": st(xs)}


def main():
    c = lp.prepare(500)
    days, sched, sector = c.adj.index, c.schedule, c.sector
    sue = lp.leg_scores(c, "sue")
    fee = hc.lending_fees(c.client, c.tickers, days)
    quota, lend60 = bc.load_short_data(c.client, c.tickers, days)
    raw = bc.raw_close(c)
    mem = c.member.astype(bool)

    def shortable_at(d):
        n_short = max(1, int(c.member.loc[d].sum() / 3))
        need = lt.K_CAPITAL / n_short / raw.loc[d]
        return (lend60.loc[d] > 0) & (quota.loc[d] >= need) & (need <= bc.DEPTH_FRAC * lend60.loc[d]) & (fee.loc[d] <= bc.FEE_MAX)

    ear = ear_scores(c.adj, mem, sector, sched)
    fv5, wd_f = book(lambda d: sue[d], sched, c.rets, c.betas, c.tx, sector, shortable_at, fee)
    xe, wd_e = book(lambda d: ear.get(d, pd.Series(dtype=float)), sched, c.rets, c.betas, c.tx, sector, shortable_at, fee)
    F = style_factors(c.adj, c.rets, c.betas, mem, sector, c.logcap, c.client, c.tickers)
    s0, se = st(fv5), st(xe)
    p1 = se["sh_oos"] > 0 and se["sh_is"] > 0
    X = pd.concat([fv5.rename("fv5"), F.reindex(xe.index)], axis=1)
    a_all = span(xe, X, 5)
    a_seg = [span(xe[(xe.index < lp.SPLIT) == f], X, 5) for f in (True, False)]
    p2 = a_all[1] >= 2.58 and a_seg[0][0] > 0 and a_seg[1][0] > 0
    blend = (0.5 * fv5 + 0.5 * xe.reindex(fv5.index).fillna(0.0))
    sb = st(blend)
    p3 = sb["sh_oos"] >= s0["sh_oos"] and sb["sh_is"] >= s0["sh_is"] and sb["full"] >= 1.79
    print("P1", p1, "P2", a_all, "P3", sb, flush=True)
    import dotenv
    dotenv.load_dotenv(ROOT / ".env")
    mkt, tx = lp.market_tri(c.client), lp.tx_continuous(c.client)
    k3 = confirm(c.client, 1001, 1500, scm.M1500, mkt, tx)
    k2 = confirm(c.client, 501, 1000, ROOT / "config" / "universe_mcap_membership.csv", mkt, tx)
    pc = k3["a"] > 0 and k3["t"] >= 2.0
    print("confirm", k3["a"], k3["t"], flush=True)
    # 只報告
    corr = float(pd.concat([xe, fv5], axis=1).dropna().corr().iloc[0, 1])
    share, swaps = [], {"多方換出": [], "多方換入": [], "空方換出": [], "空方換入": []}
    fwd = c.adj.shift(-60) / c.adj - 1
    for d in sched:
        if d not in ear:
            continue
        e = ear[d]
        ep = e.groupby(sector.reindex(e.index)).rank(pct=True)
        w0 = lt.ew_ls_buffer(sue[d], sector, shortable_at(d), q_keep=None)
        lg = w0[w0 > 0].index
        share.append(float((ep.reindex(lg) > 2 / 3).mean()))
        s = sue[d].dropna()
        g = sector.reindex(s.index)
        sp = s.groupby(g).rank(pct=True)
        comp = 0.75 * sp + 0.25 * e.reindex(s.index).groupby(g).rank(pct=True).fillna(0.5)
        w1 = lt.ew_ls_buffer(comp, sector, shortable_at(d), q_keep=None)
        kd = int(days.searchsorted(d))
        if kd + 60 < int(days.searchsorted(lp.HOLDOUT)):
            fr = sector_mean_adj(fwd.loc[d], mem.loc[d], sector)
            for side, sg in (("多方", 1), ("空方", -1)):
                a0, a1 = set(w0[w0 * sg > 0].index), set(w1[w1 * sg > 0].index)
                for lab, names in (("換出", a0 - a1), ("換入", a1 - a0)):
                    for t in names:
                        swaps[side + lab].append((float(sp.get(t, np.nan)), float(fr.get(t, np.nan))))
    sw = {k: (np.nanmean([x[0] for x in v]), np.nanmean([x[1] for x in v]), len(v)) for k, v in swaps.items() if v}
    R = c.rets.where(mem)
    dm = R.copy()
    for _, cols in sector.groupby(sector).groups.items():
        cols = [t for t in cols if t in R.columns]
        if cols:
            dm[cols] = R[cols].sub(R[cols].mean(axis=1), axis=0)
    dm = dm.fillna(0.0)
    legs = {"多方腿": [], "空方腿": []}
    for wd in wd_e:
        reb = sorted(wd)
        lr, sr = pd.Series(0.0, index=days), pd.Series(0.0, index=days)
        for n, d in enumerate(reb):
            nxt = reb[n + 1] if n + 1 < len(reb) else lp.HOLDOUT
            per = days[(days > d) & (days <= nxt)]
            w = wd[d]
            lr.loc[per] = dm.loc[per, w[w > 0].index].to_numpy() @ w[w > 0].to_numpy()
            sr.loc[per] = dm.loc[per, w[w < 0].index].to_numpy() @ w[w < 0].to_numpy()
        legs["多方腿"].append(lr)
        legs["空方腿"].append(sr)
    legr = {k: float(pd.concat(v, axis=1).mean(axis=1).loc[xe.index].mean() * 252) for k, v in legs.items()}
    shr = {"EAR": [], "SUE": []}
    for d in sched:
        if d not in ear:
            continue
        ok = shortable_at(d)
        for nm, s in (("EAR", ear[d]), ("SUE", sue[d].dropna())):
            p = s.groupby(sector.reindex(s.index)).rank(pct=True)
            bot = p[p <= 1 / 3].index
            shr[nm].append(float(ok.reindex(bot).fillna(False).mean()))
    R5, _ = ff.run_backtests()
    fx = R5["fv5x（E+S+V）"]
    fx = fx[fx.index > sched[2]]
    sx, sxb = st(fx), st(0.5 * fx + 0.5 * xe.reindex(fx.index).fillna(0.0))
    ok = p1 and p2 and p3 and pc
    seg_lab = ("2019–2022", "2023–2026/04")
    L = ["# I068 EAR 獨立多空與 fv5 各半組合（自動產生）", "",
         "由 [analysis/ear_standalone.py](../analysis/ear_standalone.py) 產生；設計見程式開頭（看結果前固定）。"
         "Sharpe 為年化、扣成本（單邊 0.29625% ＋ 借券費）與台指期對沖後，格式 2019–2022 / 2023–2026/04；"
         "截距 a 為日報酬（第 1001–1500 名為月報酬）迴歸常數項，括號為（Newey-West t，觀測數）。研究結果，非投資建議。", "",
         "## 前 500 名", "", "| 組合 | Sharpe | 全期 | 年化淨報酬 | 年化波動 | 最大回撤 |", "|---|---|---|---|---|---|"]
    for nm, s in (("fv5（基準）", s0), ("EAR 多空", se), ("**50% fv5 + 50% EAR 多空（P3）**", sb),
                  ("只報告：fv5x", sx), ("只報告：50% fv5x + 50% EAR 多空", sxb)):
        L.append(f"| {nm} | {s['sh_oos']:.2f} / {s['sh_is']:.2f} | {s['full']:.2f} | {s['ann']:+.1%} | {s['vol']:.1%} | {s['mdd']:.1%} |")
    L += ["", "跨越迴歸（EAR 多空日淨報酬對 fv5 與 5 個風格因子）：",
          f"全期 a = {a_all[0]:+.5f}／日（年化 {a_all[0] * 252:+.1%}，t {a_all[1]:.2f}，{a_all[2]} 日）；"
          + "；".join(f"{lab} a = {v[0]:+.5f}（t {v[1]:.2f}）" for lab, v in zip(seg_lab, a_seg)) + "。",
          "全期係數：fv5 " + f"{a_all[3][0]:+.3f}、" + "、".join(f"{k} {v:+.3f}" for k, v in zip(F_NAMES, a_all[3][1:])) + "。", "",
          "## 確認樣本（不限可借、只扣交易成本）", "", "| 樣本 | EAR 多空 Sharpe（全期） | SUE 多空 Sharpe（全期） | 月截距 a（t，月數） |", "|---|---|---|---|"]
    for nm, k in (("**第 1001–1500 名**", k3), ("只報告：第 501–1000 名", k2)):
        L.append(f"| {nm} | {k['ear']['sh_oos']:.2f} / {k['ear']['sh_is']:.2f}（{k['ear']['full']:.2f}） | "
                 f"{k['sue']['sh_oos']:.2f} / {k['sue']['sh_is']:.2f}（{k['sue']['full']:.2f}） | {k['a']:+.2%}（{k['t']:.2f}，{k['n']}） |")
    L += ["", "## 只報告（診斷 I063 H2）", "",
          f"- EAR 多空與 fv5 日淨報酬相關 {corr:+.2f}；fv5 多方名單中 EAR 產業內前 1/3 的比例平均 {np.mean(share):.0%}（隨機約 33%）。",
          f"- EAR 多空相對產業平均的年化報酬：多方腿 {legr['多方腿']:+.1%}、空方腿 {legr['空方腿']:+.1%}（正值 = 對組合有貢獻）。",
          f"- 產業內後 1/3 名單的可借（條件 D）比例：EAR {np.mean(shr['EAR']):.0%}、SUE {np.mean(shr['SUE']):.0%}。",
          "- I063 的 0.75 SUE + 0.25 EAR 合成相對 fv5 的名單變動（SUE 產業內分位平均；之後 60 日產業調整報酬平均；檔次）："
          + "；".join(f"{k} {v[0]:.2f}、{v[1]:+.2%}、{v[2]}" for k, v in sw.items()) + "。", "",
          "## 判定", "",
          f"- P1 EAR 多空兩段 Sharpe > 0（{se['sh_oos']:.2f} / {se['sh_is']:.2f}）→ {'✓' if p1 else '✗'}",
          f"- P2 跨越截距全期 t ≥ 2.58 且兩段 a > 0（t {a_all[1]:.2f}；{a_seg[0][0]:+.5f} / {a_seg[1][0]:+.5f}）→ {'✓' if p2 else '✗'}",
          f"- P3 各半組合兩段 Sharpe ≥ fv5 且全期 ≥ 1.79（{sb['sh_oos']:.2f} / {sb['sh_is']:.2f}，{sb['full']:.2f}）→ {'✓' if p3 else '✗'}",
          f"- 確認 第 1001–1500 名截距 > 0 且 t ≥ 2.0（t {k3['t']:.2f}）→ {'✓' if pc else '✗'}", "",
          f"**結論：{'通過（另立前瞻規格，與 fv5 平行記錄）' if ok else '未通過'}**"]
    (ROOT / "docs" / "ear_standalone.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
