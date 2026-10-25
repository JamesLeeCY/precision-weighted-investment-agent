"""I063 月營收公告期間的市場反應（EAR）對 SUE 的增量（點子卡 research/ideas/I063-revenue-announcement-window-return-ear.md，檢定計畫看結果前固定）。

用法（於專案根目錄；資料皆已快取）：
    .venv/Scripts/python analysis/revenue_ear.py
輸出 docs/revenue_ear.md。

設計（依點子卡；補充以「補」標示）：
- 換倉日 d：月營收公告期限的次一交易日（leg_probe.event_dates），2019-03 ~ 2026-04。
- EAR：還原價報酬，從 m 月第一個交易日的前一交易日收盤到 d 的前一交易日收盤，減同名次組同產業成員等權平均。
- 控制：SUE、營收創新高（rec24，max_rec_robust.rec_n）、PRE（上一個換倉日收盤到 m − 1 月最後交易日收盤的產業調整報酬）、log 市值；全部為產業內百分位 − 0.5。
- H1：每個換倉日，被解釋變數 = d 收盤起 60 個交易日的產業調整報酬的產業內百分位 − 0.5；Fama-MacBeth，Newey-West 落後 3。
  方向 s = 2019–2022 前 500 名 EAR 係數正負號。通過：2023–2026/04 同號且 t ≥ 1.5；全期 |t| ≥ 2.58；第 1001–1500 名同號且 t ≥ 2.0。
- H2（H1 通過才做）：fv5 建構，分數 = 0.75 × SUE 產業內百分位 + 0.25 × s·EAR 產業內百分位；兩段 Sharpe ≥ fv5、全期 ≥ 1.74、年換手增加 ≤ 20%。
- 只報告：EAR 對 SUE 殘差版本的係數、EAR 五分組 60 日報酬、EAR 與前一日報酬（1 日反轉）的相關、視窗內觸及漲跌停比例。補：fv5x 合成版本未做。
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
import ls_turnover as lt  # noqa: E402
import max_rec_robust as mr  # noqa: E402
import smallcap_composite as scm  # noqa: E402
from sue_attention import nw_t  # noqa: E402


def sector_mean_adj(ret: pd.Series, member_mask: pd.Series, sector: pd.Series) -> pd.Series:
    df = pd.DataFrame({"r": ret, "m": member_mask.reindex(ret.index).fillna(False), "sec": sector.reindex(ret.index)})
    mean = df[df["m"]].groupby("sec")["r"].mean()
    return df["r"] - df["sec"].map(mean)


def panel(adj, member, sector, sue_at, rec, logcap, sched, raw_close=None) -> pd.DataFrame:
    days = adj.index
    limit = int(days.searchsorted(lp.HOLDOUT))
    rows = []
    for i, d in enumerate(sched):
        kd = int(days.searchsorted(d))
        if kd + 60 >= limit or i == 0:
            continue
        m0 = d.to_period("M").to_timestamp()
        k_first = int(days.searchsorted(m0))
        a, b = k_first - 1, kd - 1
        if a < 1 or b <= a:
            continue
        kp = int(days.searchsorted(sched[i - 1]))
        k_last_prev = k_first - 1
        mem = member.iloc[kd]
        ear = sector_mean_adj(adj.iloc[b] / adj.iloc[a] - 1, mem, sector)
        pre = sector_mean_adj(adj.iloc[k_last_prev] / adj.iloc[kp] - 1, mem, sector) if k_last_prev > kp else ear * np.nan
        fwd = sector_mean_adj(adj.iloc[kd + 60] / adj.iloc[kd] - 1, mem, sector)
        r1 = adj.iloc[b] / adj.iloc[b - 1] - 1
        df = pd.DataFrame({"y": fwd, "ear": ear, "sue": sue_at(d), "rec": rec.loc[m0] if m0 in rec.index else np.nan,
                           "pre": pre, "lm": logcap.iloc[kd - 1] if kd >= 1 else np.nan, "r1": r1, "sector": sector})
        df = df[mem.reindex(df.index).fillna(False).to_numpy(bool)].dropna(subset=["y", "ear", "sue"])
        if raw_close is not None:
            rc = raw_close.iloc[a:b + 1][df.index]
            ch = rc / rc.shift(1) - 1
            df["limit"] = (ch.abs() >= 0.095).any().reindex(df.index).astype(float)
        df["d"] = d
        rows.append(df.rename_axis("ticker").reset_index())
    return pd.concat(rows, ignore_index=True)


def fm(P, var="ear") -> pd.Series:
    out = {}
    for d, g in P.groupby("d"):
        if len(g) < 50:
            continue
        sec = g["sector"]
        y = g["y"].groupby(sec).rank(pct=True) - 0.5
        r = lambda c: (g[c].groupby(sec).rank(pct=True) - 0.5).fillna(0.0).to_numpy(float)  # noqa: E731
        X = np.column_stack([np.ones(len(g)), r(var), r("sue"), r("rec"), r("pre"), r("lm")])
        b, *_ = np.linalg.lstsq(X, y.to_numpy(float), rcond=None)
        out[d] = b[1]
    return pd.Series(out).sort_index()


def segs(x, lag=3):
    f = lambda y: (float(y.mean()), nw_t(y, lag), len(y))  # noqa: E731
    return {"2019–2022": f(x[x.index < lp.SPLIT]), "2023–2026/04": f(x[x.index >= lp.SPLIT]), "全期": f(x)}


def fmt(v):
    return "—" if v[0] != v[0] else f"{v[0]:+.4f}（{v[1]:.2f}，{v[2]}）"


def rec_frame(client, tickers):
    revs = {t: client.get("TaiwanStockMonthRevenue", t.split(".")[0], "2017-01-01") for t in tickers}
    return pd.DataFrame({t: mr.rec_n(rv, 24) for t, rv in revs.items() if not rv.empty})


def main():
    c = lp.prepare(500)
    sue = lp.leg_scores(c, "sue")
    rec = rec_frame(c.client, c.tickers)
    raw = bc.raw_close(c)
    P1 = panel(c.adj, c.member, c.sector, lambda d: sue[d], rec, c.logcap, c.schedule, raw)
    b1 = fm(P1)
    s1 = segs(b1)
    sign = 1.0 if s1["2019–2022"][0] >= 0 else -1.0
    # 確認：第 1001–1500 名
    import dotenv
    dotenv.load_dotenv(ROOT / ".env")
    mkt, tx = lp.market_tri(c.client), lp.tx_continuous(c.client)
    ce.MEMBERSHIP = de.MEMBERSHIP = scm.M1500
    S3 = ce.Sample(c.client, 1001, 1500, mkt, tx)
    ce.MEMBERSHIP = de.MEMBERSHIP = ROOT / "config" / "universe_mcap_membership.csv"
    sec3 = pd.Series({t: S3.sector.get(t.split(".")[0], "NA") for t in S3.tickers})
    sched3 = [d for d in lp.event_dates(S3.days) if pd.Timestamp("2019-01-01") <= d < lp.HOLDOUT]
    rec3 = rec_frame(c.client, S3.tickers)
    P3 = panel(S3.adj, S3.member, sec3, lambda d: S3.sue.iloc[int(S3.days.searchsorted(d))], rec3, S3.lmcap.shift(-1), sched3)
    s3 = segs(fm(P3))
    # 只報告：501–1000
    S2 = ce.Sample(c.client, 501, 1000, mkt, tx)
    sec2 = pd.Series({t: S2.sector.get(t.split(".")[0], "NA") for t in S2.tickers})
    sched2 = [d for d in lp.event_dates(S2.days) if pd.Timestamp("2019-01-01") <= d < lp.HOLDOUT]
    rec2 = rec_frame(c.client, S2.tickers)
    P2 = panel(S2.adj, S2.member, sec2, lambda d: S2.sue.iloc[int(S2.days.searchsorted(d))], rec2, S2.lmcap.shift(-1), sched2)
    s2 = segs(fm(P2))
    # 只報告
    P1["ear_res"] = np.nan
    for d, g in P1.groupby("d"):
        X = np.column_stack([np.ones(len(g)), g["sue"].rank(pct=True)])
        b, *_ = np.linalg.lstsq(X, g["ear"].to_numpy(float), rcond=None)
        P1.loc[g.index, "ear_res"] = g["ear"].to_numpy() - X @ b
    sres = segs(fm(P1, "ear_res"))
    q = P1.assign(q=P1.groupby("d")["ear"].transform(lambda x: pd.qcut(x.rank(method="first"), 5, labels=False))).groupby("q")["y"].mean()
    corr_r1 = float(P1.groupby("d").apply(lambda g: g["ear"].rank().corr(g["r1"].rank())).mean())
    k1 = np.sign(s1["2023–2026/04"][0]) == sign and abs(s1["2023–2026/04"][1]) >= 1.5
    k2 = abs(s1["全期"][1]) >= 2.58 and np.sign(s1["全期"][0]) == sign
    k3 = np.sign(s3["全期"][0]) == sign and sign * s3["全期"][1] >= 2.0
    L = ["# I063 月營收公告期間的市場反應（EAR）對 SUE 的增量（自動產生）", "",
         "由 [analysis/revenue_ear.py](../analysis/revenue_ear.py) 產生；設計見程式開頭（看結果前固定）。"
         "EAR = 該月第一個交易日前一日收盤到換倉日前一日收盤的產業調整報酬；係數為 Fama-MacBeth（被解釋變數為之後 60 個交易日產業調整報酬的產業內百分位 − 0.5，"
         "控制 SUE、營收創新高、上月公告後報酬、市值，皆為產業內百分位 − 0.5），括號為（Newey-West t，換倉日數）。研究結果，非投資建議。", "",
         f"方向 s（2019–2022 前 500 名 EAR 係數正負號）= {'+' if sign > 0 else '−'}。", "",
         "| 樣本 | 2019–2022 | 2023–2026/04 | 全期 |", "|---|---|---|---|",
         "| **前 500 名 EAR 係數** | " + " | ".join(fmt(v) for v in s1.values()) + " |",
         "| **確認：第 1001–1500 名** | " + " | ".join(fmt(v) for v in s3.values()) + " |",
         "| 只報告：第 501–1000 名 | " + " | ".join(fmt(v) for v in s2.values()) + " |",
         "| 只報告：前 500 名 EAR 對 SUE 殘差版本 | " + " | ".join(fmt(v) for v in sres.values()) + " |", "",
         "只報告：前 500 名 EAR 五分組（0 = 最低）之後 60 日產業調整報酬平均：" + "、".join(f"Q{int(k)} {v:+.2%}" for k, v in q.items()),
         f"；EAR 與公告期最後一日報酬的等級相關 {corr_r1:+.2f}；視窗內觸及漲跌停的比例 {P1['limit'].mean():.0%}。", "",
         "## 判定（H1）", "",
         f"- 2023–2026/04 同號且 t ≥ 1.5 → {'✓' if k1 else '✗'}",
         f"- 全期 |t| ≥ 2.58 → {'✓' if k2 else '✗'}",
         f"- 第 1001–1500 名同號且 t ≥ 2.0 → {'✓' if k3 else '✗'}", ""]
    if k1 and k2 and k3:
        fee = hc.lending_fees(c.client, c.tickers, c.adj.index)
        quota, lend60 = bc.load_short_data(c.client, c.tickers, c.adj.index)
        ear_d = {d: g.set_index("ticker")["ear"] for d, g in P1.groupby("d")}

        def shortable_at(d):
            n_short = max(1, int(c.member.loc[d].sum() / 3))
            need = lt.K_CAPITAL / n_short / raw.loc[d]
            return (lend60.loc[d] > 0) & (quota.loc[d] >= need) & (need <= bc.DEPTH_FRAC * lend60.loc[d]) & (fee.loc[d] <= bc.FEE_MAX)

        def comp(d):
            s = sue[d].dropna()
            g = c.sector.reindex(s.index)
            e = (sign * ear_d.get(d, pd.Series(dtype=float))).reindex(s.index)
            return 0.75 * s.groupby(g).rank(pct=True) + 0.25 * e.groupby(g).rank(pct=True).fillna(0.5)

        def book(fn):
            parts, tos = [], []
            for off in range(3):
                wd = {d: lt.ew_ls_buffer(fn(d), c.sector, shortable_at(d), q_keep=None) for d in c.schedule[off::3]}
                sim = hc.simulate_weights(wd, c.rets, c.betas, c.tx, list(wd), fee=fee)
                parts.append(sim["ret"])
                tos.append(sim["turnover"].sum() / (len(sim) / 252))
            x = pd.concat(parts, axis=1).mean(axis=1)
            x = x[x.index > c.schedule[2]]
            return hc.stats(x) | {"full": lp.sharpe(x.dropna()), "to": float(np.mean(tos))}
        b0, bb = book(lambda d: sue[d]), book(comp)
        h2 = bb["sh_oos"] >= b0["sh_oos"] and bb["sh_is"] >= b0["sh_is"] and bb["full"] >= 1.74 and bb["to"] <= b0["to"] * 1.2
        L += ["## H2：fv5 合成", "", "| 建構 | Sharpe | 全期 | 年化 | 年換手 |", "|---|---|---|---|---|",
              f"| fv5 | {b0['sh_oos']:.2f} / {b0['sh_is']:.2f} | {b0['full']:.2f} | {b0['ann']:+.1%} | {b0['to']:.1f} |",
              f"| 0.75 SUE + 0.25 s·EAR | {bb['sh_oos']:.2f} / {bb['sh_is']:.2f} | {bb['full']:.2f} | {bb['ann']:+.1%} | {bb['to']:.1f} |", "",
              f"**結論：{'通過（另立前瞻規格）' if h2 else 'H1 通過、H2 未通過'}**"]
    else:
        L.append("**結論：未通過（H1 不成立，不做 fv5 合成）**")
    (ROOT / "docs" / "revenue_ear.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
