"""強化月營收驚奇：加入季報盈餘驚奇、合成、拉長持有（每 1 / 2 / 3 個月換倉）。

用法（於專案根目錄）：
    .venv/Scripts/python analysis/revenue_surprise_plus.py daily_pit_val_tech.csv config/tickers_pit.yaml
輸出 docs/revenue_surprise_plus_data.md。

設計（看結果前固定）：
- 盈餘驚奇 SUE_e =（本季歸屬母公司淨利 − 去年同季 − μ）÷ σ，μ、σ 為過去 8 季年差的平均與標準差（至少 4 季）；
  用淨利而非 EPS（股票分割會改變 EPS 尺度）。FinMind 第 4 季為單季數字。
- 季報可用日依法定期限（保守）：Q1 → 5/15、Q2 → 8/14、Q3 → 11/14、Q4 → 隔年 3/31；每個營收進場日只用期限已過（嚴格早於）的最新一季。
- 合成：營收 SUE 與盈餘 SUE 的產業內百分位平均（任一缺值時用另一個）。
- 持有：在每月營收進場日中每 k 個月換倉一次（k = 1 / 2 / 3，約 20 / 40 / 60 個交易日），k 種起始月份取中位數。
- 組合：每日回測引擎（analysis/fund_tech_daily.py），產業內前 1/3 + 緩衝；並與「0050 + 每日 200 日線濾網」各半混合。
"""
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "analysis"))
import fund_tech_daily as ftd  # noqa: E402
import revenue_surprise as rs  # noqa: E402
from data.fetch_financials import FinMindClient  # noqa: E402

SPLIT = pd.Timestamp("2023-01-01")
DEADLINE = {3: (5, 15), 6: (8, 14), 9: (11, 14), 12: (3, 31)}


def quarter_available(q_end: pd.Timestamp) -> pd.Timestamp:
    m, d = DEADLINE[q_end.month]
    year = q_end.year + (1 if q_end.month == 12 else 0)
    return pd.Timestamp(year=year, month=m, day=d)


def earnings_surprise(fs: pd.DataFrame) -> pd.DataFrame:
    """fs：FinMind TaiwanStockFinancialStatements；回傳 [avail_date, sue_e]（每季一列）。"""
    ni = fs[fs["type"] == "EquityAttributableToOwnersOfParent"][["date", "value"]]
    if ni.empty:
        ni = fs[fs["type"] == "IncomeAfterTaxes"][["date", "value"]]
    if ni.empty:
        return pd.DataFrame(columns=["avail_date", "sue_e"])
    s = ni.assign(date=pd.to_datetime(ni["date"])).drop_duplicates("date", keep="last").set_index("date")["value"].astype(float)
    s = s[s.index.month.isin([3, 6, 9, 12])].asfreq("QE-DEC") if len(s) else s
    diff = s - s.shift(4)
    mu = diff.shift(1).rolling(8, min_periods=4).mean()
    sd = diff.shift(1).rolling(8, min_periods=4).std()
    sue = (diff - mu) / sd.where(sd > 0)
    out = pd.DataFrame({"q_end": sue.index, "sue_e": sue.to_numpy()}).dropna()
    out["avail_date"] = out["q_end"].map(quarter_available)
    return out[["avail_date", "sue_e"]].sort_values("avail_date")


def within_ic_cells(ev, col, ret):
    ic = rs.within_ic(ev, col, ret)
    cells = []
    for lo, hi in ((None, SPLIT), (SPLIT, None)):
        x = ic[[(lo is None or d >= lo) and (hi is None or d < hi) for d in ic.index]].dropna()
        t = x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))
        cells.append(f"{x.mean():+.3f}（t {t:+.1f}）")
    return cells


def main(path, config):
    import dotenv

    dotenv.load_dotenv(ROOT / ".env")
    ev, daily, days, events, tickers = rs.build_events(path, config)
    client = FinMindClient()
    parts = []
    for t in tickers:
        fs = client.get("TaiwanStockFinancialStatements", t.split(".")[0], "2017-01-01")
        if fs.empty:
            continue
        e = earnings_surprise(fs)
        e["ticker"] = t
        parts.append(e)
    es = pd.concat(parts, ignore_index=True).sort_values("avail_date")
    ev = ev.sort_values("date")
    ev = pd.merge_asof(ev, es, left_on="date", right_on="avail_date", by="ticker", allow_exact_matches=False)
    g = ev.groupby(["date", "sector"])
    r_rev, r_earn = g["sue"].rank(pct=True), g["sue_e"].rank(pct=True)
    ev["sue_combo"] = pd.concat([r_rev, r_earn], axis=1).mean(axis=1, skipna=True)
    ev = ev.sort_values(["date", "ticker"]).reset_index(drop=True)

    out = ["# 強化月營收驚奇（自動產生）", "",
           "由 [analysis/revenue_surprise_plus.py](../analysis/revenue_surprise_plus.py) 產生；解讀見 [revenue_surprise_plus_report.md](revenue_surprise_plus_report.md)。",
           f"每月營收公告期限後進場，共 {ev['date'].nunique()} 期；盈餘 SUE 覆蓋率 {ev['sue_e'].notna().mean():.0%}。", "",
           "## 產業內 IC（同產業內訊號排名與之後報酬排名的相關係數，−1～1；括號為 t 值）", "",
           "| 訊號 | 20 日 2019–2022 | 20 日 2023–2026 | 60 日 2019–2022 | 60 日 2023–2026 |", "|---|---|---|---|---|"]
    for col, label in (("sue", "營收驚奇"), ("sue_e", "盈餘驚奇（季報，法定期限後）"), ("sue_combo", "營收 + 盈餘驚奇")):
        c20, c60 = within_ic_cells(ev, col, "ret"), within_ic_cells(ev, col, "ret60")
        out.append(f"| {label} | {c20[0]} | {c20[1]} | {c60[0]} | {c60[1]} |")
        print(out[-1], flush=True)
    corr = ev.groupby("date").apply(lambda x: x["sue"].rank().corr(x["sue_e"].rank())).mean()
    out += ["", f"營收驚奇與盈餘驚奇的橫斷面排名相關（每期平均）：{corr:+.2f}", ""]

    # 每日回測：每 k 個月換倉
    close, ma20, ma60 = ftd.load_prices(tickers)
    close = close.loc["2019-01-01":"2026-05-29"]
    ma20, ma60 = ma20.reindex(close.index), ma60.reindex(close.index)
    on, bret = ftd.market_on(close.index)
    eng = ev.assign(pc_technical=np.nan)
    ev_dates = sorted(ev["date"].unique())
    timed = ftd.run(eng, close, ma20, ma60, on, bret, 0, kind="0050", mkt=True, rebalance_on=set(ev_dates)).set_index("d")
    bh = ftd.run(eng, close, ma20, ma60, on, bret, 0, kind="0050", rebalance_on=set(ev_dates))

    def seg(series_list, f):
        res = []
        for mask in (lambda s: s["d"] < SPLIT, lambda s: s["d"] >= SPLIT):
            st = [ftd.stats(s[mask(s)]) for s in series_list]
            res.append({k: float(np.median([x[k] for x in st])) for k in st[0]})
        return [f(r) for r in res]

    fmt = lambda m: f"{m['ann'] * 100:+.1f}% / {m['sharpe']:.2f} / {m['mdd'] * 100:.0f}% / {m['to_yr']:.1f}"  # noqa: E731
    out += ["## 每日回測（年化報酬 / Sharpe / 最大回撤〔每日淨值〕 / 年換手；k 種起始月份的中位數）", "",
            "| 組合 | 換倉間隔 | 2019–2022 | 2023–2026/05 | 與 0050 擇時各半：2019–2022 | 同左 2023–2026 |", "|---|---|---|---|---|---|"]
    for signal, label in (("sue", "營收驚奇"), ("sue_combo", "營收 + 盈餘驚奇")):
        for k in (1, 2, 3):
            runs, blends = [], []
            for off in range(k):
                r = ftd.run(eng, close, ma20, ma60, on, bret, 0, signal=signal, rebalance_on=set(ev_dates[off::k]))
                runs.append(r)
                j = r.set_index("d").join(timed, lsuffix="_s", rsuffix="_m", how="inner")
                blends.append(pd.DataFrame({"d": j.index, "net": 0.5 * j["net_s"] + 0.5 * j["net_m"],
                                            "expo": 0.5 * j["expo_s"] + 0.5 * j["expo_m"], "to": 0.5 * j["to_s"] + 0.5 * j["to_m"]}))
            a, b = seg(runs, fmt), seg(blends, fmt)
            out.append(f"| {label} | 每 {k} 個月 | {a[0]} | {a[1]} | {b[0]} | {b[1]} |")
            print(out[-1], flush=True)
    c = seg([bh], fmt)
    out.append(f"| 對照：0050 買進持有 | — | {c[0]} | {c[1]} | — | — |")
    c = seg([timed.reset_index()], fmt)
    out.append(f"| 對照：0050 + 每日 200 日線濾網 | — | {c[0]} | {c[1]} | — | — |")
    (ROOT / "docs" / "revenue_surprise_plus_data.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("DONE", flush=True)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
