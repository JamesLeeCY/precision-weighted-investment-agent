"""I079 fv5 多方腿改用指數避險：台指期 ＋ 0051 滾動 β（點子卡 research/ideas/I079-fv5-long-leg-index-hedge-capacity.md，檢定計畫看結果前固定）。

用法（於專案根目錄；資料皆已快取，0051 價格與借券約 2 次請求）：
    .venv/Scripts/python analysis/fv5_long_index_hedge.py
輸出 docs/fv5_long_index_hedge.md。

設計（依點子卡；補充以「補」標示）：
- 多方腿：fv5 每個換倉日權重的正數部分（產業內 SUE 前 1/3 等權，合計 1），三份錯開、每份每 3 個換倉日換倉。
- 避險 LH：每個換倉日 d，用 d 之前（含 d）250 個交易日，把當時持股權重回推的日報酬對台指期近月報酬與 0051 還原日報酬
  做 OLS（含截距），兩個係數為空單比率，到下個換倉日前固定。
  補：回推窗內有效觀測少於 120 日時用全部可得觀測（至少 60 日）；股票缺值以 0 計。
- 成本：股票單邊 0.29625%（多方換手與 0051 空單比率變動）；台指期 0.005%（比率變動），另每月轉倉一次（平倉＋建倉 2 × 0.005% × |台指期比率|，
  補：按日平均攤提）；0051 空單扣借券費（前 60 日成交量加權費率，無成交時 1.5%／年）。
- 期間：與 fv5 相同，從第 3 個換倉日之後起算，2019–2022 / 2023–2026/04。
- 通過（兩項皆成立）：LH 日淨報酬全期平均 > 0、Newey-West（落後 5）t ≥ 2.58、兩段平均皆 > 0；兩段 Sharpe 皆 ≥ 1.0。
- 只報告：與 fv5 的日報酬相關、50% fv5 + 50% LH；資金 10 億時的 fv5（條件 D 的 K_CAPITAL = 10 億）；回推窗 R² 中位數與 LH 扣成本前波動；
  2023-07 起改用中型100期貨（M1F）取代 0051 的版本（期貨成本，不計借券費）；三因子（加櫃買報酬指數，成本與 0051 相同假設）；
  fv5 多空兩腿各自相對同產業等權（全部成員等權，產業權重與 fv5 相同）的淨貢獻。
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
import hedge_construction as hc  # noqa: E402
import leg_probe as lp  # noqa: E402
import ls_turnover as lt  # noqa: E402
import smallcap_execution as sx  # noqa: E402
from data.fetch_financials import get_total_return_prices  # noqa: E402
from sue_attention import nw_t  # noqa: E402

WIN, MIN_OBS, MIN_ANY = 250, 120, 60
FEE_DEFAULT = 1.5
ROLL = 2 * lp.FUT_COST * 12 / 252


def hedge_book(wds, R, factors: dict, kinds: dict, fee51: pd.Series, start, r2s: list | None = None):
    """wds：各份 {換倉日: 多方權重}；factors：{名稱: 日報酬}；kinds：{名稱: "fut" / "stock"}。回傳（日淨報酬, 日毛報酬）。"""
    days = R.index
    F = pd.DataFrame(factors).reindex(days)
    parts, gparts = [], []
    for wd in wds:
        reb = list(wd)
        net, gross = pd.Series(np.nan, index=days), pd.Series(np.nan, index=days)
        w_prev, b_prev = pd.Series(dtype=float), pd.Series(0.0, index=F.columns)
        for n, d in enumerate(reb):
            nxt = reb[n + 1] if n + 1 < len(reb) else lp.HOLDOUT
            period = days[(days > d) & (days <= nxt)]
            if not len(period):
                continue
            w = wd[d]
            kd = int(days.searchsorted(d))
            win = days[max(0, kd - WIN + 1):kd + 1]
            y = R.loc[win, w.index].fillna(0.0).to_numpy() @ w.to_numpy()
            X = F.loc[win]
            ok = X.notna().all(axis=1).to_numpy() & (np.abs(y) > 0)
            if ok.sum() < MIN_ANY:
                continue
            A = np.column_stack([np.ones(ok.sum()), X.to_numpy()[ok]])
            coef, *_ = np.linalg.lstsq(A, y[ok], rcond=None)
            b = pd.Series(coef[1:], index=F.columns)
            if r2s is not None:
                res = y[ok] - A @ coef
                r2s.append(1 - res.var() / y[ok].var())
            g = R.loc[period, w.index].fillna(0.0).to_numpy() @ w.to_numpy() - F.loc[period].fillna(0.0).to_numpy() @ b.to_numpy()
            r = g.copy()
            for f in F.columns:
                if kinds[f] == "fut":
                    r -= abs(b[f]) * ROLL
                else:
                    r -= max(b[f], 0.0) * fee51.reindex(period).fillna(FEE_DEFAULT).to_numpy() / 100 / 252
            cost = float(w.sub(w_prev, fill_value=0.0).abs().sum()) * lp.STOCK_COST
            cost += sum(abs(b[f] - b_prev[f]) * (lp.FUT_COST if kinds[f] == "fut" else lp.STOCK_COST) for f in F.columns)
            r[0] -= cost
            net.loc[period], gross.loc[period] = r, g
            w_prev, b_prev = w, b
        parts.append(net)
        gparts.append(gross)
    x = pd.concat(parts, axis=1).mean(axis=1)
    gx = pd.concat(gparts, axis=1).mean(axis=1)
    return x[x.index > start].dropna(), gx[gx.index > start].dropna()


def st(x):
    x = x.dropna()
    return hc.stats(x) | {"full": lp.sharpe(x), "m1": float(x[x.index < lp.SPLIT].mean() * 252),
                          "m2": float(x[x.index >= lp.SPLIT].mean() * 252)}


def main():
    import dotenv

    dotenv.load_dotenv(ROOT / ".env")
    c = lp.prepare(500)
    days, sched, sector = c.adj.index, c.schedule, c.sector
    sue = lp.leg_scores(c, "sue")
    fee = hc.lending_fees(c.client, c.tickers, days)
    quota, lend60 = bc.load_short_data(c.client, c.tickers, days)
    raw = bc.raw_close(c)

    def shortable_at(d, K=lt.K_CAPITAL):
        n_short = max(1, int(c.member.loc[d].sum() / 3))
        need = K / n_short / raw.loc[d]
        return (lend60.loc[d] > 0) & (quota.loc[d] >= need) & (need <= bc.DEPTH_FRAC * lend60.loc[d]) & (fee.loc[d] <= bc.FEE_MAX)

    start = sched[2]
    W = {d: lt.ew_ls_buffer(sue[d], sector, shortable_at(d), q_keep=None) for d in sched}
    W = {d: w for d, w in W.items() if len(w)}

    def ls_book(W_, fee_=fee):
        parts = []
        for off in range(3):
            wd = {d: W_[d] for d in sched[off::3] if d in W_}
            parts.append(hc.simulate_weights(wd, c.rets, c.betas, c.tx, list(wd), fee=fee_)["ret"])
        x = pd.concat(parts, axis=1).mean(axis=1)
        return x[x.index > start]

    x_fv5 = ls_book(W)
    longs = [{d: W[d][W[d] > 0] for d in sched[off::3] if d in W} for off in range(3)]
    p51 = get_total_return_prices(c.client, "0051.TW", "2017-01-01", "2026-05-31")
    r51 = pd.Series(p51["adj_close"].astype(float).to_numpy(), index=pd.DatetimeIndex(p51["date"])).pct_change()
    fee51 = hc.lending_fees(c.client, ["0051.TW"], days)["0051.TW"]
    rtx = sx.fut_series(c.client, "TX")[0]
    rm1f = sx.fut_series(c.client, "M1F")[0]
    otc = c.client.get("TaiwanStockTotalReturnIndex", "TPEx", "2017-01-01", "2026-05-31")
    rotc = pd.Series(otc["price"].astype(float).to_numpy(), index=pd.to_datetime(otc["date"])).sort_index().pct_change()
    R = c.rets
    r2s = []
    x_lh, g_lh = hedge_book(longs, R, {"TX": rtx, "0051": r51}, {"TX": "fut", "0051": "stock"}, fee51, start, r2s)
    s_fv5, s_lh = st(x_fv5), st(x_lh)
    t = nw_t(x_lh, 5)
    k1 = s_lh["ann"] > 0 and t >= 2.58 and s_lh["m1"] > 0 and s_lh["m2"] > 0
    k2 = s_lh["sh_oos"] >= 1.0 and s_lh["sh_is"] >= 1.0
    print("main", s_lh["sh_oos"], s_lh["sh_is"], t, flush=True)
    # 只報告
    corr = float(pd.concat([x_fv5, x_lh], axis=1).dropna().corr().iloc[0, 1])
    s_mix = st((0.5 * x_fv5 + 0.5 * x_lh).dropna())
    W10 = {d: lt.ew_ls_buffer(sue[d], sector, shortable_at(d, 1e9), q_keep=None) for d in sched}
    W10 = {d: w for d, w in W10.items() if len(w)}
    s_fv5_10 = st(ls_book(W10))
    x_tx, _ = hedge_book(longs, R, {"TX": rtx}, {"TX": "fut"}, fee51, start)
    s_tx = st(x_tx)
    x3f, _ = hedge_book(longs, R, {"TX": rtx, "0051": r51, "TPEx": rotc}, {"TX": "fut", "0051": "stock", "TPEx": "stock"}, fee51, start)
    s_3f = st(x3f)
    m_start = max(start, pd.Timestamp("2023-07-01"))
    rm = rm1f.where(rm1f.index >= pd.Timestamp("2023-01-01"))
    x_m1f, _ = hedge_book(longs, R, {"TX": rtx, "M1F": rm}, {"TX": "fut", "M1F": "fut"}, fee51, m_start)
    x_m1f = x_m1f[x_m1f.index > m_start]
    x_51b = x_lh[x_lh.index > m_start]
    # fv5 兩腿拆解：相對同產業等權（全部成員、產業權重同 fv5）
    def ew_bench(d):
        w = W[d]
        sec_w = w[w > 0].groupby(sector.reindex(w[w > 0].index)).sum()
        m = c.member.loc[d].astype(bool)
        g = sector.reindex(m[m].index)
        b = g.map(sec_w).fillna(0.0) / g.map(g.value_counts())
        return b[b > 0]
    WLc = {d: W[d][W[d] > 0].sub(ew_bench(d), fill_value=0.0) for d in W}
    WSc = {d: W[d][W[d] < 0].add(ew_bench(d), fill_value=0.0) for d in W}
    s_lc, s_sc = st(ls_book(WLc, None)), st(ls_book(WSc))
    ok = k1 and k2
    row = lambda nm, s: f"| {nm} | {s['sh_oos']:.2f} / {s['sh_is']:.2f} | {s['full']:.2f} | {s['ann']:+.2%} | {s['vol']:.1%} | {s['mdd']:.1%} |"  # noqa: E731
    hdr = ["| 版本 | Sharpe | 全期 | 年化淨報酬 | 年化波動 | 最大回撤 |", "|---|---|---|---|---|---|"]
    L = ["# I079 fv5 多方腿改用指數避險（自動產生）", "",
         "由 [analysis/fv5_long_index_hedge.py](../analysis/fv5_long_index_hedge.py) 產生；設計見程式開頭（看結果前固定）。"
         "Sharpe 為年化、扣成本後，格式 2019–2022 / 2023–2026/04；fv5 為多空各 100%、LH 為多方 100% 加指數空單。研究結果，非投資建議。", "",
         *hdr, row("fv5（多空，條件 D、2 億）", s_fv5), row("**LH：多方腿 − 台指期 − 0051（滾動 β）**", s_lh),
         row("只報告：多方腿 − 台指期（單因子）", s_tx), row("只報告：三因子（加櫃買報酬指數）", s_3f),
         row("只報告：50% fv5 + 50% LH", s_mix), row("只報告：fv5，資金 10 億（條件 D）", s_fv5_10), "",
         f"LH 日報酬與 fv5 相關 {corr:+.2f}；回推窗 R² 中位數 {np.median(r2s):.2f}；LH 扣成本前年化波動 {g_lh.std() * np.sqrt(252):.1%}、"
         f"扣成本前年化 {g_lh.mean() * 252:+.2%}（扣成本後 {x_lh.mean() * 252:+.2%}）。", "",
         f"只報告：{m_start.date()} 之後，0051 版 Sharpe {lp.sharpe(x_51b):.2f}、年化 {x_51b.mean() * 252:+.2%}；"
         f"改用中型100期貨（M1F）版 Sharpe {lp.sharpe(x_m1f):.2f}、年化 {x_m1f.mean() * 252:+.2%}。", "",
         "只報告：fv5 兩腿相對同產業等權的淨貢獻（多方不計借券費、空方扣借券費；各自以台指期對沖剩餘 β）：", "",
         *hdr, row("多方腿 − 同產業等權", s_lc), row("同產業等權 − 空方腿（扣借券費）", s_sc), "",
         "## 判定", "",
         f"1. LH 日淨報酬全期平均 > 0 且 Newey-West t ≥ 2.58、兩段皆 > 0（年化 {s_lh['ann']:+.2%}，t {t:.2f}；兩段 {s_lh['m1']:+.2%} / {s_lh['m2']:+.2%}）→ {'✓' if k1 else '✗'}",
         f"2. 兩段 Sharpe 皆 ≥ 1.0（{s_lh['sh_oos']:.2f} / {s_lh['sh_is']:.2f}）→ {'✓' if k2 else '✗'}", "",
         f"**結論：{'通過（是否另立前瞻規格由使用者決定）' if ok else '未通過'}**"]
    (ROOT / "docs" / "fv5_long_index_hedge.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
