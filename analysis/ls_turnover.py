"""降低等權多空（月營收驚奇）的換手：換倉頻率與持有緩衝。

用法（於專案根目錄；資料同 borrow_capacity.py）：
    .venv/Scripts/python analysis/ls_turnover.py 300
輸出 docs/ls_turnover_top{N}.md 與 reports/legs/ls_turnover_top{N}.csv。

設計（看結果前固定）：
- 基準：docs/borrow_capacity_report.md 的等權多空，放空只用可借股票（資金 2 億、條件 D），剩餘 β 以台指期對沖，扣交易成本與借券費。
- 換倉頻率：每 1 / 2 / 3 個月（只在第 1、1+k、1+2k… 個換倉日調整，中間持有不動）。
- 緩衝：新進場只從產業內前 1/3（做多）或後 1/3（放空）；已持有的多單仍在產業內前 1/2 就續抱，
  已持有的空單仍在後 1/2 且仍可借就續抱。產業內等權，產業權重 = 參與產業的檔數占比，多空各 100%。
- 可借條件 D：同 borrow_capacity（前 60 日有借券成交、需借股數 ≤ 前一日借券賣出額度、≤ 前 60 日借券量 10%、費率 ≤ 5%）；
  需借股數以「當日放空檔數的平均權重」估計（避免權重與可借條件互相依賴）。
- 共 6 個版本（3 種頻率 × 有無緩衝）；另列不限制可借（只要求有借券成交）的每 1 個月與每 3 個月 + 緩衝作參考。
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "analysis"))
import borrow_capacity as bc  # noqa: E402
import hedge_construction as hc  # noqa: E402
import leg_probe as lp  # noqa: E402

K_CAPITAL = 2e8
Q_IN, Q_KEEP = 1 / 3, 1 / 2


def ew_ls_buffer(score: pd.Series, sector: pd.Series, shortable: pd.Series, prev_long=frozenset(), prev_short=frozenset(),
                 q_in: float = Q_IN, q_keep: float | None = Q_KEEP) -> pd.Series:
    s = score.dropna()
    sec = sector.reindex(s.index)
    parts = {}
    for name, idx in s.groupby(sec).groups.items():
        sub = s.loc[idx]
        if len(sub) < 3:
            continue
        r = sub.rank(pct=True)
        long = r > 1 - q_in
        short = r <= q_in
        if q_keep is not None:
            long |= r.index.isin(list(prev_long)) & (r > 1 - q_keep)
            short |= r.index.isin(list(prev_short)) & (r <= q_keep)
        short &= shortable.reindex(sub.index).fillna(False).to_numpy(bool)
        top, bot = sub.index[long.to_numpy(bool)], sub.index[short.to_numpy(bool)]
        if len(top) and len(bot):
            parts[name] = (top, bot, len(sub))
    if not parts:
        return pd.Series(dtype=float)
    total = sum(v[2] for v in parts.values())
    out = []
    for top, bot, n in parts.values():
        out.append(pd.Series(n / total / len(top), index=top))
        out.append(pd.Series(-n / total / len(bot), index=bot))
    return pd.concat(out)


def run_variant(scores, sector, sched, k: int, buffer: bool, shortable_at) -> dict:
    """回傳 {換倉日: 權重}；只在每 k 個換倉日調整。"""
    dates = sched[::k]
    wd, pl, ps = {}, frozenset(), frozenset()
    for d in dates:
        w = ew_ls_buffer(scores[d], sector, shortable_at(d), pl, ps, q_keep=Q_KEEP if buffer else None)
        wd[d] = w
        pl, ps = frozenset(w[w > 0].index), frozenset(w[w < 0].index)
    return wd


def main(top_n: int):
    c = lp.prepare(top_n)
    scores = lp.leg_scores(c, "sue")
    fee = hc.lending_fees(c.client, c.tickers, c.adj.index)
    quota, lend60 = bc.load_short_data(c.client, c.tickers, c.adj.index)
    close = bc.raw_close(c)
    sched = c.schedule

    def shortable_at(d, constrained=True):
        n_short = max(1, int(c.member.loc[d].sum() / 3))
        need = K_CAPITAL / n_short / close.loc[d]
        a = lend60.loc[d] > 0
        if not constrained:
            return a
        return a & (quota.loc[d] >= need) & (need <= bc.DEPTH_FRAC * lend60.loc[d]) & (fee.loc[d] <= bc.FEE_MAX)

    rows, series = [], {}
    variants = [(k, b, True) for k in (1, 2, 3) for b in (False, True)] + [(1, False, False), (3, True, False)]
    for k, buf, cons in variants:
        name = f"每 {k} 個月{'＋緩衝' if buf else ''}{'' if cons else '（不限制可借）'}"
        wd = run_variant(scores, c.sector, sched, k, buf, lambda d: shortable_at(d, cons))
        sim = hc.simulate_weights(wd, c.rets, c.betas, c.tx, list(wd), fee=fee)
        s = hc.stats(sim["ret"], sim)
        s["n_long"] = float(np.mean([(w > 0).sum() for w in wd.values()]))
        rows.append((name, s))
        series[name] = sim["ret"]
        print(f"  {name}: {s['sh_oos']:.2f} / {s['sh_is']:.2f}  換手 {s['turnover']:.1f}", flush=True)
    pd.DataFrame(series).to_csv(ROOT / "reports" / "legs" / f"ls_turnover_top{top_n}.csv")

    lines = [f"# 降低等權多空的換手：換倉頻率與緩衝（全市場市值前 {top_n} 檔，自動產生）", "",
             "由 [analysis/ls_turnover.py](../analysis/ls_turnover.py) 產生；設計見程式開頭。Sharpe 為年化（無風險利率 0），"
             "兩段為 2019–2022 / 2023–2026/04；已扣交易成本與借券費，剩餘 β 以台指期對沖。研究結果，非投資建議。", "",
             "| 版本 | Sharpe 2019–2022 | 2023–2026/04 | 年化報酬 | 年化波動 | 最大回撤 | 年換手（倍） | 交易成本／年 | 借券成本／年 | 平均做多檔數 | 逐年 Sharpe |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for name, s in rows:
        yearly = "、".join(f"{y}:{v:+.1f}" for y, v in s["yearly"].items() if v == v)
        lines.append(f"| {name} | {s['sh_oos']:.2f} | {s['sh_is']:.2f} | {s['ann']:+.1%} | {s['vol']:.1%} | {s['mdd']:.1%} | "
                     f"{s['turnover']:.1f} | {s['turnover'] * lp.STOCK_COST:.1%} | {s['borrow']:.2%} | {s['n_long']:.0f} | {yearly} |")
    (ROOT / "docs" / f"ls_turnover_top{top_n}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print("DONE", flush=True)


if __name__ == "__main__":
    main(int(sys.argv[1]))
