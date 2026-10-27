"""I074 fv5 持股遇到反向季報反應就出場（點子卡 research/ideas/I074-fv5-qear-contrary-exit.md，檢定計畫看結果前固定）。

用法（於專案根目錄；資料皆已快取）：
    .venv/Scripts/python analysis/fv5_qear_exit.py
輸出 docs/fv5_qear_exit.md。

設計（依點子卡；補充以「補」標示）：
- QEAR：與 I070 相同（analysis/quarterly_ear.events，前 500 名，財報季 2020Q2 ~ 2025Q4）。
- 門檻：事件所屬財報季 q 的前 1 ~ 4 季（至少 1 季）全部前 500 名 QEAR 的 1/3、2/3 分位數。
- 規則 R：fv5 某份資金持有期間（換倉日 d 之後、下次換倉日之前），多單 QEAR ≤ 1/3 門檻、或空單 QEAR ≥ 2/3 門檻時，
  於反應日 t0 後第 +3 個交易日收盤平倉；資金不再投入，到該份資金下次換倉才依 fv5 規則重建。補：t0 + 3 ≤ d 的公告（換倉前已知）不觸發。
- 實作：在該份資金的換倉排程中插入出場日，出場日的權重 = 原權重去掉出場股票；hedge_construction.simulate_weights 會依新淨 β 調整台指期並計成本。
  補：插入日沿用該份資金上次換倉日的 β 與借券費率（只讓出場本身改變對沖與借券費，不因重估 β 而改變其他持股的對沖）。
- 比較期間：2020-08 ~ 2026-04，兩段 2020-08 ~ 2022 / 2023 ~ 2026-04。
- 通過（四項皆成立）：年化淨報酬差 ≥ +0.10 個百分點、兩段差皆 > 0、兩段 Sharpe 皆不低於 fv5（同期間）、配對日報酬差全期 Newey-West（落後 5）t ≥ 2.58。
- 只報告：只用多方出場、只用空方出場；釋出資金按比例加碼到同份資金同腿其他持股；衝突持股比例與出場後 60 日產業調整報酬；年換手；fv5x + R。
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
import fv5_family as ff  # noqa: E402
import hedge_construction as hc  # noqa: E402
import leg_probe as lp  # noqa: E402
import ls_turnover as lt  # noqa: E402
import margin_surprise_actual as msa  # noqa: E402
import quarterly_ear as qe  # noqa: E402
from revenue_ear import sector_mean_adj  # noqa: E402
from sue_attention import nw_t  # noqa: E402

START = pd.Timestamp("2020-08-01")
SEG = ("2020-08 ~ 2022", "2023 ~ 2026-04")


def thresholds(ev: pd.DataFrame) -> pd.DataFrame:
    qs = sorted(ev["q"].unique())
    rows = {}
    for i, q in enumerate(qs):
        past = ev[ev["q"].isin(qs[max(0, i - 4):i])]["qear"].dropna()
        if i >= 1 and len(past):
            rows[q] = (float(past.quantile(1 / 3)), float(past.quantile(2 / 3)))
    return pd.DataFrame(rows, index=["lo", "hi"]).T


def apply_rule(wd: dict, ev: pd.DataFrame, days, mode: str, log: list | None = None) -> tuple[dict, dict]:
    """回傳（新權重排程, 插入日 → 沿用的換倉日）。mode：both / long / short / reinvest / none。"""
    reb = sorted(wd)
    W, src = {}, {}
    for n, d in enumerate(reb):
        W[d] = wd[d]
        src[d] = d
        if mode == "none":
            continue
        nxt = reb[n + 1] if n + 1 < len(reb) else lp.HOLDOUT
        w = wd[d]
        g = ev[(ev["exit"] > d) & (ev["exit"] < nxt) & ev["ticker"].isin(w.index)].sort_values("exit")
        cur = w.copy()
        for x, gg in g.groupby("exit"):
            drop = []
            for r in gg.itertuples():
                side = cur.get(r.ticker, 0.0)
                if side > 0 and mode in ("both", "long", "reinvest") and r.qear <= r.lo:
                    drop.append(r.ticker)
                elif side < 0 and mode in ("both", "short", "reinvest") and r.qear >= r.hi:
                    drop.append(r.ticker)
            if not drop:
                continue
            if log is not None:
                for t in drop:
                    log.append((x, t, float(np.sign(cur[t]))))
            new = cur.drop(drop)
            if mode == "reinvest":
                for sg in (1, -1):
                    leg_old = cur[cur * sg > 0].abs().sum()
                    keep = new[new * sg > 0]
                    if len(keep) and keep.abs().sum() > 0:
                        new.loc[keep.index] = keep / keep.abs().sum() * leg_old
            cur = new
            W[x] = cur
            src[x] = d
    return W, src


def run(wds, ev, c, fee, mode, log=None):
    parts, tos = [], []
    for wd in wds:
        W, src = apply_rule(wd, ev, c.adj.index, mode, log)
        dates = sorted(W)
        fee_f, beta_f = fee.copy(), c.betas.copy()
        ins = [x for x in dates if src[x] != x]
        if ins:
            fee_f.loc[ins] = fee.loc[[src[x] for x in ins]].to_numpy()
            beta_f.loc[ins] = c.betas.loc[[src[x] for x in ins]].to_numpy()
        sim = hc.simulate_weights(W, c.rets, beta_f, c.tx, dates, fee=fee_f)
        parts.append(sim["ret"])
        s2 = sim[sim.index >= START]
        tos.append(s2["turnover"].sum() / (len(s2) / 252))
    x = pd.concat(parts, axis=1).mean(axis=1)
    x = x[x.index >= START]
    return x, hc.stats(x) | {"full": lp.sharpe(x.dropna()), "to": float(np.mean(tos)),
                             "s1": lp.sharpe(x[x.index < lp.SPLIT]), "s2": lp.sharpe(x[x.index >= lp.SPLIT])}


def main():
    import dotenv

    dotenv.load_dotenv(ROOT / ".env")
    c = lp.prepare(500)
    days, sched, sector = c.adj.index, c.schedule, c.sector
    sue = lp.leg_scores(c, "sue")
    fee = hc.lending_fees(c.client, c.tickers, days)
    quota, lend60 = bc.load_short_data(c.client, c.tickers, days)
    raw = bc.raw_close(c)

    def shortable_at(d):
        n_short = max(1, int(c.member.loc[d].sum() / 3))
        need = lt.K_CAPITAL / n_short / raw.loc[d]
        return (lend60.loc[d] > 0) & (quota.loc[d] >= need) & (need <= bc.DEPTH_FRAC * lend60.loc[d]) & (fee.loc[d] <= bc.FEE_MAX)

    msa.Q_FIRST, msa.Q_LAST = pd.Timestamp("2020-06-30"), pd.Timestamp("2025-12-31")
    S = ce.Sample(c.client, 1, 500, lp.market_tri(c.client), lp.tx_continuous(c.client))
    ev = qe.events(S, msa.announcements())
    th = thresholds(ev)
    ev = ev.join(th, on="q").dropna(subset=["lo", "qear"])
    k0 = days.searchsorted(ev["t0"])
    ev = ev[k0 + 3 < len(days)].copy()
    ev["exit"] = days[days.searchsorted(ev["t0"]) + 3]
    _, wds = es.book(lambda d: sue[d], sched, c.rets, c.betas, c.tx, sector, shortable_at, fee)
    log = []
    x0, s0 = run(wds, ev, c, fee, "none")
    x1, s1 = run(wds, ev, c, fee, "both", log)
    rep = {nm: run(wds, ev, c, fee, m)[1] for nm, m in (("只報告：只用多方出場", "long"), ("只報告：只用空方出場", "short"), ("只報告：釋出資金加碼同腿", "reinvest"))}
    diff = (x1 - x0).dropna()
    seg = [float(diff[(diff.index < lp.SPLIT) == f].mean() * 252) for f in (True, False)]
    d_ann = s1["ann"] - s0["ann"]
    t = nw_t(diff, 5)
    k1 = d_ann >= 0.001
    k2 = seg[0] > 0 and seg[1] > 0
    k3 = s1["s1"] >= s0["s1"] and s1["s2"] >= s0["s2"]
    k4 = t >= 2.58
    # 衝突持股之後 60 日
    fwd = c.adj.shift(-60) / c.adj - 1
    post = []
    for x, tk, sg in log:
        if int(days.searchsorted(x)) + 60 < int(days.searchsorted(lp.HOLDOUT)):
            fr = sector_mean_adj(fwd.loc[x], c.member.loc[x].astype(bool), sector)
            post.append((sg, float(fr.get(tk, np.nan))))
    post = pd.DataFrame(post, columns=["side", "r"])
    n_hold = sum(len(wd[d]) for wd in wds for d in wd if d >= START)
    # fv5x + R
    ff.run_backtests()
    wx = ff.LAST["wd"][(True, True, True)]
    _, sx0 = run(wx, ev, c, fee, "none")
    _, sx1 = run(wx, ev, c, fee, "both")
    ok = k1 and k2 and k3 and k4
    row = lambda nm, s: f"| {nm} | {s['s1']:.2f} / {s['s2']:.2f} | {s['full']:.2f} | {s['ann']:+.2%} | {s['mdd']:.1%} | {s['to']:.1f} |"  # noqa: E731
    L = ["# I074 fv5 持股遇到反向季報反應就出場（自動產生）", "",
         "由 [analysis/fv5_qear_exit.py](../analysis/fv5_qear_exit.py) 產生；設計見程式開頭（看結果前固定）。"
         "Sharpe 為年化、扣成本（單邊 0.29625% ＋ 借券費）與台指期對沖後，格式 2020-08 ~ 2022 / 2023 ~ 2026-04；"
         "年換手 = 每份資金每年單邊權重變動合計（三份平均）。研究結果，非投資建議。", "",
         "| 版本 | Sharpe | 全期 | 年化淨報酬 | 最大回撤 | 年換手 |", "|---|---|---|---|---|---|",
         row("fv5（同期間）", s0), row("**fv5 + R（多空都出場）**", s1)] + [row(k, v) for k, v in rep.items()] + [
         row("只報告：fv5x（同期間）", sx0), row("只報告：fv5x + R", sx1), "",
         f"觸發出場 {len(log)} 次（多單 {int((post['side'] > 0).sum()) if len(post) else 0}、空單 {int((post['side'] < 0).sum()) if len(post) else 0}，"
         f"約占同期間換倉持股檔次 {len(log) / max(n_hold, 1):.1%}）；出場後 60 日產業調整報酬平均："
         f"多單 {post.loc[post['side'] > 0, 'r'].mean():+.2%}、空單 {post.loc[post['side'] < 0, 'r'].mean():+.2%}"
         "（多單為負、空單為正 = 出場有利）。", "",
         "## 判定", "",
         f"1. 年化淨報酬差 ≥ +0.10 個百分點（{d_ann:+.2%}）→ {'✓' if k1 else '✗'}",
         f"2. 兩段差皆 > 0（{seg[0]:+.2%} / {seg[1]:+.2%}）→ {'✓' if k2 else '✗'}",
         f"3. 兩段 Sharpe 不低於 fv5（{s1['s1']:.2f} / {s1['s2']:.2f} vs {s0['s1']:.2f} / {s0['s2']:.2f}）→ {'✓' if k3 else '✗'}",
         f"4. 配對日報酬差 Newey-West t ≥ 2.58（{t:.2f}）→ {'✓' if k4 else '✗'}", "",
         f"**結論：{'通過（是否加入 fv5 前瞻執行規則由使用者決定）' if ok else '未通過'}**"]
    (ROOT / "docs" / "fv5_qear_exit.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
