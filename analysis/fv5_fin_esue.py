"""I018 fv5 的金融股改用自結盈餘驚奇排序（點子卡 research/ideas/I018-fv5-financials-esue-score.md，檢定計畫看結果前固定）。

用法（於專案根目錄；先執行 self_earnings_parse.py）：
    .venv/Scripts/python analysis/fv5_fin_esue.py
輸出 docs/fv5_fin_esue.md。

設計（依點子卡）：
- 建構與 fv5 完全相同（前 500 名、SUE 產業內等權多空、每 3 個月三份錯開、不含緩衝、借券條件 D、台指期對沖；同 corp_event_study.fv5_filter）。
- 唯一差異（主版本）：換倉日當天，金融股（產業「金融保險」「金融業」）若在過去 45 個交易日內有已知的 ESUE（事件日 0 + 1 ≤ 換倉日，取最新一則），
  先把 ESUE 轉成這些金融股之間的百分位，再取當日全股票池 SUE 分數的同一分位數值，取代其 SUE 分數；沒有 ESUE 的金融股維持 SUE。
- 基準：fv5 建構（1.45 / 1.87，全期 1.64）。
- 通過：主版本兩段 Sharpe 都不低於基準 − 0.02，且全期 Sharpe 高於基準。
- 只報告：金融股直接排除在 fv5 之外的版本；以及各版本中金融股部位單獨的報酬（只保留金融股權重、各自對沖）。
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
import self_earnings_events as see  # noqa: E402

LOOKBACK = 45


def main():
    c = lp.prepare(500)
    days = c.adj.index
    scores = lp.leg_scores(c, "sue")
    fee = hc.lending_fees(c.client, c.tickers, days)
    quota, lend60 = bc.load_short_data(c.client, c.tickers, days)
    close = bc.raw_close(c)
    e = see.esue_table(c.client)
    e["ticker"] = e["stock_id"] + ".TW"
    e = e[e["ticker"].isin(c.tickers)].copy()
    e["k0"] = [int(days.searchsorted(d)) for d in e["date"]]
    fin = set(t for t in c.tickers if c.sector.get(t) in see.FIN)

    def shortable_at(d):
        n_short = max(1, int(c.member.loc[d].sum() / 3))
        need = lt.K_CAPITAL / n_short / close.loc[d]
        return (lend60.loc[d] > 0) & (quota.loc[d] >= need) & (need <= bc.DEPTH_FRAC * lend60.loc[d]) & (fee.loc[d] <= bc.FEE_MAX)

    replaced = []

    def esue_scores(d):
        s = scores[d].copy()
        kd = int(days.searchsorted(d))
        g = e[(e["k0"] + 1 <= kd) & (kd - e["k0"] <= LOOKBACK) & e["ticker"].isin(fin)]
        g = g.sort_values("k0").drop_duplicates("ticker", keep="last")
        g = g[[bool(c.member.at[d, t]) for t in g["ticker"]]]
        base = s.dropna()
        if len(g) >= 2 and len(base):
            p = g["esue"].rank(pct=True).to_numpy()
            s.loc[g["ticker"].to_numpy()] = np.nanquantile(base.to_numpy(), p)
        replaced.append(len(g))
        return s

    def drop_fin(d):
        s = scores[d].copy()
        s.loc[[t for t in s.index if t in fin]] = np.nan
        return s

    variants = {"fv5 建構（基準）": lambda d: scores[d], "主版本：金融股改用 ESUE": esue_scores, "金融股排除（只報告）": drop_fin}
    sched = c.schedule
    start = sched[2]
    res = {}
    for name, fn in variants.items():
        full, finpart = [], []
        for off in (0, 1, 2):
            wd = {d: lt.ew_ls_buffer(fn(d), c.sector, shortable_at(d), q_keep=None) for d in sched[off::3]}
            sim = hc.simulate_weights(wd, c.rets, c.betas, c.tx, list(wd), fee=fee)
            full.append(sim["ret"][sim.index > start])
            wf = {d: w[[t in fin for t in w.index]] for d, w in wd.items()}
            sf = hc.simulate_weights(wf, c.rets, c.betas, c.tx, list(wf), fee=fee)
            finpart.append(sf["ret"][sf.index > start])
        r = pd.concat(full, axis=1).mean(axis=1)
        rf = pd.concat(finpart, axis=1).mean(axis=1)
        res[name] = hc.stats(r) | {"full": lp.sharpe(r.dropna()), "fin_ann": float(rf.mean() * 252), "fin_sh": lp.sharpe(rf.dropna()),
                                   "fin_oos": lp.sharpe(rf[rf.index < lp.SPLIT].dropna()), "fin_is": lp.sharpe(rf[rf.index >= lp.SPLIT].dropna())}
    b, m = res["fv5 建構（基準）"], res["主版本：金融股改用 ESUE"]
    c1 = m["sh_oos"] >= b["sh_oos"] - 0.02 and m["sh_is"] >= b["sh_is"] - 0.02
    c2 = m["full"] > b["full"]
    n_rep = [x for x in replaced if x > 0]
    L = ["# I018 fv5 的金融股改用自結盈餘驚奇排序（自動產生）", "",
         "由 [analysis/fv5_fin_esue.py](../analysis/fv5_fin_esue.py) 產生；設計見程式開頭（看結果前固定）。"
         "Sharpe 為扣成本（單邊 0.29625% ＋ 借券費）與台指期對沖後，格式 2019–2022 / 2023–2026/04。事後設計、與 I015 同一段資料。研究結果，非投資建議。", "",
         f"換倉日 {len(sched)} 個；主版本每次換倉平均有 {np.mean(n_rep) if n_rep else 0:.1f} 檔金融股改用 ESUE。", "",
         "| 版本 | Sharpe 2019–2022 | Sharpe 2023–2026/04 | 全期 | 年化報酬 | 最大回撤 | 金融股部位年化貢獻 | 金融股部位 Sharpe（兩段） |", "|---|---|---|---|---|---|---|---|"]
    for name, s in res.items():
        L.append(f"| {name} | {s['sh_oos']:.2f} | {s['sh_is']:.2f} | {s['full']:.2f} | {s['ann']:+.1%} | {s['mdd']:.1%} | {s['fin_ann']:+.2%} | "
                 f"{s['fin_oos']:.2f} / {s['fin_is']:.2f} |")
    L += ["", "## 判定（主版本）", "",
          f"1. 兩段 Sharpe 不低於基準 − 0.02：{m['sh_oos']:.2f} / {m['sh_is']:.2f} vs {b['sh_oos']:.2f} / {b['sh_is']:.2f} → {'✓' if c1 else '✗'}",
          f"2. 全期 Sharpe 高於基準：{m['full']:.2f} vs {b['full']:.2f} → {'✓' if c2 else '✗'}", "",
          f"**結論：{'通過（需與 fv5 平行前瞻記錄後才能取代）' if c1 and c2 else '未通過'}**"]
    (ROOT / "docs" / "fv5_fin_esue.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
