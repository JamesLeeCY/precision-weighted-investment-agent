"""I048 利潤率驚奇改用季報實際公告日（點子卡 research/ideas/I048-margin-surprise-actual-announcement-date.md，檢定計畫看結果前固定）。

用法（於專案根目錄；先執行 analysis/fetch_fin_report_dates.py）：
    .venv/Scripts/python analysis/margin_surprise_actual.py coverage   # 前置：公告日覆蓋率（不看報酬）
    .venv/Scripts/python analysis/margin_surprise_actual.py test       # 主檢定
輸出 docs/margin_surprise_actual.md。

設計（依點子卡；補充以「補」標示）：
- 公告日：重大訊息主旨含「財務報」且含「通過／決議／承認／提報」，不含「預計／更正／補正／召開／代」；
  依發言日期歸屬季度（補：法定期限 − 100 日 < 發言日 ≤ 期限 + 5 日，取最早的期限），每家每季取最早一筆。
  發言時間 ≥ 13:30 或非交易日 → t0 移到下一個交易日；第 +1 日收盤進場。d = 法定期限次一交易日。
- 覆蓋率：前 500 名非金融股中，有該季財報者裡有公告日的比例；< 80% 的季整季剔除。
- MS*：ΔOPM（單季營業利益率年變動，|ΔOPM| ≤ 50 個百分點）減去「同產業前 8 季（q−8 ~ q−1）合併迴歸 ΔOPM = a + b × 季營收年增率」的預測值，
  再除以該公司前 8 季（至少 4 季）同一殘差的標準差；迴歸樣本為前 1500 名全部非金融股（補：產業前 8 季少於 20 筆時改用全市場；資料起點 2018Q1 的 ΔOPM 不足 8 季時用已有的前 4–7 季，讓 2020Q3 起的標準差有 4 季以上）。
  每季 1%／99% 截尾，產業內 Spearman。
- P1：MS* 與 [t0+2, d+1] 報酬的產業內 IC，只用 d − t0 ≥ 5 個交易日的事件；每季一個截面，Newey-West 落後 2。
- P2：MS* 與 [t0+2, t0+61] 報酬的 IC。只報告：期限版 [d+2, d+61] 的 IC 與兩者差。
- Fama-MacBeth：[t0+2, t0+61] 報酬 = MS* + t0 前最新 SUE + 季營收年增率 + 前 20 日報酬 + log 市值 + 帳面市值比 + 產業虛擬變數（百分位 − 0.5），Newey-West 落後 2。
- 樣本：前 500 名非金融（主）；第 1001–1500 名（確認）；第 501–1000 名只報告。2020Q3 ~ 2026Q1 財報、t0 ≤ 2026-04-30；兩段以 t0 分 2020Q3–2022 / 2023–2026/04。
- 通過：(1) 前 500 名 P1 兩段 > 0、全期 t > 2；(2) P2 兩段 > 0、全期 t > 2.5；(3) Fama-MacBeth 全期 t > 2；(4) 第 1001–1500 名 P1 同號且 t > 1.65。
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
import smallcap_composite as sc  # noqa: E402
from data.fetch_financials import FinMindClient  # noqa: E402
from sue_attention import nw_t  # noqa: E402

HEAD = ROOT / "data_cache" / "events" / "fin_report_headlines.csv"
OUT = ROOT / "docs" / "margin_surprise_actual.md"
Q_FIRST, Q_LAST = pd.Timestamp("2020-09-30"), pd.Timestamp("2026-03-31")


def announcements() -> pd.DataFrame:
    h = pd.read_csv(HEAD, dtype={"stock_id": str, "spoke_time": str}, parse_dates=["date"])
    s = h["subject"].astype(str)
    h = h[s.str.contains("財務報") & s.str.contains("通過|決議|承認|提報") & ~s.str.contains("預計|更正|補正|召開|代")].copy()
    qs = pd.date_range("2020-03-31", "2026-06-30", freq="QE-DEC")
    dl = pd.Series([msm.deadline(q) for q in qs], index=qs)
    qq = []
    for d in h["date"]:
        c = dl[(dl - pd.Timedelta(days=100) < d) & (d <= dl + pd.Timedelta(days=5))]
        qq.append(c.sort_values().index[0] if len(c) else pd.NaT)
    h["q"] = qq
    h = h.dropna(subset=["q"])
    h["late"] = h["spoke_time"].fillna("0").astype(str).str.zfill(6) >= "133000"
    h = h.sort_values(["date", "spoke_time"]).drop_duplicates(["stock_id", "q"], keep="first")
    return h[(h["q"] >= Q_FIRST) & (h["q"] <= Q_LAST)][["stock_id", "q", "date", "spoke_time", "late", "subject"]]


def t0_index(days: pd.DatetimeIndex, date: pd.Timestamp, late: bool) -> int:
    k = int(days.searchsorted(date, side="left"))
    if k < len(days) and days[k] == date and late:
        k += 1
    return k


def ms_star(client, firms: pd.DataFrame) -> pd.DataFrame:
    """firms：stock_id、sector（前 1500 名非金融聯集）；回傳每檔每季 MS*（含 rev_yoy）。"""
    rows = []
    for r in firms.itertuples():
        f = msm.firm_quarters(client, r.stock_id)
        if f.empty:
            continue
        f = f.reset_index().rename(columns={"date": "q", "index": "q"})
        f["stock_id"], f["sector"] = r.stock_id, r.sector
        rows.append(f[["q", "stock_id", "sector", "d_opm", "rev_yoy"]])
    df = pd.concat(rows, ignore_index=True).dropna(subset=["d_opm", "rev_yoy"])
    qs = sorted(df["q"].unique())
    df["pred"] = np.nan
    for i, q in enumerate(qs):
        if i < 4:
            continue
        past = df[df["q"].isin(qs[max(0, i - 8):i])]
        cur = df.index[df["q"] == q]
        for s, idx in df.loc[cur].groupby("sector").groups.items():
            p = past[past["sector"] == s]
            if len(p) < 20:
                p = past
            b = np.polyfit(p["rev_yoy"].to_numpy(float), p["d_opm"].to_numpy(float), 1)
            df.loc[idx, "pred"] = b[1] + b[0] * df.loc[idx, "rev_yoy"]
    df["res"] = df["d_opm"] - df["pred"]
    df = df.sort_values(["stock_id", "q"])
    df["sd"] = df.groupby("stock_id")["res"].transform(lambda x: x.shift(1).rolling(8, min_periods=4).std())
    df["ms"] = df["res"] / df["sd"].where(df["sd"] > 0)
    df["ms"] = df.groupby("q")["ms"].transform(lambda x: x.clip(x.quantile(0.01), x.quantile(0.99)))
    return df


_FS: dict = {}


def fs_dates(client, sid: str) -> set:
    if sid not in _FS:
        fs = client.get("TaiwanStockFinancialStatements", sid, "2017-01-01")
        _FS[sid] = set(pd.to_datetime(fs["date"])) if not fs.empty else set()
    return _FS[sid]


def coverage(client) -> pd.DataFrame:
    a = announcements()
    mem = pd.read_csv(ce.MEMBERSHIP, dtype={"stock_id": str})
    out = []
    for q in pd.date_range(Q_FIRST, Q_LAST, freq="QE-DEC"):
        y = msm.deadline(q).year
        g = mem[(mem["year"] == y) & (mem["rank"] <= 500) & ~mem["sector"].isin(msm.FIN)]
        have = set(a.loc[a["q"] == q, "stock_id"])
        n_fs = sum(q in fs_dates(client, sid) for sid in g["stock_id"])
        hit = len(set(g["stock_id"]) & have)
        early = a[(a["q"] == q) & a["stock_id"].isin(g["stock_id"])]
        lead = (msm.deadline(q) - early["date"]).dt.days
        out.append({"q": q.strftime("%Y-%m"), "n_fs": n_fs, "n_date": hit, "cov": hit / max(n_fs, 1),
                    "lead_med": float(lead.median()) if len(lead) else np.nan, "lead_ge7": float((lead >= 7).mean()) if len(lead) else np.nan})
    return pd.DataFrame(out)


def events(S, a: pd.DataFrame, ms: pd.DataFrame, keep_q: set) -> pd.DataFrame:
    days = S.days
    A = S.adj.to_numpy()
    eqty = {}
    rows = []
    a = a[a["q"].isin(keep_q)]
    msi = ms.set_index(["stock_id", "q"])
    for r in a.itertuples():
        t = r.stock_id + ".TW"
        if t not in S.col or (r.stock_id, r.q) not in msi.index:
            continue
        k0 = t0_index(days, r.date, r.late)
        kd = int(days.searchsorted(msm.deadline(r.q), side="right"))
        if k0 >= len(days) or kd >= len(days) or days[k0] >= lp.HOLDOUT:
            continue
        j = S.col[t]
        if not S.member.iat[k0, j] or S.sector.get(r.stock_id, "NA") in msm.FIN:
            continue
        m = msi.loc[(r.stock_id, r.q)]
        f = lambda a_, b_: A[b_, j] / A[a_, j] - 1 if b_ < S.limit and a_ < len(days) else np.nan  # noqa: E731
        if r.stock_id not in eqty:
            eqty[r.stock_id] = msm.balance_equity(S.client, r.stock_id)
        e = eqty[r.stock_id]
        eq_v = float(e.get(r.q, np.nan)) if len(e) else np.nan
        rows.append({"ticker": t, "q": r.q, "t0": days[k0], "k0": k0, "kd": kd, "gap": kd - k0, "sector": S.sector.get(r.stock_id, "NA"),
                     "ms": float(m["ms"]), "rev_yoy": float(m["rev_yoy"]),
                     "r_p1": f(k0 + 1, kd + 1), "r_p2": f(k0 + 1, k0 + 61), "r_dl": f(kd + 1, kd + 61),
                     "sue": S.sue.iat[k0, j], "p20": S.pre20.iat[k0, j], "lm": S.lmcap.iat[k0, j],
                     "bm": eq_v / np.exp(S.lmcap.iat[k0, j]) if np.isfinite(S.lmcap.iat[k0, j]) else np.nan})
    ev = pd.DataFrame(rows).dropna(subset=["ms"])
    ev["seg"] = np.where(ev["t0"] < lp.SPLIT, "2020Q3–2022", "2023–2026/04")
    return ev


def ic_q(ev, ret, mask=None):
    x = ev if mask is None else ev[mask]
    out = {}
    for q, g in x.dropna(subset=[ret]).groupby("q"):
        g = g.set_index("ticker")
        out[g["t0"].max()] = lp.within_ic(g["ms"], g[ret], g["sector"])
    return pd.Series(out).dropna().sort_index()


def segs(x):
    f = lambda y: (float(y.mean()), nw_t(y, 2), len(y))  # noqa: E731
    return {"2020Q3–2022": f(x[x.index < lp.SPLIT]), "2023–2026/04": f(x[x.index >= lp.SPLIT]), "全期": f(x)}


def fm(ev):
    out = {}
    for q, g in ev.dropna(subset=["r_p2"]).groupby("q"):
        if len(g) < 50:
            continue
        r = lambda c: (g[c].rank(pct=True) - 0.5).fillna(0.0).to_numpy(float)  # noqa: E731
        X = np.column_stack([np.ones(len(g)), r("ms"), r("sue"), r("rev_yoy"), r("p20"), r("lm"), r("bm"),
                             pd.get_dummies(g["sector"], drop_first=True, dtype=float).to_numpy()])
        b, *_ = np.linalg.lstsq(X, g["r_p2"].to_numpy(float), rcond=None)
        out[g["t0"].max()] = b[1]
    return pd.Series(out).sort_index()


def main():
    import dotenv

    dotenv.load_dotenv(ROOT / ".env")
    client = FinMindClient()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "test"
    cov = coverage(client)
    keep_q = set(pd.to_datetime([q for q, c in zip(cov["q"], cov["cov"]) if c >= 0.8]) + pd.offsets.MonthEnd(0))
    L = ["# I048 利潤率驚奇改用季報實際公告日（自動產生）", "",
         "由 [analysis/margin_surprise_actual.py](../analysis/margin_surprise_actual.py) 產生；設計見程式開頭（看結果前固定）。研究結果，非投資建議。", "",
         "## 前置：公告日覆蓋率（前 500 名非金融，未看報酬）", "",
         "| 財報季 | 有財報 | 有公告日 | 覆蓋率 | 公告日距法定期限（日曆日中位數） | 提早 ≥ 7 日的比例 |", "|---|---|---|---|---|---|"]
    for r in cov.itertuples():
        L.append(f"| {r.q} | {r.n_fs} | {r.n_date} | {r.cov:.0%} | {r.lead_med:.0f} | {r.lead_ge7:.0%} |")
    L += ["", f"覆蓋率 ≥ 80% 的季：{len(keep_q)} / {len(cov)}。", ""]
    if cmd == "coverage":
        OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
        print("\n".join(L))
        return
    a = announcements()
    mem = pd.read_csv(sc.M1500, dtype={"stock_id": str})
    firms = mem[~mem["sector"].isin(msm.FIN)].drop_duplicates("stock_id", keep="last")[["stock_id", "sector"]]
    ms = ms_star(client, firms)
    mkt, tx = lp.market_tri(client), lp.tx_continuous(client)
    res = {}
    for lo, hi, path in ((1, 500, ce.MEMBERSHIP), (1001, 1500, sc.M1500), (501, 1000, ce.MEMBERSHIP)):
        ce.MEMBERSHIP = de.MEMBERSHIP = path
        S = ce.Sample(client, lo, hi, mkt, tx)
        res[lo] = events(S, a, ms, keep_q)
    ce.MEMBERSHIP = de.MEMBERSHIP = ROOT / "config" / "universe_mcap_membership.csv"
    ev, evc, evv = res[1], res[1001], res[501]
    gap5 = ev["gap"] >= 5
    p1, p2, pdl = segs(ic_q(ev, "r_p1", gap5)), segs(ic_q(ev, "r_p2")), segs(ic_q(ev, "r_dl"))
    f = segs(fm(ev))
    c1 = segs(ic_q(evc, "r_p1", evc["gap"] >= 5))
    v1 = segs(ic_q(evv, "r_p1", evv["gap"] >= 5))
    k1 = p1["2020Q3–2022"][0] > 0 and p1["2023–2026/04"][0] > 0 and p1["全期"][1] > 2
    k2 = p2["2020Q3–2022"][0] > 0 and p2["2023–2026/04"][0] > 0 and p2["全期"][1] > 2.5
    k3 = f["全期"][1] > 2
    k4 = np.sign(c1["全期"][0]) == np.sign(p1["全期"][0]) and c1["全期"][1] > 1.65
    fmt = lambda v, pct=False: "—" if v[0] != v[0] else (f"{v[0]:+.2%}" if pct else f"{v[0]:+.3f}") + f"（{v[1]:.1f}，{v[2]}）"  # noqa: E731
    L += [f"前 500 名非金融事件 {len(ev):,} 個（公告日距期限 ≥ 5 個交易日者 {int(gap5.sum()):,}，距離中位數 {ev['gap'].median():.0f} 個交易日）；"
          f"第 1001–1500 名 {len(evc):,}、第 501–1000 名 {len(evv):,}。", "",
          "IC 為產業內 Spearman（−1～1，0 為無預測力），每季一個截面，括號為（Newey-West t，季數）；Fama-MacBeth 係數為 MS* 百分位差 1 對應的 60 日報酬差。", "",
          "| 統計量 | 2020Q3–2022 | 2023–2026/04 | 全期 |", "|---|---|---|---|",
          "| **P1 前 500 名：實際日到期限 [t0+2, d+1]** | " + " | ".join(fmt(v) for v in p1.values()) + " |",
          "| **P2 前 500 名：實際日起 60 日** | " + " | ".join(fmt(v) for v in p2.values()) + " |",
          "| 只報告：期限版 [d+2, d+61] | " + " | ".join(fmt(v) for v in pdl.values()) + " |",
          "| **Fama-MacBeth MS*（60 日）** | " + " | ".join(fmt(v, True) for v in f.values()) + " |",
          "| **確認：第 1001–1500 名 P1** | " + " | ".join(fmt(v) for v in c1.values()) + " |",
          "| 只報告：第 501–1000 名 P1 | " + " | ".join(fmt(v) for v in v1.values()) + " |",
          "| 只報告：第 1001–1500 名 P2 | " + " | ".join(fmt(v) for v in segs(ic_q(evc, "r_p2")).values()) + " |",
          "| 只報告：第 501–1000 名 P2 | " + " | ".join(fmt(v) for v in segs(ic_q(evv, "r_p2")).values()) + " |", "",
          "## 判定", "",
          f"1. 前 500 名 P1 兩段 > 0、全期 t > 2 → {'✓' if k1 else '✗'}",
          f"2. 前 500 名 P2 兩段 > 0、全期 t > 2.5 → {'✓' if k2 else '✗'}",
          f"3. Fama-MacBeth 全期 t > 2 → {'✓' if k3 else '✗'}",
          f"4. 第 1001–1500 名 P1 同號且 t > 1.65 → {'✓' if k4 else '✗'}", "",
          f"**結論：{'通過（下一步做 fv5 合成回測）' if all((k1, k2, k3, k4)) else '未通過'}**"]
    OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
