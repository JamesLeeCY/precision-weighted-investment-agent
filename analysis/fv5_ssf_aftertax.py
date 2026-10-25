"""I064 fv5 多方腿改用股票期貨的稅後執行（I031 修訂版；點子卡 research/ideas/I064-fv5-long-leg-ssf-after-tax.md，檢定計畫看結果前固定）。

用法（於專案根目錄；股票期貨與股利資料已快取）：
    .venv/Scripts/python analysis/fv5_ssf_aftertax.py
輸出 docs/fv5_ssf_aftertax.md。

設計（依點子卡；補充以「補」標示）：
- P0 制度前置：補——期交所公告逐年抽查未做；依點子卡引用的 2026 年公告與股票期貨契約交易規則第 21 條，假設全期現金股利以權益數加入買方。
  期貨股利的稅務歸類未經國稅局確認；主判定依點子卡假設期貨損益（含權益數股利）稅率 0。
- P1 追蹤前置：期貨月報酬 = 持有契約結算價變動（futures_exec.fut_series）＋ 除息日權益數股利（每股現金股利 ÷ 前一日現股收盤）；
  與現股含息月報酬差的絕對值中位數 < 0.5%，未過即停止。另報告非除息月份。
- F1：fv5 各份資金每次換倉時，多單若有標準型股票期貨、持有契約前 20 日均量 ≥ 50 口、擬建口數（2 億 ÷ 3 × 權重 ÷（2,000 × 收盤價））
  ≤ 前一日未平倉 10%，且口數 ≥ 1，改用期貨持有；其餘多單、全部空單、台指期對沖照 fv5。
  補：同一份資金的多單每次換倉都重新判斷（續抱的現股改為期貨時計現股賣出與期貨買進成本）。
- 成本（同 I031）：期交稅 0.002%、每口手續費 50 元、滑價每邊 0.10%（均量 < 200 口時 0.20%），轉倉兩邊都計；現股單邊 0.29625%（含證交稅）。
- 稅：T0 不課稅、T1 13.61%、T2 30.11%，只對現股多單的應稅股利（現金＋股票股利面額）在除息日課稅；期貨多單 0。
- 通過（T2）：年化淨報酬差 ≥ +0.30 個百分點、兩段皆 > 0；兩段 Sharpe ≥ fv5 T2；每次換倉配對差 Newey-West t ≥ 2.58；T0 年化損失 ≤ 0.20 個百分點。
- 補：只報告的 fv5x 版本與次近月版本未做。
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
import futures_exec as fx  # noqa: E402
import fv5_after_tax as fat  # noqa: E402
import hedge_construction as hc  # noqa: E402
import leg_probe as lp  # noqa: E402
import ls_turnover as lt  # noqa: E402
from sue_attention import nw_t  # noqa: E402


def main():
    c = lp.prepare(500)
    days, sched = c.adj.index, c.schedule
    sue = lp.leg_scores(c, "sue")
    fee = hc.lending_fees(c.client, c.tickers, days)
    quota, lend60 = bc.load_short_data(c.client, c.tickers, days)
    close = bc.raw_close(c)
    fmap = fx.stock_futures_map()
    dv = fat.div_events(c.client, c.tickers)
    Y = pd.DataFrame(0.0, index=days, columns=c.tickers)        # 應稅股利率
    Dcash = pd.DataFrame(0.0, index=days, columns=c.tickers)    # 現金股利率（權益數調整）
    for t, e in dv.items():
        for r in e.itertuples():
            k = int(days.searchsorted(r.ex))
            if 0 < k < len(days) and days[k] == r.ex:
                p = close[t].iat[k - 1]
                if p == p and p > 0:
                    Y.iat[k, Y.columns.get_loc(t)] += r.amt / p
    for t in c.tickers:
        d = c.client.get("TaiwanStockDividend", t.split(".")[0], "2005-01-01")
        if d.empty:
            continue
        for r in d.itertuples():
            cash = float(r.CashEarningsDistribution or 0) + float(r.CashStatutorySurplus or 0)
            cd = pd.to_datetime(r.CashExDividendTradingDate, errors="coerce")
            if cash > 0 and cd == cd:
                k = int(days.searchsorted(cd))
                if 0 < k < len(days) and days[k] == cd and close[t].iat[k - 1] > 0:
                    Dcash.iat[k, Dcash.columns.get_loc(t)] += cash / close[t].iat[k - 1]
    F = {}
    for t in c.tickers:
        sid = t.split(".")[0]
        if sid in fmap:
            s = fx.fut_series(c.client, fmap[sid], days)
            if s is not None:
                s = s.copy()
                s["ret"] = s["ret"] + Dcash[t].reindex(s.index).fillna(0.0).where(s["ret"].notna(), np.nan)
                F[t] = s
    # P1
    te, te_nd = [], []
    for t, f in F.items():
        g = pd.DataFrame({"f": f["ret"], "s": c.rets[t], "dv": Dcash[t]}).dropna(subset=["f", "s"])
        g = g[(g.index >= "2019-01-01") & (g.index < lp.HOLDOUT)]
        if len(g) < 20:
            continue
        for _, m in g.groupby(g.index.to_period("M")):
            x = abs((1 + m["f"]).prod() - (1 + m["s"]).prod())
            te.append(x)
            if m["dv"].sum() == 0:
                te_nd.append(x)
    p1 = float(np.median(te)) < 0.005
    L = ["# I064 fv5 多方腿改用股票期貨的稅後執行（自動產生）", "",
         "由 [analysis/fv5_ssf_aftertax.py](../analysis/fv5_ssf_aftertax.py) 產生；設計見程式開頭（看結果前固定）。"
         "Sharpe 為扣成本、借券費與台指期對沖後，格式 2019–2022 / 2023–2026/04。期貨股利的稅務歸類未經確認。研究結果，非投資建議。", "",
         "## P1 追蹤前置（加回權益數股利後）", "",
         f"- 有股票期貨的前 500 名成員 {len(F)} 檔；期貨與現股含息月報酬差的絕對值中位數 {np.median(te):.2%}（{len(te):,} 個月；門檻 0.5%）→ {'通過' if p1 else '停止'}。",
         f"- 只報告：非除息月份 {np.median(te_nd):.2%}（{len(te_nd):,} 個月）。I031 未加回股利時為 0.53%。", ""]
    if not p1:
        L.append("**結論：未通過（P1 停止）**")
        (ROOT / "docs" / "fv5_ssf_aftertax.md").write_text("\n".join(L) + "\n", encoding="utf-8")
        print("\n".join(L))
        return

    def shortable_at(d):
        n_short = max(1, int(c.member.loc[d].sum() / 3))
        need = lt.K_CAPITAL / n_short / close.loc[d]
        return (lend60.loc[d] > 0) & (quota.loc[d] >= need) & (need <= bc.DEPTH_FRAC * lend60.loc[d]) & (fee.loc[d] <= bc.FEE_MAX)

    cap = fx.CAP / 3

    def run(sub, use_fut):
        wd = {d: lt.ew_ls_buffer(sue[d], c.sector, shortable_at(d), q_keep=None) for d in sub}
        rows, prev = [], {"S": pd.Series(dtype=float), "F": pd.Series(dtype=float)}
        b_prev, cov, tax_s = 0.0, [], pd.Series(0.0, index=days)
        comp = {"stock": 0.0, "fut": 0.0, "roll": 0.0}
        per = []
        for k, d in enumerate(sub):
            nxt = sub[k + 1] if k + 1 < len(sub) else lp.HOLDOUT
            w = wd[d][wd[d] != 0]
            fset = set()
            if use_fut:
                for t, x in w[w > 0].items():
                    f = F.get(t)
                    if f is None or d not in f.index or not bool(f.at[d, "has"]) or not f.at[d, "vol20"] >= 50:
                        continue
                    pxd = close.at[d, t]
                    n = cap * x / (fx.MULT * pxd) if pxd == pxd and pxd > 0 else 0.0
                    if 1 <= n <= 0.10 * f.at[d, "oi_prev"]:
                        fset.add(t)
            wf, ws = w[[t in fset for t in w.index]], w[[t not in fset for t in w.index]]
            cov.append(float(wf.sum() / max(w[w > 0].sum(), 1e-12)))
            b = float(np.nansum(w.to_numpy() * c.betas.loc[d, list(w.index)].fillna(1.0).to_numpy()))
            to_s = float(ws.sub(prev["S"], fill_value=0.0).abs().sum())
            dfu = wf.sub(prev["F"], fill_value=0.0).abs()

            def fcost(t):
                pxd = close.at[d, t]
                slip = fx.SLIP_THIN if F[t].at[d, "vol20"] < 200 else fx.SLIP
                return fx.TAX + fx.COMM / (fx.MULT * pxd) + slip
            fc = float(sum(v * fcost(t) for t, v in dfu.items() if v > 0 and t in F))
            period = days[(days > d) & (days <= nxt)]
            Rs = c.rets.reindex(index=period, columns=list(ws.index)).fillna(0.0).to_numpy() @ ws.to_numpy() if len(ws) else np.zeros(len(period))
            Rf, rc = np.zeros(len(period)), np.zeros(len(period))
            for t, x in wf.items():
                f = F[t].reindex(period)
                Rf += f["ret"].fillna(c.rets.reindex(period)[t].fillna(0.0)).to_numpy() * x
                rc += f["roll"].fillna(False).to_numpy(bool) * 2 * abs(x) * fcost(t)
            ret = Rs + Rf - b * c.tx.reindex(period).fillna(0.0).to_numpy() - rc
            short = -ws[ws < 0]
            if len(short):
                ret = ret - float(short.to_numpy() @ (fee.loc[d, short.index].fillna(fee.loc[d].median()).to_numpy() / 100)) / 252
            cost = to_s * lp.STOCK_COST + fc + abs(b - b_prev) * lp.FUT_COST
            if len(period):
                ret[0] -= cost
            lg = ws[ws > 0]
            tax_s.loc[period] += (Y.loc[period, lg.index] * lg).sum(axis=1)
            comp["stock"] += to_s * lp.STOCK_COST
            comp["fut"] += fc
            comp["roll"] += float(rc.sum())
            rows.append(pd.Series(ret, index=period))
            per.append((d, period))
            prev, b_prev = {"S": ws, "F": wf}, b
        return pd.concat(rows), tax_s, per, float(np.mean(cov)), comp

    res = {}
    for use_fut in (False, True):
        parts, taxes, pers, covs, comps = [], [], [], [], []
        for off in range(3):
            r, tx_, per, cv, cp = run(sched[off::3], use_fut)
            parts.append(r)
            taxes.append(tx_)
            pers.append(per)
            covs.append(cv)
            comps.append(cp)
        res[use_fut] = (parts, taxes, pers, float(np.mean(covs)), comps)
    start = sched[2]
    out = {}
    for rate_name, rate in fat.RATES.items():
        for use_fut in (False, True):
            parts, taxes, _, _, _ = res[use_fut]
            x = pd.concat([p - t.reindex(p.index).fillna(0.0) * rate for p, t in zip(parts, taxes)], axis=1).mean(axis=1)
            x = x[x.index > start]
            out[(rate_name, use_fut)] = (x, hc.stats(x) | {"full": lp.sharpe(x.dropna())})
    t2, t0 = list(fat.RATES)[2], list(fat.RATES)[0]
    xb, xf = out[(t2, False)][0], out[(t2, True)][0]
    diff = (xf - xb).dropna()
    # 每次換倉配對差：各份資金每個持有期的差加總
    pair = {}
    for off in range(3):
        pb, pf = res[False][0][off], res[True][0][off]
        tb, tf_ = res[False][1][off], res[True][1][off]
        for d, period in res[True][2][off]:
            v = float((pf.reindex(period) - tf_.reindex(period) * fat.RATES[t2]).sum() - (pb.reindex(period) - tb.reindex(period) * fat.RATES[t2]).sum())
            pair[d] = pair.get(d, 0.0) + v
    pair = pd.Series(pair).sort_index()
    pair = pair[pair.index > sched[0]]
    tp = nw_t(pair, 2)
    d2 = out[(t2, True)][1]["ann"] - out[(t2, False)][1]["ann"]
    d0 = out[(t0, True)][1]["ann"] - out[(t0, False)][1]["ann"]
    seg = [float(diff[(diff.index < lp.SPLIT) == f].mean() * 252) for f in (True, False)]
    sb, sf = out[(t2, False)][1], out[(t2, True)][1]
    shok = sf["sh_oos"] >= sb["sh_oos"] and sf["sh_is"] >= sb["sh_is"]
    ok = d2 >= 0.003 and seg[0] > 0 and seg[1] > 0 and shok and tp >= 2.58 and d0 >= -0.002
    yrs = len(xb) / 252
    cpf = {k: np.mean([cc[k] for cc in res[True][4]]) / yrs for k in ("stock", "fut", "roll")}
    cpb = {k: np.mean([cc[k] for cc in res[False][4]]) / yrs for k in ("stock", "fut", "roll")}
    L += ["## 結果", "", f"期貨覆蓋的多方權重比例（每次換倉平均）：{res[True][3]:.0%}。", "",
          "| 稅率情境 | fv5（全部現股） | F1（多單可用期貨者改期貨） | 年化淨報酬差 |", "|---|---|---|---|"]
    for rn in fat.RATES:
        b_, f_ = out[(rn, False)][1], out[(rn, True)][1]
        L.append(f"| {rn} | {b_['sh_oos']:.2f} / {b_['sh_is']:.2f}，全期 {b_['full']:.2f}，{b_['ann']:+.2%} | "
                 f"{f_['sh_oos']:.2f} / {f_['sh_is']:.2f}，全期 {f_['full']:.2f}，{f_['ann']:+.2%} | {f_['ann'] - b_['ann']:+.2%} |")
    L += ["", f"年化成本（占資金）：fv5 現股交易 {cpb['stock']:.2%}；F1 現股交易 {cpf['stock']:.2%}、期貨建平倉 {cpf['fut']:.2%}、轉倉 {cpf['roll']:.2%}。", "",
          "## 判定（T2）", "",
          f"- 年化淨報酬差 ≥ +0.30 個百分點：{d2:+.2%} → {'✓' if d2 >= 0.003 else '✗'}",
          f"- 兩段皆 > 0：{seg[0]:+.2%} / {seg[1]:+.2%} → {'✓' if seg[0] > 0 and seg[1] > 0 else '✗'}",
          f"- 兩段 Sharpe ≥ fv5 T2 → {'✓' if shok else '✗'}",
          f"- 每次換倉配對差 t ≥ 2.58：{tp:.2f} → {'✓' if tp >= 2.58 else '✗'}",
          f"- T0 年化損失 ≤ 0.20 個百分點：{d0:+.2%} → {'✓' if d0 >= -0.002 else '✗'}", "",
          f"**結論：{'通過（稅務歸類需先確認；只作為實作工具的依據）' if ok else '未通過'}**"]
    (ROOT / "docs" / "fv5_ssf_aftertax.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
