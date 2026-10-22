"""I042 中小型股（市值第 501–1000 名）執行面前置檢查（點子卡 research/ideas/I042-smallcap-execution-precheck.md，檢定計畫看結果前固定）。

用法（於專案根目錄；第 501–1000 名借券成交資料約 611 次 FinMind，額度不足會自動等待）：
    .venv/Scripts/python analysis/smallcap_execution.py
輸出 docs/smallcap_execution.md。本程式不計算任何訊號的報酬。

設計（依點子卡；補充以「補」標示）：
- 名單：第 501–1000 名，2019-01 ~ 2026-04 月營收換倉日（leg_probe.event_dates），SUE（原始值）產業內前／後 1/3
  （ls_turnover.ew_ls_buffer，不含緩衝；補：放空端先不限可借，以便計算借券覆蓋率）；三份錯開、每 3 個換倉日換倉。
  對照：前 500 名同樣規則。
- 容量：K = 2,000 萬、5,000 萬、2 億；每份 K/3；單檔交易 = |新權重 − 同一份前次權重| × K/3；參與率 = 交易 ÷ 換倉日前 20 日平均成交值。
  L1 = 做多名單（依目標權重加權）參與率 ≤ 10% 的比例。另報告 ≤ 5%／20%，與 10% 參與率完成交易所需天數（中位數、90 分位）。
- 滑價：前 60 日 Abdi–Ranaldo 與 Corwin–Schultz 價差（各自 60 日平均，負值設 0，取較大者），下限 = 1 個升降單位 ÷ 收盤價（補：
  價差至少 1 個升降單位，即半價差至少半個升降單位）；衝擊 = 60 日日報酬標準差 × √(交易 ÷ 20 日平均成交值)；
  單邊額外成本 = 半價差 + 衝擊。L2 = 有交易的檔次（多空皆計）單邊額外成本中位數；另報告交易金額加權平均。
- 漲跌停：新買進者進場日漲幅 ≥ 9.5% 且（高 = 低 或 成交值 < 20 日平均 20%）視為買不到；新放空者跌幅 ≤ −9.5% 同理。L3 = 買不到的做多權重比例。
  另報告進場日為處置股的權重比例（data_cache/events/disposition.csv）。
- 借券：條件 D（前 60 日有借券成交、需借股數 ≤ 前一日借券賣出額度、≤ 前 60 日借券成交 10%、60 日加權費率 ≤ 5%／年），
  需借股數 = K × |權重| ÷ 收盤價（與 fv5 的 K ÷ 放空檔數 ÷ 收盤價同一慣例）。S = 放空權重覆蓋率，兩段分列。
- 避險：每個換倉日的做多名單等權持有到下個換倉日的日報酬，對 TX、M1F（臺灣中型100）、G2F（富櫃200）近月連續日報酬
  做 60 日滾動迴歸（R²、β、殘差年化波動，取各日中位數）；所需口數 = β × K ÷（期貨價格 × 契約乘數），與 60 日平均日成交量比較。
  補：契約乘數 TX 200、M1F 50、G2F 50 元／點（期交所契約規格，檢定後再核對）；成交量為一般交易時段全部月份合計。
- 通過（K = 5,000 萬）：L1 ≥ 80%；L2 ≤ 0.30%；L3 ≤ 5%；S 兩段皆 ≥ 60%；H 最佳中型期貨殘差波動 ≤ TX 的 0.8 倍且所需口數 ≤ 日均量 10%。
- 建構對應：L、S 皆過 → T1 產業中性多空；L 過、S 不過、H 過 → T2 只做多 + 中型期貨；L 過、S、H 不過 → T3 只做多 + 台指期（並報告 T4）；
  L 不過 → 只做統計檢定。
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
import hedge_construction as hc  # noqa: E402
import leg_probe as lp  # noqa: E402
import ls_turnover as lt  # noqa: E402
from data.fetch_financials import FinMindClient  # noqa: E402

KS = (2e7, 5e7, 2e8)
K_MAIN = 5e7
MULT = {"TX": 200, "M1F": 50, "G2F": 50}


def tick(p: np.ndarray) -> np.ndarray:
    return np.select([p < 10, p < 50, p < 100, p < 500, p < 1000], [0.01, 0.05, 0.1, 0.5, 1.0], 5.0)


def ohlc(client, tickers, days):
    O, H, L, C, M = {}, {}, {}, {}, {}
    for t in tickers:
        px = client.get("TaiwanStockPrice", t.split(".")[0], lp.PX_START)
        if px.empty:
            continue
        px = px.assign(date=pd.to_datetime(px["date"])).drop_duplicates("date").set_index("date")
        px = px[px["close"].astype(float) > 0]
        H[t], L[t], C[t] = px["max"].astype(float), px["min"].astype(float), px["close"].astype(float)
        M[t] = px["Trading_money"].astype(float)
    f = lambda d: pd.DataFrame(d).reindex(index=days, columns=tickers)  # noqa: E731
    return f(H), f(L), f(C), f(M)


def spreads(H, L, C) -> pd.DataFrame:
    lh, ll_, lc = np.log(H), np.log(L), np.log(C)
    eta = (lh + ll_) / 2
    ar = (4 * (lc - eta) * (lc - eta.shift(-1))).shift(1)            # 用 t−1、t 的資料，對齊到 t
    ar = np.sqrt(ar.rolling(60, min_periods=40).mean().clip(lower=0))
    beta = (np.log(H / L) ** 2) + (np.log(H / L) ** 2).shift(1)
    gamma = np.log(np.maximum(H, H.shift(1)) / np.minimum(L, L.shift(1))) ** 2
    k = 3 - 2 * np.sqrt(2)
    alpha = (np.sqrt(2 * beta) - np.sqrt(beta)) / k - np.sqrt(gamma / k)
    cs = (2 * (np.exp(alpha) - 1) / (1 + np.exp(alpha))).clip(lower=0).rolling(60, min_periods=40).mean()
    s = np.maximum(ar.fillna(0), cs.fillna(0))
    floor = pd.DataFrame(tick(C.to_numpy()), index=C.index, columns=C.columns) / C
    return np.maximum(s, floor).shift(1)                               # 換倉日只用前一日以前


def fut_series(client, fid: str) -> tuple[pd.Series, pd.Series, pd.Series]:
    d = client.get("TaiwanFuturesDaily", fid, "2018-06-01", "2026-05-31")
    d = d[(d["trading_session"] == "position") & d["contract_date"].astype(str).str.fullmatch(r"\d{6}")].copy()
    d["date"] = pd.to_datetime(d["date"])
    for c in ("close", "volume"):
        d[c] = d[c].astype(float)
    vol = d.groupby("date")["volume"].sum()
    d = d[d["close"] > 0]
    front = d.sort_values(["date", "volume"]).groupby("date").tail(1).set_index("date")["contract_date"]
    px = d.pivot_table(index="date", columns="contract_date", values="close")
    rets, price = {}, {}
    dates = list(px.index)
    for k in range(1, len(dates)):
        c = front[dates[k]]
        p0, p1 = px.at[dates[k - 1], c] if c in px.columns else np.nan, px.at[dates[k], c]
        rets[dates[k]] = p1 / p0 - 1 if p0 == p0 and p0 > 0 else np.nan
        price[dates[k]] = p1
    return pd.Series(rets), pd.Series(price), vol


def books(score_at, sector, sched):
    """三份錯開：回傳 [(日期, 份別, 新權重, 前次權重)]。"""
    out, prev = [], {0: pd.Series(dtype=float), 1: pd.Series(dtype=float), 2: pd.Series(dtype=float)}
    for i, d in enumerate(sched):
        k = i % 3
        s = score_at(d)
        w = lt.ew_ls_buffer(s, sector, pd.Series(True, index=s.index), q_keep=None)
        out.append((d, k, w, prev[k]))
        prev[k] = w
    return out


def analyse(S, label, client, with_borrow=True):
    days = S.days
    sched = [d for d in lp.event_dates(days) if pd.Timestamp("2019-01-01") <= d < lp.HOLDOUT]
    sector = pd.Series({t: S.sector.get(t.split(".")[0], "NA") for t in S.tickers})
    H, L, C, M = ohlc(client, S.tickers, days)
    m20 = M.rolling(20, min_periods=10).mean().shift(1)
    sd60 = S.rets.rolling(60, min_periods=40).std().shift(1)
    spr = spreads(H, L, C)
    chg = C / C.shift(1) - 1
    disp = pd.read_csv(ROOT / "data_cache" / "events" / "disposition.csv", dtype={"stock_id": str}, parse_dates=["start", "end"])

    def score_at(d):
        k = int(days.searchsorted(d))
        mem = S.member.iloc[k].to_numpy(bool)
        return S.sue.iloc[k][mem].dropna()
    B = books(score_at, sector, sched)
    if with_borrow:
        fee = hc.lending_fees(client, S.tickers, days)
        quota, lend60 = bc.load_short_data(client, S.tickers, days)
    rows, cov, lim, dsp = [], [], [], []
    for d, k, w, wp in B:
        kd = int(days.searchsorted(d))
        seg = "2019–2022" if d < lp.SPLIT else "2023–2026/04"
        names = w.index.union(wp.index)
        dw = (w.reindex(names).fillna(0) - wp.reindex(names).fillna(0))
        for K in KS:
            trade = dw.abs() * K / 3
            part = trade / m20.loc[d].reindex(names)
            cost = spr.loc[d].reindex(names) / 2 + sd60.loc[d].reindex(names) * np.sqrt(part)
            for t in names:
                if trade[t] <= 0:
                    continue
                rows.append({"d": d, "seg": seg, "K": K, "ticker": t, "side": "long" if w.get(t, wp.get(t, 0)) > 0 else "short",
                             "tw": abs(w.get(t, 0.0)), "trade": trade[t], "part": part[t], "cost": cost[t]})
        longs, shorts = w[w > 0], -w[w < 0]
        newl = longs.index.difference(wp[wp > 0].index)
        news = shorts.index.difference(wp[wp < 0].index)
        up = ((chg.loc[d] >= 0.095) & ((H.loc[d] == L.loc[d]) | (M.loc[d] < 0.2 * m20.loc[d])))
        dn = ((chg.loc[d] <= -0.095) & ((H.loc[d] == L.loc[d]) | (M.loc[d] < 0.2 * m20.loc[d])))
        lim.append({"seg": seg, "long_blocked": float(longs[newl][up.reindex(newl).fillna(False).to_numpy(bool)].sum() / longs.sum()),
                    "short_blocked": float(shorts[news][dn.reindex(news).fillna(False).to_numpy(bool)].sum() / max(shorts.sum(), 1e-12))})
        on = set(disp.loc[(disp["start"] <= d) & (disp["end"] >= d), "stock_id"] + ".TW")
        dsp.append({"seg": seg, "long": float(longs[[t in on for t in longs.index]].sum() / longs.sum())})
        if with_borrow and len(shorts):
            c0 = C.loc[d].reindex(shorts.index)
            need = K_MAIN * shorts / c0
            ok = (lend60.loc[d].reindex(shorts.index) > 0) & (quota.loc[d].reindex(shorts.index) >= need) \
                & (need <= bc.DEPTH_FRAC * lend60.loc[d].reindex(shorts.index)) & (fee.loc[d].reindex(shorts.index) <= bc.FEE_MAX)
            had = lend60.loc[d].reindex(shorts.index) > 0
            f = fee.loc[d].reindex(shorts.index)
            cov.append({"seg": seg, "cov": float(shorts[ok.to_numpy(bool)].sum() / shorts.sum()),
                        "any": float(shorts[had.to_numpy(bool)].sum() / shorts.sum()),
                        "fee_med": float(f.median()) if f.notna().any() else np.nan, "fee_hi": float(shorts[(f > 5).to_numpy(bool)].sum() / shorts.sum())})
    tr = pd.DataFrame(rows)
    # 避險：做多名單等權日報酬（每個換倉日的名單持有到下個換倉日）
    lr = {}
    for i, (d, k, w, wp) in enumerate(B):
        nxt = B[i + 1][0] if i + 1 < len(B) else lp.HOLDOUT
        longs = w[w > 0].index
        seg_days = days[(days > d) & (days <= nxt) & (days < lp.HOLDOUT)]
        for x in seg_days:
            lr[x] = float(S.rets.loc[x, longs].mean())
    return {"label": label, "trades": tr, "lim": pd.DataFrame(lim), "disp": pd.DataFrame(dsp), "cov": pd.DataFrame(cov), "lret": pd.Series(lr).sort_index(),
            "n_long": float(np.mean([(w > 0).sum() for _, _, w, _ in B])), "n_short": float(np.mean([(w < 0).sum() for _, _, w, _ in B]))}


def hedge_stats(lret: pd.Series, fut: dict) -> dict:
    out = {}
    for fid, (r, p, v) in fut.items():
        df = pd.DataFrame({"y": lret, "x": r}).dropna()
        cov = df["y"].rolling(60, min_periods=40).cov(df["x"])
        var = df["x"].rolling(60, min_periods=40).var()
        b = cov / var
        r2 = df["y"].rolling(60, min_periods=40).corr(df["x"]) ** 2
        # 樣本外殘差：用前一日估計的 β
        res = df["y"] - b.shift(1) * df["x"]
        contracts = b * K_MAIN / (p.reindex(b.index) * MULT[fid])
        vol60 = v.rolling(60, min_periods=20).mean().reindex(b.index)
        segs = {}
        for nm, m in (("2019–2022", b.index < lp.SPLIT), ("2023–2026/04", b.index >= lp.SPLIT), ("全期", np.ones(len(b), bool))):
            segs[nm] = {"beta": float(b[m].median()), "r2": float(r2[m].median()), "resvol": float(res[m].std() * np.sqrt(252)),
                        "contracts": float(contracts[m].median()), "vol": float(vol60[m].median()),
                        "share": float((contracts[m] / vol60[m]).median())}
        out[fid] = segs
    return out


def main():
    import dotenv

    dotenv.load_dotenv(ROOT / ".env")
    client = FinMindClient()
    mkt, tx = lp.market_tri(client), lp.tx_continuous(client)
    V = ce.Sample(client, 501, 1000, mkt, tx)
    res = analyse(V, "第 501–1000 名", client)
    P = ce.Sample(client, 1, 500, mkt, tx)
    ref = analyse(P, "前 500 名（對照）", client)
    fut = {fid: fut_series(client, fid) for fid in ("TX", "M1F", "G2F")}
    hs = hedge_stats(res["lret"], fut)
    hs_ref = hedge_stats(ref["lret"], {"TX": fut["TX"]})

    def cap_table(r):
        tr = r["trades"]
        lines = []
        for K in KS:
            x = tr[(tr["K"] == K) & (tr["side"] == "long")]
            wsum = x.groupby("d")["tw"].sum()
            f = lambda q: float((x[x["part"] <= q].groupby("d")["tw"].sum() / wsum).reindex(wsum.index).fillna(0).mean())  # noqa: E731
            dd = x["part"] / 0.10
            all_ = tr[tr["K"] == K]
            lines.append((K, f(0.05), f(0.10), f(0.20), float(dd.median()), float(dd.quantile(0.9)), float(all_["cost"].median()),
                          float((all_["cost"] * all_["trade"]).sum() / all_["trade"].sum())))
        return lines
    cv, cr = cap_table(res), cap_table(ref)
    seg_med = lambda df, col: {s: float(df.loc[df["seg"] == s, col].mean()) for s in ("2019–2022", "2023–2026/04")}  # noqa: E731
    covs = seg_med(res["cov"], "cov")
    covs_ref = seg_med(ref["cov"], "cov")
    L1 = [x for x in cv if x[0] == K_MAIN][0]
    l1, l2 = L1[2] >= 0.80, L1[6] <= 0.003
    l3 = float(res["lim"]["long_blocked"].mean()) <= 0.05
    s_ok = all(v >= 0.60 for v in covs.values())
    tx_res = hs["TX"]["全期"]["resvol"]
    best = min(("M1F", "G2F"), key=lambda f: hs[f]["全期"]["resvol"])
    h_ok = hs[best]["全期"]["resvol"] <= 0.8 * tx_res and hs[best]["全期"]["share"] <= 0.10
    max_k = max([x[0] for x in cv if x[2] >= 0.80], default=None)
    L_ok = l1 and l2 and l3
    cons = ("T1 第 501–1000 名內產業中性多空（借券條件 D、台指期補 β）" if L_ok and s_ok else
            "T2 只做多 + 中型期貨避險" if L_ok and h_ok else
            "T3 只做多 + 台指期避險（並報告 T4：做多第 501–1000 名、放空 fv5 前 500 名放空腿）" if L_ok else
            "只做統計檢定（可交易版本只在通過 L1 的最大資金下報告）")
    pct = lambda x: f"{x:.0%}"  # noqa: E731
    L = ["# I042 中小型股執行面前置檢查（自動產生）", "",
         "由 [analysis/smallcap_execution.py](../analysis/smallcap_execution.py) 產生；設計見程式開頭（看結果前固定）。本檢查不計算任何訊號的報酬。"
         "名單 = 月營收換倉日 SUE 產業內前／後 1/3（三份錯開、每 3 個換倉日換倉）；參與率 = 單檔交易金額 ÷ 前 20 日平均成交值；"
         "單邊額外成本 = 半價差（Abdi–Ranaldo 與 Corwin–Schultz 較大者，至少 1 個升降單位）+ 衝擊（日報酬標準差 × √參與率），單位為交易金額的百分比，不含已計入回測的 0.29625%。研究結果，非投資建議。", "",
         f"平均名單：第 501–1000 名做多 {res['n_long']:.0f} 檔、放空 {res['n_short']:.0f} 檔；前 500 名做多 {ref['n_long']:.0f}、放空 {ref['n_short']:.0f} 檔。", "",
         "## 容量與滑價", "",
         "| 樣本 | 資金 | 做多權重參與率 ≤ 5% | ≤ 10% | ≤ 20% | 10% 參與率需天數（中位數／90 分位） | 單邊額外成本中位數 | 交易金額加權平均 |", "|---|---|---|---|---|---|---|---|"]
    for lab, tab in ((res["label"], cv), (ref["label"], cr)):
        for K, a, b, c_, m, q9, med, wavg in tab:
            L.append(f"| {lab} | {K / 1e4:,.0f} 萬 | {pct(a)} | {pct(b)} | {pct(c_)} | {m:.2f}／{q9:.2f} | {med:.2%} | {wavg:.2%} |")
    L += ["", "## 漲跌停、處置股與借券", "",
          "| 樣本 | 新買進遇漲停買不到（做多權重） | 新放空遇跌停（放空權重） | 處置股（做多權重） | 放空條件 D 覆蓋（資金 5,000 萬）2019–2022 / 2023–2026/04 | 有借券成交 | 費率中位數 | 費率 > 5% 權重 |",
          "|---|---|---|---|---|---|---|---|"]
    for r, cvv in ((res, covs), (ref, covs_ref)):
        L.append(f"| {r['label']} | {r['lim']['long_blocked'].mean():.1%} | {r['lim']['short_blocked'].mean():.1%} | {r['disp']['long'].mean():.1%} | "
                 f"{cvv['2019–2022']:.0%} / {cvv['2023–2026/04']:.0%} | {r['cov']['any'].mean():.0%} | {r['cov']['fee_med'].median():.2f}% | {r['cov']['fee_hi'].mean():.0%} |")
    L += ["", "## 避險工具（第 501–1000 名做多名單等權日報酬，60 日滾動迴歸；資金 5,000 萬）", "",
          "| 期貨 | 期間 | β 中位數 | R² 中位數 | 樣本外殘差年化波動 | 所需口數中位數 | 60 日平均日成交量（口） | 口數 ÷ 日均量 |", "|---|---|---|---|---|---|---|---|"]
    for fid, segs in list(hs.items()) + [("TX（前 500 名對照）", hs_ref["TX"])]:
        for nm, v in segs.items():
            L.append(f"| {fid} | {nm} | {v['beta']:.2f} | {v['r2']:.2f} | {v['resvol']:.1%} | {v['contracts']:.1f} | {v['vol']:,.0f} | {v['share']:.1%} |")
    L += ["", "## 判定（資金 5,000 萬）", "",
          f"- L1 做多 ≥ 80% 權重參與率 ≤ 10%：{pct(L1[2])} → {'✓' if l1 else '✗'}（L1 成立的最大資金：{'—' if max_k is None else f'{max_k / 1e4:,.0f} 萬'}）",
          f"- L2 單邊額外成本中位數 ≤ 0.30%：{L1[6]:.2%} → {'✓' if l2 else '✗'}",
          f"- L3 漲停買不到 ≤ 5% 權重：{res['lim']['long_blocked'].mean():.1%} → {'✓' if l3 else '✗'}",
          f"- S 放空條件 D 覆蓋兩段皆 ≥ 60%：{covs['2019–2022']:.0%} / {covs['2023–2026/04']:.0%} → {'✓' if s_ok else '✗'}",
          f"- H 最佳中型期貨（{best}）殘差波動 ≤ TX 的 0.8 倍（{hs[best]['全期']['resvol']:.1%} vs {tx_res:.1%}）且口數 ≤ 日均量 10%（{hs[best]['全期']['share']:.1%}）→ {'✓' if h_ok else '✗'}", "",
          f"**中小型股卡的可交易建構：{cons}**", "",
          f"單邊額外成本假設（之後中小型股回測使用，資金 5,000 萬）：{L1[6]:.2%}（中位數）。"]
    (ROOT / "docs" / "smallcap_execution.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
