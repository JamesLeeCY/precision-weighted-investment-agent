"""I070 H2：季報 EAR 的可交易多空建構（點子卡 research/ideas/I070-quarterly-report-announcement-return.md，H1 通過後依事前固定的 H2 計畫執行）。

用法（於專案根目錄；資料皆已快取）：
    .venv/Scripts/python analysis/quarterly_ear_h2.py
輸出 docs/quarterly_ear_h2.md。

設計（依點子卡；補充以「補」標示）：
- 換倉日 d = 每季財報法定期限（margin_surprise.deadline）後第一個交易日，2020Q2 ~ 2025Q4 財報。
- 分數：t0 在 d 前 60 個交易日內、且 t0 + 1 ≤ d 前一交易日以前（反應視窗已結束）的 QEAR（analysis/quarterly_ear.events，前 500 名）；d 當日成員。
- 產業內前／後 1/3 等權多空（ls_turnover.ew_ls_buffer，不含緩衝、放空只用借券條件 D 可借者），持有 60 個交易日後平倉；
  單邊 0.29625% + 借券費、台指期對沖（hedge_construction.simulate_weights）。補：持有期重疊時（Q4 → Q1 間隔不足 60 日）兩份資金各半，
  沒有部位的日子報酬為 0（11 月中到 3 月底的空窗）。
- 判定：日淨報酬對 fv5 與 5 個 I049 風格因子的跨越迴歸（Newey-West 落後 5，期間為第一個換倉日到 2026-04），截距 t ≥ 2.0 且兩段 a > 0；
  且 0.5 × fv5 + 0.5 × QEAR 多空的全期 Sharpe ≥ 1.74（2020-08 以前 QEAR 半份資金閒置，報酬 0）。
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
import ear_standalone as es  # noqa: E402
import hedge_construction as hc  # noqa: E402
import leg_probe as lp  # noqa: E402
import ls_turnover as lt  # noqa: E402
import margin_surprise as msm  # noqa: E402
import margin_surprise_actual as msa  # noqa: E402
import quarterly_ear as qe  # noqa: E402

HOLD = 60


def main():
    import dotenv

    dotenv.load_dotenv(ROOT / ".env")
    c = lp.prepare(500)
    days, sched, sector = c.adj.index, c.schedule, c.sector
    sue = lp.leg_scores(c, "sue")
    fee = hc.lending_fees(c.client, c.tickers, days)
    quota, lend60 = bc.load_short_data(c.client, c.tickers, days)
    raw = bc.raw_close(c)
    mem = c.member.astype(bool)

    def shortable_at(d):
        n_short = max(1, int(c.member.loc[d].sum() / 3))
        need = lt.K_CAPITAL / n_short / raw.loc[d]
        return (lend60.loc[d] > 0) & (quota.loc[d] >= need) & (need <= bc.DEPTH_FRAC * lend60.loc[d]) & (fee.loc[d] <= bc.FEE_MAX)

    msa.Q_FIRST, msa.Q_LAST = pd.Timestamp("2020-06-30"), pd.Timestamp("2025-12-31")
    a = msa.announcements()
    S = ce.Sample(c.client, 1, 500, lp.market_tri(c.client), lp.tx_continuous(c.client))
    ev = qe.events(S, a)
    ev["k0"] = days.searchsorted(ev["t0"])
    books, nnames, shr = [], [], []
    for q in pd.date_range("2020-06-30", "2025-12-31", freq="QE-DEC"):
        kd = int(days.searchsorted(msm.deadline(q), side="right"))
        if kd >= len(days) or days[kd] >= lp.HOLDOUT:
            continue
        d = days[kd]
        g = ev[(ev["k0"] >= kd - HOLD) & (ev["k0"] + 1 <= kd - 1)].sort_values("t0").drop_duplicates("ticker", keep="last")
        s = g.set_index("ticker")["qear"]
        s = s[mem.loc[d].reindex(s.index).fillna(False).to_numpy(bool)]
        ok = shortable_at(d)
        p = s.groupby(sector.reindex(s.index)).rank(pct=True)
        shr.append(float(ok.reindex(p[p <= 1 / 3].index).fillna(False).mean()))
        w = lt.ew_ls_buffer(s, sector, ok, q_keep=None)
        if not len(w):
            continue
        d_end = days[min(kd + HOLD, len(days) - 1)]
        sim = hc.simulate_weights({d: w, d_end: pd.Series(dtype=float)}, c.rets, c.betas, c.tx, [d, d_end], fee=fee)
        books.append(sim["ret"][(sim.index > d) & (sim.index <= d_end)])
        nnames.append((int((w > 0).sum()), int((w < 0).sum())))
    B = pd.concat(books, axis=1)
    act = B.notna().sum(axis=1)
    xq = (B.sum(axis=1) / act.replace(0, np.nan)).reindex(days).fillna(0.0)
    xq = xq[(xq.index >= B.index.min()) & (xq.index < lp.HOLDOUT)]
    fv5, _ = es.book(lambda d: sue[d], sched, c.rets, c.betas, c.tx, sector, shortable_at, fee)
    F = es.style_factors(c.adj, c.rets, c.betas, mem, sector, c.logcap, c.client, c.tickers)
    X = pd.concat([fv5.rename("fv5"), F], axis=1)
    a_all = es.span(xq, X, 5)
    a_seg = [es.span(xq[(xq.index < lp.SPLIT) == f], X, 5) for f in (True, False)]
    blend = 0.5 * fv5 + 0.5 * xq.reindex(fv5.index).fillna(0.0)
    s0, sq, sb = es.st(fv5), es.st(xq), es.st(blend)
    k1 = a_all[1] >= 2.0 and a_seg[0][0] > 0 and a_seg[1][0] > 0
    k2 = sb["full"] >= 1.74
    corr = float(pd.concat([xq, fv5], axis=1).dropna().corr().iloc[0, 1])
    L = ["# I070 H2 季報 EAR 可交易多空（自動產生）", "",
         "由 [analysis/quarterly_ear_h2.py](../analysis/quarterly_ear_h2.py) 產生；設計見程式開頭（H1 通過後依事前固定的 H2 計畫）。"
         "Sharpe 為年化、扣成本（單邊 0.29625% ＋ 借券費）與台指期對沖後，格式 2019–2022 / 2023–2026/04（QEAR 多空自 "
         f"{B.index.min():%Y-%m} 起）；截距 a 為日報酬迴歸常數項，括號為 Newey-West t。研究結果，非投資建議。", "",
         f"換倉 {len(books)} 次，平均多方 {np.mean([n[0] for n in nnames]):.0f} 檔、空方 {np.mean([n[1] for n in nnames]):.0f} 檔；"
         f"QEAR 產業內後 1/3 的可借（條件 D）比例 {np.mean(shr):.0%}；有部位的交易日比例 {(xq != 0).mean():.0%}。", "",
         "| 組合 | Sharpe | 全期 | 年化淨報酬 | 年化波動 | 最大回撤 |", "|---|---|---|---|---|---|"]
    for nm, s in (("fv5（基準）", s0), ("QEAR 多空", sq), ("**50% fv5 + 50% QEAR 多空**", sb)):
        L.append(f"| {nm} | {s['sh_oos']:.2f} / {s['sh_is']:.2f} | {s['full']:.2f} | {s['ann']:+.1%} | {s['vol']:.1%} | {s['mdd']:.1%} |")
    L += ["", f"QEAR 多空與 fv5 日淨報酬相關 {corr:+.2f}。",
          f"跨越迴歸：全期 a = {a_all[0]:+.5f}／日（年化 {a_all[0] * 252:+.1%}，t {a_all[1]:.2f}，{a_all[2]} 日）；"
          + "；".join(f"{lab} a = {v[0]:+.5f}（t {v[1]:.2f}）" for lab, v in zip(("2020-08 ~ 2022", "2023 ~ 2026/04"), a_seg)) + "；"
          "係數：fv5 " + f"{a_all[3][0]:+.3f}、" + "、".join(f"{k} {v:+.3f}" for k, v in zip(es.F_NAMES, a_all[3][1:])) + "。", "",
          "## 判定（H2）", "",
          f"- 跨越截距 t ≥ 2.0 且兩段 a > 0 → {'✓' if k1 else '✗'}",
          f"- 各半組合全期 Sharpe ≥ 1.74（{sb['full']:.2f}）→ {'✓' if k2 else '✗'}", "",
          f"**結論：{'H2 通過（另立前瞻規格，與 fv5 平行記錄）' if k1 and k2 else 'H1 通過、H2 未通過'}**"]
    (ROOT / "docs" / "quarterly_ear_h2.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
