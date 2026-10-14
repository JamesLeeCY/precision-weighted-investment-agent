"""0050 擇時 + 月營收驚奇多空的混合、月營收驚奇做多（不對沖）與做多版降換手。

用法（於專案根目錄；不需新的 API 呼叫）：
    .venv/Scripts/python analysis/blend_longonly.py 500
輸出 docs/blend_longonly_top{N}.md 與 reports/legs/blend_longonly_top{N}.csv。

設計（看結果前固定）：
- 期間：2019-03-12 ~ 2026-04-30（與 fv3 建構的比較期間相同），兩段 2019–2022 / 2023–2026/04。
- 對照：0050 買進持有；0050 + 200 日線 ±2% 緩衝帶（analysis/allocation_study.timing_series，規則與成本不變）；
  等權持有整個股票池（產業權重 = 檔數占比）。
- 1. 混合：多空 = 月營收驚奇等權多空（fv3 建構：限制可借、每 3 個月、三份資金錯開，扣成本與借券費、台指期對沖）。
     資金分配 a × 擇時 0050 +（1 − a）× 多空，a = 50% / 75%；疊加 100% 擇時 0050 + k × 多空，k = 0.5 / 1.0
     （疊加需要額外保證金與借券額度，只作上限參考）。兩部位之間的再平衡成本忽略（同 allocation_study）。
- 2. 做多：產業內月營收驚奇前 1/3 等權、產業權重 = 檔數占比，不對沖、扣成本；與 0050 比較（超額報酬與 t 值）；
     另列 50% 擇時 0050 + 50% 做多。
- 3. 做多降換手：每月；每月 + 緩衝（已持有者仍在產業內前 1/2 就續抱）；每 3 個月、三份資金錯開。
"""
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "analysis"))
sys.path.insert(0, str(ROOT))
import allocation_study as al  # noqa: E402
import borrow_capacity as bc  # noqa: E402
import hedge_construction as hc  # noqa: E402
import leg_probe as lp  # noqa: E402
import ls_turnover as lt  # noqa: E402
from data.fetch_financials import get_total_return_prices  # noqa: E402

END = pd.Timestamp("2026-04-30")


def long_weights(score: pd.Series, sector: pd.Series, prev: frozenset = frozenset(), keep: float | None = None) -> pd.Series:
    """產業內前 1/3 等權（keep：已持有者仍在前 keep 就續抱），產業權重 = 檔數占比（成員 < 3 檔的產業全部持有）。"""
    s = score.dropna()
    sec = sector.reindex(s.index)
    w_sec = sec.value_counts(normalize=True)
    out = []
    for name, idx in s.groupby(sec).groups.items():
        sub = s.loc[idx]
        if len(sub) < 3:
            pick = sub.index
        else:
            r = sub.rank(pct=True)
            sel = r > 1 - lt.Q_IN
            if keep is not None:
                sel |= r.index.isin(list(prev)) & (r > 1 - keep)
            pick = sub.index[sel.to_numpy(bool)]
        if len(pick):
            out.append(pd.Series(w_sec[name] / len(pick), index=pick))
    return pd.concat(out) if out else pd.Series(dtype=float)


def timed_0050(adj: pd.Series, index: pd.DatetimeIndex) -> pd.Series:
    """allocation_study 的 ±2% 緩衝帶：timing_series 的 net 是「第 d 日決定 → 下一個交易日」的報酬，對齊到實現日。"""
    s = al.timing_series(adj, "band", start="2018-06-01", end="2026-12-31")
    nxt = pd.Series(adj.index[1:], index=adj.index[:-1])
    ser = pd.Series(s["net"].to_numpy(), index=pd.DatetimeIndex(s["d"]).map(lambda d: nxt.get(d, pd.NaT)))
    return ser[ser.index.notna()].reindex(index)


def stats(x: pd.Series, bench: pd.Series | None = None) -> dict:
    x = x.dropna()
    out = hc.stats(x)
    if bench is not None:
        d = (x - bench.reindex(x.index)).dropna()
        out["ex_ann"] = d.mean() * 252
        out["ex_t"] = d.mean() / (d.std() / math.sqrt(len(d)))
        out["corr"] = float(x.corr(bench.reindex(x.index)))
    return out


def main(top_n: int):
    c = lp.prepare(top_n)
    sched = c.schedule
    fee = hc.lending_fees(c.client, c.tickers, c.adj.index)
    quota, lend60 = bc.load_short_data(c.client, c.tickers, c.adj.index)
    close = bc.raw_close(c)

    def shortable_at(d):
        n_short = max(1, int(c.member.loc[d].sum() / 3))
        need = lt.K_CAPITAL / n_short / close.loc[d]
        return (lend60.loc[d] > 0) & (quota.loc[d] >= need) & (need <= bc.DEPTH_FRAC * lend60.loc[d]) & (fee.loc[d] <= bc.FEE_MAX)

    short_ok = {d: shortable_at(d) for d in sched}
    start = sched[2]
    zero_tx = pd.Series(0.0, index=c.tx.index)
    sue = lp.leg_scores(c, "sue")

    def tranche_book(weight_fn, hedge=True):
        parts = []
        for off in range(3):
            wd = {d: weight_fn(d) for d in sched[off::3]}
            parts.append(hc.simulate_weights(wd, c.rets, c.betas, c.tx if hedge else zero_tx, list(wd), fee=fee if hedge else None)["ret"])
        return pd.concat(parts, axis=1).mean(axis=1)

    def window(x):
        return x[(x.index > start) & (x.index <= END)]

    ls = window(tranche_book(lambda d: lt.ew_ls_buffer(sue[d], c.sector, short_ok[d], q_keep=None)))
    idx = ls.index
    e = get_total_return_prices(c.client, "0050.TW", "2018-06-01", "2026-05-31").set_index("date")["adj_close"].astype(float)
    bh = e.pct_change().reindex(idx)
    timed = timed_0050(e, idx)
    ew = window(lp.simulate({d: pd.Series(1.0, index=c.member.columns[c.member.loc[d]]) for d in sched},
                            c.rets, c.betas, c.tx, sched, c.sector, q=1.0)["long"])

    # 做多版本
    def yearly_turnover(sim):
        x = window(sim["turnover"])
        return float(x.sum() / (len(x) / 252))

    sim_m = hc.simulate_weights({d: long_weights(sue[d], c.sector) for d in sched}, c.rets, c.betas, zero_tx, sched)
    wd, prev = {}, frozenset()
    for d in sched:
        w = long_weights(sue[d], c.sector, prev, keep=0.5)
        wd[d], prev = w, frozenset(w.index)
    sim_buf = hc.simulate_weights(wd, c.rets, c.betas, zero_tx, sched)
    q3_sims = [hc.simulate_weights({d: long_weights(sue[d], c.sector) for d in sched[off::3]}, c.rets, c.betas, zero_tx,
                                   sched[off::3]) for off in range(3)]
    lo_m, lo_buf = window(sim_m["ret"]), window(sim_buf["ret"])
    lo_q3 = window(pd.concat([s["ret"] for s in q3_sims], axis=1).mean(axis=1))
    turn = {"做多：每月": yearly_turnover(sim_m), "做多：每月 + 緩衝": yearly_turnover(sim_buf),
            "做多：每 3 個月、三份錯開": float(np.mean([yearly_turnover(s) for s in q3_sims]))}

    S = {"0050 買進持有": bh, "0050 + ±2% 緩衝帶擇時": timed, "等權持有股票池": ew, "月營收驚奇多空（fv3 建構）": ls,
         "50% 擇時 0050 + 50% 多空": 0.5 * timed + 0.5 * ls, "75% 擇時 0050 + 25% 多空": 0.75 * timed + 0.25 * ls,
         "50% 0050 買進持有 + 50% 多空": 0.5 * bh + 0.5 * ls,
         "擇時 0050 + 0.5 × 多空（疊加）": timed + 0.5 * ls, "擇時 0050 + 1.0 × 多空（疊加）": timed + ls,
         "做多：每月": lo_m, "做多：每月 + 緩衝": lo_buf, "做多：每 3 個月、三份錯開": lo_q3,
         "50% 擇時 0050 + 50% 做多（每 3 個月）": 0.5 * timed + 0.5 * lo_q3}
    P = pd.DataFrame(S)
    P.to_csv(ROOT / "reports" / "legs" / f"blend_longonly_top{top_n}.csv")

    lines = [f"# 0050 擇時 + 多空混合、做多與做多降換手（全市場市值前 {top_n} 檔，自動產生）", "",
             "由 [analysis/blend_longonly.py](../analysis/blend_longonly.py) 產生；設計見程式開頭。Sharpe = 年化報酬 ÷ 年化波動（無風險利率 0），"
             f"兩段為 2019–2022 / 2023–2026/04；期間 {idx[0]:%Y-%m-%d} ~ {idx[-1]:%Y-%m-%d}；已扣交易成本（多空另扣借券費）。"
             "超額 = 相對 0050 買進持有的年化每日報酬差（括號 t 值）。研究結果，非投資建議。", "",
             "| 策略 | Sharpe 2019–2022 | 2023–2026/04 | 年化報酬 | 年化波動 | 最大回撤 | 相對 0050 超額 | 與 0050 相關 |",
             "|---|---|---|---|---|---|---|---|"]
    for k in P.columns:
        s = stats(P[k], bh)
        ex = "—" if k == "0050 買進持有" else f"{s['ex_ann']:+.1%}（{s['ex_t']:+.1f}）"
        lines.append(f"| {k} | {s['sh_oos']:.2f} | {s['sh_is']:.2f} | {s['ann']:+.1%} | {s['vol']:.1%} | {s['mdd']:.1%} | {ex} | {s['corr']:+.2f} |")
    lines += ["", "做多版年換手（倍，單一份資金計）：" + "；".join(f"{k} {v:.1f}" for k, v in turn.items()) + "。"]
    (ROOT / "docs" / f"blend_longonly_top{top_n}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print("DONE", flush=True)


if __name__ == "__main__":
    main(int(sys.argv[1]))
