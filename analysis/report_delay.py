"""I075 季報公告延遲（相對自身去年同季）（點子卡 research/ideas/I075-quarterly-report-delay-vs-own-history.md，檢定計畫看結果前固定）。

用法（於專案根目錄；公告日已由 analysis/fetch_fin_report_dates.py 抓好，其餘資料皆已快取）：
    .venv/Scripts/python analysis/report_delay.py
輸出 docs/report_delay.md。

設計（依點子卡；補充以「補」標示）：
- 公告日：沿用 I048（analysis/margin_surprise_actual.announcements，每家每季最早一則），財報季 2020Q2 ~ 2025Q4。
- 交易日位置：公告日 ka = 發言日期當日或其後第一個交易日；期限日 kl = 法定期限當日或之前最後一個交易日。
- 慣常日：去年同季 d = kl' − ka'；今年預期日 ke = kl − d。
- 事件：今年的發言日期晚於第 ke + 2 個交易日（該日收盤時仍未公告），且 kl − (ke + 2) ≥ 2；
  進場：ke + 3 收盤（當日跌停 → 延到下一個非跌停日）；若進場日 13:30 前已公告 → 剔除。
  出場：實際反應日（13:30 後或非交易日公告 → 下一交易日）次一日收盤；晚於期限 + 2 個交易日者在期限 + 2 收盤出場。
  補：今年在 I048 公告資料中沒有該季公告紀錄者不列入（無法區分「延遲」與「資料缺漏」）；進場日須為該樣本成員。
- 報酬：每日相對同樣本同產業成員等權平均的超額報酬，從進場次日累加到出場日 = CAR；平均 CAR 以財報季為群做群聚標準誤。
- 兩段以進場日分 2021-08 ~ 2022 / 2023 ~ 2026-03。通過：前 500 名平均 CAR < 0、t ≤ −2.58、兩段皆 < 0；
  第 501–1500 名（第 501–1000 名與第 1001–1500 名兩個樣本的事件合併）同號且 t ≤ −2.0。前置：前 500 名事件數 ≥ 300。
- 只報告：延遲事件與同季準時（非延遲、非提前）公告者的 QEAR（反應日前一日收盤 → 反應日次一日收盤，產業調整）；
  提前 ≥ 3 個交易日公告者的 QEAR 與之後 20 日報酬；延遲天數分組；Q4 與 Q1–Q3；日曆時間組合（補：每日持有當日所有事件股、
  以產業調整報酬計，不另做台指期對沖）；可放空比例（補：前 60 日有借券成交且費率 ≤ 5%，不檢查額度與深度）與
  扣借券費、0.59% 來回成本後的放空淨報酬。補：作為 fv5 多單出場濾網的效果未做。
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
import hedge_construction as hc  # noqa: E402
import leg_probe as lp  # noqa: E402
import margin_surprise as msm  # noqa: E402
import margin_surprise_actual as msa  # noqa: E402
import smallcap_composite as sc  # noqa: E402
from data.fetch_financials import FinMindClient  # noqa: E402

SEG = ("2021-08 ~ 2022", "2023 ~ 2026-03")
Q_TEST0 = pd.Timestamp("2021-06-30")


def demeaned(S) -> np.ndarray:
    R = S.rets.where(S.member.astype(bool)).to_numpy()
    out = np.full(R.shape, np.nan)
    for s in np.unique(S.sec_arr):
        j = np.where(S.sec_arr == s)[0]
        with np.errstate(all="ignore"):
            out[:, j] = R[:, j] - np.nanmean(R[:, j], axis=1, keepdims=True)
    return out


def build(S, a: pd.DataFrame, fee=None, lend60=None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """回傳（延遲事件, 全部公告的 QEAR 與時點分類）。"""
    days = S.days
    DM = demeaned(S)
    C = S.close.to_numpy()
    A = S.adj.to_numpy()
    lim = S.limit
    pos = lambda d: int(days.searchsorted(d, side="left"))  # noqa: E731
    a = a.copy()
    a["ka"] = [pos(d) for d in a["date"]]
    a["kl"] = [int(days.searchsorted(msm.deadline(q), side="right")) - 1 for q in a["q"]]
    a["gap"] = a["kl"] - a["ka"]
    prev = a.assign(q=a["q"] + pd.offsets.QuarterEnd(4)).set_index(["stock_id", "q"])["gap"]
    ev, allq = [], []
    for r in a[a["q"] >= Q_TEST0].itertuples():
        t = r.stock_id + ".TW"
        if t not in S.col or (r.stock_id, r.q) not in prev.index:
            continue
        j = S.col[t]
        d_prev = int(prev.loc[(r.stock_id, r.q)])
        ke = r.kl - d_prev
        k0 = msa.t0_index(days, r.date, r.late)
        if k0 + 1 >= lim or k0 < 2:
            continue
        qear = np.nansum(DM[k0:k0 + 2, j]) if np.isfinite(DM[k0:k0 + 2, j]).any() else np.nan
        post20 = np.nansum(DM[k0 + 2:k0 + 22, j]) if k0 + 22 < lim else np.nan
        timing = "延遲" if r.date > days[min(ke + 2, len(days) - 1)] and r.kl - (ke + 2) >= 2 else ("提前" if r.gap - d_prev >= 3 else "準時")
        if bool(S.member.iat[k0, j]):
            allq.append({"ticker": t, "q": r.q, "timing": timing, "qear": qear, "post20": post20})
        if timing != "延遲":
            continue
        ken = ke + 3
        while ken < lim and C[ken - 1, j] > 0 and C[ken, j] / C[ken - 1, j] - 1 <= -0.095:
            ken += 1
        if ken >= lim or not bool(S.member.iat[ken, j]):
            continue
        if r.date < days[ken] or (r.date == days[ken] and not r.late):
            continue
        kx = min(k0 + 1, r.kl + 2, lim - 1)
        if kx <= ken:
            continue
        car = float(np.nansum(DM[ken + 1:kx + 1, j]))
        row = {"ticker": t, "q": r.q, "entry": days[ken], "ken": ken, "kx": kx, "hold": kx - ken,
               "delay": int(r.ka - ke), "car": car, "qear": qear}
        if fee is not None:
            f = fee.iat[ken, fee.columns.get_loc(t)] if t in fee.columns else np.nan
            l60 = lend60.iat[ken, lend60.columns.get_loc(t)] if t in lend60.columns else 0.0
            row["shortable"] = bool(l60 > 0 and f == f and f <= bc.FEE_MAX)
            row["fee"] = f
        ev.append(row)
    ev = pd.DataFrame(ev)
    ev["seg"] = np.where(ev["entry"] < lp.SPLIT, SEG[0], SEG[1])
    return ev, pd.DataFrame(allq)


def cl_t(x: pd.Series, g: pd.Series) -> tuple[float, float, int]:
    x = x.dropna()
    g = g.reindex(x.index)
    n = len(x)
    if n < 3:
        return (float(x.mean()) if n else np.nan, np.nan, n)
    e = x - x.mean()
    s = e.groupby(g).sum()
    se = float(np.sqrt((s ** 2).sum()) / n)
    return float(x.mean()), float(x.mean() / se) if se > 0 else np.nan, n


def main():
    import dotenv

    dotenv.load_dotenv(ROOT / ".env")
    client = FinMindClient()
    msa.Q_FIRST, msa.Q_LAST = pd.Timestamp("2020-06-30"), pd.Timestamp("2025-12-31")
    a = msa.announcements()
    mkt, tx = lp.market_tri(client), lp.tx_continuous(client)
    S1 = ce.Sample(client, 1, 500, mkt, tx)
    fee = hc.lending_fees(client, S1.tickers, S1.days)
    _, lend60 = bc.load_short_data(client, S1.tickers, S1.days)
    ev, allq = build(S1, a, fee, lend60)
    S2 = ce.Sample(client, 501, 1000, mkt, tx)
    ev2, _ = build(S2, a)
    ce.MEMBERSHIP = de.MEMBERSHIP = sc.M1500
    S3 = ce.Sample(client, 1001, 1500, mkt, tx)
    ce.MEMBERSHIP = de.MEMBERSHIP = ROOT / "config" / "universe_mcap_membership.csv"
    ev3, _ = build(S3, a)
    evc = pd.concat([ev2.assign(s="501–1000"), ev3.assign(s="1001–1500")], ignore_index=True)
    pre = len(ev) >= 300
    main_ = cl_t(ev["car"], ev["q"])
    seg = {s: cl_t(ev.loc[ev["seg"] == s, "car"], ev["q"]) for s in SEG}
    conf = cl_t(evc["car"], evc["q"])
    conf_seg = {s: cl_t(evc.loc[evc["seg"] == s, "car"], evc["q"]) for s in SEG}
    k1 = pre and main_[0] < 0 and main_[1] <= -2.58 and all(seg[s][0] < 0 for s in SEG)
    k2 = conf[0] < 0 and conf[1] <= -2.0
    # 只報告
    qa = allq.groupby("timing")[["qear", "post20"]].agg(["mean", "count"])
    buckets = pd.cut(ev["delay"], [2, 5, 10, 1000], labels=["3–5 日", "6–10 日", "> 10 日"])
    byb = ev.groupby(buckets, observed=True)["car"].agg(["mean", "count"])
    q4 = ev["q"].dt.month == 12
    days = S1.days
    DM1 = demeaned(S1)
    calr = {}
    for r in ev.itertuples():
        j = S1.col[r.ticker]
        for k in range(r.ken + 1, r.kx + 1):
            calr.setdefault(days[k], []).append(DM1[k, j])
    cs = pd.Series({d: np.nanmean(v) for d, v in calr.items()}).sort_index()
    sh = ev[ev["shortable"]]
    net = -sh["car"] - sh["fee"].fillna(0) / 100 * sh["hold"] / 252 - 0.0059
    pct = lambda v: "—" if v != v else f"{v:+.2%}"  # noqa: E731
    fmt = lambda v: f"{pct(v[0])}（{v[1]:.2f}，{v[2]}）" if v[2] else "—"  # noqa: E731
    L = ["# I075 季報公告延遲（相對自身去年同季）（自動產生）", "",
         "由 [analysis/report_delay.py](../analysis/report_delay.py) 產生；設計見程式開頭（看結果前固定）。"
         "CAR = 進場（預期公告日後第 3 個交易日收盤）到出場（實際公告反應日次一日收盤，最晚期限後第 2 個交易日）的產業調整報酬累加；"
         "括號為（以財報季為群的群聚 t，事件數）。研究結果，非投資建議。", "",
         f"前置：前 500 名延遲事件 {len(ev)} 件（門檻 300）→ {'✓' if pre else '✗'}；平均持有 {ev['hold'].mean():.1f} 個交易日；"
         f"第 501–1000 名 {len(ev2)} 件、第 1001–1500 名 {len(ev3)} 件。", "",
         "| 樣本 | " + " | ".join(SEG) + " | 全期 |", "|---|---|---|---|",
         "| **前 500 名平均 CAR** | " + " | ".join(fmt(seg[s]) for s in SEG) + f" | {fmt(main_)} |",
         "| **確認：第 501–1500 名** | " + " | ".join(fmt(conf_seg[s]) for s in SEG) + f" | {fmt(conf)} |",
         "| 只報告：第 501–1000 名 | — | — | " + fmt(cl_t(ev2["car"], ev2["q"])) + " |",
         "| 只報告：第 1001–1500 名 | — | — | " + fmt(cl_t(ev3["car"], ev3["q"])) + " |",
         "| 只報告：前 500 名 Q4（年報） | — | — | " + fmt(cl_t(ev.loc[q4, "car"], ev["q"])) + " |",
         "| 只報告：前 500 名 Q1–Q3 | — | — | " + fmt(cl_t(ev.loc[~q4, "car"], ev["q"])) + " |", "",
         "只報告（前 500 名）：", "",
         "- 公告時點分類的 QEAR 與之後 20 日產業調整報酬（平均，件數）：" + "；".join(
             f"{k} QEAR {pct(qa.loc[k, ('qear', 'mean')])}、之後 20 日 {pct(qa.loc[k, ('post20', 'mean')])}（{int(qa.loc[k, ('qear', 'count')])}）" for k in qa.index) + "。",
         "- 延遲天數（實際公告距預期日的交易日數）分組平均 CAR：" + "；".join(f"{k} {pct(v['mean'])}（{int(v['count'])}）" for k, v in byb.iterrows()) + "。",
         f"- 日曆時間組合（每日持有當日所有事件股、產業調整報酬等權）：有部位 {len(cs)} 日，日平均 {cs.mean():+.3%}，年化 Sharpe {cs.mean() / cs.std() * np.sqrt(252):.2f}（負值 = 放空有利）。",
         f"- 可放空比例 {ev['shortable'].mean():.0%}；可放空事件扣借券費與 0.59% 來回成本後的放空淨報酬平均 {pct(float(net.mean()))}（{len(net)} 件）。", "",
         "## 判定", "",
         f"- 前 500 名平均 CAR < 0、t ≤ −2.58、兩段皆 < 0 → {'✓' if k1 else '✗'}",
         f"- 第 501–1500 名同號且 t ≤ −2.0 → {'✓' if k2 else '✗'}", "",
         f"**結論：{'通過' if k1 and k2 else '未通過'}**"]
    (ROOT / "docs" / "report_delay.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
