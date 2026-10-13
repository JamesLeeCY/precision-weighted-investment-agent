"""借券腿：借券賣出餘額比、借券賣出增量、借券費率、借券需求量（全市場市值前 N 檔，fv3 建構）。

用法（於專案根目錄；資料已在快取，不需新的 API 呼叫）：
    .venv/Scripts/python analysis/lending_legs.py 300
輸出 docs/lending_legs_top{N}.md 與 reports/legs/lending_legs_top{N}.csv。

設計（看結果前固定；方向事先定為負向：借券／放空越多 → 之後報酬越差）：
- sbl_ratio：前一日借券賣出餘額（TaiwanDailyShortSaleBalances.SBLShortSalesCurrentDayBalance，股）÷ 已發行股數。
- sbl_flow：20 日借券賣出餘額變化 ÷ 已發行股數（Lin、Ho、Ko 2023：放空流量預測負報酬）。
- lend_fee：前 60 日借券成交量加權費率（Cohen、Diether、Malloy 2007：借券需求與費率高 → 之後報酬差）；無成交為缺值。
- lend_demand：20 日借券成交量（張 × 1000）÷ 已發行股數。
- 皆取負號、第 t 日只用 t−1 日以前；固定包裝（產業內 z → 20 日平均 → 對產業與 log 市值中性化）。
- 評估：產業內 IC（20 / 60 日）；fv3 建構（等權多空、限制可借、每 3 個月換倉、三份資金錯開）的單獨 Sharpe；
  與 SUE 各半合成（判準：兩段都高於 SUE 單獨）；與 SUE + 營收創新高三者等權合成（判準：兩段都高於 SUE + 營收創新高）。
"""
import math
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
import max_rec_robust as mr  # noqa: E402


def lending_raw(client, tickers, index, shares: pd.DataFrame, fee: pd.DataFrame) -> dict:
    bal, lend = {}, {}
    for t in tickers:
        sid = t.split(".")[0]
        d = client.get("TaiwanDailyShortSaleBalances", sid, "2018-06-01", "2026-05-31")
        if not d.empty:
            bal[t] = pd.Series(d["SBLShortSalesCurrentDayBalance"].astype(float).to_numpy(), index=pd.to_datetime(d["date"]))
        ld = client.get("TaiwanStockSecuritiesLending", sid, lp.EV_START, lp.EV_END)
        if not ld.empty:
            lend[t] = ld.assign(date=pd.to_datetime(ld["date"])).groupby("date")["volume"].sum().astype(float) * 1000
    B = pd.DataFrame(bal).reindex(index=index, columns=tickers).ffill()
    L = pd.DataFrame(lend).reindex(index=index, columns=tickers).fillna(0.0)
    sh = shares.reindex(index=index, columns=tickers).ffill()
    raw = {"sbl_ratio": B / sh, "sbl_flow": B.diff(20) / sh, "lend_fee": fee.copy(),
           "lend_demand": L.rolling(20, min_periods=15).sum() / sh}
    # 取負號；fee 已是前一日以前（hc.lending_fees 已 shift），其餘落後一日
    return {k: (-v if k == "lend_fee" else -v.shift(1)) for k, v in raw.items()}


def load_shares(client, tickers, index) -> pd.DataFrame:
    out = {}
    for t in tickers:
        sh = client.get("TaiwanStockShareholding", t.split(".")[0], lp.EV_START, lp.EV_END)
        if not sh.empty:
            out[t] = pd.Series(sh["NumberOfSharesIssued"].astype(float).to_numpy(), index=pd.to_datetime(sh["date"]))
    return pd.DataFrame(out).reindex(index=index, columns=tickers).ffill()


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

    def book(scores):
        parts = []
        for off in range(3):
            wd = {d: lt.ew_ls_buffer(scores[d], c.sector, short_ok[d], q_keep=None) for d in sched[off::3]}
            parts.append(hc.simulate_weights(wd, c.rets, c.betas, c.tx, list(wd), fee=fee)["ret"])
        x = pd.concat(parts, axis=1).mean(axis=1)
        return x[x.index > start]

    def zs(s):
        s = s.dropna()
        return (s - s.mean()) / s.std() if len(s) > 2 and s.std() > 0 else s * 0

    def avg(*scs):
        out = {}
        for d in sched:
            parts = [zs(sc[d]) for sc in scs]
            m = pd.concat(parts, axis=1)
            out[d] = m.mean(axis=1, skipna=False).dropna()
        return out

    def ic(scores, fwd):
        ics = pd.Series({d: lp.within_ic(scores[d], fwd.loc[d], c.sector) for d in sched}).dropna()
        out = []
        for m in (ics.index < lp.SPLIT, ics.index >= lp.SPLIT):
            x = ics[m]
            out.append((x.mean(), x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))))
        return out

    sue = lp.leg_scores(c, "sue")
    revs = {t: c.client.get("TaiwanStockMonthRevenue", t.split(".")[0], "2017-01-01") for t in c.tickers}
    mat = pd.DataFrame({t: mr.rec_n(rv, 24) for t, rv in revs.items() if not rv.empty})
    rec = {}
    for d in sched:
        mo = d.to_period("M").to_timestamp()
        v = mat.loc[mo] if mo in mat.index else pd.Series(dtype=float)
        v = v.reindex(c.tickers).where(c.member.loc[d]).replace([np.inf, -np.inf], np.nan)
        z = v.groupby(c.sector.reindex(v.index)).transform(lambda x: (x - x.mean()) / x.std())
        rec[d] = lp.neutralize(z, c.sector, c.logcap.loc[d])

    shares = load_shares(c.client, c.tickers, c.adj.index)
    raws = lending_raw(c.client, c.tickers, c.adj.index, shares, fee)
    fwd60 = c.adj.shift(-60) / c.adj - 1
    series = {"sue": book(sue), "sue+rec24": book(avg(sue, rec))}
    base1, base2 = hc.stats(series["sue"]), hc.stats(series["sue+rec24"])
    rows = []
    for name, raw in raws.items():
        wz = lp.wrap(raw.replace([np.inf, -np.inf], np.nan), c.member, c.sector)
        sc = {d: lp.neutralize(wz.loc[d], c.sector, c.logcap.loc[d]) for d in sched}
        b, b1, b2 = book(sc), book(avg(sue, sc)), book(avg(sue, rec, sc))
        series[name], series[f"sue+{name}"], series[f"sue+rec24+{name}"] = b, b1, b2
        s, s1, s2 = hc.stats(b), hc.stats(b1), hc.stats(b2)
        cov = float(np.mean([sc[d].notna().sum() / max(1, c.member.loc[d].sum()) for d in sched]))
        rows.append((name, ic(sc, c.fwd20), ic(sc, fwd60), s, s1, s2,
                     s1["sh_oos"] > base1["sh_oos"] and s1["sh_is"] > base1["sh_is"],
                     s2["sh_oos"] > base2["sh_oos"] and s2["sh_is"] > base2["sh_is"],
                     float(pd.Series({d: sc[d].corr(sue[d]) for d in sched}).mean()), cov))
        print(f"  {name}: IC20 {rows[-1][1][0][0]:+.3f}/{rows[-1][1][1][0]:+.3f}  單獨 {s['sh_oos']:.2f}/{s['sh_is']:.2f}  "
              f"+SUE {s1['sh_oos']:.2f}/{s1['sh_is']:.2f}  +SUE+rec {s2['sh_oos']:.2f}/{s2['sh_is']:.2f}", flush=True)
    pd.DataFrame(series).to_csv(ROOT / "reports" / "legs" / f"lending_legs_top{top_n}.csv")

    names = {"sbl_ratio": "借券賣出餘額比（−）", "sbl_flow": "借券賣出 20 日增量（−）", "lend_fee": "借券費率（−）", "lend_demand": "借券需求量（−）"}
    lines = [f"# 借券腿（全市場市值前 {top_n} 檔，自動產生）", "",
             "由 [analysis/lending_legs.py](../analysis/lending_legs.py) 產生；設計見程式開頭。IC 為產業內 Spearman IC（−1～1，括號 t 值），格式 2019–2022 / 2023–2026；"
             "Sharpe 為 fv3 建構（等權多空、限制可借、每 3 個月、三份資金錯開）扣交易成本與借券費、台指期對沖的年化 Sharpe，"
             f"格式 2019–2022 / 2023–2026/04（從 {start:%Y-%m-%d} 起）。研究結果，非投資建議。", "",
             f"對照：SUE 單獨 {base1['sh_oos']:.2f} / {base1['sh_is']:.2f}；SUE + 營收創新高 {base2['sh_oos']:.2f} / {base2['sh_is']:.2f}。", "",
             "| 腿 | 有值比例 | IC 20 日 | IC 60 日 | 單獨 Sharpe | 與 SUE 分數相關 | + SUE | 通過 | + SUE + 營收創新高 | 通過 |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for name, i20, i60, s, s1, s2, ok1, ok2, corr, cov in rows:
        f = lambda i: f"{i[0][0]:+.3f}（{i[0][1]:+.1f}）/ {i[1][0]:+.3f}（{i[1][1]:+.1f}）"  # noqa: E731
        lines.append(f"| {names[name]} | {cov:.0%} | {f(i20)} | {f(i60)} | {s['sh_oos']:.2f} / {s['sh_is']:.2f} | {corr:+.2f} | "
                     f"{s1['sh_oos']:.2f} / {s1['sh_is']:.2f} | {'✓' if ok1 else '✗'} | {s2['sh_oos']:.2f} / {s2['sh_is']:.2f} | {'✓' if ok2 else '✗'} |")
    (ROOT / "docs" / f"lending_legs_top{top_n}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print("DONE", flush=True)


if __name__ == "__main__":
    main(int(sys.argv[1]))
