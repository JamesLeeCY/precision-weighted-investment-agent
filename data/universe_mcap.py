"""全市場、依市值排名的無選股偏誤股票池（使用者 2026-10-12：擴大到全市場前 300 / 500 / 1000 檔，依市值）。

1. 候選池：FinMind TaiwanStockInfo 中所有 4 碼普通股（上市 / 上櫃，含已下市；00 開頭 ETF、權證、特別股不在 4 碼普通股內）。
2. 每年第一個交易日：市值 = 前一個交易日收盤價 × 普通股股數；股數 = 資產負債表普通股股本 ÷ 面額 10 元，
   季報遞延 75 天才使用（FinMind 免費層沒有市值資料，以此自行計算）。依市值排序取前 TOP_N 檔，
   並要求前 60 個交易日中至少 40 天有成交（排除停牌或剛上市）。
3. 產業：TaiwanStockInfo 可能有多筆分類，優先取非泛稱的分類（「電子工業」「其他電子類」「其他」最後）。

輸出 config/universe_mcap_membership.csv：[year, rebalance_date, stock_id, stock_name, sector, market_type, mcap, avg_trading_value, rank]；
前 300 / 500 / 1000 的版本以 rank 篩選。

已知限制：產業分類不是逐年歷史；面額不是 10 元的公司（少數 KY、面額變更）市值會失真；下市前的大跌可能未完整反映。
"""
from __future__ import annotations

import pandas as pd

from data.fetch_financials import FinMindClient

TOP_N = 1000
LOOKBACK_DAYS, MIN_TRADED_DAYS = 60, 40
PRICE_HISTORY_START = "2018-06-01"       # 與 data/universe.py 相同 → 共用既有快取
BALANCE_HISTORY_START = "2017-01-01"     # 與財報 Agent 相同 → 共用既有快取
STATEMENT_LAG_DAYS = 75
GENERIC = ("電子工業", "其他電子類", "其他")


def candidate_pool(client: FinMindClient) -> pd.DataFrame:
    info = client.get("TaiwanStockInfo", "", "2000-01-01")
    info = info[info["stock_id"].str.fullmatch(r"[1-9]\d{3}") & info["type"].isin(["twse", "tpex"])].copy()
    info["_generic"] = info["industry_category"].isin(GENERIC).astype(int)
    info = info.sort_values(["stock_id", "_generic"])
    pool = info.drop_duplicates("stock_id")[["stock_id", "stock_name", "industry_category", "type"]]
    return pool.rename(columns={"industry_category": "sector", "type": "market_type"}).reset_index(drop=True)


def price_and_shares(client: FinMindClient, stock_id: str) -> tuple[pd.DataFrame, pd.Series]:
    px = client.get("TaiwanStockPrice", stock_id, PRICE_HISTORY_START)
    if not px.empty:
        px = px[px["close"].astype(float) > 0].assign(date=lambda x: pd.to_datetime(x["date"]))
        px = px[["date", "close", "Trading_money"]].astype({"close": float, "Trading_money": float}).sort_values("date")
    bs = client.get("TaiwanStockBalanceSheet", stock_id, BALANCE_HISTORY_START)
    shares = pd.Series(dtype=float)
    if not bs.empty:
        sh = bs[bs["type"] == "OrdinaryShare"][["date", "value"]]
        if not sh.empty:
            avail = pd.to_datetime(sh["date"]) + pd.Timedelta(days=STATEMENT_LAG_DAYS)
            shares = pd.Series(sh["value"].astype(float).to_numpy() / 10.0, index=avail).sort_index()
    return px, shares


def build_membership(client: FinMindClient, years: range, top_n: int = TOP_N, progress: bool = True) -> pd.DataFrame:
    pool = candidate_pool(client)
    data = {}
    for i, sid in enumerate(pool["stock_id"]):
        data[sid] = price_and_shares(client, sid)
        if progress and i % 100 == 0:
            print(f"  價格與股本 {i}/{len(pool)}", flush=True)
    calendar = sorted(set().union(*(set(px["date"]) for px, _ in data.values() if len(px))))
    rows = []
    for year in years:
        days = [d for d in calendar if d.year == year]
        if not days:
            continue
        rebalance = days[0]
        prior = [d for d in calendar if d < rebalance][-LOOKBACK_DAYS:]
        if not prior:
            continue
        for r in pool.itertuples():
            px, shares = data[r.stock_id]
            if px.empty or shares.empty:
                continue
            window = px[(px["date"] >= prior[0]) & (px["date"] <= prior[-1])]
            if len(window) < MIN_TRADED_DAYS:
                continue
            last = window.iloc[-1]
            avail = shares[shares.index <= prior[-1]]
            if avail.empty:
                continue
            rows.append({"year": year, "rebalance_date": rebalance.strftime("%Y-%m-%d"), "stock_id": r.stock_id,
                         "stock_name": r.stock_name, "sector": r.sector, "market_type": r.market_type,
                         "mcap": float(last["close"] * avail.iloc[-1]), "avg_trading_value": float(window["Trading_money"].mean())})
    df = pd.DataFrame(rows)
    df["rank"] = df.groupby("year")["mcap"].rank(ascending=False, method="first").astype(int)
    return df[df["rank"] <= top_n].sort_values(["year", "rank"]).reset_index(drop=True)


def load_membership(path, top_n: int | None = None) -> dict[int, set[str]]:
    """{year: {ticker(.TW)}}；top_n 指定時只取前 top_n 名。"""
    m = pd.read_csv(path, dtype={"stock_id": str})
    if top_n is not None:
        m = m[m["rank"] <= top_n]
    return {int(y): set(g["stock_id"] + ".TW") for y, g in m.groupby("year")}
