"""I043 中小型股多因子合成（點子卡 research/ideas/I043-smallcap-multifactor-composite.md，檢定計畫看結果前固定）。

用法（於專案根目錄；第 1001–1500 名約 2,500 次 FinMind，額度不足會自動等待）：
    .venv/Scripts/python analysis/smallcap_composite.py
輸出 docs/smallcap_composite.md。本程式只做階段 1（第 1001–1500 名確認）與階段 2（第 501–1000 名增量）；
兩者都通過、且 I042 的容量門檻通過，才另寫階段 3（可交易）。

設計（依點子卡；補充以「補」標示）：
- 樣本：確認第 1001–1500 名（config/universe_mcap_membership_1500.csv，前 1000 名與原檔完全相同）、開發第 501–1000 名；
  2019-07 ~ 2026-04 的月營收換倉日（leg_probe.event_dates）；報酬 = 換倉日次一交易日收盤到第 61 個交易日（第 +2 ~ +61 日），
  視窗須在 2026-05 前結束；兩段 2019-07–2022 / 2023–2026/04。
- 成分（沿用既有定義）：SUE（corp_event_study.sue_matrix，每月 10 日後用當月公告值）；MS（analysis/margin_surprise.build，
  非金融，法定期限次一交易日 ≤ 換倉日的最新一季）；NSI（analysis/net_issuance.nsi_matrix）；AG（analysis/asset_growth.sample_ag，非金融）。
  每個成分在同一名次組、同產業內轉成百分位；缺值以 0.5 計（金融股的 MS、AG 因此為 0.5）。
  C = 0.5·SUE + (1/6)·(MS + (−NSI) + (−AG))；X = (MS + (−NSI) + (−AG)) / 3。
- 階段 1（第 1001–1500 名）：C 的產業內 Spearman IC（60 日），Newey-West 落後 3；Fama-MacBeth：60 日報酬 = SUE 百分位 + X + log 市值
  + 帳面市值比（補：同季權益 ÷ 市值，法定期限後可用）+ 12-1 月報酬 + 產業固定效果，X 係數用 Newey-West 落後 3。
  通過：X 係數兩段 > 0、全期 t > 2；C 的 60 日 IC 兩段 > 0、全期 t > 2。
- 階段 2（第 501–1000 名）：每月 IC(C) − IC(SUE) 的平均，Newey-West（落後 3）全期 t > 3 且兩段皆 > 0。
- 只報告：等權四成分版本、20 日 IC、第 501–750 / 751–1000 名、上市／上櫃、前 500 名的 C 與 SUE IC。
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
import corp_event_study as ce  # noqa: E402
import dividend_events as de  # noqa: E402
import leg_probe as lp  # noqa: E402
import margin_surprise as msm  # noqa: E402
import net_issuance as nim  # noqa: E402
from data.fetch_financials import FinMindClient  # noqa: E402
from sue_attention import nw_t  # noqa: E402

M1500 = ROOT / "config" / "universe_mcap_membership_1500.csv"
START = pd.Timestamp("2019-07-01")


def components(S, client) -> dict:
    sector = pd.Series({t: S.sector.get(t.split(".")[0], "NA") for t in S.tickers})
    nsi, _ = nim.nsi_matrix(S, client)
    ag, _, _, _ = agm.sample_ag(S, client)
    ms_q = msm.build(S, client).dropna(subset=["ms"]).sort_values("t0")
    eq = {}
    for t in S.tickers:
        if sector[t] in msm.FIN:
            continue
        e = msm.balance_equity(client, t.split(".")[0])
        if len(e):
            eq[t] = e[e.index.month.isin([3, 6, 9, 12])]
    equity = agm.to_daily(pd.DataFrame(eq).sort_index(), S.days).reindex(columns=S.tickers) if eq else pd.DataFrame(index=S.days, columns=S.tickers)
    return {"sector": sector, "nsi": nsi, "ag": ag, "ms_q": ms_q, "equity": equity}


def panel(S, comp, sched, mtype) -> pd.DataFrame:
    """每個換倉日 × 成員：各成分的產業內百分位、C、X、報酬與控制變數。"""
    days, sector = S.days, comp["sector"]
    mom = S.adj.shift(21) / S.adj.shift(252) - 1
    rows = []
    for d in sched:
        k = int(days.searchsorted(d))
        mem = S.member.iloc[k].to_numpy(bool)
        tk = [t for t, m in zip(S.tickers, mem) if m]
        known = comp["ms_q"][comp["ms_q"]["t0"] <= d].drop_duplicates("ticker", keep="last").set_index("ticker")["ms"]
        df = pd.DataFrame({"sue": S.sue.iloc[k].reindex(tk), "ms": known.reindex(tk), "nnsi": -agm.winsor(comp["nsi"].iloc[k].reindex(tk)).reindex(tk),
                           "nag": -agm.winsor(comp["ag"].iloc[k].reindex(tk)).reindex(tk), "sector": sector.reindex(tk),
                           "lm": S.lmcap.iloc[k].reindex(tk), "mom": mom.iloc[k].reindex(tk),
                           "bm": (comp["equity"].iloc[k].reindex(tk).astype(float) / np.exp(S.lmcap.iloc[k].reindex(tk)))}, index=tk)
        for c in ("sue", "ms", "nnsi", "nag"):
            df["p_" + c] = df.groupby("sector")[c].rank(pct=True).fillna(0.5)
        df["X"] = (df["p_ms"] + df["p_nnsi"] + df["p_nag"]) / 3
        df["C"] = 0.5 * df["p_sue"] + 0.5 * df["X"]
        df["E"] = (df["p_sue"] + df["p_ms"] + df["p_nnsi"] + df["p_nag"]) / 4
        A = S.adj.to_numpy()
        j = np.array([S.col[t] for t in tk])
        for h, nm in ((21, "r20"), (61, "r60")):
            df[nm] = A[k + h, j] / A[k + 1, j] - 1 if k + h < S.limit else np.nan
        df["d"], df["ticker"] = d, tk
        df["mkt"] = [mtype.get(t.split(".")[0], "") for t in tk]
        df["has_sue"] = df["sue"].notna()
        rows.append(df)
    return pd.concat(rows, ignore_index=True)


def ic_series(P, sig, ret, mask=None):
    x = P if mask is None else P[mask]
    out = {}
    for d, g in x.dropna(subset=[ret]).groupby("d"):
        g = g.set_index("ticker")
        out[d] = lp.within_ic(g[sig], g[ret], g["sector"])
    return pd.Series(out).dropna()


def segs(x: pd.Series, lag=3) -> dict:
    f = lambda y: (float(y.mean()), nw_t(y, lag), len(y))  # noqa: E731
    return {"2019-07–2022": f(x[x.index < lp.SPLIT]), "2023–2026/04": f(x[x.index >= lp.SPLIT]), "全期": f(x)}


def fmt(v, pct=False) -> str:
    return "—" if v[0] != v[0] else (f"{v[0]:+.2%}" if pct else f"{v[0]:+.3f}") + f"（{v[1]:.1f}，{v[2]}）"


def fama_macbeth(P) -> pd.Series:
    out = {}
    for d, g in P.dropna(subset=["r60"]).groupby("d"):
        if len(g) < 50:
            continue
        r = lambda c: (g[c].rank(pct=True) - 0.5).fillna(0.0).to_numpy(float)  # noqa: E731
        Xm = np.column_stack([np.ones(len(g)), g["p_sue"] - 0.5, g["X"] - 0.5, r("lm"), r("bm"), r("mom"),
                              pd.get_dummies(g["sector"], drop_first=True, dtype=float).to_numpy()])
        b, *_ = np.linalg.lstsq(Xm, g["r60"].to_numpy(float), rcond=None)
        out[d] = b[2]
    return pd.Series(out)


def main():
    import dotenv

    dotenv.load_dotenv(ROOT / ".env")
    client = FinMindClient()
    mkt, tx = lp.market_tri(client), lp.tx_continuous(client)
    mem = pd.read_csv(M1500, dtype={"stock_id": str})
    mtype = mem.drop_duplicates("stock_id", keep="last").set_index("stock_id")["market_type"]
    out = {}
    for lo, hi, path in ((1001, 1500, M1500), (501, 1000, ce.MEMBERSHIP), (1, 500, ce.MEMBERSHIP)):
        ce.MEMBERSHIP = de.MEMBERSHIP = path
        S = ce.Sample(client, lo, hi, mkt, tx)
        sched = [d for d in lp.event_dates(S.days) if START <= d < lp.HOLDOUT]
        comp = components(S, client)
        P = panel(S, comp, sched, mtype)
        P["rank_tier"] = lo
        out[lo] = P
        print(f"[I043] {lo}–{hi}：{P['d'].nunique()} 個換倉日、平均 {P.groupby('d').size().mean():.0f} 檔", flush=True)
    ce.MEMBERSHIP = de.MEMBERSHIP = ROOT / "config" / "universe_mcap_membership.csv"
    Pc, Pd, Pt = out[1001], out[501], out[1]
    # 階段 1
    icC = ic_series(Pc, "C", "r60")
    fm = fama_macbeth(Pc)
    s1_ic, s1_fm = segs(icC), segs(fm)
    p1 = (s1_fm["2019-07–2022"][0] > 0 and s1_fm["2023–2026/04"][0] > 0 and s1_fm["全期"][1] > 2
          and s1_ic["2019-07–2022"][0] > 0 and s1_ic["2023–2026/04"][0] > 0 and s1_ic["全期"][1] > 2)
    # 階段 2
    icCd, icSd = ic_series(Pd, "C", "r60"), ic_series(Pd, "p_sue", "r60")
    diff = (icCd - icSd).dropna()
    s2 = segs(diff)
    p2 = s2["全期"][1] > 3 and s2["2019-07–2022"][0] > 0 and s2["2023–2026/04"][0] > 0
    cov = lambda P, c: P.groupby("d")[c].apply(lambda x: x.notna().mean()).mean()  # noqa: E731
    L = ["# I043 中小型股多因子合成（自動產生）", "",
         "由 [analysis/smallcap_composite.py](../analysis/smallcap_composite.py) 產生；設計見程式開頭（看結果前固定）。"
         "C = 0.5 × SUE 百分位 + 1/6 ×（MS + 負的淨發行 + 負的資產成長 的百分位），各成分在同名次組、同產業內排百分位，缺值 0.5；X = 後三者平均。"
         "IC 為產業內 Spearman（−1～1，0 為無預測力），對換倉日次一交易日收盤起 60 個交易日報酬；括號為（Newey-West t，換倉日數）；"
         "Fama-MacBeth 係數為 X 百分位差 1 對應的 60 日報酬差（控制 SUE、市值、帳面市值比、12-1 動能、產業）。研究結果，非投資建議。", ""]
    L += ["| 樣本 | 每期檔數 | SUE 有值 | MS 有值 | NSI 有值 | AG 有值 |", "|---|---|---|---|---|---|"]
    for lo, P in out.items():
        L.append(f"| 第 {lo}– 名組 | {P.groupby('d').size().mean():.0f} | {cov(P, 'sue'):.0%} | {cov(P, 'ms'):.0%} | {cov(P, 'nnsi'):.0%} | {cov(P, 'nag'):.0%} |")
    L += ["", "## 階段 1：確認樣本（第 1001–1500 名，從未使用）", "", "| 統計量 | 2019-07–2022 | 2023–2026/04 | 全期 |", "|---|---|---|---|",
          "| **C 的 IC 60 日** | " + " | ".join(fmt(v) for v in s1_ic.values()) + " |",
          "| **Fama-MacBeth X 係數（控制 SUE 等）** | " + " | ".join(fmt(v, True) for v in s1_fm.values()) + " |",
          "| 只報告：SUE 的 IC 60 日 | " + " | ".join(fmt(v) for v in segs(ic_series(Pc, "p_sue", "r60")).values()) + " |",
          "| 只報告：X 的 IC 60 日 | " + " | ".join(fmt(v) for v in segs(ic_series(Pc, "X", "r60")).values()) + " |",
          "| 只報告：等權四成分 IC 60 日 | " + " | ".join(fmt(v) for v in segs(ic_series(Pc, "E", "r60")).values()) + " |",
          "| 只報告：C 的 IC 20 日 | " + " | ".join(fmt(v) for v in segs(ic_series(Pc, "C", "r20"), 1).values()) + " |"]
    for c, nm in (("p_ms", "MS"), ("p_nnsi", "−NSI"), ("p_nag", "−AG")):
        L.append(f"| 只報告：{nm} 的 IC 60 日 | " + " | ".join(fmt(v) for v in segs(ic_series(Pc, c, "r60")).values()) + " |")
    L += ["", "## 階段 2：開發樣本（第 501–1000 名）相對 SUE 的增量", "", "| 統計量 | 2019-07–2022 | 2023–2026/04 | 全期 |", "|---|---|---|---|",
          "| **IC(C) − IC(SUE)，60 日** | " + " | ".join(fmt(v) for v in s2.values()) + " |",
          "| C 的 IC 60 日 | " + " | ".join(fmt(v) for v in segs(icCd).values()) + " |",
          "| SUE 的 IC 60 日 | " + " | ".join(fmt(v) for v in segs(icSd).values()) + " |",
          "| 只報告：等權四成分 IC 60 日 | " + " | ".join(fmt(v) for v in segs(ic_series(Pd, "E", "r60")).values()) + " |"]
    rk = mem.set_index(["year", "stock_id"])["rank"]
    Pd["rk"] = [rk.get((d.year, t.split(".")[0]), np.nan) for d, t in zip(Pd["d"], Pd["ticker"])]
    for lab, mask in (("只報告：第 501–750 名", Pd["rk"] <= 750), ("只報告：第 751–1000 名", Pd["rk"] > 750)):
        L.append(f"| {lab} C 的 IC 60 日 | " + " | ".join(fmt(v) for v in segs(ic_series(Pd, "C", "r60", mask)).values()) + " |")
    for lab, mask in (("只報告：上市", Pd["mkt"].astype(str).str.contains("twse|sii", case=False)), ("只報告：上櫃", Pd["mkt"].astype(str).str.contains("tpex|otc", case=False))):
        L.append(f"| {lab} C 的 IC 60 日 | " + " | ".join(fmt(v) for v in segs(ic_series(Pd, "C", "r60", mask)).values()) + " |")
    L += ["", "## 只報告：前 500 名", "", "| 統計量 | 2019-07–2022 | 2023–2026/04 | 全期 |", "|---|---|---|---|",
          "| C 的 IC 60 日 | " + " | ".join(fmt(v) for v in segs(ic_series(Pt, "C", "r60")).values()) + " |",
          "| SUE 的 IC 60 日 | " + " | ".join(fmt(v) for v in segs(ic_series(Pt, "p_sue", "r60")).values()) + " |"]
    L += ["", "## 判定", "",
          f"- 階段 1（X 係數兩段 > 0、全期 t > 2；C 的 IC 兩段 > 0、全期 t > 2）：{'✓' if p1 else '✗'}",
          f"- 階段 2（IC(C) − IC(SUE) 兩段 > 0、全期 t > 3）：{'✓' if p2 else '✗'}", "",
          f"**結論：{'階段 1、2 通過，依 I042 結果做階段 3（可交易）' if p1 and p2 else '未通過，停止（不做可交易版本）'}**"]
    (ROOT / "docs" / "smallcap_composite.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    Pd.to_pickle(ROOT / "data_cache" / "events" / "i043_panel_501_1000.pkl")
    print("\n".join(L))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
