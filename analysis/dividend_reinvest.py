"""I060 現金股利發放日的再投資買壓（點子卡 research/ideas/I060-dividend-payment-reinvestment-pressure.md，檢定計畫看結果前固定）。

用法（於專案根目錄；先執行 analysis/fetch_i058_i060.py）：
    .venv/Scripts/python analysis/dividend_reinvest.py
輸出 docs/dividend_reinvest.md。

設計（依點子卡；補充以「補」標示）：
- 發放金額：TaiwanStockDividend（前 1500 名聯集＋16 檔主要 ETF），每筆 =（現金盈餘配息 + 公積配息）× 參與分派股數，記在 CashDividendPaymentDate；
  同日除息金額記在 CashExDividendTradingDate（控制變數）。
- 補：沒有每日全市場總市值，分母改用前一日加權報酬指數水準（D_t = 發放金額 ÷ 指數水準，再在每年內標準化為該年平均 = 1）；
  迴歸含年 × 月固定效果，所以分母的長期趨勢不影響係數方向。涵蓋率前置改為報告每年發放總額與檔數（沒有官方全市場總額可比對）。
- 前置 (2)：隨機 200 筆，AnnouncementDate 早於發放日 ≥ 5 個交易日的比例（門檻 95%）。
- 訊號：每年把交易日依 D_t 排名，Q5 = 前 20%，Q0 = D_t = 0。
- 報酬：加權報酬指數 R = r_t + r_{t+1}；只報告 r_t、r_{t+1}、t+2 ~ t+5。
- 迴歸：R = b × D_t + 同日除息金額（同樣標準化）+ 星期虛擬變數 + 期貨結算日（每月第三個星期三）虛擬變數 + 年 × 月固定效果，Newey-West 落後 5。
- 三段：2007–2018、2019–2022、2023–2026/04。通過：b 三段皆 > 0、合併 t > 2；Q5 − Q0 平均 R 在 2019–2022 與 2023–2026/04 皆 > 0。
- 可交易（通過才判定）：Q5 日 t − 1 收盤買台指期、t + 1 收盤平倉，單邊 0.005% + 1 檔滑價（補：以 1 點 ÷ 指數水準計）。
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
import fetch_i058_i060 as fi  # noqa: E402
import timing_futures as tf  # noqa: E402
from data.fetch_financials import FinMindClient  # noqa: E402
from sue_attention import nw_t  # noqa: E402

SEGS = (("2007–2018", "2007-01-01", "2019-01-01"), ("2019–2022", "2019-01-01", "2023-01-01"), ("2023–2026/04", "2023-01-01", "2026-05-01"))


def ols_nw(y, X, lag=5):
    b, *_ = np.linalg.lstsq(X, y, rcond=None)
    e = y - X @ b
    n, k = X.shape
    inv = np.linalg.pinv(X.T @ X)
    S = (X * e[:, None]).T @ (X * e[:, None])
    for l in range(1, lag + 1):
        w = 1 - l / (lag + 1)
        G = (X[l:] * e[l:, None]).T @ (X[:-l] * e[:-l, None])
        S += w * (G + G.T)
    V = inv @ S @ inv
    return b, np.sqrt(np.diag(V))


def main():
    import dotenv

    dotenv.load_dotenv(ROOT / ".env")
    client = FinMindClient()
    m = pd.read_csv(ROOT / "config" / "universe_mcap_membership_1500.csv", dtype={"stock_id": str})
    ids = fi.ETFS + sorted(m["stock_id"].unique())
    pay, exd, ann_chk = {}, {}, []
    n_rec = 0
    for sid in ids:
        d = client.get("TaiwanStockDividend", sid, fi.DIV_START)
        if d.empty:
            continue
        for r in d.itertuples():
            cash = float(r.CashEarningsDistribution or 0) + float(r.CashStatutorySurplus or 0)
            sh = float(r.ParticipateDistributionOfTotalShares or 0)
            if cash <= 0 or sh <= 0:
                continue
            amt = cash * sh
            pdte = pd.to_datetime(r.CashDividendPaymentDate, errors="coerce")
            xdte = pd.to_datetime(r.CashExDividendTradingDate, errors="coerce")
            if pdte == pdte:
                pay[pdte] = pay.get(pdte, 0.0) + amt
                n_rec += 1
                ann_chk.append((pd.to_datetime(r.AnnouncementDate, errors="coerce"), pdte))
            if xdte == xdte:
                exd[xdte] = exd.get(xdte, 0.0) + amt
    tri = client.get("TaiwanStockTotalReturnIndex", "TAIEX", "2006-06-01", "2026-05-31")
    lvl = pd.Series(tri["price"].astype(float).to_numpy(), index=pd.to_datetime(tri["date"])).sort_index()
    days = lvl.index
    r = lvl.pct_change()
    P = pd.Series(pay).groupby(level=0).sum()
    X_ = pd.Series(exd).groupby(level=0).sum()
    # 非交易日的發放日歸到下一個交易日
    to_td = lambda s: s.groupby(days[np.minimum(days.searchsorted(s.index), len(days) - 1)]).sum().reindex(days, fill_value=0.0)  # noqa: E731
    P, X_ = to_td(P), to_td(X_)
    D = P / lvl.shift(1)
    Xd = X_ / lvl.shift(1)
    df = pd.DataFrame({"D": D, "X": Xd, "r0": r, "r1": r.shift(-1), "rr": r.shift(-2).rolling(4).sum().shift(-3)}).dropna(subset=["D", "r0", "r1"])
    df = df[(df.index >= "2007-01-01") & (df.index < "2026-05-01")]
    for c_ in ("D", "X"):
        df[c_] = (df[c_] / df.groupby(df.index.year)[c_].transform("mean")).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    df["R"] = df["r0"] + df["r1"]
    df["q5"] = df.groupby(df.index.year)["D"].transform(lambda x: x.rank(pct=True) > 0.8) & (df["D"] > 0)
    df["q0"] = df["D"] == 0
    roll = tf.roll_days(df.index) if hasattr(tf, "roll_days") else pd.Series(False, index=df.index)
    df["settle"] = roll.reindex(df.index).fillna(False).astype(float)
    # 前置 (2)
    rng = np.random.default_rng(0)
    smp = [ann_chk[i] for i in rng.choice(len(ann_chk), size=min(200, len(ann_chk)), replace=False)]
    ok = 0
    for a, p in smp:
        if a == a:
            ka, kp = days.searchsorted(a), days.searchsorted(p)
            ok += (kp - ka) >= 5
    pre2 = ok / len(smp)
    yearly = P.groupby(P.index.year).sum()

    def reg(sub):
        dow = pd.get_dummies(sub.index.dayofweek, prefix="d", drop_first=True, dtype=float).to_numpy()
        ym = pd.get_dummies(sub.index.strftime("%Y-%m"), drop_first=True, dtype=float).to_numpy()
        Xm = np.column_stack([np.ones(len(sub)), sub["D"], sub["X"], sub["settle"], dow, ym])
        b, se = ols_nw(sub["R"].to_numpy(float), Xm, 5)
        return float(b[1]), float(b[1] / se[1]), len(sub)
    rows, bpos = [], True
    for nm, a, b in SEGS:
        sub = df[(df.index >= a) & (df.index < b)]
        rb = reg(sub)
        q = float(sub.loc[sub["q5"], "R"].mean() - sub.loc[sub["q0"], "R"].mean())
        rows.append((nm, rb, q, float(sub.loc[sub["q5"], "r0"].mean() - sub.loc[sub["q0"], "r0"].mean()),
                     float(sub.loc[sub["q5"], "r1"].mean() - sub.loc[sub["q0"], "r1"].mean()),
                     float(sub.loc[sub["q5"], "rr"].mean() - sub.loc[sub["q0"], "rr"].mean()), int(sub["q5"].sum())))
        bpos &= rb[0] > 0
    allr = reg(df)
    k1 = bpos and allr[1] > 2
    k2 = rows[1][2] > 0 and rows[2][2] > 0
    L = ["# I060 現金股利發放日的再投資買壓（自動產生）", "",
         "由 [analysis/dividend_reinvest.py](../analysis/dividend_reinvest.py) 產生；設計見程式開頭（看結果前固定）。"
         "D = 當日現金股利發放總額 ÷ 前一日指數水準，每年標準化為平均 1；R = 發放日與次一日的加權報酬指數報酬合計；"
         "係數 b = D 每增加 1（該年平均發放日規模）對 R 的影響，括號為（Newey-West t，交易日數）。研究結果，非投資建議。", "",
         "## 前置", "",
         f"- 發放紀錄 {n_rec:,} 筆（前 1500 名聯集與 {len(fi.ETFS)} 檔 ETF）；每年發放總額（億元）：" + "、".join(f"{y} {v / 1e8:,.0f}" for y, v in yearly.items() if 2007 <= y <= 2026),
         f"- 公告日早於發放日 ≥ 5 個交易日的比例：{pre2:.0%}（隨機 {len(smp)} 筆；門檻 95%）。", "",
         "## 結果", "",
         "| 期間 | b（t，日數） | Q5 − Q0：R | 只報告：r_t | 只報告：r_{t+1} | 只報告：t+2 ~ t+5 | Q5 日數 |", "|---|---|---|---|---|---|---|"]
    for nm, rb, q, q0, q1, qr, n5 in rows:
        L.append(f"| {nm} | {rb[0]:+.4%}（{rb[1]:.1f}，{rb[2]}） | {q:+.3%} | {q0:+.3%} | {q1:+.3%} | {qr:+.3%} | {n5} |")
    L.append(f"| 合併 | {allr[0]:+.4%}（{allr[1]:.1f}，{allr[2]}） | | | | | |")
    L += ["", "## 判定", "",
          f"- b 三段皆 > 0、合併 t > 2 → {'✓' if k1 else '✗'}",
          f"- Q5 − Q0 在 2019–2022 與 2023–2026/04 皆 > 0 → {'✓' if k2 else '✗'}", ""]
    if k1 and k2:
        txr = tf.tx_returns(client)
        out = []
        for nm, a, b in SEGS:
            sub = df[(df.index >= a) & (df.index < b) & df["q5"]]
            net = [float(txr.reindex([t, days[min(days.searchsorted(t) + 1, len(days) - 1)]]).fillna(0).sum()) - 2 * (0.00005 + 1 / lvl.asof(t)) for t in sub.index]
            out.append((nm, float(np.sum(net)) / max((pd.Timestamp(b) - pd.Timestamp(a)).days / 365.25, 1e-9), len(net)))
        L += ["## 可交易（台指期，Q5 日 t − 1 收盤買、t + 1 收盤平倉）", "", "| 期間 | 年化淨報酬 | 交易次數 |", "|---|---|---|"]
        L += [f"| {nm} | {v:+.2%} | {n} |" for nm, v, n in out]
        L.append("")
        L.append(f"**結論：{'通過，可交易版本' + ('成立' if all(v > 0 for _, v, _ in out) else '不成立')}**")
    else:
        L.append("**結論：未通過**")
    (ROOT / "docs" / "dividend_reinvest.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
