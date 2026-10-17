"""I021 月營收驚奇的連續性（點子卡 research/ideas/I021-revenue-surprise-streak.md，檢定計畫看結果前固定）。

用法（於專案根目錄；資料皆已快取）：
    .venv/Scripts/python analysis/sue_streak.py
輸出 docs/sue_streak.md。

設計（依點子卡；點子卡沒寫清楚、在看結果前補上的細節以「補」標示）：
- SUE：本專案定義（data/revenue_signal.revenue_surprise）；換倉日 = 營收公告期限次一交易日（leg_probe 的 schedule），用當月可得的 SUE，持有 20、60 個交易日。
- streak = 往回數與本月 SUE 同號的連續月數（含本月，上限 6）；延續 = streak ≥ 3；
  中斷 = 本月與上月 SUE 異號，且上月的 streak ≥ 2（本月打斷一個長度 ≥ 2 的連串）。
- 主檢定：每個換倉日在產業內把 SUE 排序，前 30% 組內「延續 − 中斷」的等權 20 日報酬差（兩組都有股票的月份），
  t 值 = 月份差額平均 ÷ 標準誤（依月份群集）；後 30% 組做同樣比較（預期為負）；另報 60 日。
- 迴歸：Fama-MacBeth，20 日報酬 = a + b1·SUE + b2·帶符號 streak + b3·SUE × I(延續) + 產業固定效果
  （補：SUE、帶符號 streak 用當月橫斷面百分位 − 0.5）。報告 streak 與 SUE、營收創新高（24 個月）的平均橫斷面等級相關。
- 驗證：第 501–1000 名做主檢定。
- 可交易（只在 (1)(2) 成立時執行）：fv5 建構，分數改為 SUE 百分位與帶符號 streak 百分位各半，與 fv5 原版比較。
- 通過：(1) 前 30% 組延續 − 中斷兩段 > 0、全期 t > 2；(2) b2 或 b3 全期 t > 2 且兩段同號；(3) 驗證樣本前 30% 組全期同號；
  (4) 合成版兩段 Sharpe 都不低於 fv5 原版。
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
import borrow_capacity as bc  # noqa: E402
import corp_event_study as ce  # noqa: E402
import hedge_construction as hc  # noqa: E402
import leg_probe as lp  # noqa: E402
import ls_turnover as lt  # noqa: E402
import max_rec_robust as mr  # noqa: E402
from data.revenue_signal import revenue_surprise  # noqa: E402


def sue_monthly(client, tickers) -> pd.DataFrame:
    out = {}
    for t in tickers:
        rev = client.get("TaiwanStockMonthRevenue", t.split(".")[0], "2017-01-01")
        if not rev.empty:
            out[t] = revenue_surprise(rev).set_index("avail_month")["sue"]
    return pd.DataFrame(out).sort_index()


def streaks(sue: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """回傳（帶符號 streak、延續旗標、中斷旗標），索引同 sue（可得月份）。"""
    sg = np.sign(sue)
    st = pd.DataFrame(0.0, index=sue.index, columns=sue.columns)
    prev = None
    for i, mo in enumerate(sue.index):
        cur = sg.loc[mo]
        if prev is None:
            val = cur.abs().where(cur.notna())
        else:
            same = (cur == sg.iloc[i - 1]) & (cur != 0)
            val = np.where(same, np.minimum(prev + 1, 6), 1.0)
            val = pd.Series(val, index=cur.index).where(cur.notna() & (cur != 0))
        st.loc[mo] = val
        prev = st.loc[mo].fillna(0.0)
    cont = st >= 3
    brk = (sg != sg.shift(1)) & sg.notna() & sg.shift(1).notna() & (st.shift(1) >= 2)
    return st * sg, cont, brk


def run(adj, member, sector, sue, sched, limit, rec=None):
    signed, cont, brk = streaks(sue)
    rows = []
    for d in sched:
        k = int(adj.index.searchsorted(d))
        mo = d.to_period("M").to_timestamp()
        if mo not in sue.index or k + 20 >= limit:
            continue
        mem = member.loc[d]
        s = sue.loc[mo].reindex(adj.columns)[mem.to_numpy(bool)].dropna()
        if len(s) < 50:
            continue
        r = s.groupby(sector.reindex(s.index)).rank(pct=True)
        f20 = adj.iloc[k + 20] / adj.iloc[k] - 1
        f60 = adj.iloc[k + 60] / adj.iloc[k] - 1 if k + 60 < limit else pd.Series(np.nan, index=adj.columns)
        rows.append({"d": d, "sue": s, "rank": r, "signed": signed.loc[mo].reindex(s.index), "cont": cont.loc[mo].reindex(s.index).fillna(False),
                     "brk": brk.loc[mo].reindex(s.index).fillna(False), "f20": f20.reindex(s.index), "f60": f60.reindex(s.index),
                     "rec": rec.loc[mo].reindex(s.index) if rec is not None and mo in rec.index else None})
    return rows


def diff_series(rows, top: bool, h: str) -> pd.Series:
    out = {}
    for r in rows:
        g = (r["rank"] > 0.7) if top else (r["rank"] <= 0.3)
        a, b = r[h][g & r["cont"]].dropna(), r[h][g & r["brk"]].dropna()
        if len(a) and len(b):
            out[r["d"]] = a.mean() - b.mean()
    return pd.Series(out, dtype=float)


def tstat(x):
    x = x.dropna()
    return (float(x.mean()), float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 else float("nan"), len(x))


def segs(x):
    return {"2019–2022": tstat(x[x.index < lp.SPLIT]), "2023–2026/04": tstat(x[x.index >= lp.SPLIT]), "全期": tstat(x)}


def f(x, pct=True):
    m, t, n = x
    return "—" if m != m else (f"{m:+.2%}" if pct else f"{m:+.3f}") + f"（{t:.1f}，{n}）"


def main():
    c = lp.prepare(500)
    sched = c.schedule
    limit = int(c.adj.index.searchsorted(lp.HOLDOUT))
    sue = sue_monthly(c.client, c.tickers)
    revs = {t: c.client.get("TaiwanStockMonthRevenue", t.split(".")[0], "2017-01-01") for t in c.tickers}
    rec = pd.DataFrame({t: mr.rec_n(rv, 24) for t, rv in revs.items() if not rv.empty})
    rows = run(c.adj, c.member, c.sector, sue, sched, limit, rec)
    d_top20, d_bot20 = diff_series(rows, True, "f20"), diff_series(rows, False, "f20")
    d_top60, d_bot60 = diff_series(rows, True, "f60"), diff_series(rows, False, "f60")
    n_cont = np.mean([int((r["rank"] > 0.7)[r["cont"]].sum()) for r in rows])
    n_brk = np.mean([int((r["rank"] > 0.7)[r["brk"]].sum()) for r in rows])
    # Fama-MacBeth
    fm, c_sue, c_rec = [], [], []
    for r in rows:
        df = pd.DataFrame({"y": r["f20"], "sue": r["sue"], "st": r["signed"], "cont": r["cont"].astype(float), "sec": c.sector.reindex(r["sue"].index)}).dropna()
        if len(df) < 50:
            continue
        rs, rt = df["sue"].rank(pct=True) - 0.5, df["st"].rank(pct=True) - 0.5
        X = np.column_stack([np.ones(len(df)), rs, rt, rs * df["cont"], pd.get_dummies(df["sec"], drop_first=True, dtype=float).to_numpy()])
        beta, *_ = np.linalg.lstsq(X, df["y"].to_numpy(float), rcond=None)
        fm.append(pd.Series({"b1 SUE": beta[1], "b2 帶符號 streak": beta[2], "b3 SUE × 延續": beta[3]}, name=r["d"]))
        c_sue.append(rs.corr(rt))
        if r["rec"] is not None:
            x = pd.concat([df["st"], r["rec"].reindex(df.index)], axis=1).dropna()
            if len(x) > 30:
                c_rec.append(x.iloc[:, 0].rank().corr(x.iloc[:, 1].rank()))
    fm = pd.DataFrame(fm)
    # 驗證
    import dotenv
    dotenv.load_dotenv(ROOT / ".env")
    V = ce.Sample(c.client, 501, 1000, lp.market_tri(c.client), lp.tx_continuous(c.client))
    vsec = pd.Series({t: V.sector.get(t.split(".")[0], "NA") for t in V.tickers})
    vsue = sue_monthly(c.client, V.tickers)
    vrows = run(V.adj, V.member, vsec, vsue, [d for d in sched if d in V.days], V.limit)
    v_top20, v_bot20 = diff_series(vrows, True, "f20"), diff_series(vrows, False, "f20")

    a_top, a_bot, a_top60, a_bot60 = segs(d_top20), segs(d_bot20), segs(d_top60), segs(d_bot60)
    fmseg = {k: segs(fm[k]) for k in fm.columns}
    vt, vb = segs(v_top20), segs(v_bot20)
    c1 = a_top["2019–2022"][0] > 0 and a_top["2023–2026/04"][0] > 0 and a_top["全期"][1] > 2
    c2 = any(fmseg[k]["全期"][1] > 2 and np.sign(fmseg[k]["2019–2022"][0]) == np.sign(fmseg[k]["2023–2026/04"][0])
             for k in ("b2 帶符號 streak", "b3 SUE × 延續"))
    c3 = vt["全期"][0] > 0
    port = None
    if c1 and c2:
        fee = hc.lending_fees(c.client, c.tickers, c.adj.index)
        quota, lend60 = bc.load_short_data(c.client, c.tickers, c.adj.index)
        close = bc.raw_close(c)
        sue_sc = lp.leg_scores(c, "sue")
        signed, _, _ = streaks(sue)

        def shortable_at(d):
            n_short = max(1, int(c.member.loc[d].sum() / 3))
            need = lt.K_CAPITAL / n_short / close.loc[d]
            return (lend60.loc[d] > 0) & (quota.loc[d] >= need) & (need <= bc.DEPTH_FRAC * lend60.loc[d]) & (fee.loc[d] <= bc.FEE_MAX)

        def comp(d):
            s = sue_sc[d].dropna()
            mo = d.to_period("M").to_timestamp()
            st = signed.loc[mo].reindex(s.index) if mo in signed.index else pd.Series(np.nan, index=s.index)
            return 0.5 * s.rank(pct=True) + 0.5 * st.rank(pct=True).fillna(0.5)

        def book(fn):
            parts = []
            for off in range(3):
                wd = {d: lt.ew_ls_buffer(fn(d), c.sector, shortable_at(d), q_keep=None) for d in sched[off::3]}
                parts.append(hc.simulate_weights(wd, c.rets, c.betas, c.tx, list(wd), fee=fee)["ret"])
            x = pd.concat(parts, axis=1).mean(axis=1)
            x = x[x.index > sched[2]]
            return hc.stats(x) | {"full": lp.sharpe(x.dropna())}
        port = {"fv5 原版（SUE）": book(lambda d: sue_sc[d]), "合成：SUE ＋ 帶符號 streak 各半": book(comp)}
    c4 = port is not None and port["合成：SUE ＋ 帶符號 streak 各半"]["sh_oos"] >= port["fv5 原版（SUE）"]["sh_oos"] \
        and port["合成：SUE ＋ 帶符號 streak 各半"]["sh_is"] >= port["fv5 原版（SUE）"]["sh_is"]

    L = ["# I021 月營收驚奇的連續性（自動產生）", "",
         "由 [analysis/sue_streak.py](../analysis/sue_streak.py) 產生；設計見程式開頭（看結果前固定）。"
         "差額 = 同一 SUE 組內「延續（同號連續 ≥ 3 個月）」減「中斷（打斷長度 ≥ 2 的連串）」的等權平均報酬，括號為（t 值，月份數，依月份群集）；"
         "Fama-MacBeth 係數為百分位差 1 對應的 20 日報酬差。研究結果，非投資建議。", "",
         f"主樣本換倉日 {len(rows)} 個；SUE 前 30% 組平均每月延續 {n_cont:.1f} 檔、中斷 {n_brk:.1f} 檔。"
         f"帶符號 streak 與 SUE 的平均等級相關 {np.mean(c_sue):+.2f}、與營收創新高 {np.mean(c_rec) if c_rec else float('nan'):+.2f}。", "",
         "| 統計量 | 2019–2022 | 2023–2026/04 | 全期 |", "|---|---|---|---|",
         "| 前 30% 組：延續 − 中斷（20 日） | " + " | ".join(f(a_top[s]) for s in a_top) + " |",
         "| 後 30% 組：延續 − 中斷（20 日，預期 < 0） | " + " | ".join(f(a_bot[s]) for s in a_bot) + " |",
         "| 前 30% 組：延續 − 中斷（60 日） | " + " | ".join(f(a_top60[s]) for s in a_top60) + " |",
         "| 後 30% 組：延續 − 中斷（60 日） | " + " | ".join(f(a_bot60[s]) for s in a_bot60) + " |"]
    for k, v in fmseg.items():
        L.append(f"| Fama-MacBeth {k} | " + " | ".join(f(v[s]) for s in v) + " |")
    L += ["| 驗證樣本前 30% 組：延續 − 中斷（20 日） | " + " | ".join(f(vt[s]) for s in vt) + " |",
          "| 驗證樣本後 30% 組：延續 − 中斷（20 日） | " + " | ".join(f(vb[s]) for s in vb) + " |", ""]
    if port:
        L += ["| 建構（fv5） | Sharpe | 全期 | 年化報酬 |", "|---|---|---|---|"]
        for k, s in port.items():
            L.append(f"| {k} | {s['sh_oos']:.2f} / {s['sh_is']:.2f} | {s['full']:.2f} | {s['ann']:+.1%} |")
        L.append("")
    L += ["## 判定", "",
          f"1. 前 30% 組延續 − 中斷兩段 > 0、全期 t > 2：{f(a_top['2019–2022'])}、{f(a_top['2023–2026/04'])}、全期 {f(a_top['全期'])} → {'✓' if c1 else '✗'}",
          f"2. b2 或 b3 全期 t > 2 且兩段同號 → {'✓' if c2 else '✗'}",
          f"3. 驗證樣本前 30% 組全期 > 0：{f(vt['全期'])} → {'✓' if c3 else '✗'}",
          f"4. 合成版兩段不低於 fv5：{'未執行（(1)(2) 未全部成立）' if port is None else ('✓' if c4 else '✗')}", "",
          f"**結論：{'通過' if c1 and c2 and c3 and c4 else '未通過'}**"]
    (ROOT / "docs" / "sue_streak.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
