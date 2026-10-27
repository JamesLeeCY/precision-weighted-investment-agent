"""I077 處分效果的未實現獲利（CGO，Grinblatt–Han 台股版）（點子卡 research/ideas/I077-capital-gains-overhang-disposition.md，檢定計畫看結果前固定）。

用法（於專案根目錄；資料皆已快取）：
    .venv/Scripts/python analysis/cgo.py
輸出 docs/cgo.md。

設計（依點子卡；補充以「補」標示）：
- 名目價 P：未還原收盤價，只調整分割（TaiwanStockSplitPrice）與配股（TaiwanStockDividendResult 含「權」者，含權息時以整筆參考價比例調整），
  不調整純現金除息。補：減資參考價資料集未快取，改以「單日收盤變動超過 ±11%（超過漲跌停）且當日無上述事件」視為公司事件並移除該跳動。
- 換手率 V = 成交股數 ÷ 已發行股數（TaiwanStockShareholding，往前填補），上限 0.999（補：避免 log(0)）；缺值視為 0。
- 參考價 RP_t = Σ_{n=1..250} w_n P_{t−n} / Σ w_n，w_n = V_{t−n} Π_{τ=1..n−1}(1 − V_{t−n+τ})。補：以累積 log(1 − V) 改寫為兩個 250 日滾動和的比值，分段重設基準避免溢位；
  需有 250 個交易日的價格歷史。
- CGO_t = (P_{t−5} − RP_{t−5}) / P_{t−5}。
- H1：每月最後一個交易日（2019-07 ~ 2026-04，且之後 60 個交易日在 2026-05 前結束），被解釋變數 = 之後 60 個交易日產業調整報酬的產業內百分位 − 0.5；
  自變數 CGO 與控制（12-1 動能、前 20 日報酬、最新月營收 SUE、log 市值、前 250 日平均換手率）皆為產業內百分位 − 0.5；Fama-MacBeth、Newey-West 落後 2。
  兩段 2019-07 ~ 2022 / 2023 ~ 2026/04。通過：全期 t ≥ 2.58、兩段同號且第二段 t ≥ 1.5、第 1001–1500 名同號且 t ≥ 2.0。
- H2 只在 H1 通過時做。
- 只報告：不控制的原始產業內 IC；用還原價（含息）計算的 CGO；CGO 與 12-1 動能、SUE 的等級相關；CGO 單獨產業內前／後 1/3 等權多空（每月換倉、
  台指期對沖、單邊 0.29625% ＋ 借券費，補：不限可借）的 Sharpe 與年換手。補：An（2016）的 V 型分數未做。
研究結果，非投資建議。
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "analysis"))
sys.path.insert(0, str(ROOT))
import corp_event_study as ce  # noqa: E402
import dividend_events as de  # noqa: E402
import hedge_construction as hc  # noqa: E402
import leg_probe as lp  # noqa: E402
import ls_turnover as lt  # noqa: E402
import smallcap_composite as sc  # noqa: E402
from data.fetch_financials import FinMindClient  # noqa: E402
from sue_attention import nw_t  # noqa: E402

WIN, SKIP, BLOCK = 250, 5, 40
SEG = ("2019-07 ~ 2022", "2023 ~ 2026/04")


def nominal_and_turnover(client, S) -> tuple[pd.DataFrame, pd.DataFrame]:
    days = S.days
    P, V = {}, {}
    for t in S.tickers:
        sid = t.split(".")[0]
        px = client.get("TaiwanStockPrice", sid, lp.PX_START)
        px = px[px["close"].astype(float) > 0]
        px = px.assign(date=pd.to_datetime(px["date"])).drop_duplicates("date").set_index("date").sort_index()
        close = px["close"].astype(float)
        ev = []
        sp = client.get("TaiwanStockSplitPrice", sid, lp.EV_START, lp.EV_END)
        if not sp.empty:
            ev += [(pd.Timestamp(r.date), float(r.before_price), float(r.after_price)) for r in sp.itertuples()]
        dv = client.get("TaiwanStockDividendResult", sid, lp.EV_START, lp.EV_END)
        if not dv.empty:
            dv = dv[dv["stock_or_cache_dividend"].astype(str).str.contains("權")]
            ev += [(pd.Timestamp(r.date), float(r.before_price), float(r.after_price)) for r in dv.itertuples()]
        ev = [e for e in ev if e[1] > 0 and e[2] > 0]
        ev_days = {e[0] for e in ev}
        ch = close / close.shift(1) - 1
        for d, x in ch[ch.abs() > 0.11].items():
            if not any(abs((d - e).days) <= 3 for e in ev_days):
                k = close.index.get_loc(d)
                ev.append((d, float(close.iloc[k - 1]), float(close.iloc[k])))
        fac = pd.Series(1.0, index=close.index)
        for d, b, a in ev:
            fac[close.index >= d] *= b / a
        P[t] = close * fac
        sh = client.get("TaiwanStockShareholding", sid, lp.EV_START, lp.EV_END)
        if not sh.empty:
            s = pd.Series(sh["NumberOfSharesIssued"].astype(float).to_numpy(), index=pd.to_datetime(sh["date"]))
            s = s[~s.index.duplicated(keep="last")].sort_index().reindex(close.index).ffill()
            V[t] = (px["Trading_Volume"].astype(float) / s.where(s > 0)).clip(upper=0.999)
    return (pd.DataFrame(P).reindex(index=days, columns=S.tickers),
            pd.DataFrame(V).reindex(index=days, columns=S.tickers))


def ref_price(P: pd.DataFrame, V: pd.DataFrame) -> pd.DataFrame:
    p = P.to_numpy(float)
    v = np.nan_to_num(V.to_numpy(float), nan=0.0)
    v = np.where(np.isfinite(p), v, 0.0)
    pz = np.nan_to_num(p)
    L = np.cumsum(np.log1p(-v), axis=0)
    T, N = p.shape
    out = np.full((T, N), np.nan)
    hist = np.cumsum(np.isfinite(p), axis=0)
    for b in range(WIN, T, BLOCK):
        s0, s1 = b - WIN, min(T, b + BLOCK)
        E = np.exp(-(L[s0:s1] - L[s1 - 1]))  # ∝ exp(−L_s)，以區段末為基準（E ≤ 1，避免溢位）
        num = np.vstack([np.zeros((1, N)), np.cumsum(v[s0:s1] * pz[s0:s1] * E, axis=0)])
        den = np.vstack([np.zeros((1, N)), np.cumsum(v[s0:s1] * E, axis=0)])
        for t in range(b, s1):
            a_, z_ = t - WIN - s0, t - s0
            nn, dd = num[z_] - num[a_], den[z_] - den[a_]
            with np.errstate(all="ignore"):
                out[t] = np.where((dd > 0) & (hist[t - 1] >= WIN), nn / dd, np.nan)
    return pd.DataFrame(out, index=P.index, columns=P.columns)


def cgo_matrix(P, V):
    RP = ref_price(P, V)
    return ((P - RP) / P).shift(SKIP)


def panel(S, cgo, cgo_adj, V, sec):
    days = S.days
    me = pd.Series(days, index=days).groupby(days.to_period("M")).max()
    me = [d for d in me if pd.Timestamp("2019-07-01") <= d < lp.HOLDOUT]
    A = S.adj
    turn = V.rolling(250, min_periods=120).mean()
    rows = []
    for d in me:
        k = int(days.searchsorted(d))
        if k + 60 >= S.limit or k < 252:
            continue
        mem = S.member.iloc[k].astype(bool)
        fwd = A.iloc[k + 60] / A.iloc[k] - 1
        df = pd.DataFrame({"fwd": fwd, "cgo": cgo.iloc[k], "cgo_adj": cgo_adj.iloc[k],
                           "mom": A.iloc[k - 21] / A.iloc[k - 252] - 1, "p20": A.iloc[k] / A.iloc[k - 20] - 1,
                           "sue": S.sue.iloc[k], "lm": S.lmcap.iloc[k], "turn": turn.iloc[k], "sector": sec})
        df = df[mem.reindex(df.index).fillna(False).to_numpy(bool)].dropna(subset=["fwd", "cgo"])
        df["fwd"] = df["fwd"] - df.groupby("sector")["fwd"].transform("mean")
        df["d"] = d
        rows.append(df.rename_axis("ticker").reset_index())
    return pd.concat(rows, ignore_index=True)


def fm(P, var="cgo", controls=True):
    out = {}
    for d, g in P.groupby("d"):
        if len(g) < 50:
            continue
        sec = g["sector"]
        r = lambda c: (g[c].groupby(sec).rank(pct=True) - 0.5).fillna(0.0).to_numpy(float)  # noqa: E731
        cols = [r(var)] + ([r("mom"), r("p20"), r("sue"), r("lm"), r("turn")] if controls else [])
        X = np.column_stack([np.ones(len(g))] + cols)
        b, *_ = np.linalg.lstsq(X, r("fwd"), rcond=None)
        out[d] = b[1]
    return pd.Series(out).sort_index()


def segs(x):
    f = lambda y: (float(y.mean()), nw_t(y, 2), len(y)) if len(y) > 4 else (np.nan, np.nan, len(y))  # noqa: E731
    return {SEG[0]: f(x[x.index < lp.SPLIT]), SEG[1]: f(x[x.index >= lp.SPLIT]), "全期": f(x)}


def fmt(v):
    return "—" if v[0] != v[0] else f"{v[0]:+.4f}（{v[1]:.2f}，{v[2]}）"


def sample(client, lo, hi, path, mkt, tx):
    ce.MEMBERSHIP = de.MEMBERSHIP = path
    S = ce.Sample(client, lo, hi, mkt, tx)
    ce.MEMBERSHIP = de.MEMBERSHIP = ROOT / "config" / "universe_mcap_membership.csv"
    sec = pd.Series({t: S.sector.get(t.split(".")[0], "NA") for t in S.tickers})
    P, V = nominal_and_turnover(client, S)
    cgo = cgo_matrix(P, V)
    cgo_adj = cgo_matrix(S.adj, V)
    return S, sec, cgo, panel(S, cgo, cgo_adj, V, sec)


def main():
    import dotenv

    dotenv.load_dotenv(ROOT / ".env")
    client = FinMindClient()
    mkt, tx = lp.market_tri(client), lp.tx_continuous(client)
    S1, sec1, cgo1, P1 = sample(client, 1, 500, ROOT / "config" / "universe_mcap_membership.csv", mkt, tx)
    print("top500 panel", len(P1), flush=True)
    _, _, _, P3 = sample(client, 1001, 1500, sc.M1500, mkt, tx)
    h1, h3 = segs(fm(P1)), segs(fm(P3))
    sign = np.sign(h1["全期"][0])
    k1 = h1["全期"][1] * sign >= 2.58
    k2 = np.sign(h1[SEG[0]][0]) == sign and np.sign(h1[SEG[1]][0]) == sign and h1[SEG[1]][1] * sign >= 1.5
    k3 = np.sign(h3["全期"][0]) == sign and h3["全期"][1] * sign >= 2.0
    # 只報告
    raw_ic = {}
    for nm, P in (("前 500 名", P1), ("第 1001–1500 名", P3)):
        x = pd.Series({d: lp.within_ic(g.set_index("ticker")["cgo"], g.set_index("ticker")["fwd"], g.set_index("ticker")["sector"]) for d, g in P.groupby("d")})
        raw_ic[nm] = segs(x.dropna())
    h_adj = segs(fm(P1.dropna(subset=["cgo_adj"]), "cgo_adj"))
    rc = {c: float(P1.groupby("d").apply(lambda g: g["cgo"].rank().corr(g[c].rank())).mean()) for c in ("mom", "sue", "cgo_adj")}
    fee = hc.lending_fees(client, S1.tickers, S1.days)
    days = S1.days
    me = sorted(P1["d"].unique())
    me_all = [d for d in pd.Series(days, index=days).groupby(days.to_period("M")).max() if pd.Timestamp("2019-07-01") <= d < lp.HOLDOUT]
    allok = pd.Series(True, index=S1.tickers)
    wd = {}
    for d in me_all:
        k = int(days.searchsorted(d))
        s = cgo1.iloc[k][S1.member.iloc[k].astype(bool)].dropna()
        w = lt.ew_ls_buffer(s, sec1, allok, q_keep=None)
        if len(w):
            wd[d] = w
    sim = hc.simulate_weights(wd, S1.rets, S1.betas, tx, list(wd), fee=fee)
    ls = sim["ret"]
    sls = hc.stats(ls) | {"full": lp.sharpe(ls.dropna()), "to": float(sim["turnover"].sum() / (len(sim) / 252))}
    L = ["# I077 處分效果的未實現獲利（CGO）（自動產生）", "",
         "由 [analysis/cgo.py](../analysis/cgo.py) 產生；設計見程式開頭（看結果前固定）。"
         "CGO = 5 個交易日前收盤相對換手率加權持有成本的未實現獲利率；係數為每月 Fama-MacBeth（被解釋變數為之後 60 個交易日產業調整報酬的產業內百分位 − 0.5，"
         "控制 12-1 動能、前 20 日報酬、SUE、市值、換手率，皆為產業內百分位 − 0.5），括號為（Newey-West t，月數）。研究結果，非投資建議。", "",
         f"前 500 名觀測 {len(P1):,}（{P1['d'].nunique()} 個月）、第 1001–1500 名 {len(P3):,}。", "",
         "| 樣本 | " + " | ".join(SEG) + " | 全期 |", "|---|---|---|---|",
         "| **前 500 名 CGO 係數** | " + " | ".join(fmt(v) for v in h1.values()) + " |",
         "| **確認：第 1001–1500 名** | " + " | ".join(fmt(v) for v in h3.values()) + " |",
         "| 只報告：前 500 名用還原價（含息）的 CGO | " + " | ".join(fmt(v) for v in h_adj.values()) + " |"]
    L += [f"| 只報告：{k} 原始產業內 IC（不控制） | " + " | ".join(fmt(v) for v in x.values()) + " |" for k, x in raw_ic.items()]
    L += ["", f"只報告：CGO 與 12-1 動能的每月等級相關平均 {rc['mom']:+.2f}、與 SUE {rc['sue']:+.2f}、與還原價版 CGO {rc['cgo_adj']:+.2f}。",
          f"只報告：CGO 單獨產業內前／後 1/3 等權多空（每月換倉、不限可借、扣成本與借券費、台指期對沖）Sharpe {sls['sh_oos']:.2f} / {sls['sh_is']:.2f}"
          f"（2019–2022 / 2023–2026/04），全期 {sls['full']:.2f}，年化 {sls['ann']:+.1%}，年換手 {sls['to']:.1f}。", "",
          "## 判定（H1）", "",
          f"- 全期 t ≥ 2.58（{h1['全期'][1]:.2f}）→ {'✓' if k1 else '✗'}",
          f"- 兩段同號且第二段 t ≥ 1.5 → {'✓' if k2 else '✗'}",
          f"- 第 1001–1500 名同號且 t ≥ 2.0（{h3['全期'][1]:.2f}）→ {'✓' if k3 else '✗'}", "",
          f"**結論：{'H1 通過（接著做 H2 fv5 合成）' if k1 and k2 and k3 else '未通過（H1 不成立，不做 H2）'}**"]
    (ROOT / "docs" / "cgo.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
