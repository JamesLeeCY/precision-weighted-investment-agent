"""I026 工作日（交易日）調整的月營收驚奇（點子卡 research/ideas/I026-workday-adjusted-sue.md，檢定計畫看結果前固定）。

用法（於專案根目錄；資料皆已快取）：
    .venv/Scripts/python analysis/sue_workday.py
輸出 docs/sue_workday.md。

設計（依點子卡；點子卡沒寫清楚、在看結果前補上的細節以「補」標示）：
- 交易日數：加權指數含息（TaiwanStockTotalReturnIndex）有資料的日數，按營收月份計算。
- SUE_wd：R_wd = 當月營收 ÷ 當月交易日數，其餘公式與 data/revenue_signal.revenue_surprise 相同（年差、過去 24 個月、最少 12 個）；
  只對製造業與電子業調整（產業名稱含點子卡列出的關鍵字），其他產業 SUE_wd = SUE。
- 日曆衝擊月：營收月份的交易日數與去年同月相差 ≥ 2 日；IC 在營收公告後的換倉日（leg_probe schedule）計算，即「可得月份 = 營收月份 + 1」。
- 主檢定：產業內 Spearman 20 日 IC（原始 SUE 與 SUE_wd 的數值，不做中性化，補），每月 IC(SUE_wd) − IC(SUE)，
  日曆衝擊月與一般月分開，成對 t（以月份為單位）。
- 驗證：第 501–1000 名的日曆衝擊月 IC 差。
- 可交易（只在 (1)(2) 成立時執行）：fv5 建構，分數由 SUE 換成 SUE_wd（同樣產業內 z → 對產業與 log 市值取殘差），與 fv5 比較。
- 通過：(1) 日曆衝擊月 IC 差全期 > 0、t > 2、兩段同號；(2) 一般月 IC 差 t > −1.5；(3) 驗證樣本日曆衝擊月 IC 差 > 0；(4) 取代版兩段 Sharpe 不低於 fv5。
- 只報告：所有產業都調整的版本。點子卡的「1–2 月合併」與「與 I025 重疊月份」兩項未做（補：I025 尚未測）。
研究結果，非投資建議。
"""
import math
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
import ls_turnover as lt  # noqa: E402

KEYS = ("電子", "半導體", "光電", "電腦", "通信網路", "電機", "機械", "塑膠", "紡織", "鋼鐵", "汽車", "化學", "橡膠", "造紙", "水泥", "玻璃陶瓷")


def tdays(client) -> pd.Series:
    tri = client.get("TaiwanStockTotalReturnIndex", "TAIEX", "2007-01-01", "2026-05-31")
    d = pd.to_datetime(tri["date"])
    s = pd.Series(1, index=d).groupby(d.dt.to_period("M").to_numpy()).sum()
    s.index = pd.PeriodIndex(s.index, freq="M").to_timestamp()
    return s


def sue_pair(rev: pd.DataFrame, td: pd.Series) -> tuple[pd.Series, pd.Series]:
    """回傳（原始 SUE、工作日調整 SUE），索引為可得月份（同 revenue_surprise）。"""
    r = rev.copy()
    r["ym"] = pd.to_datetime(dict(year=r["revenue_year"], month=r["revenue_month"], day=1))
    r = r.drop_duplicates("ym", keep="last").set_index("ym")["revenue"].astype(float).asfreq("MS")
    out = []
    for x in (r, r / td.reindex(r.index)):
        diff = x - x.shift(12)
        mu = diff.shift(1).rolling(24, min_periods=12).mean()
        sd = diff.shift(1).rolling(24, min_periods=12).std()
        s = (diff - mu) / sd.where(sd > 0)
        s.index = s.index + pd.offsets.MonthBegin(1)
        out.append(s)
    return out[0], out[1]


def build(client, tickers, sector, td, adjust_all=False):
    raw, wd = {}, {}
    for t in tickers:
        rev = client.get("TaiwanStockMonthRevenue", t.split(".")[0], "2017-01-01")
        if rev.empty:
            continue
        a, b = sue_pair(rev, td)
        raw[t] = a
        sec = str(sector.get(t, ""))
        wd[t] = b if adjust_all or any(k in sec for k in KEYS) else a
    return pd.DataFrame(raw).sort_index(), pd.DataFrame(wd).sort_index()


def ic_diff(adj, member, sector, raw, wd, sched, limit):
    rows = {}
    for d in sched:
        k = int(adj.index.searchsorted(d))
        mo = d.to_period("M").to_timestamp()
        if k + 20 >= limit or mo not in raw.index:
            continue
        mem = member.loc[d].to_numpy(bool)
        fwd = adj.iloc[k + 20] / adj.iloc[k] - 1
        a = raw.loc[mo].reindex(adj.columns)[mem].dropna()
        b = wd.loc[mo].reindex(adj.columns)[mem].dropna()
        rows[d] = (lp.within_ic(a, fwd, sector), lp.within_ic(b, fwd, sector), mo)
    return pd.DataFrame(rows, index=["ic_raw", "ic_wd", "mo"]).T


def tstat(x):
    x = pd.Series(x, dtype=float).dropna()
    return (float(x.mean()), float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 and x.std(ddof=1) > 0 else float("nan"), len(x))


def f(x, d=4):
    m, t, n = x
    return "—" if m != m else f"{m:+.{d}f}（{t:.1f}，{n}）"


def main():
    c = lp.prepare(500)
    td = tdays(c.client)
    shock_rev = (td - td.shift(12)).abs() >= 2                         # 營收月份
    shock_avail = shock_rev.copy()
    shock_avail.index = shock_avail.index + pd.offsets.MonthBegin(1)  # 可得月份
    limit = int(c.adj.index.searchsorted(lp.HOLDOUT))
    raw, wd = build(c.client, c.tickers, c.sector, td)
    _, wd_all = build(c.client, c.tickers, c.sector, td, adjust_all=True)
    D = ic_diff(c.adj, c.member, c.sector, raw, wd, c.schedule, limit)
    Dall = ic_diff(c.adj, c.member, c.sector, raw, wd_all, c.schedule, limit)
    for X in (D, Dall):
        X["diff"] = X["ic_wd"].astype(float) - X["ic_raw"].astype(float)
        X["shock"] = [bool(shock_avail.get(m, False)) for m in X["mo"]]
        X["seg"] = np.where(X.index < lp.SPLIT, "2019–2022", "2023–2026/04")
    n_shock = int(D["shock"].sum())

    def seg3(X, mask, col="diff"):
        g = X[mask]
        return {s: tstat(g.loc[g["seg"] == s, col]) for s in ("2019–2022", "2023–2026/04")} | {"全期": tstat(g[col])}
    s_shock, s_norm = seg3(D, D["shock"]), seg3(D, ~D["shock"])
    a_shock = seg3(Dall, Dall["shock"])
    ic_raw_shock, ic_wd_shock = seg3(D, D["shock"], "ic_raw"), seg3(D, D["shock"], "ic_wd")
    # 驗證
    import dotenv
    dotenv.load_dotenv(ROOT / ".env")
    V = ce.Sample(c.client, 501, 1000, lp.market_tri(c.client), lp.tx_continuous(c.client))
    vsec = pd.Series({t: V.sector.get(t.split(".")[0], "NA") for t in V.tickers})
    vraw, vwd = build(c.client, V.tickers, vsec, td)
    VD = ic_diff(V.adj, V.member, vsec, vraw, vwd, [d for d in c.schedule if d in V.days], V.limit)
    VD["diff"] = VD["ic_wd"].astype(float) - VD["ic_raw"].astype(float)
    VD["shock"] = [bool(shock_avail.get(m, False)) for m in VD["mo"]]
    VD["seg"] = np.where(VD.index < lp.SPLIT, "2019–2022", "2023–2026/04")
    v_shock = seg3(VD, VD["shock"])

    c1 = s_shock["全期"][0] > 0 and s_shock["全期"][1] > 2 and np.sign(s_shock["2019–2022"][0]) == np.sign(s_shock["2023–2026/04"][0])
    c2 = not (s_norm["全期"][1] <= -1.5)
    c3 = v_shock["全期"][0] > 0
    port = None
    if c1 and c2:
        fee = hc.lending_fees(c.client, c.tickers, c.adj.index)
        quota, lend60 = bc.load_short_data(c.client, c.tickers, c.adj.index)
        close = bc.raw_close(c)
        sue = lp.leg_scores(c, "sue")
        swd = {}
        for d in c.schedule:
            mo = d.to_period("M").to_timestamp()
            v = wd.loc[mo] if mo in wd.index else pd.Series(dtype=float)
            v = v.reindex(c.tickers).where(c.member.loc[d])
            z = v.groupby(c.sector.reindex(v.index)).transform(lambda x: (x - x.mean()) / x.std())
            swd[d] = lp.neutralize(z, c.sector, c.logcap.loc[d])

        def shortable_at(d):
            n_short = max(1, int(c.member.loc[d].sum() / 3))
            need = lt.K_CAPITAL / n_short / close.loc[d]
            return (lend60.loc[d] > 0) & (quota.loc[d] >= need) & (need <= bc.DEPTH_FRAC * lend60.loc[d]) & (fee.loc[d] <= bc.FEE_MAX)

        def book(sc):
            parts = []
            for off in range(3):
                w = {d: lt.ew_ls_buffer(sc[d], c.sector, shortable_at(d), q_keep=None) for d in c.schedule[off::3]}
                parts.append(hc.simulate_weights(w, c.rets, c.betas, c.tx, list(w), fee=fee)["ret"])
            x = pd.concat(parts, axis=1).mean(axis=1)
            x = x[x.index > c.schedule[2]]
            return hc.stats(x) | {"full": lp.sharpe(x.dropna())}
        port = {"fv5 原版（SUE）": book(sue), "SUE_wd 取代": book(swd)}
    c4 = port is not None and port["SUE_wd 取代"]["sh_oos"] >= port["fv5 原版（SUE）"]["sh_oos"] and port["SUE_wd 取代"]["sh_is"] >= port["fv5 原版（SUE）"]["sh_is"]
    corr = []
    for mo in raw.index[(raw.index >= "2019-01-01") & (raw.index < lp.HOLDOUT)]:
        x = pd.concat([raw.loc[mo], wd.loc[mo]], axis=1).dropna()
        if len(x) > 50 and shock_avail.get(mo, False):
            corr.append(x.iloc[:, 0].rank().corr(x.iloc[:, 1].rank()))

    L = ["# I026 工作日調整的月營收驚奇（自動產生）", "",
         "由 [analysis/sue_workday.py](../analysis/sue_workday.py) 產生；設計見程式開頭（看結果前固定）。"
         "IC 為產業內 Spearman（SUE vs 換倉後 20 個交易日報酬，−1～1）；「IC 差」= IC(SUE_wd) − IC(SUE)，括號為（成對 t 值，月份數）。研究結果，非投資建議。", "",
         f"換倉月份 {len(D)} 個，其中日曆衝擊月（營收月份交易日數與去年同月差 ≥ 2 日）{n_shock} 個；衝擊月中 SUE 與 SUE_wd 的平均等級相關 {np.mean(corr):+.3f}。", "",
         "| 統計量 | 2019–2022 | 2023–2026/04 | 全期 |", "|---|---|---|---|",
         "| 衝擊月 IC(SUE) | " + " | ".join(f(ic_raw_shock[s], 3) for s in ic_raw_shock) + " |",
         "| 衝擊月 IC(SUE_wd) | " + " | ".join(f(ic_wd_shock[s], 3) for s in ic_wd_shock) + " |",
         "| (1) 衝擊月 IC 差 | " + " | ".join(f(s_shock[s]) for s in s_shock) + " |",
         "| (2) 一般月 IC 差 | " + " | ".join(f(s_norm[s]) for s in s_norm) + " |",
         "| (3) 驗證樣本衝擊月 IC 差 | " + " | ".join(f(v_shock[s]) for s in v_shock) + " |",
         "| 只報告：所有產業都調整，衝擊月 IC 差 | " + " | ".join(f(a_shock[s]) for s in a_shock) + " |", ""]
    if port:
        L += ["| 建構（fv5） | Sharpe | 全期 | 年化報酬 |", "|---|---|---|---|"]
        for k, s in port.items():
            L.append(f"| {k} | {s['sh_oos']:.2f} / {s['sh_is']:.2f} | {s['full']:.2f} | {s['ann']:+.1%} |")
        L.append("")
    L += ["## 判定", "",
          f"1. 衝擊月 IC 差全期 > 0、t > 2、兩段同號：{f(s_shock['全期'])} → {'✓' if c1 else '✗'}",
          f"2. 一般月 IC 差不顯著為負（t > −1.5）：{f(s_norm['全期'])} → {'✓' if c2 else '✗'}",
          f"3. 驗證樣本衝擊月 IC 差 > 0：{f(v_shock['全期'])} → {'✓' if c3 else '✗'}",
          f"4. 取代版兩段 Sharpe 不低於 fv5：{'未執行（(1)(2) 未全部成立）' if port is None else ('✓' if c4 else '✗')}", "",
          f"**結論：{'通過' if c1 and c2 and c3 and c4 else '未通過'}**"]
    (ROOT / "docs" / "sue_workday.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
