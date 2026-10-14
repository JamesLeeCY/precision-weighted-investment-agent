"""除權息事件研究：除息前布局、除息日、填息（全市場市值前 500 名為主樣本，第 501–1000 名為獨立驗證樣本）。

用法（於專案根目錄；先跑過 event_study.py 與 disposition_replication.py，價格與除權息資料都在快取中）：
    .venv/Scripts/python analysis/dividend_events.py
輸出 docs/dividend_events.md 與 reports/legs/dividend_events.csv。

設計（看結果前固定）：
- 事件：TaiwanStockDividendResult 的現金除息（含權息合併；除息前收盤 > 除息參考價），除息日在 2019-01 ~ 2026-04，
  除息日當年為樣本成員。殖利率 = 1 − 參考價 ÷ 前一日收盤。
- 除息日是否事先公告：以 TaiwanStockDividend（公告日、除息交易日）抽 80 檔估計公告到除息的交易日數；
  事件前視窗只用到 [−10, −1]，若九成以上的事件提前 ≥ 11 個交易日公告即視為可交易。
- 異常報酬：r − β × 加權指數含息報酬（還原報酬，除息日已含股利）；t 值以事件日聚集。
- 視窗：[−10, −1]、[−5, −1]（除息前一日收盤賣出，不領股利、不涉股利稅）、[0] 除息日（含股利，未扣股利所得稅與二代健保，
  個人實際收益較低）、[+1, +5]、[+1, +20]、[+1, +60]。
- 填息：除息後第 5 個交易日收盤（未還原）≥ 除息前一日收盤 → 「5 日內填息」；之後 [+6, +25] 的 CAR（第 5 日收盤可知、可交易）。
- 分組：殖利率 ≥ 5% / < 5%；除息月份 6–9 月（旺季）/ 其他。
- 策略（日曆時間組合，台指期對沖，換手 × 單邊 0.29625%）：
  A 除息前布局：第 −11 日收盤買進、第 −1 日收盤賣出；B 5 日內填息者第 +5 日收盤買進、持有 20 日。
- 判定（事前寫下）：主樣本兩段（2019–2022 / 2023–2026/04）同號且 t > 2，且驗證樣本整體同號且 t > 2，才算通過。
"""
import math
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "analysis"))
sys.path.insert(0, str(ROOT))
import event_study as es  # noqa: E402
import hedge_construction as hc  # noqa: E402
import leg_probe as lp  # noqa: E402
from data.fetch_financials import FinMindClient  # noqa: E402

WINDOWS = {"[−10, −1]": (-10, -1), "[−5, −1]": (-5, -1), "[0] 除息日": (0, 0), "[+1, +5]": (1, 5), "[+1, +20]": (1, 20), "[+1, +60]": (1, 60)}
SAMPLES = {"前 500 名（主樣本）": (1, 500), "第 501–1000 名（驗證）": (501, 1000)}
LEAD_SAMPLE = 80


def load_sample(client, lo: int, hi: int):
    mem = pd.read_csv(ROOT / "config" / "universe_mcap_membership.csv", dtype={"stock_id": str})
    mem = mem[(mem["rank"] >= lo) & (mem["rank"] <= hi)]
    ids = sorted(mem["stock_id"].unique())
    adj, close, divs = {}, {}, []
    for k, sid in enumerate(ids):
        px = client.get("TaiwanStockPrice", sid, lp.PX_START)
        if px.empty:
            continue
        px = px[px["close"].astype(float) > 0]
        s = lp.load_stock(client, sid)
        t = sid + ".TW"
        adj[t] = s["adj"]
        close[t] = pd.Series(px["close"].astype(float).to_numpy(), index=pd.to_datetime(px["date"]))
        d = client.get("TaiwanStockDividendResult", sid, lp.EV_START, lp.EV_END)
        if not d.empty:
            divs.append(d.assign(ticker=t))
        if k % 100 == 0:
            print(f"  [{lo}-{hi}] 載入 {k}/{len(ids)}", flush=True)
    adj = pd.DataFrame(adj).sort_index()
    adj = adj[adj.index <= pd.Timestamp(lp.EV_END)]
    close = pd.DataFrame(close).reindex(index=adj.index, columns=adj.columns)
    member = pd.DataFrame(False, index=adj.index, columns=adj.columns)
    for y, g in mem.groupby("year"):
        cols = [s + ".TW" for s in g["stock_id"] if s + ".TW" in member.columns]
        member.loc[member.index.year == y, cols] = True
    member &= adj.notna()
    return adj, close, member, pd.concat(divs, ignore_index=True)


def lead_days(client, tickers: list, days: pd.DatetimeIndex) -> pd.Series:
    """抽樣估計：除息交易日公告日到除息日之間的交易日數。"""
    rng = np.random.default_rng(0)
    pick = rng.choice(sorted(tickers), size=min(LEAD_SAMPLE, len(tickers)), replace=False)
    out = []
    for t in pick:
        d = client.get("TaiwanStockDividend", t.split(".")[0], "2019-01-01")
        if d.empty:
            continue
        for _, r in d.iterrows():
            ex, an = pd.to_datetime(r.get("CashExDividendTradingDate"), errors="coerce"), pd.to_datetime(r.get("AnnouncementDate"), errors="coerce")
            if ex == ex and an == an and pd.Timestamp("2019-01-01") <= ex < lp.HOLDOUT:
                out.append(int(days.searchsorted(ex)) - int(days.searchsorted(an)))
    return pd.Series(out, dtype=float)


def build_events(divs: pd.DataFrame, adj, close, member, ar, limit) -> pd.DataFrame:
    days = adj.index
    col = {t: j for j, t in enumerate(adj.columns)}
    d = divs.copy()
    d["date"] = pd.to_datetime(d["date"])
    d = d[(d["date"] >= es.EV_FROM) & (d["date"] < lp.HOLDOUT)]
    d["before"], d["after"] = d["before_price"].astype(float), d["after_price"].astype(float)
    d = d[(d["before"] > 0) & (d["after"] > 0) & (d["after"] < d["before"])].drop_duplicates(["ticker", "date"])
    d["k0"] = [int(days.searchsorted(x)) for x in d["date"]]
    d = d[(d["k0"] < len(days)) & (d["k0"] >= 11)]
    d = d[[days[k] == x for k, x in zip(d["k0"], d["date"])]]           # 除息日須為交易日
    d["t0"] = days[d["k0"].to_numpy()]
    d = d[[bool(member.at[t, tk]) for t, tk in zip(d["t0"], d["ticker"])]].reset_index(drop=True)
    d["yield"] = 1 - d["after"] / d["before"]
    d["seg"] = np.where(d["t0"] < lp.SPLIT, "2019–2022", "2023–2026/04")
    for name, (a, b) in WINDOWS.items():
        d[name] = [es.car(ar[:, col[t]], k, a, b, limit) for t, k in zip(d["ticker"], d["k0"])]
    cl = close.to_numpy()
    d["fill5"] = [bool(cl[k + 5, col[t]] >= b) if k + 5 < limit and cl[k + 5, col[t]] == cl[k + 5, col[t]] else np.nan
                  for t, k, b in zip(d["ticker"], d["k0"], d["before"])]
    d["[+6, +25]"] = [es.car(ar[:, col[t]], k, 6, 25, limit) for t, k in zip(d["ticker"], d["k0"])]
    d["peak"] = d["t0"].dt.month.between(6, 9)
    return d


def window_portfolio(ev: pd.DataFrame, start: int, end: int, days, limit) -> dict:
    """第 k0+start 日收盤買進、持有到第 k0+end 日收盤；同日持有者等權。"""
    active = {}
    for r in ev.itertuples():
        for k in range(max(r.k0 + start, 0), min(r.k0 + end, limit - 1)):
            active.setdefault(days[k], set()).add(r.ticker)
    return {d: pd.Series(1.0 / len(v), index=sorted(v)) for d, v in active.items()}


def cell(df, w):
    m, t, _ = es.date_clustered(df, w)
    return f"{m:+.2%}（{t:.1f}）" if m == m else "—"


def main():
    import dotenv

    dotenv.load_dotenv(ROOT / ".env")
    client = FinMindClient()
    mkt_tri = lp.market_tri(client)
    tx = lp.tx_continuous(client)
    lines = ["# 除權息事件研究：除息前布局、除息日、填息（自動產生）", "",
             "由 [analysis/dividend_events.py](../analysis/dividend_events.py) 產生；設計與判定標準見程式開頭（看結果前固定）。"
             "CAR = 累積異常報酬（還原報酬 − β × 加權指數含息報酬），括號為 t 值（同日事件先平均）。研究結果，非投資建議。", ""]
    results, rets_out = {}, {}
    for sname, (lo, hi) in SAMPLES.items():
        adj, close, member, divs = load_sample(client, lo, hi)
        rets = adj.pct_change()
        days = rets.index
        limit = int(days.searchsorted(lp.HOLDOUT))
        m = mkt_tri.pct_change().reindex(days)
        betas = rets.rolling(250, min_periods=120).cov(m).div(m.rolling(250, min_periods=120).var(), axis=0).shift(1)
        ar = (rets - betas.fillna(1.0).mul(m, axis=0)).to_numpy()
        ev = build_events(divs, adj, close, member, ar, limit)
        results[sname] = ev
        if lo == 1:
            lead = lead_days(client, list(adj.columns), days)
            lines += ["## 0. 除息日是否事先公告（抽樣）", "",
                      f"抽 {LEAD_SAMPLE} 檔、{len(lead)} 次除息：公告到除息的交易日數中位數 {lead.median():.0f} 日；"
                      f"≥ 11 日者占 {(lead >= 11).mean():.0%}，≥ 6 日者占 {(lead >= 6).mean():.0%}。", ""]
        lines += [f"## {sname}", "", f"現金除息事件 {len(ev)} 筆；殖利率中位數 {ev['yield'].median():.1%}。", "",
                  "| 分組 | 事件數 | " + " | ".join(WINDOWS) + " |", "|---|---|" + "---|" * len(WINDOWS)]
        groups = [("全部", ev)] + [(s, ev[ev["seg"] == s]) for s in ("2019–2022", "2023–2026/04")] + \
                 [("殖利率 ≥ 5%", ev[ev["yield"] >= 0.05]), ("殖利率 < 5%", ev[ev["yield"] < 0.05]),
                  ("6–9 月", ev[ev["peak"]]), ("其他月份", ev[~ev["peak"]])]
        for g, df in groups:
            lines.append(f"| {g} | {len(df)} | " + " | ".join(cell(df, w) for w in WINDOWS) + " |")
        f = ev.dropna(subset=["fill5"])
        lines += ["", "填息（第 +5 日收盤是否回到除息前一日收盤）與之後 [+6, +25] 的 CAR：", "",
                  "| 分組 | 事件數 | 2019–2022 | 2023–2026/04 | 全部 |", "|---|---|---|---|---|"]
        for g, df in [("5 日內填息", f[f["fill5"] == True]), ("5 日內未填息", f[f["fill5"] == False])]:  # noqa: E712
            lines.append(f"| {g} | {len(df)} | {cell(df[df['seg'] == '2019–2022'], '[+6, +25]')} | "
                         f"{cell(df[df['seg'] == '2023–2026/04'], '[+6, +25]')} | {cell(df, '[+6, +25]')} |")
        c = SimpleNamespace(rets=rets, betas=betas, tx=tx)
        sims = {"A 除息前布局（−11 日收盤買、−1 日收盤賣）": es.simulate_daily(window_portfolio(ev, -11, -1, days, limit), c, None),
                "B 5 日內填息者第 +5 日收盤買、持有 20 日": es.simulate_daily(window_portfolio(f[f["fill5"] == True], 5, 25, days, limit), c, None)}  # noqa: E712
        lines += ["", "策略（台指期對沖，扣交易成本；2019 ~ 2026/04）：", "",
                  "| 策略 | Sharpe 2019–2022 | 2023–2026/04 | 年化報酬 | 年化波動 | 最大回撤 | 平均持有檔數 | 有持股的日子 |", "|---|---|---|---|---|---|---|---|"]
        # 事後追加（看過除息後視窗通過判定後才加入）：除息日收盤放空、持有 20 日；主樣本扣借券費，驗證樣本無借券費資料（偏樂觀）
        fee = hc.lending_fees(client, list(adj.columns), days) if lo == 1 else None

        def short_pf(df):
            return {d: -w for d, w in window_portfolio(df, 0, 20, days, limit).items()}
        sims["C（事後追加）除息日收盤放空、持有 20 日"] = es.simulate_daily(short_pf(ev), c, fee)
        sims["D（事後追加）同上，只做殖利率 ≥ 5%"] = es.simulate_daily(short_pf(ev[ev["yield"] >= 0.05]), c, fee)
        for name, sim in sims.items():
            s = hc.stats(sim["ret"])
            lines.append(f"| {name} | {s['sh_oos']:.2f} | {s['sh_is']:.2f} | {s['ann']:+.1%} | {s['vol']:.1%} | {s['mdd']:.1%} | "
                         f"{sim.loc[sim['n'] > 0, 'n'].mean():.1f} | {(sim['n'] > 0).mean():.0%} |")
            rets_out[f"{sname}｜{name}"] = sim["ret"]
        lines.append("")

    # ---- 判定 ----
    main_ev, val_ev = results["前 500 名（主樣本）"], results["第 501–1000 名（驗證）"]
    lines += ["## 判定（主樣本兩段同號且 t > 2，且驗證樣本整體同號且 t > 2）", "", "| 視窗 | 主樣本 2019–2022 | 2023–2026/04 | 驗證樣本 | 判定 |", "|---|---|---|---|---|"]
    tests = list(WINDOWS) + ["填息 [+6, +25]"]
    for w in tests:
        if w.startswith("填息"):
            a = main_ev[main_ev["fill5"] == True]; v = val_ev[val_ev["fill5"] == True]; col = "[+6, +25]"  # noqa: E702,E712
        else:
            a, v, col = main_ev, val_ev, w
        r1 = es.date_clustered(a[a["seg"] == "2019–2022"], col)
        r2 = es.date_clustered(a[a["seg"] == "2023–2026/04"], col)
        r3 = es.date_clustered(v, col)
        ok = all(abs(r[1]) > 2 for r in (r1, r2, r3)) and np.sign(r1[0]) == np.sign(r2[0]) == np.sign(r3[0])
        lines.append(f"| {w} | {r1[0]:+.2%}（{r1[1]:.1f}） | {r2[0]:+.2%}（{r2[1]:.1f}） | {r3[0]:+.2%}（{r3[1]:.1f}） | {'通過' if ok else '未通過'} |")
    lines += ["", "除息日 [0] 含股利，未扣股利所得稅（個人）與二代健保補充保費 2.11%，即使通過也不代表個人可賺到。"]
    pd.DataFrame(rets_out).to_csv(ROOT / "reports" / "legs" / "dividend_events.csv")
    (ROOT / "docs" / "dividend_events.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
