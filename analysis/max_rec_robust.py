"""彩券型股票濾網（MAX、漲停）與營收創新高的參數穩健性（全市場市值前 N 檔，fv3 建構）。

用法（於專案根目錄；不需新的 API 呼叫）：
    .venv/Scripts/python analysis/max_rec_robust.py 300
輸出 docs/max_rec_robust_top{N}.md 與 reports/legs/max_rec_robust_top{N}.csv。

設計（看結果前固定）：
- MAX = 過去 21 個交易日最大單日含息報酬（Bali、Cakici、Whitelaw 2011）；漲停 = 過去 60 個交易日單日報酬 ≥ 9.5% 的天數
  （台股漲跌幅 ±10%）。第 t 日只用 t−1 日以前的資料。
- 單獨：−MAX 用固定包裝（產業內 z → 20 日平均 → 中性化）的產業內 IC（方向事先定為負向：MAX 高 → 之後報酬低）。
- 濾網（只用在做多端，放空端不變）：月營收驚奇等權多空（fv3 建構：限制可借、每 3 個月換倉、三份資金錯開），
  做多候選中排除 (1) MAX 在當日股票池前 20% 者；(2) 前 60 日有漲停者。
- 營收創新高穩健性：rec12 / rec36（÷ 前 12 / 36 個月最高；至少 12 個月）與 SUE 各半合成；只作檢查，不改 fv4（rec24）。
- 判準：兩段 Sharpe 都高於月營收驚奇單獨（同期間、同建構）。
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

LIMIT = 0.095
MAX_TOP = 0.20


def lottery_measures(adj: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    r = adj.pct_change()
    mx = r.rolling(21, min_periods=15).max().shift(1)
    hits = (r >= LIMIT).astype(float).rolling(60, min_periods=40).sum().shift(1)
    return mx, hits


def rec_n(rev: pd.DataFrame, n: int) -> pd.Series:
    r = rev.copy()
    r["ym"] = pd.to_datetime(dict(year=r["revenue_year"], month=r["revenue_month"], day=1))
    r = r.drop_duplicates("ym", keep="last").set_index("ym")["revenue"].astype(float).asfreq("MS")
    prior_max = r.shift(1).rolling(n, min_periods=12).max()
    out = r / prior_max.where(prior_max > 0) - 1
    out.index = out.index + pd.offsets.MonthBegin(1)
    return out


def ew_ls_exclude_long(score: pd.Series, sector: pd.Series, shortable: pd.Series, exclude: set) -> pd.Series:
    """同 ew_ls_buffer（無緩衝），但做多端排除 exclude 中的股票（排名仍用全部股票）。"""
    s = score.dropna()
    sec = sector.reindex(s.index)
    parts = {}
    for name, idx in s.groupby(sec).groups.items():
        sub = s.loc[idx]
        if len(sub) < 3:
            continue
        r = sub.rank(pct=True)
        top = sub.index[(r > 1 - lt.Q_IN).to_numpy() & ~sub.index.isin(list(exclude))]
        bot = sub.index[(r <= lt.Q_IN).to_numpy() & shortable.reindex(sub.index).fillna(False).to_numpy(bool)]
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

    def book_from(weight_fn):
        parts = []
        for off in range(3):
            wd = {d: weight_fn(d) for d in sched[off::3]}
            parts.append(hc.simulate_weights(wd, c.rets, c.betas, c.tx, list(wd), fee=fee)["ret"])
        x = pd.concat(parts, axis=1).mean(axis=1)
        return x[x.index > start]

    def zs(s):
        s = s.dropna()
        return (s - s.mean()) / s.std() if len(s) > 2 and s.std() > 0 else s * 0

    sue = lp.leg_scores(c, "sue")
    mx, hits = lottery_measures(c.adj)
    series = {"sue": book_from(lambda d: lt.ew_ls_buffer(sue[d], c.sector, short_ok[d], q_keep=None))}

    def excl_max(d):
        m = mx.loc[d].where(c.member.loc[d]).dropna()
        return set(m[m.rank(pct=True) > 1 - MAX_TOP].index)

    def excl_limit(d):
        h = hits.loc[d].where(c.member.loc[d]).dropna()
        return set(h[h > 0].index)

    series["sue_ex_max"] = book_from(lambda d: ew_ls_exclude_long(sue[d], c.sector, short_ok[d], excl_max(d)))
    series["sue_ex_limit"] = book_from(lambda d: ew_ls_exclude_long(sue[d], c.sector, short_ok[d], excl_limit(d)))
    share_excl = {"sue_ex_max": [], "sue_ex_limit": []}
    for d in sched:
        top = set(lt.ew_ls_buffer(sue[d], c.sector, short_ok[d], q_keep=None).pipe(lambda w: w[w > 0]).index)
        if top:
            share_excl["sue_ex_max"].append(len(top & excl_max(d)) / len(top))
            share_excl["sue_ex_limit"].append(len(top & excl_limit(d)) / len(top))

    # −MAX 單獨的產業內 IC
    wz = lp.wrap(-mx, c.member, c.sector)
    mscore = {d: lp.neutralize(wz.loc[d], c.sector, c.logcap.loc[d]) for d in sched}
    ics = pd.Series({d: lp.within_ic(mscore[d], c.fwd20.loc[d], c.sector) for d in sched}).dropna()

    # 營收創新高 12 / 24 / 36
    revs = {t: c.client.get("TaiwanStockMonthRevenue", t.split(".")[0], "2017-01-01") for t in c.tickers}
    rec_ic = {}
    for n in (12, 24, 36):
        mat = pd.DataFrame({t: rec_n(rv, n) for t, rv in revs.items() if not rv.empty})
        sc = {}
        for d in sched:
            mo = d.to_period("M").to_timestamp()
            v = mat.loc[mo] if mo in mat.index else pd.Series(dtype=float)
            v = v.reindex(c.tickers).where(c.member.loc[d]).replace([np.inf, -np.inf], np.nan)
            z = v.groupby(c.sector.reindex(v.index)).transform(lambda x: (x - x.mean()) / x.std())
            sc[d] = lp.neutralize(z, c.sector, c.logcap.loc[d])
        comp = {d: (zs(sue[d]).add(zs(sc[d]), fill_value=np.nan) / 2).dropna() for d in sched}
        series[f"sue+rec{n}"] = book_from(lambda d, comp=comp: lt.ew_ls_buffer(comp[d], c.sector, short_ok[d], q_keep=None))
        rec_ic[n] = pd.Series({d: lp.within_ic(sc[d], c.fwd20.loc[d], c.sector) for d in sched}).dropna()
        print(f"  rec{n} 完成", flush=True)
    P = pd.DataFrame(series)
    P.to_csv(ROOT / "reports" / "legs" / f"max_rec_robust_top{top_n}.csv")

    base = hc.stats(P["sue"])

    def seg_ic(x):
        o = []
        for m in (x.index < lp.SPLIT, x.index >= lp.SPLIT):
            y = x[m]
            o.append(f"{y.mean():+.3f}（{y.mean() / (y.std(ddof=1) / math.sqrt(len(y))):+.1f}）")
        return " / ".join(o)

    labels = {"sue": "月營收驚奇（對照）", "sue_ex_max": "做多排除 MAX 前 20%", "sue_ex_limit": "做多排除前 60 日有漲停",
              "sue+rec12": "SUE + 營收創新高（前 12 個月）", "sue+rec24": "SUE + 營收創新高（前 24 個月，fv4）",
              "sue+rec36": "SUE + 營收創新高（前 36 個月）"}
    lines = [f"# 彩券型股票濾網與營收創新高穩健性（全市場市值前 {top_n} 檔，自動產生）", "",
             "由 [analysis/max_rec_robust.py](../analysis/max_rec_robust.py) 產生；設計見程式開頭。fv3 建構（等權多空、限制可借、每 3 個月換倉、三份資金錯開），"
             f"扣交易成本與借券費、台指期對沖；Sharpe 為年化，兩段為 2019–2022 / 2023–2026/04（從 {start:%Y-%m-%d} 起）。研究結果，非投資建議。", "",
             f"−MAX 單獨的產業內 20 日 IC（括號 t 值）：{seg_ic(ics)}。", "",
             "| 版本 | Sharpe 2019–2022 | 2023–2026/04 | 年化報酬 | 最大回撤 | 兩段都高於對照 | 備註 |", "|---|---|---|---|---|---|---|"]
    for k in P.columns:
        s = hc.stats(P[k])
        ok = "—" if k == "sue" else ("✓" if s["sh_oos"] > base["sh_oos"] and s["sh_is"] > base["sh_is"] else "✗")
        note = ""
        if k in share_excl:
            note = f"做多名單平均排除 {np.mean(share_excl[k]):.0%}"
        if k.startswith("sue+rec"):
            note = f"rec{k[7:]} 單獨 IC {seg_ic(rec_ic[int(k[7:])])}"
        lines.append(f"| {labels[k]} | {s['sh_oos']:.2f} | {s['sh_is']:.2f} | {s['ann']:+.1%} | {s['mdd']:.1%} | {ok} | {note} |")
    (ROOT / "docs" / f"max_rec_robust_top{top_n}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print("DONE", flush=True)


if __name__ == "__main__":
    main(int(sys.argv[1]))
