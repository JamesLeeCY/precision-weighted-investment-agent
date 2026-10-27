"""I077 H2：fv5 合成 0.75 SUE + 0.25 CGO（點子卡 research/ideas/I077-capital-gains-overhang-disposition.md，H1 通過後依事前固定的 H2 計畫執行）。

用法（於專案根目錄；資料皆已快取）：
    .venv/Scripts/python analysis/cgo_h2.py
輸出 docs/cgo_h2.md。

設計（依點子卡；補充以「補」標示）：
- CGO 與 analysis/cgo.py 相同（名目價、換手率加權參考價、跳過 5 日），取 fv5 換倉日當日值。
- 分數 = 0.75 × SUE 產業內百分位 + 0.25 × CGO 產業內百分位（CGO 缺值 0.5），照 I040（fv5s）的合成方式；其餘全部照 fv5。
- 通過：兩段 Sharpe 皆高於 fv5（1.45 / 1.87）且全期 > 1.64。
- 只報告：年換手、與 fv5 的日報酬相關、CGO 涵蓋率。
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
import cgo as cg  # noqa: E402
import corp_event_study as ce  # noqa: E402
import hedge_construction as hc  # noqa: E402
import leg_probe as lp  # noqa: E402
import ls_turnover as lt  # noqa: E402


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

    S = ce.Sample(c.client, 1, 500, lp.market_tri(c.client), lp.tx_continuous(c.client))
    P, V = cg.nominal_and_turnover(c.client, S)
    cgo = cg.cgo_matrix(P, V).reindex(index=days, columns=c.tickers)

    def comp(d):
        s = sue[d].dropna()
        g = sector.reindex(s.index)
        x = cgo.loc[d].reindex(s.index)
        return 0.75 * s.groupby(g).rank(pct=True) + 0.25 * x.groupby(g).rank(pct=True).fillna(0.5)

    def book(fn):
        parts, tos = [], []
        for off in range(3):
            wd = {d: lt.ew_ls_buffer(fn(d), sector, shortable_at(d), q_keep=None) for d in sched[off::3]}
            sim = hc.simulate_weights(wd, c.rets, c.betas, c.tx, list(wd), fee=fee)
            parts.append(sim["ret"])
            tos.append(sim["turnover"].sum() / (len(sim) / 252))
        x = pd.concat(parts, axis=1).mean(axis=1)
        x = x[x.index > sched[2]]
        return x, hc.stats(x) | {"full": lp.sharpe(x.dropna()), "to": float(np.mean(tos))}

    x0, b0 = book(lambda d: sue[d])
    x1, b1 = book(comp)
    cov = float(np.mean([cgo.loc[d].reindex(sue[d].dropna().index).notna().mean() for d in sched]))
    ok = b1["sh_oos"] > b0["sh_oos"] and b1["sh_is"] > b0["sh_is"] and b1["full"] > b0["full"]
    corr = float(pd.concat([x0, x1], axis=1).dropna().corr().iloc[0, 1])
    L = ["# I077 H2：fv5 合成 0.75 SUE + 0.25 CGO（自動產生）", "",
         "由 [analysis/cgo_h2.py](../analysis/cgo_h2.py) 產生；設計見程式開頭（H1 通過後依事前固定的 H2 計畫）。"
         "Sharpe 為年化、扣成本（單邊 0.29625% ＋ 借券費）與台指期對沖後，格式 2019–2022 / 2023–2026/04；"
         "年換手 = 每份資金每年單邊權重變動合計（三份平均）。研究結果，非投資建議。", "",
         f"fv5 換倉日 SUE 有分數的股票中有 CGO 的比例平均 {cov:.0%}（2019 年前段不足 250 日歷史者為缺值，以 0.5 代入）。", "",
         "| 建構 | Sharpe | 全期 | 年化淨報酬 | 年化波動 | 最大回撤 | 年換手 |", "|---|---|---|---|---|---|---|"]
    for nm, s in (("fv5", b0), ("**0.75 SUE + 0.25 CGO**", b1)):
        L.append(f"| {nm} | {s['sh_oos']:.2f} / {s['sh_is']:.2f} | {s['full']:.2f} | {s['ann']:+.2%} | {s['vol']:.1%} | {s['mdd']:.1%} | {s['to']:.1f} |")
    L += ["", f"兩者日淨報酬相關 {corr:+.2f}。", "",
          "## 判定（H2）", "",
          f"- 兩段 Sharpe 皆高於 fv5 且全期 > 1.64（{b1['sh_oos']:.2f} / {b1['sh_is']:.2f}，{b1['full']:.2f}）→ {'✓' if ok else '✗'}", "",
          f"**結論：{'H2 通過（是否另立前瞻規格由使用者決定）' if ok else 'H1 通過、H2 未通過'}**"]
    (ROOT / "docs" / "cgo_h2.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
