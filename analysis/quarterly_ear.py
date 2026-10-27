"""I070 季報公告的價格反應（季報 EAR）對 SUE 與月營收 EAR 的增量（點子卡 research/ideas/I070-quarterly-report-announcement-return.md，檢定計畫看結果前固定）。

用法（於專案根目錄；公告日已由 analysis/fetch_fin_report_dates.py 抓好，其餘資料皆已快取）：
    .venv/Scripts/python analysis/quarterly_ear.py
輸出 docs/quarterly_ear.md。

設計（依點子卡；補充以「補」標示）：
- 公告日：沿用 I048（analysis/margin_surprise_actual.announcements 的主旨篩選與季度歸屬，每家每季取最早一則），財報季 2020Q2 ~ 2025Q4、
  t0 ≤ 2026-04-30；發言時間 ≥ 13:30 或非交易日 → t0 為下一交易日。補：含金融股；不剔除低覆蓋率的季（覆蓋率另報告）。
- QEAR = 收盤(t0−1) → 收盤(t0+1) 的還原價報酬，減同產業、同樣本當日成員的等權平均（同一視窗）。
- 被解釋變數 y = 收盤(t0+1) → 收盤(t0+61) 的產業調整報酬（同樣方法）。
- H1：每個財報季一個截面（補：以財報季分組，季內所有公告事件），y 與自變數皆為產業內百分位 − 0.5；
  控制 t0 前一日的最新月營收 SUE、最新月營收 EAR（t0 前最近一個月營收換倉日的 I063 EAR）、t0−1 前 60 日產業調整報酬、log 市值；
  Fama-MacBeth 跨季平均，Newey-West 落後 2；兩段以 t0 所在季中位日分 2020-07 ~ 2022 / 2023 ~ 2026/04（補：以季的最大 t0 歸段）。
  通過：全期 t ≥ 2.58、兩段同號且第二段 t ≥ 1.5、第 1001–1500 名同號且 t ≥ 2.0。
- H2 只在 H1 通過時做（可交易建構，見點子卡）。
- 只報告：QEAR 三分組的平均 y；QEAR 與 I048 MS* 的每季產業內等級相關平均（非金融）；盤後公告比例；反應日（t0、t0+1）觸及漲跌停的比例；
  只用年報（Q4）或只用 Q1–Q3 的 H1 係數；第 501–1000 名。
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
import leg_probe as lp  # noqa: E402
import margin_surprise as msm  # noqa: E402
import margin_surprise_actual as msa  # noqa: E402
import smallcap_composite as sc  # noqa: E402
from data.fetch_financials import FinMindClient  # noqa: E402
from ear_standalone import ear_scores  # noqa: E402
from sue_attention import nw_t  # noqa: E402

SEG = ("2020-07 ~ 2022", "2023 ~ 2026/04")


def events(S, a: pd.DataFrame) -> pd.DataFrame:
    days = S.days
    A = S.adj.to_numpy()
    C = S.close.to_numpy()
    M = S.member.to_numpy(bool)
    sec = S.sec_arr
    secs = {s: np.where(sec == s)[0] for s in np.unique(sec)}
    tsec = pd.Series(sec, index=S.tickers)
    sched = [d for d in lp.event_dates(days) if pd.Timestamp("2019-01-01") <= d < lp.HOLDOUT]
    ear = ear_scores(S.adj, S.member, tsec, sched)
    ear_days = pd.DatetimeIndex(sorted(ear))
    rows = []
    for r in a.itertuples():
        t = r.stock_id + ".TW"
        if t not in S.col:
            continue
        k0 = msa.t0_index(days, r.date, r.late)
        if k0 < 62 or k0 + 1 >= len(days) or days[k0] >= lp.HOLDOUT:
            continue
        j = S.col[t]
        if not M[k0, j]:
            continue
        peers = secs[sec[j]]
        peers = peers[M[k0, peers]]

        def adj_ret(x, y_):
            if y_ >= S.limit:
                return np.nan
            v = A[y_, peers] / A[x, peers] - 1
            own = A[y_, j] / A[x, j] - 1
            return own - np.nanmean(v) if np.isfinite(own) else np.nan
        ke = int(ear_days.searchsorted(days[k0 - 1], side="right")) - 1
        e_m = ear[ear_days[ke]].get(t, np.nan) if ke >= 0 else np.nan
        ch = C[k0 - 1:k0 + 2, j]
        rows.append({"ticker": t, "q": r.q, "t0": days[k0], "sector": sec[j], "late": bool(r.late),
                     "qear": adj_ret(k0 - 1, k0 + 1), "y": adj_ret(k0 + 1, k0 + 61),
                     "sue": S.sue.iat[k0 - 1, j], "ear_m": e_m, "pre": adj_ret(k0 - 61, k0 - 1), "lm": S.lmcap.iat[k0, j],
                     "limit": bool((np.abs(ch[1:] / ch[:-1] - 1) >= 0.095).any())})
    ev = pd.DataFrame(rows).dropna(subset=["qear"])
    seg_q = ev.groupby("q")["t0"].transform("max")
    ev["seg"] = np.where(seg_q < lp.SPLIT, SEG[0], SEG[1])
    return ev


def fm(ev: pd.DataFrame, var: str = "qear") -> pd.Series:
    out = {}
    for q, g in ev.dropna(subset=["y"]).groupby("q"):
        if len(g) < 50:
            continue
        sec = g["sector"]
        r = lambda c: (g[c].groupby(sec).rank(pct=True) - 0.5).fillna(0.0).to_numpy(float)  # noqa: E731
        X = np.column_stack([np.ones(len(g)), r(var), r("sue"), r("ear_m"), r("pre"), r("lm")])
        b, *_ = np.linalg.lstsq(X, r("y"), rcond=None)
        out[g["t0"].max()] = b[1]
    return pd.Series(out).sort_index()


def segs(x):
    f = lambda y: (float(y.mean()), nw_t(y, 2), len(y)) if len(y) > 2 else (np.nan, np.nan, len(y))  # noqa: E731
    return {SEG[0]: f(x[x.index < lp.SPLIT]), SEG[1]: f(x[x.index >= lp.SPLIT]), "全期": f(x)}


def fmt(v):
    return "—" if v[0] != v[0] else f"{v[0]:+.4f}（{v[1]:.2f}，{v[2]}）"


def main():
    import dotenv

    dotenv.load_dotenv(ROOT / ".env")
    client = FinMindClient()
    msa.Q_FIRST, msa.Q_LAST = pd.Timestamp("2020-06-30"), pd.Timestamp("2025-12-31")
    a = msa.announcements()
    mkt, tx = lp.market_tri(client), lp.tx_continuous(client)
    res = {}
    for lo, hi, path in ((1, 500, ce.MEMBERSHIP), (1001, 1500, sc.M1500), (501, 1000, ce.MEMBERSHIP)):
        ce.MEMBERSHIP = de.MEMBERSHIP = path
        S = ce.Sample(client, lo, hi, mkt, tx)
        res[lo] = events(S, a)
        print(lo, len(res[lo]), flush=True)
    ce.MEMBERSHIP = de.MEMBERSHIP = ROOT / "config" / "universe_mcap_membership.csv"
    ev, evc, evv = res[1], res[1001], res[501]
    h1, hc_, hv = segs(fm(ev)), segs(fm(evc)), segs(fm(evv))
    sign = np.sign(h1["全期"][0])
    k1 = h1["全期"][1] * sign >= 2.58
    k2 = np.sign(h1[SEG[0]][0]) == sign and np.sign(h1[SEG[1]][0]) == sign and h1[SEG[1]][1] * sign >= 1.5
    k3 = np.sign(hc_["全期"][0]) == sign and hc_["全期"][1] * sign >= 2.0
    # 只報告
    q4 = ev["q"].dt.month == 12
    h_q4, h_q13 = segs(fm(ev[q4])), segs(fm(ev[~q4]))
    terc = ev.dropna(subset=["y"]).assign(g=lambda x: x.groupby("q")["qear"].transform(lambda s: pd.qcut(s.rank(method="first"), 3, labels=False)))
    tm = terc.groupby("g")["y"].mean()
    mem = pd.read_csv(sc.M1500, dtype={"stock_id": str})
    firms = mem[~mem["sector"].isin(msm.FIN)].drop_duplicates("stock_id", keep="last")[["stock_id", "sector"]]
    ms = msa.ms_star(client, firms)
    ms["ticker"] = ms["stock_id"] + ".TW"
    mm = ev.merge(ms[["ticker", "q", "ms"]], on=["ticker", "q"], how="inner").dropna(subset=["ms"])
    rho = float(mm.groupby("q").apply(lambda g: g["qear"].rank().corr(g["ms"].rank())).mean())
    cov = ev.groupby("q").size()
    L = ["# I070 季報公告的價格反應（季報 EAR）（自動產生）", "",
         "由 [analysis/quarterly_ear.py](../analysis/quarterly_ear.py) 產生；設計見程式開頭（看結果前固定）。"
         "QEAR = 公告反應日前一日收盤到反應日次一日收盤（2 日）的產業調整報酬；係數為每季 Fama-MacBeth（被解釋變數為之後 60 個交易日產業調整報酬的產業內百分位 − 0.5，"
         "控制月營收 SUE、月營收 EAR、前 60 日報酬、市值，皆為產業內百分位 − 0.5），括號為（Newey-West t，季數）。研究結果，非投資建議。", "",
         f"事件數：前 500 名 {len(ev):,}（每季 {cov.min()}–{cov.max()}）、第 1001–1500 名 {len(evc):,}、第 501–1000 名 {len(evv):,}；"
         f"前 500 名盤後（13:30 後）公告比例 {ev['late'].mean():.0%}、反應日觸及漲跌停比例 {ev['limit'].mean():.1%}。", "",
         "| 樣本 | " + " | ".join(SEG) + " | 全期 |", "|---|---|---|---|",
         "| **前 500 名 QEAR 係數** | " + " | ".join(fmt(v) for v in h1.values()) + " |",
         "| **確認：第 1001–1500 名** | " + " | ".join(fmt(v) for v in hc_.values()) + " |",
         "| 只報告：第 501–1000 名 | " + " | ".join(fmt(v) for v in hv.values()) + " |",
         "| 只報告：前 500 名只用年報（Q4） | " + " | ".join(fmt(v) for v in h_q4.values()) + " |",
         "| 只報告：前 500 名只用 Q1–Q3 | " + " | ".join(fmt(v) for v in h_q13.values()) + " |", "",
         "只報告：前 500 名 QEAR 三分組（0 = 最低）之後 60 日產業調整報酬平均：" + "、".join(f"T{int(k)} {v:+.2%}" for k, v in tm.items())
         + f"；QEAR 與 I048 利潤率驚奇 MS* 的每季等級相關平均 {rho:+.2f}（非金融，{len(mm):,} 筆）。", "",
         "## 判定（H1）", "",
         f"- 全期 t ≥ 2.58（{h1['全期'][1]:.2f}）→ {'✓' if k1 else '✗'}",
         f"- 兩段同號且第二段 t ≥ 1.5 → {'✓' if k2 else '✗'}",
         f"- 第 1001–1500 名同號且 t ≥ 2.0（{hc_['全期'][1]:.2f}）→ {'✓' if k3 else '✗'}", "",
         f"**結論：{'H1 通過（接著做 H2 可交易建構）' if k1 and k2 and k3 else '未通過（H1 不成立，不做 H2）'}**"]
    (ROOT / "docs" / "quarterly_ear.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
