"""I058 融券強制回補的價格壓力（I050 修訂版；點子卡 research/ideas/I058-forced-covering-oos-501-1500.md，檢定計畫看結果前固定）。

用法（於專案根目錄；先執行 analysis/fetch_i058_i060.py）：
    .venv/Scripts/python analysis/forced_covering.py
輸出 docs/forced_covering.md。

設計（依點子卡；補充以「補」標示）：
- 事件：TaiwanStockMarginPurchaseShortSale 官方 Note「X」（停止融券賣出）的連續區間，s = 第一個 X 日（最後回補日，事前公告）；
  s 在 2019-01-02 ~ 2026-04-30，且 s 前 20 個交易日內沒有另一個停券窗開始。s 當日為該名次組成員。
- 類別：除權息類（窗內或窗後 10 個交易日內有除權息交易日，TaiwanStockDividendResult）；股東常會類（2–5 月、非除權息類）；其他。
- 前置（不看報酬）：除權息類 TaiwanStockDividend 的 AnnouncementDate 早於 s − 5 個交易日的比例（門檻 90%）；
  股東常會類以「前一年同類窗的 s 加 52 週」預測，命中 ±3 個交易日的比例（門檻 70%）。補：公開資訊觀測站股東會公告 30 筆人工核對未做。
- 強度 MSR = s − 6 日融券餘額 ÷ 已發行股數（融券餘額單位為張，× 1,000 股）；在「類別 × 年 × 名次組」內排名，高 = 前 20%；
  低 = 後 20%（MSR = 0 者超過 20% 時，低 = 全部 MSR = 0 者）。
- 報酬：產業調整日報酬 = 含息日報酬 − 同名次組同產業成員等權平均；CAR[s − 4, s]（s − 5 收盤進場、s 收盤出場）；
  反轉 [s + 1, s + 5]、先行 [s − 15, s − 5]、股東常會類 [s + 1, s + 3]（只報告）。市場調整版用 β × 加權指數含息（corp_event_study.Sample.car）。
- 主檢定 P1（第 501–1000 名）：CAR[s − 4, s] 對「高組」虛擬變數（只含高、低組事件）的迴歸係數 = 高 − 低，標準誤依 s 日群聚；兩段 > 0、全期 t > 2。
- P2（第 501–1000 名）：CAR = MSR 百分位 + 借券賣出餘額比百分位 + 現金殖利率（除權息類，其餘 0）+ 除權息類虛擬變數 + SUE 百分位 + 前 20 日報酬百分位
  + log 市值百分位 + 產業與「類別 × 年」固定效果，s 日群聚；MSR 係數 t > 2。
- P3（第 1001–1500 名）、P4（前 500 名）：高 − 低 同號、t > 1.65。
- 無條件（只報告、I059 啟動條件）：第 501–1000 名全部事件 CAR[s − 4, s] 平均（產業調整與市場調整），s 日群聚 t。
- 批次 Holm：P1 單尾 p（本批 5 張卡、家族 5%，最嚴格順位需 ≤ 0.01），報告。
- 可交易（P1–P4 全成立才判定）：前 500 名高組，市場調整 CAR[s − 4, s] − 0.59%（另報告 − 0.59% − 0.78%），s 日群聚 t；兩段 > 0、全期 t > 2。
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
import corp_event_study as ce  # noqa: E402
import dividend_events as de  # noqa: E402
import dividend_surprise as dsu  # noqa: E402
import leg_probe as lp  # noqa: E402
import lending_legs as ll  # noqa: E402
import smallcap_composite as scm  # noqa: E402
from data.fetch_financials import FinMindClient  # noqa: E402

START, END = pd.Timestamp("2019-01-02"), pd.Timestamp("2026-04-30")


def phi(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def sector_adj(S) -> pd.DataFrame:
    r = S.rets.where(S.member)
    sec = pd.Series({t: S.sector.get(t.split(".")[0], "NA") for t in S.tickers})
    out = pd.DataFrame(np.nan, index=r.index, columns=r.columns)
    for _, cols in sec.groupby(sec).groups.items():
        cols = list(cols)
        out[cols] = S.rets[cols].sub(r[cols].mean(axis=1), axis=0)     # 平均只用成員；個股報酬不限成員日（事件視窗可能跨年）
    return out


def events_for(S, client) -> pd.DataFrame:
    days = S.days
    shares = ll.load_shares(client, S.tickers, days)
    rows = []
    for t in S.tickers:
        sid = t.split(".")[0]
        d = client.get("TaiwanStockMarginPurchaseShortSale", sid, lp.EV_START, lp.EV_END)
        if d.empty:
            continue
        d = d.assign(date=pd.to_datetime(d["date"])).drop_duplicates("date").set_index("date").reindex(days)
        x = d["Note"].astype(str).str.contains("X").fillna(False).to_numpy()
        bal = d["ShortSaleTodayBalance"].astype(float).to_numpy()
        dv = client.get("TaiwanStockDividendResult", sid, lp.EV_START, lp.EV_END)
        exd = pd.DatetimeIndex(pd.to_datetime(dv["date"])) if not dv.empty else pd.DatetimeIndex([])
        cash = {}
        if not dv.empty:
            for r in dv.itertuples():
                cash[pd.Timestamp(r.date)] = (float(r.before_price) - float(r.after_price)) / float(r.before_price) if float(r.before_price) > 0 else 0.0
        last_start = -999
        i = 0
        j_col = S.col[t]
        while i < len(x):
            if not x[i]:
                i += 1
                continue
            j = i
            while j + 1 < len(x) and x[j + 1]:
                j += 1
            s_day = days[i]
            if START <= s_day <= END and i - last_start > 20 and i >= 16 and bool(S.member.iat[i, j_col]):
                hi = days[min(j + 10, len(days) - 1)]
                ex_in = exd[(exd >= s_day) & (exd <= hi)]
                cat = "除權息" if len(ex_in) else ("股東常會" if s_day.month in (2, 3, 4, 5) else "其他")
                sh = shares[t].iat[i - 6] if t in shares else np.nan
                b6 = bal[i - 6]
                msr = b6 * 1000 / sh if sh == sh and sh > 0 and b6 == b6 else np.nan
                rows.append({"ticker": t, "k": i, "s": s_day, "cat": cat, "msr": msr, "ex": ex_in[0] if len(ex_in) else pd.NaT,
                             "yld": cash.get(ex_in[0], 0.0) if len(ex_in) else 0.0})
            last_start = i
            i = j + 1
    return pd.DataFrame(rows)


def attach(S, ev: pd.DataFrame, ar: pd.DataFrame, sbl_ratio: pd.DataFrame | None) -> pd.DataFrame:
    A = ar.to_numpy()
    lim = S.limit
    rows = []
    for r in ev.itertuples():
        j, k = S.col[r.ticker], r.k
        f = lambda a, b: float(np.nansum(A[a:b + 1, j])) if a >= 0 and b < lim else np.nan  # noqa: E731
        car_m = float(S.car(j, k - 4, k)) if k + 1 <= lim else np.nan
        c0, c1 = S.close.iat[k - 5, j], S.close.iat[k - 6, j]
        rows.append({"car": f(k - 4, k), "rev": f(k + 1, k + 5), "pre": f(k - 15, k - 5), "agm": f(k + 1, k + 3), "car_m": car_m,
                     "limit_up": bool(c1 > 0 and c0 / c1 - 1 >= 0.095), "sue": S.sue.iat[k, j], "p20": S.pre20.iat[k, j], "lm": S.lmcap.iat[k, j],
                     "sbl": sbl_ratio[r.ticker].iat[k - 6] if sbl_ratio is not None and r.ticker in sbl_ratio else np.nan,
                     "sector": S.sector.get(r.ticker.split(".")[0], "NA")})
    out = pd.concat([ev.reset_index(drop=True), pd.DataFrame(rows)], axis=1)
    out["seg"] = np.where(out["s"] < lp.SPLIT, "2019–2022", "2023–2026/04")
    out["year"] = out["s"].dt.year
    out["grp"] = ""
    for _, g in out.groupby(["cat", "year"]):
        m = g["msr"]
        zero = (m == 0).mean()
        hi = m.rank(pct=True) > 0.8
        lo = (m == 0) if zero > 0.2 else (m.rank(pct=True) <= 0.2)
        out.loc[g.index[hi.to_numpy()], "grp"] = "高"
        out.loc[g.index[lo.to_numpy() & ~hi.to_numpy()], "grp"] = "低"
    return out


def hl(ev: pd.DataFrame, col="car") -> tuple[float, float, int]:
    x = ev[ev["grp"].isin(["高", "低"])].dropna(subset=[col])
    if x["grp"].nunique() < 2 or len(x) < 30:
        return float("nan"), float("nan"), len(x)
    X = np.column_stack([np.ones(len(x)), (x["grp"] == "高").astype(float)])
    b, se = dsu.ols_cluster(x[col].to_numpy(float), X, x["s"].astype(str).to_numpy())
    return float(b[1]), float(b[1] / se[1]), len(x)


def mean_t(x: pd.Series, cl: pd.Series) -> tuple[float, float, int]:
    m = x.notna()
    if m.sum() < 30:
        return float("nan"), float("nan"), int(m.sum())
    X = np.ones((int(m.sum()), 1))
    b, se = dsu.ols_cluster(x[m].to_numpy(float), X, cl[m].astype(str).to_numpy())
    return float(b[0]), float(b[0] / se[0]), int(m.sum())


def segs(ev, f):
    return {"2019–2022": f(ev[ev["seg"] == "2019–2022"]), "2023–2026/04": f(ev[ev["seg"] == "2023–2026/04"]), "全期": f(ev)}


def fmt(v, pct=True):
    return "—" if v[0] != v[0] else (f"{v[0]:+.2%}" if pct else f"{v[0]:+.4f}") + f"（{v[1]:.1f}，{v[2]}）"


def p2_reg(ev):
    x = ev.dropna(subset=["car", "msr"]).copy()
    r = lambda c: (x[c].rank(pct=True) - 0.5).fillna(0.0).to_numpy(float)  # noqa: E731
    fe = pd.get_dummies(x["sector"], drop_first=True, dtype=float)
    fe2 = pd.get_dummies(x["cat"] + x["year"].astype(str), drop_first=True, dtype=float)
    X = np.column_stack([np.ones(len(x)), r("msr"), r("sbl"), x["yld"].fillna(0.0).to_numpy(float), (x["cat"] == "除權息").astype(float),
                         r("sue"), r("p20"), r("lm"), fe.to_numpy(), fe2.to_numpy()])
    b, se = dsu.ols_cluster(x["car"].to_numpy(float), X, x["s"].astype(str).to_numpy())
    return float(b[1]), float(b[1] / se[1]), len(x)


def precheck(client, evs: pd.DataFrame, days: pd.DatetimeIndex) -> dict:
    ex = evs[evs["cat"] == "除權息"]
    ok, n = 0, 0
    cache = {}
    for r in ex.itertuples():
        sid = r.ticker.split(".")[0]
        if sid not in cache:
            d = client.get("TaiwanStockDividend", sid, "2005-01-01")
            cache[sid] = d
        d = cache[sid]
        if d.empty or "AnnouncementDate" not in d:
            continue
        cand = []
        for col in ("CashExDividendTradingDate", "StockExDividendTradingDate"):
            if col in d:
                dd = pd.to_datetime(d[col], errors="coerce")
                m = (dd - r.ex).abs() <= pd.Timedelta(days=3)
                cand += list(pd.to_datetime(d.loc[m, "AnnouncementDate"], errors="coerce").dropna())
        if not cand:
            continue
        n += 1
        k = int(days.searchsorted(r.s))
        ok += min(cand) < days[max(k - 5, 0)]
    agm = evs[evs["cat"] == "股東常會"].sort_values("s")
    hit, tot = 0, 0
    for t, g in agm.groupby("ticker"):
        ss = list(g["s"])
        for a, b in zip(ss[:-1], ss[1:]):
            if 300 <= (b - a).days <= 430:
                pred = a + pd.Timedelta(weeks=52)
                kp, kb = int(days.searchsorted(pred)), int(days.searchsorted(b))
                tot += 1
                hit += abs(kp - kb) <= 3
    return {"ex_ok": ok / n if n else float("nan"), "ex_n": n, "agm_hit": hit / tot if tot else float("nan"), "agm_n": tot}


def main():
    import dotenv

    dotenv.load_dotenv(ROOT / ".env")
    client = FinMindClient()
    mkt, tx = lp.market_tri(client), lp.tx_continuous(client)
    res = {}
    for lo, hi, path in ((501, 1000, ce.MEMBERSHIP), (1001, 1500, scm.M1500), (1, 500, ce.MEMBERSHIP)):
        ce.MEMBERSHIP = de.MEMBERSHIP = path
        S = ce.Sample(client, lo, hi, mkt, tx)
        ar = sector_adj(S)
        ev = events_for(S, client)
        sbl = None
        if lo == 501:
            q = {}
            for t in S.tickers:
                d = client.get("TaiwanDailyShortSaleBalances", t.split(".")[0], "2018-06-01", "2026-05-31")
                if not d.empty:
                    q[t] = pd.Series(d["SBLShortSalesCurrentDayBalance"].astype(float).to_numpy(), index=pd.to_datetime(d["date"]))
            sh = ll.load_shares(client, S.tickers, S.days)
            sbl = pd.DataFrame(q).reindex(index=S.days, columns=S.tickers).ffill() / sh
        res[lo] = (attach(S, ev, ar, sbl), S.days)
        print(f"[I058] {lo}–{hi}：事件 {len(ev)}", flush=True)
    ce.MEMBERSHIP = de.MEMBERSHIP = ROOT / "config" / "universe_mcap_membership.csv"
    E2, days = res[501]
    E3, E1 = res[1001][0], res[1][0]
    pc = precheck(client, pd.concat([E1, E2, E3]), days)
    p1 = segs(E2, hl)
    p2 = p2_reg(E2)
    p3, p4 = hl(E3), hl(E1)
    pv1 = 1 - phi(p1["全期"][1]) if p1["全期"][1] == p1["全期"][1] else 1.0
    k1 = p1["2019–2022"][0] > 0 and p1["2023–2026/04"][0] > 0 and p1["全期"][1] > 2
    k2 = p2[1] > 2
    k3 = np.sign(p3[0]) == np.sign(p1["全期"][0]) and p3[1] > 1.65
    k4 = np.sign(p4[0]) == np.sign(p1["全期"][0]) and p4[1] > 1.65
    unc = segs(E2, lambda x: mean_t(x["car"], x["s"]))
    unc_m = segs(E2, lambda x: mean_t(x["car_m"], x["s"]))
    L = ["# I058 融券強制回補的價格壓力（自動產生）", "",
         "由 [analysis/forced_covering.py](../analysis/forced_covering.py) 產生；設計見程式開頭（看結果前固定）。"
         "s = 官方停券首日（最後回補日）；CAR = 累積異常報酬（產業調整：減同名次組同產業等權平均），主要視窗 [s − 4, s]；高 − 低 = 融券餘額占股本前 20% 減後 20%；"
         "括號為（依 s 日群聚的 t，事件數）。研究結果，非投資建議。", "",
         "## 前置（不看報酬）", "",
         f"- 除權息類：股利公告日早於 s − 5 個交易日的比例 {pc['ex_ok']:.0%}（{pc['ex_n']} 筆可對應；門檻 90%）。",
         f"- 股東常會類：以前一年 s 加 52 週預測，命中 ±3 個交易日 {pc['agm_hit']:.0%}（{pc['agm_n']} 組；門檻 70%）。", "",
         "| 名次組 | 事件數 | 除權息類 | 股東常會類 | 其他 | MSR = 0 比例 | 高組進場日漲停 |", "|---|---|---|---|---|---|---|"]
    for lab, E in (("前 500 名", E1), ("第 501–1000 名", E2), ("第 1001–1500 名", E3)):
        L.append(f"| {lab} | {len(E):,} | {(E['cat'] == '除權息').sum():,} | {(E['cat'] == '股東常會').sum():,} | {(E['cat'] == '其他').sum():,} | "
                 f"{(E['msr'] == 0).mean():.0%} | {E.loc[E['grp'] == '高', 'limit_up'].mean():.1%} |")
    L += ["", "## 主檢定", "", "| 統計量 | 2019–2022 | 2023–2026/04 | 全期 |", "|---|---|---|---|",
          "| **P1 第 501–1000 名 高 − 低 CAR[s−4, s]** | " + " | ".join(fmt(v) for v in p1.values()) + " |",
          f"| **P2 第 501–1000 名 MSR 百分位係數（控制後）** | | | {fmt(p2)} |",
          f"| **P3 第 1001–1500 名 高 − 低** | | | {fmt(p3)} |",
          f"| **P4 前 500 名 高 − 低** | | | {fmt(p4)} |",
          "| 只報告（I059 啟動條件）：第 501–1000 名全部事件 CAR[s−4, s]（產業調整） | " + " | ".join(fmt(v) for v in unc.values()) + " |",
          "| 只報告：同上（市場調整） | " + " | ".join(fmt(v) for v in unc_m.values()) + " |",
          "| 只報告：第 501–1000 名 高 − 低 反轉 [s+1, s+5] | " + " | ".join(fmt(v) for v in segs(E2, lambda x: hl(x, "rev")).values()) + " |",
          "| 只報告：第 501–1000 名 高 − 低 先行 [s−15, s−5] | " + " | ".join(fmt(v) for v in segs(E2, lambda x: hl(x, "pre")).values()) + " |",
          "| 只報告：前 500 名全部事件 CAR[s−4, s]（產業調整） | " + " | ".join(fmt(v) for v in segs(E1, lambda x: mean_t(x["car"], x["s"])).values()) + " |",
          "| 只報告：第 1001–1500 名全部事件 CAR[s−4, s] | " + " | ".join(fmt(v) for v in segs(E3, lambda x: mean_t(x["car"], x["s"])).values()) + " |"]
    for cat in ("除權息", "股東常會", "其他"):
        L.append(f"| 只報告：第 501–1000 名 {cat}類 高 − 低 | " + " | ".join(fmt(v) for v in segs(E2[E2["cat"] == cat], hl).values()) + " |")
    L.append("| 只報告：第 501–1000 名股東常會類全部 [s+1, s+3]（紀念品買盤） | " + " | ".join(fmt(v) for v in segs(E2[E2["cat"] == "股東常會"], lambda x: mean_t(x["agm"], x["s"])).values()) + " |")
    trade = None
    if k1 and k2 and k3 and k4:
        H = E1[E1["grp"] == "高"].copy()
        H["net"] = H["car_m"] - 0.0059
        H["net2"] = H["car_m"] - 0.0059 - 0.0078
        trade = (segs(H, lambda x: mean_t(x["net"], x["s"])), segs(H, lambda x: mean_t(x["net2"], x["s"])))
        L += ["", "## 可交易（前 500 名高組，s − 5 收盤買、s 收盤賣，β × 台指期對沖）", "", "| 成本 | 2019–2022 | 2023–2026/04 | 全期 |", "|---|---|---|---|",
              "| 來回 0.59% | " + " | ".join(fmt(v) for v in trade[0].values()) + " |",
              "| 另加滑價單邊 0.39% | " + " | ".join(fmt(v) for v in trade[1].values()) + " |"]
    L += ["", "## 判定", "",
          f"- P1 兩段 > 0、全期 t > 2 → {'✓' if k1 else '✗'}（單尾 p = {pv1:.4f}；批次 Holm 最嚴格順位需 ≤ 0.01）",
          f"- P2 MSR 係數 t > 2 → {'✓' if k2 else '✗'}",
          f"- P3 第 1001–1500 名同號、t > 1.65 → {'✓' if k3 else '✗'}",
          f"- P4 前 500 名同號、t > 1.65 → {'✓' if k4 else '✗'}",
          f"- I059 啟動條件（第 501–1000 名無條件 CAR t > 2）：{'成立' if unc['全期'][1] > 2 else '不成立'}", ""]
    verdict = "通過" if k1 and k2 and k3 and k4 else ("partial（P1、P2 成立）" if k1 and k2 else "未通過")
    if trade is not None:
        tr = trade[0]
        tradable = tr["2019–2022"][0] > 0 and tr["2023–2026/04"][0] > 0 and tr["全期"][1] > 2
        verdict += f"；可交易版本 {'成立' if tradable else '不成立'}"
    L.append(f"**結論：{verdict}**")
    (ROOT / "docs" / "forced_covering.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
