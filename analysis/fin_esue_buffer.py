"""I017 金融股自結盈餘驚奇的低換手多空（點子卡 research/ideas/I017-financial-esue-low-turnover-ls.md，檢定計畫看結果前固定）。

用法（於專案根目錄；先執行 self_earnings_parse.py）：
    .venv/Scripts/python analysis/fin_esue_buffer.py
輸出 docs/fin_esue_buffer.md。

設計（依點子卡）：
- 樣本：2019-01 ~ 2026-04，市值前 500 名中產業為「金融保險」「金融業」的股票；ESUE 同 I015（analysis/self_earnings_events.esue_table）。
- 換倉：每月 16 日（或之後第一個交易日）收盤，用當月已公告（事件日 0 + 1 ≤ 換倉日）的 ESUE，當月至少 6 家才分三組。
- 版本：
  A. 全換倉（I015 (4a) 的重現，作為比較）：做多前三分之一、放空後三分之一。
  B. 緩衝（主規則，唯一判定用）：做多者掉到後三分之一或當月沒有公告才賣出；放空者升到前三分之一或沒有公告才回補；
     當月前／後三分之一的新名單加入；各邊等權。
  C. 每 3 個月換倉、三份資金錯開（只報告）：每份每 3 個換倉日用 A 的規則選股，三份報酬平均。
  D. 只做空端（只報告）：放空後三分之一，做多當日全部金融股成員等權。
- 所有版本：放空須通過借券條件 D（2 億資金、放空端占一半；同 borrow_capacity.py）；台指期對沖剩餘 β；單邊成本 0.29625% ＋ 實際借券費。
- 通過：B 扣成本後兩段 Sharpe 都 > 0.5，且兩段都高於 A；年換手 < 12 倍。
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
import hedge_construction as hc  # noqa: E402
import leg_probe as lp  # noqa: E402
import self_earnings_events as see  # noqa: E402

K_SHORT = 2e8


def fin_events(c, e: pd.DataFrame) -> pd.DataFrame:
    days = c.adj.index
    e = e.copy()
    e["ticker"] = e["stock_id"] + ".TW"
    e = e[e["ticker"].isin(c.tickers)]
    e["k0"] = [int(days.searchsorted(d)) for d in e["date"]]
    e = e[e["k0"] < len(days)]
    e["t0"] = days[e["k0"].to_numpy()]
    e = e[[bool(c.member.at[t0, t]) for t0, t in zip(e["t0"], e["ticker"])]]
    e = e[c.sector.reindex(e["ticker"]).isin(see.FIN).to_numpy()]
    return e.reset_index(drop=True)


def main():
    c = lp.prepare(500)
    days = c.adj.index
    e = fin_events(c, see.esue_table(c.client))
    fee = hc.lending_fees(c.client, c.tickers, days)
    quota, lend60 = bc.load_short_data(c.client, c.tickers, days)
    close = bc.raw_close(c)
    limit = int(days.searchsorted(lp.HOLDOUT))
    sched = []
    for m in pd.period_range("2019-01", "2026-04", freq="M"):
        k = int(days.searchsorted(pd.Timestamp(m.year, m.month, 16)))
        if k < limit:
            sched.append(days[k])

    def groups(d):
        """當月已知的 ESUE 三分組：{ticker: 0/1/2}（不足 6 家回傳空）。"""
        kd = int(days.searchsorted(d))
        g = e[(e["t0"].dt.to_period("M") == d.to_period("M")) & (e["k0"] + 1 <= kd)].drop_duplicates("ticker", keep="last")
        if len(g) < 6:
            return {}, set(g["ticker"])
        q = ce.terciles(g["esue"].to_numpy(float), np.ones(len(g), bool))
        return dict(zip(g["ticker"], q)), set(g["ticker"])

    def shortable(d, names):
        kd = int(days.searchsorted(d))
        ok = []
        for t in names:
            px = close.at[d, t] if t in close.columns else np.nan
            need = K_SHORT / 2 / max(len(names), 1) / px if px == px and px > 0 else np.inf
            f = fee.at[d, t]
            if lend60.at[d, t] > 0 and quota.at[d, t] >= need and need <= bc.DEPTH_FRAC * lend60.at[d, t] and f == f and f <= bc.FEE_MAX:
                ok.append(t)
        return ok

    def weights(longs, shorts):
        if not longs or not shorts:
            return pd.Series(dtype=float)
        return pd.concat([pd.Series(1 / len(longs), index=sorted(longs)), pd.Series(-1 / len(shorts), index=sorted(shorts))])

    # A 全換倉、B 緩衝、D 只做空端
    wA, wB, wD = {}, {}, {}
    pl, ps, n_b = set(), set(), []
    for d in sched:
        q, known = groups(d)
        top = {t for t, v in q.items() if v == 2}
        bot = {t for t, v in q.items() if v == 0}
        wA[d] = weights(top, shortable(d, sorted(bot)))
        keep_l = {t for t in pl if t in known and q.get(t, -1) != 0}
        keep_s = {t for t in ps if t in known and q.get(t, -1) != 2}
        L, Sh = keep_l | top, set(shortable(d, sorted(keep_s | bot)))
        wB[d] = weights(L, Sh)
        pl, ps = set(wB[d][wB[d] > 0].index), set(wB[d][wB[d] < 0].index)
        if q:
            n_b.append((len(L), len(Sh)))
        mem = [t for t in c.tickers if c.member.at[d, t] and c.sector.get(t) in see.FIN]
        wD[d] = weights(set(mem), shortable(d, sorted(bot))) if q else pd.Series(dtype=float)
    res = {}
    for name, wd in (("A. 全換倉（I015 (4a) 重現）", wA), ("B. 緩衝（主規則）", wB), ("D. 只做空端（做多全部金融股）", wD)):
        sim = hc.simulate_weights(wd, c.rets, c.betas, c.tx, sched, fee=fee)
        res[name] = hc.stats(sim["ret"], sim)
    # C 每 3 個月、三份錯開
    rets, tos = [], []
    for off in (0, 1, 2):
        sub = sched[off::3]
        sim = hc.simulate_weights({d: wA[d] for d in sub}, c.rets, c.betas, c.tx, sub, fee=fee)
        rets.append(sim["ret"][sim.index > sched[2]])
        tos.append(sim)
    r = pd.concat(rets, axis=1).mean(axis=1)
    stC = hc.stats(r)
    stC["turnover"] = float(np.mean([s["turnover"].sum() / (len(s) / 252) for s in tos]))
    stC["borrow"] = float(np.mean([s["borrow"].sum() / (len(s) / 252) for s in tos]))
    res["C. 每 3 個月換倉、三份錯開"] = stC

    a, b = res["A. 全換倉（I015 (4a) 重現）"], res["B. 緩衝（主規則）"]
    c1 = b["sh_oos"] > 0.5 and b["sh_is"] > 0.5
    c2 = b["sh_oos"] > a["sh_oos"] and b["sh_is"] > a["sh_is"]
    c3 = b["turnover"] < 12
    L = ["# I017 金融股自結盈餘驚奇的低換手多空（自動產生）", "",
         "由 [analysis/fin_esue_buffer.py](../analysis/fin_esue_buffer.py) 產生；設計見程式開頭（看結果前固定）。"
         "Sharpe 為扣成本（單邊 0.29625% ＋ 借券費）與台指期對沖後，格式 2019–2022 / 2023–2026/04。事後設計、與 I015 同一段資料。研究結果，非投資建議。", "",
         f"金融股 ESUE 事件 {len(e):,} 則、{e['ticker'].nunique()} 家；換倉日 {len(sched)} 個；B 平均做多 {np.mean([x[0] for x in n_b]):.1f} 檔、放空 {np.mean([x[1] for x in n_b]):.1f} 檔。", "",
         "| 版本 | Sharpe 2019–2022 | Sharpe 2023–2026/04 | 年化報酬 | 年化波動 | 最大回撤 | 年換手 | 年借券費 |", "|---|---|---|---|---|---|---|---|"]
    for name, s in res.items():
        L.append(f"| {name} | {s['sh_oos']:.2f} | {s['sh_is']:.2f} | {s['ann']:+.1%} | {s['vol']:.1%} | {s['mdd']:.1%} | {s['turnover']:.1f} | {s['borrow']:.2%} |")
    L += ["", "## 判定（B 緩衝）", "",
          f"1. 兩段 Sharpe > 0.5：{b['sh_oos']:.2f} / {b['sh_is']:.2f} → {'✓' if c1 else '✗'}",
          f"2. 兩段都高於 A（{a['sh_oos']:.2f} / {a['sh_is']:.2f}）→ {'✓' if c2 else '✗'}",
          f"3. 年換手 < 12 倍：{b['turnover']:.1f} → {'✓' if c3 else '✗'}", "",
          f"**結論：{'通過（需前瞻記錄後才能採用）' if c1 and c2 and c3 else '未通過'}**", "",
          "逐年 Sharpe（B）：" + "、".join(f"{y} {v:.2f}" for y, v in b["yearly"].items())]
    (ROOT / "docs" / "fin_esue_buffer.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
