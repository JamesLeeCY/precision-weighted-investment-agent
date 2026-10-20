"""I028 營收品質濾網：應收帳款與存貨成長超過營收成長的高 SUE 股（點子卡 research/ideas/I028-receivable-inventory-quality-sue.md，檢定計畫看結果前固定）。

用法（於專案根目錄；資料皆已快取）：
    .venv/Scripts/python analysis/revenue_quality.py
輸出 docs/revenue_quality.md。

設計（依點子卡；點子卡沒寫清楚、在看結果前補上的細節以「補」標示）：
- WC = 應收帳款淨額 ＋ 關係人應收帳款淨額 ＋ 存貨（FinMind 資產負債表；分項缺值以 0 計，三項都缺則缺值，補）；
  EWC = WC_q ÷ WC_q−4 − 1 −（營收_q ÷ 營收_q−4 − 1），營收_q 為該季 3 個月月營收合計；分母 ≤ 0 設缺值；
  該季法定期限次一交易日起可用（analysis/asset_growth.to_daily），換倉日當天每期 1%／99% 截尾。
- 樣本：前 500 名非金融股（產業不是「金融保險」「金融業」），換倉日 = leg_probe schedule（月營收公告後），2019-01 ~ 2026-04；驗證第 501–1000 名。
- (1) 每個換倉日在產業內把 SUE 排序；SUE 前 30% 組內，再把 EWC 在產業內排序（補：在該組內依產業取百分位），
  EWC 後三分之一 − 前三分之一的 20 日等權報酬差，t 值依月份群集；SUE 後 30% 組同樣報告。
- (2) Fama-MacBeth：20 日報酬 = a + b1·SUE + b2·EWC + b3·SUE×EWC + 資產成長 AG + log 市值 + 產業固定效果（百分位 − 0.5）。
- (4)（只在 (1)(2) 成立時）：fv5 做多名單排除 EWC 產業內前三分之一者並依原排序遞補（做多端以排除後的分數重新選股，放空端不變，補），與 fv5 比較。
- 通過：(1) SUE 前 30% 組 EWC 低 − 高兩段 > 0、全期 t > 2；(2) b3 兩段 < 0、全期 t < −2；(3) 驗證樣本 (1) 同號；(4) 濾網兩段 Sharpe 不低於 fv5。
- 只報告：只用存貨、只用應收帳款；60 日；電子業與非電子業；EWC 與 SUE、AG 的平均橫斷面等級相關。
研究結果，非投資建議。
"""
import math
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
import hedge_construction as hc  # noqa: E402
import leg_probe as lp  # noqa: E402
import ls_turnover as lt  # noqa: E402
import sue_streak as ss  # noqa: E402

FIN = ("金融保險", "金融業")
ELEC = ("半導體業", "電子零組件業", "電腦及週邊設備業", "光電業", "通信網路業", "電子通路業", "資訊服務業", "其他電子業")


def quarterly(client, tickers):
    """回傳 {名稱: 季資料 DataFrame（索引季底日期）}：ewc、ewc_ar、ewc_inv、ag。"""
    out = {k: {} for k in ("ewc", "ewc_ar", "ewc_inv", "ag")}
    for t in tickers:
        sid = t.split(".")[0]
        d = client.get("TaiwanStockBalanceSheet", sid, "2017-01-01")
        r = client.get("TaiwanStockMonthRevenue", sid, "2017-01-01")
        if d.empty or r.empty:
            continue
        p = d.assign(date=pd.to_datetime(d["date"])).pivot_table(index="date", columns="type", values="value", aggfunc="last")
        p = p[[i.month in (3, 6, 9, 12) for i in p.index]]
        g = lambda k: p[k].astype(float) if k in p else pd.Series(np.nan, index=p.index)  # noqa: E731
        ar = g("AccountsReceivableNet").fillna(0) + g("AccountsReceivableDuefromRelatedPartiesNet").fillna(0)
        inv = g("Inventories").fillna(0)
        none = g("AccountsReceivableNet").isna() & g("AccountsReceivableDuefromRelatedPartiesNet").isna() & g("Inventories").isna()
        wc = (ar + inv).where(~none)
        r = r.assign(q=pd.to_datetime(dict(year=r["revenue_year"], month=r["revenue_month"], day=1)).dt.to_period("Q"))
        rq = r.drop_duplicates(["revenue_year", "revenue_month"], keep="last").groupby("q")["revenue"].agg(["sum", "count"])
        rq = rq["sum"].where(rq["count"] == 3).astype(float)
        rq.index = rq.index.to_timestamp(how="end").normalize()
        rev = rq.reindex(p.index)
        gr = lambda x: (x / x.shift(4) - 1).where(x.shift(4) > 0)  # noqa: E731
        rg = gr(rev)
        out["ewc"][t] = gr(wc) - rg
        out["ewc_ar"][t] = gr(ar.where(~none)) - rg
        out["ewc_inv"][t] = gr(inv.where(~none)) - rg
        ta = g("TotalAssets")
        out["ag"][t] = gr(ta)
    return {k: pd.DataFrame(v).sort_index() for k, v in out.items()}


def panel(adj, member, sector, sue, sched, limit, daily):
    rows = []
    for d in sched:
        k = int(adj.index.searchsorted(d))
        mo = d.to_period("M").to_timestamp()
        if k + 20 >= limit or mo not in sue.index:
            continue
        mem = member.loc[d].to_numpy(bool)
        s = sue.loc[mo].reindex(adj.columns)[mem].dropna()
        s = s[~sector.reindex(s.index).isin(FIN).to_numpy()]
        if len(s) < 50:
            continue
        df = pd.DataFrame({"sue": s, "rank": s.groupby(sector.reindex(s.index)).rank(pct=True), "sec": sector.reindex(s.index),
                           "f20": (adj.iloc[k + 20] / adj.iloc[k] - 1).reindex(s.index),
                           "f60": (adj.iloc[k + 60] / adj.iloc[k] - 1).reindex(s.index) if k + 60 < limit else np.nan, "d": d})
        for name, D in daily.items():
            df[name] = agm.winsor(D.loc[d].reindex(s.index)).reindex(s.index) if name.startswith("ewc") else D.loc[d].reindex(s.index)
        rows.append(df)
    return pd.concat(rows)


def low_minus_high(P, col="ewc", top=True, h="f20", mask=None):
    out = {}
    for d, g in P.groupby("d"):
        if mask is not None:
            g = g[mask(g)]
        g = g[(g["rank"] > 0.7) if top else (g["rank"] <= 0.3)].dropna(subset=[col, h])
        if len(g) < 10:
            continue
        r = g.groupby("sec")[col].rank(pct=True)
        lo, hi = g.loc[r <= 1 / 3, h], g.loc[r > 2 / 3, h]
        if len(lo) and len(hi):
            out[d] = lo.mean() - hi.mean()
    return pd.Series(out, dtype=float)


def tstat(x):
    x = pd.Series(x, dtype=float).dropna()
    return (float(x.mean()), float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 else float("nan"), len(x))


def segs(x):
    cut = pd.Timestamp("2023-01-01")
    return {"2019–2022": tstat(x[x.index < cut]), "2023–2026/04": tstat(x[x.index >= cut]), "全期": tstat(x)}


def fmt(x):
    m, t, n = x
    return "—" if m != m else f"{m:+.2%}（{t:.1f}，{n}）"


def main():
    import dotenv

    c = lp.prepare(500)
    limit = int(c.adj.index.searchsorted(lp.HOLDOUT))
    Q = quarterly(c.client, c.tickers)
    daily = {k: agm.to_daily(v, c.adj.index).reindex(columns=c.tickers) for k, v in Q.items()}
    P = panel(c.adj, c.member, c.sector, c.sue, c.schedule, limit, daily)
    top, bot = low_minus_high(P), low_minus_high(P, top=False)
    # Fama-MacBeth
    fm = {}
    corr_s, corr_a = [], []
    for d, g in P.groupby("d"):
        g = g.dropna(subset=["f20", "sue", "ewc", "ag"])
        lm = c.logcap.loc[d].reindex(g.index)
        g = g.assign(lm=lm).dropna(subset=["lm"])
        if len(g) < 50:
            continue
        R = lambda x: x.rank(pct=True) - 0.5  # noqa: E731
        rs, re_ = R(g["sue"]), R(g["ewc"])
        X = np.column_stack([np.ones(len(g)), rs, re_, rs * re_, R(g["ag"]), R(g["lm"]), pd.get_dummies(g["sec"], drop_first=True, dtype=float).to_numpy()])
        beta, *_ = np.linalg.lstsq(X, g["f20"].to_numpy(float), rcond=None)
        fm[d] = beta[1:4]
        corr_s.append(rs.corr(re_))
        corr_a.append(re_.corr(R(g["ag"])))
    F = pd.DataFrame(fm, index=["b1", "b2", "b3"]).T
    # 驗證
    dotenv.load_dotenv(ROOT / ".env")
    V = ce.Sample(c.client, 501, 1000, lp.market_tri(c.client), lp.tx_continuous(c.client))
    vsec = pd.Series({t: V.sector.get(t.split(".")[0], "NA") for t in V.tickers})
    VQ = quarterly(c.client, V.tickers)
    vdaily = {"ewc": agm.to_daily(VQ["ewc"], V.days).reindex(columns=V.tickers)}
    VP = panel(V.adj, V.member, vsec, ss.sue_monthly(c.client, V.tickers), [d for d in c.schedule if d in V.days], V.limit, vdaily)
    vtop = low_minus_high(VP)

    s_top, s_b3, v_top = segs(top), segs(F["b3"]), segs(vtop)
    c1 = s_top["2019–2022"][0] > 0 and s_top["2023–2026/04"][0] > 0 and s_top["全期"][1] > 2
    c2 = s_b3["2019–2022"][0] < 0 and s_b3["2023–2026/04"][0] < 0 and s_b3["全期"][1] < -2
    c3 = v_top["全期"][0] > 0
    port = None
    if c1 and c2:
        fee = hc.lending_fees(c.client, c.tickers, c.adj.index)
        quota, lend60 = bc.load_short_data(c.client, c.tickers, c.adj.index)
        close = bc.raw_close(c)
        sue = lp.leg_scores(c, "sue")

        def shortable_at(d):
            n_short = max(1, int(c.member.loc[d].sum() / 3))
            need = lt.K_CAPITAL / n_short / close.loc[d]
            return (lend60.loc[d] > 0) & (quota.loc[d] >= need) & (need <= bc.DEPTH_FRAC * lend60.loc[d]) & (fee.loc[d] <= bc.FEE_MAX)

        def weights(d, filt):
            sc = sue[d]
            w = lt.ew_ls_buffer(sc, c.sector, shortable_at(d), q_keep=None)
            if not filt:
                return w
            e = agm.winsor(daily["ewc"].loc[d].reindex(sc.index).dropna())
            hi = set(e[e.groupby(c.sector.reindex(e.index)).rank(pct=True) > 2 / 3].index)
            wl = lt.ew_ls_buffer(sc.drop([t for t in sc.index if t in hi]), c.sector, shortable_at(d), q_keep=None)
            return pd.concat([wl[wl > 0], w[w < 0]])

        def book(filt):
            parts = []
            for off in range(3):
                w = {d: weights(d, filt) for d in c.schedule[off::3]}
                parts.append(hc.simulate_weights(w, c.rets, c.betas, c.tx, list(w), fee=fee)["ret"])
            x = pd.concat(parts, axis=1).mean(axis=1)
            x = x[x.index > c.schedule[2]]
            return hc.stats(x) | {"full": lp.sharpe(x.dropna())}
        port = {"fv5 原版": book(False), "做多排除高 EWC": book(True)}
    c4 = port is not None and port["做多排除高 EWC"]["sh_oos"] >= port["fv5 原版"]["sh_oos"] and port["做多排除高 EWC"]["sh_is"] >= port["fv5 原版"]["sh_is"]

    L = ["# I028 營收品質濾網（自動產生）", "",
         "由 [analysis/revenue_quality.py](../analysis/revenue_quality.py) 產生；設計見程式開頭（看結果前固定）。"
         "差額 = 同一 SUE 組（產業內前或後 30%）中 EWC（應收＋存貨成長 − 營收成長）低三分之一 − 高三分之一的等權報酬，括號為（t 值，月份數）；"
         "Fama-MacBeth 係數為百分位差 1 對應的 20 日報酬變化。非金融股。研究結果，非投資建議。", "",
         f"主樣本公司月 {len(P):,} 筆，EWC 有值 {P['ewc'].notna().mean():.0%}；EWC 與 SUE、資產成長的平均等級相關 {np.mean(corr_s):+.2f}、{np.mean(corr_a):+.2f}。", "",
         "| 統計量 | 2019–2022 | 2023–2026/04 | 全期 |", "|---|---|---|---|",
         "| (1) SUE 前 30%：EWC 低 − 高，20 日 | " + " | ".join(fmt(s_top[k]) for k in s_top) + " |",
         "| SUE 後 30%：EWC 低 − 高，20 日 | " + " | ".join(fmt(v) for v in segs(bot).values()) + " |",
         "| 只報告：SUE 前 30%，60 日 | " + " | ".join(fmt(v) for v in segs(low_minus_high(P, h="f60")).values()) + " |",
         "| 只報告：只用應收帳款 | " + " | ".join(fmt(v) for v in segs(low_minus_high(P, "ewc_ar")).values()) + " |",
         "| 只報告：只用存貨 | " + " | ".join(fmt(v) for v in segs(low_minus_high(P, "ewc_inv")).values()) + " |",
         "| 只報告：電子業 | " + " | ".join(fmt(v) for v in segs(low_minus_high(P, mask=lambda g: g["sec"].isin(ELEC))).values()) + " |",
         "| 只報告：非電子業 | " + " | ".join(fmt(v) for v in segs(low_minus_high(P, mask=lambda g: ~g["sec"].isin(ELEC))).values()) + " |",
         "| (2) Fama-MacBeth b3：SUE × EWC | " + " | ".join(fmt(s_b3[k]) for k in s_b3) + " |",
         "| Fama-MacBeth b2：EWC | " + " | ".join(fmt(v) for v in segs(F["b2"]).values()) + " |",
         "| Fama-MacBeth b1：SUE | " + " | ".join(fmt(v) for v in segs(F["b1"]).values()) + " |",
         "| (3) 驗證樣本 SUE 前 30%：EWC 低 − 高 | " + " | ".join(fmt(v_top[k]) for k in v_top) + " |", ""]
    if port:
        L += ["| 建構（fv5） | Sharpe | 全期 | 年化報酬 |", "|---|---|---|---|"]
        for k, s in port.items():
            L.append(f"| {k} | {s['sh_oos']:.2f} / {s['sh_is']:.2f} | {s['full']:.2f} | {s['ann']:+.1%} |")
        L.append("")
    L += ["## 判定", "",
          f"1. SUE 前 30% 組 EWC 低 − 高兩段 > 0、全期 t > 2：{fmt(s_top['全期'])} → {'✓' if c1 else '✗'}",
          f"2. b3 兩段 < 0、全期 t < −2：{fmt(s_b3['全期'])} → {'✓' if c2 else '✗'}",
          f"3. 驗證樣本同號：{fmt(v_top['全期'])} → {'✓' if c3 else '✗'}",
          f"4. 濾網兩段 Sharpe 不低於 fv5：{'未執行（(1)(2) 未全部成立）' if port is None else ('✓' if c4 else '✗')}", "",
          f"**結論：{'通過' if c1 and c2 and c3 and c4 else '未通過'}**"]
    (ROOT / "docs" / "revenue_quality.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
