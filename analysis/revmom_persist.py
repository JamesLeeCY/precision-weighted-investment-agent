"""營收動能延伸（營收創新高、年增率加速、3 個月年增率）與持續性動能（平均相對排名、frog-in-the-pan）。

用法（於專案根目錄；資料同 leg_probe / borrow_capacity，不需新的 API 呼叫）：
    .venv/Scripts/python analysis/revmom_persist.py 300
輸出 docs/revmom_persist_top{N}.md 與 reports/legs/revmom_persist_top{N}.csv。

設計（看結果前固定；方向事先決定）：
- 營收訊號（營收月份 m，於 m+1 月公告期限後的換倉日可用，同 SUE；不修改被 fv2 / fv3 凍結的 data/revenue_signal.py）：
  rec24 = R_m ÷ max(R_{m−1} … R_{m−24}) − 1（至少 12 個月）；accel = 年增率_m − 前 3 個月年增率平均；
  yoy3 =（R_m + R_{m−1} + R_{m−2}）÷ 去年同期 3 個月 − 1。分數同 SUE：產業內 z → 對產業與 log 市值中性化。
- 持續性動能（價量，第 t 日只用 t−1 日以前）：
  persist = 過去第 12 ~ 第 2 個月（11 個月）每月報酬的產業內百分位排名平均（Chen、Hsieh、Lee 2023 的持續贏家／輸家概念）；
  fip = 12-1 動能，只保留資訊離散度 ID = sign(報酬) ×（下跌日比例 − 上漲日比例）在當日中位數以下（漸進上漲／下跌）的股票
  （Da、Gurun、Warachka 2014）。分數用固定包裝（產業內 z → 20 日平均 → 中性化）。
- 評估：產業內 IC（20 日、60 日；2019–2022 / 2023–2026）；fv3 的建構（等權多空、限制可借、每 3 個月換倉、三份資金錯開平均，
  比較期間從第 3 個換倉日起）；與月營收驚奇多空的相關；與月營收驚奇的分數各半合成。
- 判準：合成的兩段 Sharpe 都高於月營收驚奇單獨，才算有增量。
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


def revenue_extensions(rev: pd.DataFrame) -> pd.DataFrame:
    """FinMind 月營收 → [avail_month, rec24, accel, yoy3]（營收月份 m 於 m+1 月可用）。"""
    r = rev.copy()
    r["ym"] = pd.to_datetime(dict(year=r["revenue_year"], month=r["revenue_month"], day=1))
    r = r.drop_duplicates("ym", keep="last").set_index("ym")["revenue"].astype(float).asfreq("MS")
    prior_max = r.shift(1).rolling(24, min_periods=12).max()
    yoy = r / r.shift(12) - 1
    s3 = r.rolling(3, min_periods=3).sum()
    out = pd.DataFrame({"rec24": r / prior_max.where(prior_max > 0) - 1,
                        "accel": yoy - yoy.shift(1).rolling(3, min_periods=3).mean(),
                        "yoy3": s3 / s3.shift(12).where(s3.shift(12) > 0) - 1})
    out.index = out.index + pd.offsets.MonthBegin(1)
    return out.rename_axis("avail_month").reset_index()


def persistence_signals(adj: pd.DataFrame, member: pd.DataFrame, sector: pd.Series) -> dict:
    """persist（11 個月平均產業內排名）、fip（低 ID 的 12-1 動能）；皆落後一日。"""
    me = adj.resample("ME").last()
    mret = me.pct_change()
    mem_me = member.resample("ME").last().reindex(index=mret.index).fillna(False).astype(bool)
    x = mret.where(mem_me)
    rank = x.T.groupby(sector.reindex(x.columns)).rank(pct=True).T
    persist_m = rank.shift(1).rolling(11, min_periods=8).mean()          # 第 t−12 ~ t−2 個月
    persist = persist_m.reindex(adj.index, method="ffill")              # 月底值延續到下個月
    r = adj.pct_change()
    pret = adj.shift(21) / adj.shift(252) - 1
    pos = (r > 0).astype(float).rolling(231, min_periods=180).mean().shift(21)
    neg = (r < 0).astype(float).rolling(231, min_periods=180).mean().shift(21)
    idisc = np.sign(pret) * (neg - pos)
    med = idisc.where(member).median(axis=1)
    fip = pret.where(idisc.le(med, axis=0))
    return {"persist": persist.shift(1), "fip": fip.shift(1)}


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
            wd = lt.run_variant(scores, c.sector, sched, 3, False, lambda d: short_ok[d], offset=off)
            sim = hc.simulate_weights(wd, c.rets, c.betas, c.tx, list(wd), fee=fee)
            parts.append(sim["ret"])
        x = pd.concat(parts, axis=1).mean(axis=1)
        return x[x.index > start]

    # 營收訊號（同 SUE 的時點與分數）
    ext = {}
    for t in c.tickers:
        rev = c.client.get("TaiwanStockMonthRevenue", t.split(".")[0], "2017-01-01")
        if not rev.empty:
            ext[t] = revenue_extensions(rev).set_index("avail_month")
    rev_scores = {}
    for name in ("rec24", "accel", "yoy3"):
        mat = pd.DataFrame({t: v[name] for t, v in ext.items()})
        sc = {}
        for d in sched:
            mo = d.to_period("M").to_timestamp()
            v = mat.loc[mo] if mo in mat.index else pd.Series(dtype=float)
            v = v.reindex(c.tickers).where(c.member.loc[d]).replace([np.inf, -np.inf], np.nan)
            z = v.groupby(c.sector.reindex(v.index)).transform(lambda x: (x - x.mean()) / x.std())
            sc[d] = lp.neutralize(z, c.sector, c.logcap.loc[d])
        rev_scores[name] = sc
    price_raw = persistence_signals(c.adj, c.member, c.sector)
    price_scores = {}
    for name, raw in price_raw.items():
        wz = lp.wrap(raw, c.member, c.sector)
        price_scores[name] = {d: lp.neutralize(wz.loc[d], c.sector, c.logcap.loc[d]) for d in sched}
    sue = lp.leg_scores(c, "sue")
    fwd60 = c.adj.shift(-60) / c.adj - 1

    def zs(s):
        s = s.dropna()
        return (s - s.mean()) / s.std() if len(s) > 2 and s.std() > 0 else s * 0

    def ic(scores, fwd):
        ics = pd.Series({d: lp.within_ic(scores[d], fwd.loc[d], c.sector) for d in sched}).dropna()
        out = []
        for m in (ics.index < lp.SPLIT, ics.index >= lp.SPLIT):
            x = ics[m]
            out.append((x.mean(), x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))))
        return out

    sue_book = book(sue)
    ss = hc.stats(sue_book)
    series = {"sue": sue_book}
    rows = []
    for name, sc in {**rev_scores, **price_scores}.items():
        b = book(sc)
        comp = {d: (zs(sue[d]).add(zs(sc[d]), fill_value=np.nan) / 2).dropna() for d in sched}
        cb = book(comp)
        series[name], series[f"sue+{name}"] = b, cb
        s, cs = hc.stats(b), hc.stats(cb)
        rows.append((name, ic(sc, c.fwd20), ic(sc, fwd60), s, float(b.corr(sue_book)), cs,
                     cs["sh_oos"] > ss["sh_oos"] and cs["sh_is"] > ss["sh_is"],
                     float(pd.Series({d: sc[d].corr(sue[d]) for d in sched}).mean())))
        print(f"  {name}: IC20 {rows[-1][1][0][0]:+.3f}/{rows[-1][1][1][0]:+.3f}  單獨 {s['sh_oos']:.2f}/{s['sh_is']:.2f}  合成 {cs['sh_oos']:.2f}/{cs['sh_is']:.2f}", flush=True)
    pd.DataFrame(series).to_csv(ROOT / "reports" / "legs" / f"revmom_persist_top{top_n}.csv")

    names = {"rec24": "營收創新高（÷ 前 24 個月最高）", "accel": "年增率加速（− 前 3 個月平均）", "yoy3": "3 個月年增率",
             "persist": "持續性：11 個月平均產業內排名", "fip": "frog-in-the-pan 動能（低 ID）"}
    lines = [f"# 營收動能延伸與持續性動能（全市場市值前 {top_n} 檔，自動產生）", "",
             "由 [analysis/revmom_persist.py](../analysis/revmom_persist.py) 產生；設計見程式開頭。IC 為產業內 Spearman IC（−1～1，括號 t 值）；"
             "多空 = fv3 建構（等權多空、限制可借、每 3 個月換倉、三份資金錯開），扣交易成本與借券費、台指期對沖，Sharpe 為年化；"
             f"兩段為 2019–2022 / 2023–2026/04（多空從 {start:%Y-%m-%d} 起）。研究結果，非投資建議。", "",
             f"對照：月營收驚奇單獨 Sharpe {ss['sh_oos']:.2f} / {ss['sh_is']:.2f}（年化 {ss['ann']:+.1%}）。", "",
             "| 訊號 | IC 20 日 2019–2022 | 2023–2026 | IC 60 日 2019–2022 | 2023–2026 | 單獨多空 Sharpe | 與 SUE 分數相關 | 與 SUE 多空報酬相關 | SUE 各半合成 Sharpe | 合成有增量 |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for name, i20, i60, s, corr, cs, ok, scorr in rows:
        lines.append(f"| {names[name]} | {i20[0][0]:+.3f}（{i20[0][1]:+.1f}） | {i20[1][0]:+.3f}（{i20[1][1]:+.1f}） | "
                     f"{i60[0][0]:+.3f}（{i60[0][1]:+.1f}） | {i60[1][0]:+.3f}（{i60[1][1]:+.1f}） | {s['sh_oos']:.2f} / {s['sh_is']:.2f} | "
                     f"{scorr:+.2f} | {corr:+.2f} | {cs['sh_oos']:.2f} / {cs['sh_is']:.2f} | {'✓' if ok else '✗'} |")
    (ROOT / "docs" / f"revmom_persist_top{top_n}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print("DONE", flush=True)


if __name__ == "__main__":
    main(int(sys.argv[1]))
