"""I044 中小型股獲利能力 GP/A（點子卡 research/ideas/I044-smallcap-gross-profitability.md，檢定計畫看結果前固定）。

用法（於專案根目錄；資料與 I043 共用，先跑 analysis/smallcap_composite.py 讓快取齊全）：
    .venv/Scripts/python analysis/smallcap_gpa.py
輸出 docs/smallcap_gpa.md。

設計（依點子卡；補充以「補」標示）：
- 樣本：主樣本第 501–1000 名非金融股；確認第 1001–1500 名；前 500 名只報告；2019-07 ~ 2026-04 月營收換倉日；兩段 2019-07–2022 / 2023–2026/04。
- GP/A = 法定期限已過的最近四季毛利合計 ÷（該季與四季前總資產的平均）；總資產 ≤ 0 或缺四季者剔除；每期 1%／99% 截尾。
  次要（只報告）：OP/A（營業利益近四季 ÷ 同樣的總資產）。產業內百分位。
- 評估：產業內 Spearman IC（GP/A 對第 +2 ~ +61 日報酬；20 日只報告），Newey-West 落後 3；
  Fama-MacBeth：60 日報酬 = GP/A + SUE + MS + (−NSI) + (−AG) + log 市值 + 帳面市值比 + 12-1 月報酬 + 產業固定效果（百分位 − 0.5）。
- 只報告：產業內五分位等權平均 60 日報酬。
- 通過：(1) 主樣本 60 日 IC 兩段 > 0、全期 t > 2；(2) Fama-MacBeth GP/A 全期 t > 2；(3) 第 1001–1500 名 60 日 IC 同號且 t > 1.65。
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
import smallcap_composite as sc  # noqa: E402
from data.fetch_financials import FinMindClient  # noqa: E402


def profitability(S, client) -> tuple[pd.DataFrame, pd.DataFrame]:
    gpa, opa = {}, {}
    for t in S.tickers:
        if S.sector.get(t.split(".")[0], "NA") in msm.FIN:
            continue
        sid = t.split(".")[0]
        fs = client.get("TaiwanStockFinancialStatements", sid, "2017-01-01")
        bs = client.get("TaiwanStockBalanceSheet", sid, "2017-01-01")
        if fs.empty or bs.empty:
            continue
        p = fs.assign(date=pd.to_datetime(fs["date"])).pivot_table(index="date", columns="type", values="value", aggfunc="last")
        b = bs.assign(date=pd.to_datetime(bs["date"]))
        ta = b[b["type"] == "TotalAssets"].drop_duplicates("date", keep="last").set_index("date")["value"].astype(float)
        p = p[p.index.month.isin([3, 6, 9, 12])]
        if p.empty or "GrossProfit" not in p:
            continue
        p = p.asfreq("QE-DEC")
        ta = ta[ta.index.month.isin([3, 6, 9, 12])].reindex(p.index)
        den = ((ta + ta.shift(4)) / 2).where(lambda x: x > 0)
        for name, col, out in (("gpa", "GrossProfit", gpa), ("opa", "OperatingIncome", opa)):
            if col not in p:
                continue
            s4 = p[col].astype(float).rolling(4, min_periods=4).sum()
            out[t] = s4 / den
    f = lambda d: agm.to_daily(pd.DataFrame(d).sort_index(), S.days).reindex(columns=S.tickers)  # noqa: E731
    return f(gpa), f(opa)


def main():
    import dotenv

    dotenv.load_dotenv(ROOT / ".env")
    client = FinMindClient()
    mkt, tx = lp.market_tri(client), lp.tx_continuous(client)
    mem = pd.read_csv(sc.M1500, dtype={"stock_id": str})
    mtype = mem.drop_duplicates("stock_id", keep="last").set_index("stock_id")["market_type"]
    res = {}
    for lo, hi, path in ((501, 1000, ce.MEMBERSHIP), (1001, 1500, sc.M1500), (1, 500, ce.MEMBERSHIP)):
        ce.MEMBERSHIP = de.MEMBERSHIP = path
        S = ce.Sample(client, lo, hi, mkt, tx)
        sched = [d for d in lp.event_dates(S.days) if sc.START <= d < lp.HOLDOUT]
        P = sc.panel(S, sc.components(S, client), sched, mtype)
        gpa, opa = profitability(S, client)
        P["gpa"] = [gpa.at[d, t] if t in gpa.columns else np.nan for d, t in zip(P["d"], P["ticker"])]
        P["opa"] = [opa.at[d, t] if t in opa.columns else np.nan for d, t in zip(P["d"], P["ticker"])]
        P = P[~P["sector"].isin(msm.FIN)].copy()
        for c in ("gpa", "opa"):
            P[c] = P.groupby("d")[c].transform(lambda x: x.clip(x.quantile(0.01), x.quantile(0.99)))
        res[lo] = P
    ce.MEMBERSHIP = de.MEMBERSHIP = ROOT / "config" / "universe_mcap_membership.csv"
    Pm, Pc, Pt = res[501], res[1001], res[1]
    a60 = sc.segs(sc.ic_series(Pm, "gpa", "r60"))
    fm = {}
    for d, g in Pm.dropna(subset=["r60", "gpa"]).groupby("d"):
        if len(g) < 50:
            continue
        r = lambda c: (g[c].rank(pct=True) - 0.5).fillna(0.0).to_numpy(float)  # noqa: E731
        X = np.column_stack([np.ones(len(g)), r("gpa"), g["p_sue"] - 0.5, g["p_ms"] - 0.5, g["p_nnsi"] - 0.5, g["p_nag"] - 0.5, r("lm"), r("bm"), r("mom"),
                             pd.get_dummies(g["sector"], drop_first=True, dtype=float).to_numpy()])
        b, *_ = np.linalg.lstsq(X, g["r60"].to_numpy(float), rcond=None)
        fm[d] = b[1]
    afm = sc.segs(pd.Series(fm))
    c60 = sc.segs(sc.ic_series(Pc, "gpa", "r60"))
    quint = {}
    for d, g in Pm.dropna(subset=["r60", "gpa"]).groupby("d"):
        q = g.groupby("sector")["gpa"].rank(pct=True)
        b = np.ceil(q * 5).clip(1, 5)
        quint[d] = g.groupby(b)["r60"].mean()
    Q = pd.DataFrame(quint).T
    p1 = a60["2019-07–2022"][0] > 0 and a60["2023–2026/04"][0] > 0 and a60["全期"][1] > 2
    p2 = afm["全期"][1] > 2
    p3 = c60["全期"][0] > 0 and c60["全期"][1] > 1.65
    L = ["# I044 中小型股獲利能力 GP/A（自動產生）", "",
         "由 [analysis/smallcap_gpa.py](../analysis/smallcap_gpa.py) 產生；設計見程式開頭（看結果前固定）。"
         "GP/A = 近四季毛利 ÷ 平均總資產（非金融）；IC 為產業內 Spearman（−1～1，0 為無預測力），對換倉日次一交易日收盤起 60 個交易日報酬，括號為（Newey-West t，換倉日數）；"
         "Fama-MacBeth 係數為 GP/A 百分位差 1 對應的 60 日報酬差（控制 SUE、MS、淨發行、資產成長、市值、帳面市值比、動能、產業）。研究結果，非投資建議。", "",
         f"GP/A 有值比例（第 501–1000 名非金融）：{Pm.groupby('d')['gpa'].apply(lambda x: x.notna().mean()).mean():.0%}。", "",
         "| 統計量 | 2019-07–2022 | 2023–2026/04 | 全期 |", "|---|---|---|---|",
         "| **主樣本（第 501–1000 名）IC 60 日** | " + " | ".join(sc.fmt(v) for v in a60.values()) + " |",
         "| **Fama-MacBeth GP/A 係數** | " + " | ".join(sc.fmt(v, True) for v in afm.values()) + " |",
         "| **確認（第 1001–1500 名）IC 60 日** | " + " | ".join(sc.fmt(v) for v in c60.values()) + " |",
         "| 只報告：主樣本 IC 20 日 | " + " | ".join(sc.fmt(v) for v in sc.segs(sc.ic_series(Pm, "gpa", "r20"), 1).values()) + " |",
         "| 只報告：OP/A 主樣本 IC 60 日 | " + " | ".join(sc.fmt(v) for v in sc.segs(sc.ic_series(Pm, "opa", "r60")).values()) + " |",
         "| 只報告：前 500 名 IC 60 日 | " + " | ".join(sc.fmt(v) for v in sc.segs(sc.ic_series(Pt, "gpa", "r60")).values()) + " |", "",
         "只報告：主樣本產業內 GP/A 五分位的等權平均 60 日報酬（1 = 最低）：" + "、".join(f"Q{int(k)} {v:+.2%}" for k, v in Q.mean().items()), "",
         "## 判定", "",
         f"1. 主樣本 60 日 IC 兩段 > 0、全期 t > 2 → {'✓' if p1 else '✗'}",
         f"2. Fama-MacBeth 控制後全期 t > 2 → {'✓' if p2 else '✗'}",
         f"3. 確認樣本 60 日 IC 同號且 t > 1.65 → {'✓' if p3 else '✗'}", "",
         f"**結論：{'通過（另立 I043 v2，只在前瞻資料比較）' if p1 and p2 and p3 else '未通過'}**"]
    (ROOT / "docs" / "smallcap_gpa.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
