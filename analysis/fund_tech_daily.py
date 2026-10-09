"""基本面選股 + 技術面每日進出場 + 權重混合：每日回測。

用法（於專案根目錄；輸入為 technical_timing.py 產生的 daily_pit_val_tech.csv）：
    .venv/Scripts/python analysis/fund_tech_daily.py daily_pit_val_tech.csv config/tickers_pit.yaml
輸出 docs/fund_tech_daily_data.md。

設計（看結果前固定）：
- 選股：每 21 個交易日，以財報 Agent 連續機率在大產業內取前 1/3（緩衝：已入選者產業內百分位 > 50% 續留），
  產業權重 = 股票池產業權重。21 種換倉起點。
- 每日進出場：第 t 日的部位只用 t−1 日收盤以前的資料決定，於 t 日收盤成交，賺取 t → t+1 的報酬。
  個股濾網：入選股前一日含息收盤 > 60 日（或 20 日）均線才持有，否則該部位持現金；回到均線上方就買回。
  大盤濾網：0050 前一日含息收盤 < 200 日均線時全部持現金。
- 權重混合：入選股在產業內依 0.5 × 財報百分位 + 0.5 × 技術面 Agent 百分位分配（產業總權重不變），取代等權。
- 成本：每日權重變動量 × 單邊 0.29625%（以目標權重計，忽略持有期間的權重漂移）。
- 下市或停牌無價格的日子報酬記為 0。
"""
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from backtest.portfolio import max_drawdown  # noqa: E402
from data.fetch_financials import FinMindClient, get_total_return_prices  # noqa: E402
from data.fetch_technical import FinMindTechnicalProvider  # noqa: E402

STEP, Q, KEEP = 21, 1 / 3, 0.5
COST = 0.0029625
SPLIT = pd.Timestamp("2023-01-01")


def load_prices(tickers):
    prov = FinMindTechnicalProvider(FinMindClient(), "2019-01-01", "2026-05-31")
    close, ma20, ma60 = {}, {}, {}
    for t in tickers:
        ind = prov.indicators(t)
        if ind.empty:
            continue
        s = ind.set_index("date")
        close[t], ma20[t], ma60[t] = s["close"], s["ma20"], s["ma60"]
    return pd.DataFrame(close).sort_index(), pd.DataFrame(ma20).sort_index(), pd.DataFrame(ma60).sort_index()


def market_on(index):
    px = get_total_return_prices(FinMindClient(), "0050.TW", "2017-06-01", "2026-05-31")
    adj = pd.Series(px["adj_close"].astype(float).to_numpy(), index=pd.DatetimeIndex(px["date"]))
    ma = adj.rolling(200, min_periods=200).mean()
    on = (adj > ma).astype(float).where(ma.notna())
    ret = adj.pct_change()
    return on.reindex(index, method="ffill"), ret.reindex(index).fillna(0.0)


def select(g: pd.DataFrame, held: set, mix: bool) -> dict:
    """g：某換倉日的成員（ticker、sector、pc_fundamentals_agent、pc_technical）。回傳 {ticker: 權重}。"""
    w_sector = g["sector"].value_counts(normalize=True)
    out = {}
    for sector, sg in g.groupby("sector"):
        pf = sg["pc_fundamentals_agent"].rank(pct=True, method="average")
        chosen = (pf > 1 - Q) | (sg["ticker"].isin(held) & (pf > KEEP))
        names = sg[chosen]
        if len(sg) < 3 or names.empty or len(names) == len(sg):
            names = sg
            pf = pf.loc[names.index]
        if mix:
            pt = sg["pc_technical"].rank(pct=True, method="average").fillna(0.5)
            score = 0.5 * pf.loc[names.index] + 0.5 * pt.loc[names.index]
            score = score.clip(lower=1e-6)
            for t, s in zip(names["ticker"], score):
                out[t] = w_sector[sector] * s / score.sum()
        else:
            for t in names["ticker"]:
                out[t] = w_sector[sector] / len(names)
    return out


def run(daily, close, ma20, ma60, mkt_on, bench_ret, phase, kind="sn", mix=False, stock_ma=None, mkt=False):
    dates = close.index
    rets = close.pct_change().fillna(0.0)
    above = {20: (close > ma20).astype(float).where(ma20.notna()), 60: (close > ma60).astype(float).where(ma60.notna())}
    reb_dates = daily.groupby("i")["date"].first()
    reb = {d: i for i, d in reb_dates.items() if i % STEP == phase}
    tickers = list(close.columns)
    col = {t: k for k, t in enumerate(tickers)}
    base = np.zeros(len(tickers))
    w_prev = np.zeros(len(tickers))
    held = set()
    rows = []
    started = False
    for k in range(1, len(dates)):
        d = dates[k]
        if d in reb:
            g = daily[daily["i"] == reb[d]]
            base = np.zeros(len(tickers))
            if kind == "ew":
                for t in g["ticker"]:
                    if t in col:
                        base[col[t]] = 1 / len(g)
            elif kind == "0050":
                pass
            else:
                sel = select(g.dropna(subset=["pc_fundamentals_agent"]), held, mix)
                held = set(sel)
                for t, x in sel.items():
                    if t in col:
                        base[col[t]] = x
            started = True
        if not started:
            continue
        w = base.copy()
        if stock_ma:
            ok = above[stock_ma].iloc[k - 1].fillna(0.0).to_numpy()  # 前一日收盤相對均線
            w = w * ok
        cash_all = mkt and mkt_on.iloc[k - 1] == 0
        if kind == "0050":
            wb = 0.0 if cash_all else 1.0
            to = abs(wb - (rows[-1]["w0050"] if rows else 0.0))
            r = wb * bench_ret.iloc[k + 1] if k + 1 < len(dates) else 0.0
            rows.append({"d": d, "net": r - to * COST, "expo": wb, "to": to, "w0050": wb})
            continue
        if cash_all:
            w = np.zeros_like(w)
        to = float(np.abs(w - w_prev).sum())
        r = float(np.dot(w, rets.iloc[k + 1].to_numpy())) if k + 1 < len(dates) else 0.0
        rows.append({"d": d, "net": r - to * COST, "expo": float(w.sum()), "to": to})
        w_prev = w
    return pd.DataFrame(rows)


def stats(s: pd.DataFrame) -> dict:
    r = s["net"].to_numpy()
    total = float(np.prod(1 + r) - 1)
    years = len(r) / 252
    ann = (1 + total) ** (1 / years) - 1 if total > -1 else -1.0
    vol = r.std(ddof=1) * math.sqrt(252)
    return {"ann": ann, "sharpe": ann / vol if vol else float("nan"), "mdd": max_drawdown(r),
            "expo": s["expo"].mean(), "to_yr": s["to"].sum() / years}


def main(path, config):
    import dotenv

    dotenv.load_dotenv(ROOT / ".env")
    cfg = yaml.safe_load(open(config, encoding="utf-8"))
    tickers = [u["ticker"] for u in cfg["universe"]]
    daily = pd.read_csv(path, parse_dates=["date"], usecols=["i", "date", "ticker", "sector", "pc_fundamentals_agent", "pc_technical"])
    daily = daily.dropna(subset=["sector"])
    close, ma20, ma60 = load_prices(tickers)
    close = close.loc["2019-01-01":"2026-05-29"]
    ma20, ma60 = ma20.reindex(close.index), ma60.reindex(close.index)
    on, bench = market_on(close.index)
    variants = [
        ("基準：財報產業中性 + 緩衝（無技術面）", dict()),
        ("+ 個股 60 日線每日進出", dict(stock_ma=60)),
        ("+ 個股 20 日線每日進出", dict(stock_ma=20)),
        ("+ 大盤 200 日線每日濾網", dict(mkt=True)),
        ("權重混合（財報 + 技術面）", dict(mix=True)),
        ("權重混合 + 個股 60 日線", dict(mix=True, stock_ma=60)),
        ("權重混合 + 個股 60 日線 + 大盤濾網", dict(mix=True, stock_ma=60, mkt=True)),
        ("對照：等權持有全部", dict(kind="ew")),
        ("對照：0050 買進持有", dict(kind="0050")),
        ("對照：0050 + 大盤濾網", dict(kind="0050", mkt=True)),
    ]
    out = ["# 基本面選股 + 技術面每日進出場（自動產生）", "",
           "由 [analysis/fund_tech_daily.py](../analysis/fund_tech_daily.py) 產生；解讀見 "
           "[fund_tech_daily_report.md](fund_tech_daily_report.md)。每日回測、21 種換倉起點中位數、扣成本；"
           "最大回撤以每日淨值計（比以 20 日為一期計算的數字深）。", "",
           "| 組合 | 期間 | 年化報酬 | Sharpe | 最大回撤 | 平均持股比例 | 年換手 |", "|---|---|---|---|---|---|---|"]
    for label, kw in variants:
        phases = [run(daily, close, ma20, ma60, on, bench, ph, **kw) for ph in (range(STEP) if kw.get("kind") != "0050" else [0])]
        for name, mask in (("2019–2022（樣本外）", lambda s: s["d"] < SPLIT), ("2023–2026/05", lambda s: s["d"] >= SPLIT)):
            st = [stats(p[mask(p)]) for p in phases]
            med = {k: np.median([x[k] for x in st]) for k in st[0]}
            out.append(f"| {label} | {name} | {med['ann'] * 100:+.1f}% | {med['sharpe']:.2f} | {med['mdd'] * 100:.0f}% | "
                       f"{med['expo']:.0%} | {med['to_yr']:.1f} |")
            print(out[-1], flush=True)
    (ROOT / "docs" / "fund_tech_daily_data.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("DONE", flush=True)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
