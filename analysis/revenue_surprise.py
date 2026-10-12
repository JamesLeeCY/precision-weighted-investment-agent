"""月營收驚奇（standardized unexpected revenue），以公告期限對齊進場日。

用法（於專案根目錄；輸入為 phase_robustness_agents.py 產生的 daily_pit.csv 或其衍生檔）：
    .venv/Scripts/python analysis/revenue_surprise.py daily_pit_val_tech.csv config/tickers_pit.yaml
輸出 docs/revenue_surprise_data.md。

設計（看結果前固定；參考顧廣平 2010、陳柔君等 2022）：
- 公告時點：上市櫃公司須於次月 10 日前公告上月營收（遇假日順延）。FinMind 的 date 欄為營收月份的次月 1 日；
  create_time 只有近期資料才有值，無法用於歷史。進場日 = 當月「10 日或之後第一個交易日」的下一個交易日（所有公司都已公告）。
- 營收驚奇 SUE = (R_m − R_{m−12} − μ) / σ，μ、σ 為過去 24 個月 (R_k − R_{k−12}) 的平均與標準差（至少 12 個月）——季節性隨機漫步加趨勢。
- 對照：同一份「準時」資料算的營收年增率 yoy_timely；現有財報 Agent（月營收遞延 40 天，等於晚一個月使用）；SUE 與財報 Agent 的產業內百分位平均。
- 評估：每月一次（單一路徑），產業內 IC（20 日主要，40 / 60 日看漂移延續），產業中性做多前 1/3（含緩衝版本）相對等權、扣成本；
  事先反映：SUE 與「上月最後交易日收盤 → 進場前一日收盤」報酬的產業內 IC。
"""
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "analysis"))
import sector_neutral_portfolio as snp  # noqa: E402
from data.fetch_financials import FinMindClient  # noqa: E402
from data.revenue_signal import event_dates, revenue_surprise  # noqa: E402,F401  （與前瞻規格 fv2 共用）
from data.fetch_technical import FinMindTechnicalProvider  # noqa: E402

SPLIT = "2023-01-01"
SEGMENTS = [("2019–2022（樣本外）", lambda d: d < SPLIT), ("2023–2026/05", lambda d: d >= SPLIT)]
PPY = 12


def within_ic(df, col, ret):
    vals = {}
    for d, g in df.groupby("date"):
        v, w = [], []
        for _, s in g.groupby("sector"):
            s = s.dropna(subset=[col, ret])
            if len(s) >= 3 and s[col].nunique() > 1:
                v.append(s[col].rank().corr(s[ret].rank()))
                w.append(len(s))
        vals[d] = np.average(v, weights=w) if v else np.nan
    return pd.Series(vals)


def portfolio(df, col, keep=None):
    rows, prev, prev_ew = [], {}, {}
    for d, g in df.groupby("date"):
        g = g.dropna(subset=[col, "ret"])
        if len(g) < 20:
            continue
        w = snp.sector_neutral_weights(g, col, 1 / 3, 3, +1, set(prev), keep)
        ew = {t: 1 / len(g) for t in g["ticker"]}
        r, r_ew = snp.portfolio_return(g, w), snp.portfolio_return(g, ew)
        to, to_ew = snp.turnover(w, prev), snp.turnover(ew, prev_ew)
        rows.append({"date": d, "ex_net": (r - to * snp.COST_PER_SIDE) - (r_ew - to_ew * snp.COST_PER_SIDE),
                     "ex_gross": r - r_ew, "to": to})
        prev, prev_ew = w, ew
    return pd.DataFrame(rows)


def seg_ic(ic):
    cells = []
    for _, fn in SEGMENTS:
        x = ic[[fn(d.strftime("%Y-%m-%d")) for d in ic.index]].dropna()
        t = x.mean() / (x.std(ddof=1) / math.sqrt(len(x))) if len(x) > 2 else float("nan")
        cells.append(f"{x.mean():+.3f}（t {t:+.1f}，{(x > 0).mean():.0%} 為正）")
    return cells


def seg_port(p, m):
    cells = []
    for _, fn in SEGMENTS:
        x = p[p["date"].dt.strftime("%Y-%m-%d").map(fn)][m]
        t = x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))
        cells.append(f"{x.mean() * 100:+.2f}%（t {t:+.1f}）")
    return cells


def main(path, config):
    import dotenv

    dotenv.load_dotenv(ROOT / ".env")
    cfg = yaml.safe_load(open(config, encoding="utf-8"))
    tickers = [u["ticker"] for u in cfg["universe"]]
    daily = pd.read_csv(path, parse_dates=["date"], usecols=["i", "date", "ticker", "sector", "ret", "pc_fundamentals_agent"])
    daily = daily.dropna(subset=["sector"])
    days = pd.DatetimeIndex(sorted(daily["date"].unique()))
    events = event_dates(days)
    ev = daily[daily["date"].isin(events)].copy()

    client = FinMindClient()
    parts = []
    for t in tickers:
        rev = client.get("TaiwanStockMonthRevenue", t.split(".")[0], "2017-01-01")
        if rev.empty:
            continue
        s = revenue_surprise(rev)
        s["ticker"] = t
        parts.append(s)
    rs = pd.concat(parts, ignore_index=True)
    ev["avail_month"] = ev["date"].dt.to_period("M").dt.to_timestamp()
    ev = ev.merge(rs, on=["ticker", "avail_month"], how="left")
    ev["combo"] = ev.groupby(["date", "sector"])["sue"].rank(pct=True) * 0.5 + ev.groupby(["date", "sector"])["pc_fundamentals_agent"].rank(pct=True) * 0.5

    # 40 / 60 日報酬與公告期間報酬（含息還原收盤，個股自身交易日）
    prov = FinMindTechnicalProvider(client, "2019-01-01", "2026-05-31")
    extra = []
    for t in ev["ticker"].unique():
        ind = prov.indicators(t)
        if ind.empty:
            continue
        c = ind.set_index("date")["close"]
        idx = c.index
        for d in ev.loc[ev["ticker"] == t, "date"]:
            pos = idx.searchsorted(d)
            if pos >= len(idx) or idx[pos] != d:
                continue
            row = {"ticker": t, "date": d}
            for h in (40, 60):
                row[f"ret{h}"] = c.iloc[pos + h] / c.iloc[pos] - 1 if pos + h < len(idx) else np.nan
            month_start = idx[(idx.year == d.year) & (idx.month == d.month)][0]
            p0 = idx.searchsorted(month_start) - 1
            row["pre"] = c.iloc[pos - 1] / c.iloc[p0] - 1 if p0 >= 0 and pos - 1 > p0 else np.nan
            extra.append(row)
    ev = ev.merge(pd.DataFrame(extra), on=["ticker", "date"], how="left")
    cover = ev["sue"].notna().mean()

    out = ["# 月營收驚奇（自動產生）", "",
           "由 [analysis/revenue_surprise.py](../analysis/revenue_surprise.py) 產生；解讀見 [revenue_surprise_report.md](revenue_surprise_report.md)。",
           f"每月公告期限後第一個交易日進場，共 {ev['date'].nunique()} 期；SUE 覆蓋率 {cover:.0%}。IC 為產業內 Spearman，括號為 t 值與為正期數比例。", "",
           "## 產業內 IC", "",
           "| 訊號 | 20 日 2019–2022 | 20 日 2023–2026 | 40 日 2019–2022 | 40 日 2023–2026 | 60 日 2019–2022 | 60 日 2023–2026 |",
           "|---|---|---|---|---|---|---|"]
    for col, label in (("sue", "營收驚奇 SUE"), ("yoy_timely", "營收年增率（準時）"),
                       ("pc_fundamentals_agent", "財報 Agent（營收晚一個月）"), ("combo", "SUE + 財報 Agent")):
        cells = []
        for ret in ("ret", "ret40", "ret60"):
            cells += seg_ic(within_ic(ev, col, ret))
        out.append(f"| {label} | " + " | ".join(cells) + " |")
        print(out[-1], flush=True)
    pre = seg_ic(within_ic(ev, "sue", "pre"))
    out += ["", "## 事先反映", "", "SUE 與公告期間報酬（上月最後交易日收盤 → 進場前一日收盤）的產業內 IC：",
            f"2019–2022 {pre[0]}；2023–2026 {pre[1]}", "",
            "## 產業中性做多前 1/3 − 等權（每期約 1 個月，扣成本）", "",
            "| 訊號 | 2019–2022（樣本外） | 2023–2026/05 | 未扣成本 2019–2022 | 未扣成本 2023–2026 | 每期換手 |", "|---|---|---|---|---|---|"]
    for col, label, keep in (("sue", "營收驚奇 SUE", None), ("sue", "SUE + 緩衝", 0.5), ("yoy_timely", "營收年增率（準時）", None),
                             ("pc_fundamentals_agent", "財報 Agent（營收晚一個月）", None), ("pc_fundamentals_agent", "財報 Agent + 緩衝", 0.5),
                             ("combo", "SUE + 財報 Agent", None), ("combo", "SUE + 財報 Agent + 緩衝", 0.5)):
        p = portfolio(ev, col, keep)
        net, gross = seg_port(p, "ex_net"), seg_port(p, "ex_gross")
        out.append(f"| {label} | {net[0]} | {net[1]} | {gross[0]} | {gross[1]} | {p['to'].mean():.2f} |")
        print(out[-1], flush=True)

    # ---- 穩健性 1：延後進場 k 個交易日（訊號不變，用該日起 20 日報酬） ----
    out += ["", "## 穩健性：延後進場（SUE 產業內 IC，20 日）", "", "| 延後 | 2019–2022 | 2023–2026 |", "|---|---|---|"]
    pos = {d: k for k, d in enumerate(days)}
    sig = ev[["ticker", "date", "sector", "sue"]]
    for k in (0, 1, 2, 3, 5, 10):
        shifted = sig.assign(date=sig["date"].map(lambda d: days[pos[d] + k] if pos[d] + k < len(days) else pd.NaT))
        dk = shifted.merge(daily[["date", "ticker", "ret"]], on=["date", "ticker"], how="inner")
        c = seg_ic(within_ic(dk, "sue", "ret"))
        out.append(f"| {k} 個交易日 | {c[0]} | {c[1]} |")
        print(out[-1], flush=True)

    # ---- 穩健性 2：組合絕對報酬、Sharpe、最大回撤（每月一期，含 0050 對照） ----
    from backtest.portfolio import max_drawdown
    from oos_report import bench_20d  # 與回測相同的共用日曆 0050 20 日報酬

    bench = bench_20d(daily)
    out += ["", "## 組合絕對表現（每月一期、扣成本；年化 / Sharpe / 最大回撤）", "",
            "| 組合 | 2019–2022（樣本外） | 2023–2026/05 |", "|---|---|---|"]

    def abs_series(col, keep):
        rows, prev = [], {}
        for d, g in ev.groupby("date"):
            g = g.dropna(subset=["ret"])
            if col is None:
                w = {t: 1 / len(g) for t in g["ticker"]}
            else:
                g = g.dropna(subset=[col])
                w = snp.sector_neutral_weights(g, col, 1 / 3, 3, +1, set(prev), keep)
            rows.append({"date": d, "r": snp.portfolio_return(g, w) - snp.turnover(w, prev) * snp.COST_PER_SIDE})
            prev = w
        return pd.DataFrame(rows)

    def stat_cells(df):
        cells = []
        for _, fn in SEGMENTS:
            x = df[df["date"].dt.strftime("%Y-%m-%d").map(fn)]["r"].to_numpy()
            tot = float(np.prod(1 + x) - 1)
            ann = (1 + tot) ** (PPY / len(x)) - 1
            vol = x.std(ddof=1) * math.sqrt(PPY)
            cells.append(f"{ann * 100:+.1f}% / {ann / vol:.2f} / {max_drawdown(x) * 100:.0f}%")
        return cells

    series = {"營收驚奇 SUE 產業中性做多": abs_series("sue", None), "SUE + 緩衝": abs_series("sue", 0.5),
              "SUE + 財報 Agent + 緩衝": abs_series("combo", 0.5), "財報 Agent + 緩衝": abs_series("pc_fundamentals_agent", 0.5),
              "等權持有全部": abs_series(None, None)}
    b = pd.DataFrame({"date": list(bench.index), "r": list(bench.values)})
    series["0050"] = b[b["date"].isin(ev["date"].unique())]
    for label, df in series.items():
        c = stat_cells(df)
        out.append(f"| {label} | {c[0]} | {c[1]} |")
        print(out[-1], flush=True)
    out += ["", "註：每月一期（約 20 個交易日，期與期之間有少數交易日空檔）；最大回撤以每期淨值計，比每日淨值淺。"]

    # ---- 穩健性 3：每日回測（與 fund_tech_daily / allocation_study 同一引擎；公告期限後換倉，含緩衝） ----
    import fund_tech_daily as ftd

    close, ma20, ma60 = ftd.load_prices(tickers)
    close = close.loc["2019-01-01":"2026-05-29"]
    ma20, ma60 = ma20.reindex(close.index), ma60.reindex(close.index)
    on, bret = ftd.market_on(close.index)
    reb = set(events)
    eng = ev.assign(pc_technical=np.nan)
    runs = {
        "SUE 產業中性 + 緩衝": ftd.run(eng, close, ma20, ma60, on, bret, 0, signal="sue", rebalance_on=reb),
        "SUE + 財報 Agent + 緩衝": ftd.run(eng, close, ma20, ma60, on, bret, 0, signal="combo", rebalance_on=reb),
        "財報 Agent + 緩衝（同樣在公告日換倉）": ftd.run(eng, close, ma20, ma60, on, bret, 0, rebalance_on=reb),
        "等權持有全部": ftd.run(eng, close, ma20, ma60, on, bret, 0, kind="ew", rebalance_on=reb),
        "0050 買進持有": ftd.run(eng, close, ma20, ma60, on, bret, 0, kind="0050", rebalance_on=reb),
        "0050 + 每日 200 日線濾網": ftd.run(eng, close, ma20, ma60, on, bret, 0, kind="0050", mkt=True, rebalance_on=reb),
    }
    a, m = runs["SUE 產業中性 + 緩衝"].set_index("d"), runs["0050 + 每日 200 日線濾網"].set_index("d")
    j = a.join(m, lsuffix="_s", rsuffix="_m", how="inner")
    runs["50% SUE + 50% 0050 擇時"] = pd.DataFrame({"d": j.index, "net": 0.5 * j["net_s"] + 0.5 * j["net_m"],
                                                    "expo": 0.5 * j["expo_s"] + 0.5 * j["expo_m"], "to": 0.5 * j["to_s"] + 0.5 * j["to_m"]})
    out += ["", "## 每日回測（年化 / Sharpe / 最大回撤〔每日淨值〕 / 年換手）", "",
            "| 組合 | 2019–2022（樣本外） | 2023–2026/05 |", "|---|---|---|"]
    split = pd.Timestamp(SPLIT)
    for label, srs in runs.items():
        cells = []
        for mask in (srs["d"] < split, srs["d"] >= split):
            st = ftd.stats(srs[mask])
            cells.append(f"{st['ann'] * 100:+.1f}% / {st['sharpe']:.2f} / {st['mdd'] * 100:.0f}% / {st['to_yr']:.1f}")
        out.append(f"| {label} | {cells[0]} | {cells[1]} |")
        print(out[-1], flush=True)
    (ROOT / "docs" / "revenue_surprise_data.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("DONE", flush=True)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
