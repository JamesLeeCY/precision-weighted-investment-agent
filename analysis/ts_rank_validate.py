"""I040 第 (c)(d) 步：只對通過 (a)(b) 的 S1（借券賣出餘額比的 ts_rank，負向）做驗證樣本與 fv5 合成（設計同 analysis/ts_rank_chips.py，看結果前固定）。

用法（於專案根目錄；第 501–1000 名的借券賣出餘額與股本約 1,200 次 FinMind，額度不足會自動等待）：
    .venv/Scripts/python analysis/ts_rank_validate.py
輸出 docs/ts_rank_validate.md。

- (c) 第 501–1000 名：同樣的 x1、ts_rank、包裝（log 市值用 corp_event_study.Sample.lmcap，補），60 日產業內 IC > 0 且 Newey-West t > 2。
- (d) fv5 建構（前 500 名、等權多空、借券條件 D、每 3 個月三份錯開、台指期對沖、單邊 0.29625% ＋ 借券費），
  分數改為 0.75 × SUE 產業內百分位 ＋ 0.25 × S1 產業內百分位；兩段 Sharpe ≥ fv5 且全期 > fv5。
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
import lending_legs as ll  # noqa: E402
import ls_turnover as lt  # noqa: E402
import ts_rank_chips as trc  # noqa: E402
from sue_attention import nw_t  # noqa: E402


def s1(client, tickers, idx):
    sbl = {}
    for i, t in enumerate(tickers):
        d = client.get("TaiwanDailyShortSaleBalances", t.split(".")[0], "2018-06-01", "2026-05-31")
        if not d.empty:
            sbl[t] = pd.Series(d["SBLShortSalesCurrentDayBalance"].astype(float).to_numpy(), index=pd.to_datetime(d["date"]))
        if i % 100 == 0:
            print(f"借券 {i}/{len(tickers)}", flush=True)
    sh = ll.load_shares(client, tickers, idx)
    x1 = pd.DataFrame(sbl).reindex(index=idx, columns=tickers).ffill() / sh
    ts = trc.ts_rank(x1).where(x1.rolling(250, min_periods=120).max() > 0)
    return -ts.shift(1)


def main():
    import dotenv

    c = lp.prepare(500)
    dotenv.load_dotenv(ROOT / ".env")
    V = ce.Sample(c.client, 501, 1000, lp.market_tri(c.client), lp.tx_continuous(c.client))
    vsec = pd.Series({t: V.sector.get(t.split(".")[0], "NA") for t in V.tickers})
    raw = s1(c.client, V.tickers, V.days)
    wz = lp.wrap(raw.replace([np.inf, -np.inf], np.nan), V.member, vsec)
    sched = [d for d in c.schedule if d in V.days and int(V.days.searchsorted(d)) + 60 < V.limit]
    fwd60 = V.adj.shift(-60) / V.adj - 1
    ic = pd.Series({d: lp.within_ic(lp.neutralize(wz.loc[d], vsec, V.lmcap.loc[d]), fwd60.loc[d], vsec) for d in sched}).dropna()
    seg = lambda s: (float(s.mean()), nw_t(s, 3), len(s))  # noqa: E731
    v = {"2019–2022": seg(ic[ic.index < lp.SPLIT]), "2023–2026/04": seg(ic[ic.index >= lp.SPLIT]), "全期": seg(ic)}
    cc = v["全期"][0] > 0 and v["全期"][1] > 2

    # (d) fv5 合成（主樣本）
    X, _ = trc.raw_fields(c)
    ts1 = trc.ts_rank(X["x1"]).where(X["x1"].rolling(250, min_periods=120).max() > 0)
    mwz = lp.wrap((-ts1.shift(1)).replace([np.inf, -np.inf], np.nan), c.member, c.sector)
    sc = {d: lp.neutralize(mwz.loc[d], c.sector, c.logcap.loc[d]) for d in c.schedule}
    sue = lp.leg_scores(c, "sue")
    fee = hc.lending_fees(c.client, c.tickers, c.adj.index)
    quota, lend60 = bc.load_short_data(c.client, c.tickers, c.adj.index)
    close = bc.raw_close(c)

    def shortable_at(d):
        n_short = max(1, int(c.member.loc[d].sum() / 3))
        need = lt.K_CAPITAL / n_short / close.loc[d]
        return (lend60.loc[d] > 0) & (quota.loc[d] >= need) & (need <= bc.DEPTH_FRAC * lend60.loc[d]) & (fee.loc[d] <= bc.FEE_MAX)

    def comp(d):
        s = sue[d].dropna()
        g = c.sector.reindex(s.index)
        a = s.groupby(g).rank(pct=True)
        b = sc[d].reindex(s.index).groupby(g).rank(pct=True).fillna(0.5)
        return 0.75 * a + 0.25 * b

    def book(fn):
        parts = []
        for off in range(3):
            w = {d: lt.ew_ls_buffer(fn(d), c.sector, shortable_at(d), q_keep=None) for d in c.schedule[off::3]}
            parts.append(hc.simulate_weights(w, c.rets, c.betas, c.tx, list(w), fee=fee)["ret"])
        x = pd.concat(parts, axis=1).mean(axis=1)
        x = x[x.index > c.schedule[2]]
        return hc.stats(x) | {"full": lp.sharpe(x.dropna())}
    base, cmb, alone = book(lambda d: sue[d]), book(comp), book(lambda d: sc[d])
    cd = cmb["sh_oos"] >= base["sh_oos"] and cmb["sh_is"] >= base["sh_is"] and cmb["full"] > base["full"]
    fic = lambda x: f"{x[0]:+.3f}（{x[1]:.1f}，{x[2]}）"  # noqa: E731
    L = ["# I040 S1（借券賣出餘額比 ts_rank）驗證與 fv5 合成（自動產生）", "",
         "由 [analysis/ts_rank_validate.py](../analysis/ts_rank_validate.py) 產生；設計見程式開頭（看結果前固定）。IC 為產業內 Spearman 60 日，括號為（Newey-West t，換倉日數）；"
         "Sharpe 為扣成本與台指期對沖後，格式 2019–2022 / 2023–2026/04。研究結果，非投資建議。", "",
         "| (c) 第 501–1000 名 60 日 IC | 2019–2022 | 2023–2026/04 | 全期 |", "|---|---|---|---|",
         f"| S1 | {fic(v['2019–2022'])} | {fic(v['2023–2026/04'])} | {fic(v['全期'])} |", "",
         "| (d) 建構（前 500 名） | Sharpe | 全期 | 年化報酬 | 最大回撤 |", "|---|---|---|---|---|"]
    for k, s in (("fv5（SUE）", base), ("合成：0.75 SUE ＋ 0.25 S1", cmb), ("只報告：S1 單獨多空", alone)):
        L.append(f"| {k} | {s['sh_oos']:.2f} / {s['sh_is']:.2f} | {s['full']:.2f} | {s['ann']:+.1%} | {s['mdd']:.1%} |")
    L += ["", "## 判定", "",
          f"(c) 驗證 60 日 IC > 0、t > 2：{fic(v['全期'])} → {'✓' if cc else '✗'}",
          f"(d) 合成兩段 ≥ fv5、全期 > fv5：{cmb['sh_oos']:.2f} / {cmb['sh_is']:.2f}、{cmb['full']:.2f} vs {base['sh_oos']:.2f} / {base['sh_is']:.2f}、{base['full']:.2f} → {'✓' if cd else '✗'}", "",
          f"**結論：{'S1 通過（另立前瞻規格，不改 fv5）' if cc and cd else ('S1 訊號成立（a–c），合成未勝過 fv5' if cc else 'S1 驗證未通過')}**"]
    (ROOT / "docs" / "ts_rank_validate.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
