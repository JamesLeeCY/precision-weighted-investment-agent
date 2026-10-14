"""月營收驚奇（SUE）依各公司公告日進場 vs 統一在 10 日後進場（全市場市值前 N 檔）。

用法（於專案根目錄）：
    .venv/Scripts/python analysis/sue_event_entry.py 300
輸出 docs/sue_event_entry_top{N}.md 與 reports/legs/sue_event_entry_top{N}.csv。

問題：現行做法（fv2–fv5）在每月 10 日後的下一個交易日統一進場；提早公告的公司（例如鴻海約 5 日）
公告後到 10 日之間的漂移被錯過了嗎？

資料限制與設計（看結果前固定）：
- FinMind 月營收的 create_time 只有 2026 年才有值，且是 FinMind 收錄日（每日批次，時間都是 00:00），
  2026-04 營收（5 月公告）起才與實際公告日相符；歷史上沒有逐家公告日。
- 因此以「各公司 2026-05 ~ 2026-10 的公告習慣日」（create_time 的日；只採同月且 ≤ 16 日者）代表歷史公告日。
  這只用來決定進場日，報酬只用到 2026/04（2026-05 起的保留期不碰）。
  風險：歷史上公司實際公告比習慣日晚時，回測會在公告前就用到該月營收（前視、偏樂觀）；
  以 2026 年的資料估計這種情況的比例，並以「最晚觀察日」版本作為保守對照。
- 進場日（版本）：
  A 習慣日（中位數）當天或之後第一個交易日的收盤（create_time 為 00:00 的收錄日，當天收盤前資訊已公開）；
  B（主要）A 再往後一個交易日；
  C（保守）2026 年觀察到的最晚一日，再往後一個交易日。
  三者都不晚於現行統一進場日；沒有 2026 公告紀錄的公司（已下市等）沿用統一進場日。
- 組合：每個「有公司進場」的交易日重新計算分數並換倉：已公告者用本月 SUE、尚未公告者沿用上月 SUE（皆為當時最新），
  產業內 z → 對產業虛擬變數與 log 市值中性化 → 等權多空（產業內前／後 1/3，產業權重 = 檔數占比，多空各 100%，
  放空只用前 60 日有借券成交者）；統一進場日起與現行做法完全相同。每月換倉（不是 fv3 的每 3 個月分批）。
- 成本：換手兩邊 × 0.29625%、借券費逐日扣、剩餘 β 以台指期對沖（與 borrow_capacity.py 相同）。
- 指標：Sharpe（2019–2022 / 2023–2026/04）、年化報酬、年換手、
  與現行做法的每日差額（年化、t 值）；另列「提早進場窗口」內新舊組合的報酬。
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

CT_FROM = pd.Timestamp("2026-04-01")      # 營收月份 ≥ 2026-04（5 月公告起）的收錄日才可信
MAX_DAY = 16


def announce_habits(client, tickers: list) -> pd.DataFrame:
    """每檔 2026 年的公告日：回傳 [ticker, avail(公告月份第一天), ct]（只取同月且 ≤ 16 日者）。"""
    rows = []
    for t in tickers:
        r = client.get("TaiwanStockMonthRevenue", t.split(".")[0], "2017-01-01")
        if r.empty or "create_time" not in r.columns:
            continue
        ct = pd.to_datetime(r["create_time"], errors="coerce")
        ym = pd.to_datetime(dict(year=r["revenue_year"], month=r["revenue_month"], day=1))
        df = pd.DataFrame({"ticker": t, "avail": ym + pd.offsets.MonthBegin(1), "ct": ct}).dropna()
        df = df[(df["avail"] - pd.offsets.MonthBegin(1) >= CT_FROM) & (df["ct"].dt.to_period("M") == df["avail"].dt.to_period("M"))
                & (df["ct"].dt.day <= MAX_DAY)]
        rows.append(df)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=["ticker", "avail", "ct"])


def habit_days(ann: pd.DataFrame) -> pd.DataFrame:
    """每檔的習慣日（中位數，四捨五入）與最晚觀察日。"""
    g = ann.assign(day=ann["ct"].dt.day).groupby("ticker")["day"]
    return pd.DataFrame({"median": g.median().round().astype(int), "latest": g.max(), "n": g.size()})


def entry_date(days: pd.DatetimeIndex, month: pd.Timestamp, day: int, lag: int, fixed: pd.Timestamp) -> pd.Timestamp:
    """month 月的 day 日當天或之後第一個交易日，再往後 lag 個交易日；不晚於統一進場日 fixed。"""
    last = (month + pd.offsets.MonthEnd(0)).day
    target = month + pd.Timedelta(days=min(day, last) - 1)
    k = days.searchsorted(target)
    k = min(k + lag, len(days) - 1)
    return min(days[k], fixed)


def mixed_score(c, d: pd.Timestamp, month: pd.Timestamp, entered: pd.Index) -> pd.Series:
    """d 日的分數：已進場（已公告）的公司用本月 SUE，其餘用上月 SUE；成員篩選、產業內 z、中性化。"""
    prev = month - pd.offsets.MonthBegin(1)
    new = c.sue.loc[month] if month in c.sue.index else pd.Series(dtype=float)
    old = c.sue.loc[prev] if prev in c.sue.index else pd.Series(dtype=float)
    v = old.reindex(c.tickers)
    idx = entered.intersection(c.tickers)
    v.loc[idx] = new.reindex(idx)
    v = v.where(c.member.loc[d])
    z = v.groupby(c.sector.reindex(v.index)).transform(lambda x: (x - x.mean()) / x.std())
    return lp.neutralize(z, c.sector, c.logcap.loc[d])


def build_schedule(c, hab: pd.DataFrame, col: str, lag: int) -> tuple[list, dict, pd.DataFrame]:
    """回傳（換倉日、{換倉日: 分數}、每檔每月的進場日紀錄）。"""
    days = c.adj.index
    sched, scores, rec = [], {}, []
    for k, fixed in enumerate(c.schedule):
        month = fixed.to_period("M").to_timestamp()
        ent = pd.Series(fixed, index=pd.Index(c.tickers))
        if k > 0:                                   # 第一個月與現行做法同起點
            for t, day in hab[col].items():
                if t in ent.index:
                    ent[t] = entry_date(days, month, int(day), lag, fixed)
        mem = c.member.loc[fixed]
        for t in ent.index[mem.reindex(ent.index).fillna(False).to_numpy(bool)]:
            rec.append((month, t, ent[t], fixed))
        for d in sorted(set(ent)):
            if k > 0 and d <= c.schedule[k - 1]:
                continue
            sched.append(d)
            scores[d] = mixed_score(c, d, month, ent.index[ent <= d])
    R = pd.DataFrame(rec, columns=["month", "ticker", "entry", "fixed"])
    return sched, scores, R


def lookahead_rate(ann: pd.DataFrame, hab: pd.DataFrame, col: str, lag: int) -> float:
    """以 2026 年資料估計：假設的進場日早於實際收錄日（公告前就交易）的比例。"""
    bad = []
    for _, r in ann.iterrows():
        if r["ticker"] not in hab.index:
            continue
        day = int(hab.at[r["ticker"], col])
        last = (r["avail"] + pd.offsets.MonthEnd(0)).day
        target = r["avail"] + pd.Timedelta(days=min(day, last) - 1)
        e = pd.offsets.BDay(0).rollforward(target) + pd.offsets.BDay(lag)
        bad.append(r["ct"].normalize() > e)
    return float(np.mean(bad)) if bad else float("nan")


def tstat(x: pd.Series) -> float:
    x = x.dropna()
    return float(x.mean() / x.std(ddof=1) * math.sqrt(len(x))) if len(x) > 20 and x.std(ddof=1) > 0 else float("nan")


VERSIONS = {"A 習慣日當天": ("median", 0), "B 習慣日 + 1 個交易日（主要）": ("median", 1), "C 最晚觀察日 + 1 個交易日（保守）": ("latest", 1)}


def main(top_n: int):
    c = lp.prepare(top_n)
    fee = hc.lending_fees(c.client, c.tickers, c.adj.index)
    shortable = fee.notna()
    ann = announce_habits(c.client, c.tickers)
    hab = habit_days(ann)

    def run(sched, scores):
        wd = {d: bc.ew_long_short(scores[d], c.sector, shortable.loc[d]) for d in sched}
        return hc.simulate_weights(wd, c.rets, c.betas, c.tx, sched, fee=fee)

    base_scores = lp.leg_scores(c, "sue")
    base = run(c.schedule, base_scores)
    res, recs = {}, {}
    for name, (col, lag) in VERSIONS.items():
        sched, scores, R = build_schedule(c, hab, col, lag)
        sim = run(sched, scores)
        res[name], recs[name] = sim, R
        print(name, "done", flush=True)

    out = pd.DataFrame({"現行（統一進場）": base["ret"]} | {k: v["ret"] for k, v in res.items()})
    out.to_csv(ROOT / "reports" / "legs" / f"sue_event_entry_top{top_n}.csv")

    # ---- 報告 ----
    cover = hab.index.intersection(c.tickers)
    dist = pd.cut(hab.loc[cover, "median"], [0, 5, 7, 9, 10, 12, 31], labels=["1–5 日", "6–7 日", "8–9 日", "10 日", "11–12 日", "13 日以後"])
    lines = [f"# 月營收驚奇：依公告日進場 vs 統一進場（全市場市值前 {top_n} 檔，自動產生）", "",
             "由 [analysis/sue_event_entry.py](../analysis/sue_event_entry.py) 產生；設計與資料限制見程式開頭。"
             "Sharpe = 年化報酬 ÷ 年化波動；差額 = 依公告日進場的每日報酬 − 統一進場的每日報酬。研究結果，非投資建議。", "",
             "## 1. 公告習慣日（2026-05 ~ 2026-10 的 FinMind 收錄日）", "",
             f"有 2026 年公告紀錄的公司：{len(cover)} / {len(c.tickers)} 檔（其餘多為已下市，沿用統一進場日）；"
             f"每檔平均 {hab.loc[cover, 'n'].mean():.1f} 個月。", "",
             "| 習慣日（中位數） | 檔數 | 占比 |", "|---|---|---|"]
    for lab, n in dist.value_counts().reindex(dist.cat.categories).items():
        lines.append(f"| {lab} | {n} | {n / len(cover):.0%} |")
    spread = (hab.loc[cover, "latest"] - hab.loc[cover, "median"])
    lines += ["", f"同一家公司各月的公告日差異：最晚 − 中位數 平均 {spread.mean():.1f} 天，{(spread >= 3).mean():.0%} 的公司差 3 天以上。", "",
              "## 2. 進場時點與前視風險", "",
              "| 版本 | 比統一進場早的股票－月占比 | 平均提早（交易日） | 2026 年資料中「進場日早於實際公告」的比例 |", "|---|---|---|---|"]
    days = c.adj.index
    for name, (col, lag) in VERSIONS.items():
        R = recs[name]
        early = R[R["entry"] < R["fixed"]]
        gap = [days.searchsorted(f) - days.searchsorted(e) for e, f in zip(early["entry"], early["fixed"])]
        lines.append(f"| {name} | {len(early) / len(R):.0%} | {np.mean(gap):.1f} | {lookahead_rate(ann, hab, col, lag):.0%} |")
    lines += ["", "前視比例 > 0 表示回測中有部分股票在營收公告前就用到該月營收，結果會偏樂觀；C 版本最保守。", "",
              "## 3. 等權多空回測（每月換倉；剩餘 β 以台指期對沖，扣交易成本與借券費；2019 ~ 2026/04）", "",
              "| 版本 | Sharpe 2019–2022 | 2023–2026/04 | 年化報酬 | 年換手（倍） | 與現行差額：扣成本後（年化，t） | 扣成本前（年化，t） | 多付的交易成本／年 |",
              "|---|---|---|---|---|---|---|---|"]
    bs = hc.stats(base["ret"], base)
    lines.append(f"| 現行：統一在 10 日後進場 | {bs['sh_oos']:.2f} | {bs['sh_is']:.2f} | {bs['ann']:+.1%} | {bs['turnover']:.1f} | — | — |")
    for name, sim in res.items():
        s = hc.stats(sim["ret"], sim)
        diff = (sim["ret"] - base["ret"].reindex(sim.index)).dropna()
        dcost = ((sim["turnover"] - base["turnover"].reindex(sim.index).fillna(0.0)) * lp.STOCK_COST).reindex(diff.index)
        gross = diff + dcost
        lines.append(f"| {name} | {s['sh_oos']:.2f} | {s['sh_is']:.2f} | {s['ann']:+.1%} | {s['turnover']:.1f} | "
                     f"{diff.mean() * 252:+.2%}（{tstat(diff):.1f}） | {gross.mean() * 252:+.2%}（{tstat(gross):.1f}） | {dcost.mean() * 252:.2%} |")
    lines += ["", "差額只來自每月「第一家提早進場 ~ 統一進場日」這段（之後兩者持股相同）；扣成本前 = 扣成本後 + 多付的交易成本"
              "（現行做法在統一進場隔日一次扣整月換倉成本，依公告日進場則分散在之前幾天，所以要看全期合計）。", "",
              "逐年差額（年化）：", ""]
    for name, sim in res.items():
        diff = (sim["ret"] - base["ret"].reindex(sim.index)).dropna()
        lines.append(f"- {name}：" + "、".join(f"{y}:{g.mean() * 252:+.1%}" for y, g in diff.groupby(diff.index.year)))
    (ROOT / "docs" / f"sue_event_entry_top{top_n}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("DONE", flush=True)


if __name__ == "__main__":
    main(int(sys.argv[1]))
