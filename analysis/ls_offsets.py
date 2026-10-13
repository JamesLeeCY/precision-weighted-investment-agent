"""每 3 個月換倉的起點穩健性（月營收驚奇等權多空，限制可借）。

用法（於專案根目錄）：
    .venv/Scripts/python analysis/ls_offsets.py 300
輸出 docs/ls_offsets_top{N}.md 與 reports/legs/ls_offsets_top{N}.csv。

設計（看結果前固定）：
- 同 ls_turnover.py（資金 2 億、條件 D、扣交易成本與借券費、剩餘 β 以台指期對沖）。
- 每 3 個月換倉，起點分別為第 1、2、3 個換倉日（2019-01 / 02 / 03 起），有無緩衝各 3 種，共 6 個版本。
- 比較期間統一從第 3 個換倉日（2019-03 換倉後）開始，三種起點的樣本相同；對照的每月換倉也只算同一期間。
- 穩健判準：3 個起點兩段 Sharpe 都高於每月換倉（同期間），且都 > 0。
- 另列 3 個起點日報酬平均（等於把資金分成三份、錯開換倉）。
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
import ls_turnover as lt  # noqa: E402


def main(top_n: int):
    c = lp.prepare(top_n)
    scores = lp.leg_scores(c, "sue")
    fee = hc.lending_fees(c.client, c.tickers, c.adj.index)
    quota, lend60 = bc.load_short_data(c.client, c.tickers, c.adj.index)
    close = bc.raw_close(c)
    sched = c.schedule

    def shortable_at(d):
        n_short = max(1, int(c.member.loc[d].sum() / 3))
        need = lt.K_CAPITAL / n_short / close.loc[d]
        return (lend60.loc[d] > 0) & (quota.loc[d] >= need) & (need <= bc.DEPTH_FRAC * lend60.loc[d]) & (fee.loc[d] <= bc.FEE_MAX)

    start = sched[2]
    after = lambda s: s[s.index > start]  # noqa: E731
    series = {}
    wd = lt.run_variant(scores, c.sector, sched, 1, False, shortable_at)
    series["每 1 個月"] = after(hc.simulate_weights(wd, c.rets, c.betas, c.tx, list(wd), fee=fee)["ret"])
    turnover = {}
    for buf in (False, True):
        for off in (0, 1, 2):
            name = f"每 3 個月{'＋緩衝' if buf else ''}，起點第 {off + 1} 個換倉日"
            wd = lt.run_variant(scores, c.sector, sched, 3, buf, shortable_at, offset=off)
            sim = hc.simulate_weights(wd, c.rets, c.betas, c.tx, list(wd), fee=fee)
            series[name] = after(sim["ret"])
            turnover[name] = after(sim["turnover"]).sum() / (len(after(sim["ret"])) / 252)
            print(f"  {name}", flush=True)
        keys = [k for k in series if k.startswith(f"每 3 個月{'＋緩衝' if buf else ''}，")]
        series[f"每 3 個月{'＋緩衝' if buf else ''}，三起點平均（資金分三份）"] = pd.concat([series[k] for k in keys], axis=1).mean(axis=1)
    P = pd.DataFrame(series).dropna()
    P.to_csv(ROOT / "reports" / "legs" / f"ls_offsets_top{top_n}.csv")

    base = hc.stats(P["每 1 個月"])
    lines = [f"# 每 3 個月換倉的起點穩健性（全市場市值前 {top_n} 檔，自動產生）", "",
             "由 [analysis/ls_offsets.py](../analysis/ls_offsets.py) 產生；設計見程式開頭。比較期間 "
             f"{P.index[0]:%Y-%m-%d} ~ {P.index[-1]:%Y-%m-%d}（三種起點相同）。Sharpe 為年化（無風險利率 0），兩段為 2019–2022 / 2023–2026/04；"
             "已扣交易成本與借券費。研究結果，非投資建議。", "",
             "| 版本 | Sharpe 2019–2022 | 2023–2026/04 | 年化報酬 | 最大回撤 | 年換手（倍） | 兩段都高於每月換倉 |", "|---|---|---|---|---|---|---|"]
    passed = {}
    for name in P.columns:
        s = hc.stats(P[name])
        ok = s["sh_oos"] > base["sh_oos"] and s["sh_is"] > base["sh_is"] and s["sh_oos"] > 0 and s["sh_is"] > 0
        if "起點第" in name:
            passed.setdefault("緩衝" in name, []).append(ok)
        flag = "—" if name == "每 1 個月" else ("✓" if ok else "✗")
        to = turnover.get(name, float("nan"))
        lines.append(f"| {name} | {s['sh_oos']:.2f} | {s['sh_is']:.2f} | {s['ann']:+.1%} | {s['mdd']:.1%} | {to:.1f} | {flag} |")
    lines += ["", "穩健判準（3 個起點都通過）：" + "；".join(f"{'有' if k else '無'}緩衝 {'通過' if all(v) else '未通過'}（{sum(v)}/3）"
                                               for k, v in sorted(passed.items()))]
    (ROOT / "docs" / f"ls_offsets_top{top_n}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print("DONE", flush=True)


if __name__ == "__main__":
    main(int(sys.argv[1]))
