"""無選股偏誤（point-in-time）的股票池。

擴大股票池（config/tickers_expanded.yaml）是 2026 年依「AI 供應鏈」事後挑選的，
多數是之後的贏家，絕對報酬與跨產業 IC 都會被高估。這裡改成每年只用「當時」可得的
資訊選股：

1. 候選池：FinMind TaiwanStockInfo 中屬於電子相關產業的 4 碼普通股（上市 / 上櫃），
   **含已下市公司**（TaiwanStockInfo 保留多數下市股票）。只依產業分類，不看任何報酬。
2. 每年第一個交易日重新選股：以前 LOOKBACK_DAYS 個交易日的平均成交金額排序，
   取前 top_n 檔；期間內交易日不足 MIN_TRADED_DAYS 的股票不納入（新上市或已停止交易）。
3. 產業：同一檔股票在 TaiwanStockInfo 可能有多筆分類（TWSE 近年把部分公司改歸到泛稱的
   「電子工業」），取最細的分類（見 SECTOR_PRIORITY）。

已知限制：
- 產業分類本身不是逐年的歷史資料（以 FinMind 目前保存的分類為準）。
- 持有期間下市的股票，以最後一個收盤價計值；下市前常有大跌或無法交易，報酬會略為高估。
- 少數 2019 年後下市的股票不在 TaiwanStockInfo 中（154 檔中缺 14 檔），無法納入。
"""
from __future__ import annotations

import pandas as pd

from data.fetch_financials import FinMindClient

# 由細到粗；同一檔股票有多筆分類時取排序最前者
SECTOR_PRIORITY = [
    "半導體業", "電子零組件業", "電腦及週邊設備業", "通信網路業", "其他電子業", "其他電子類", "電子工業",
]
LOOKBACK_DAYS = 60
MIN_TRADED_DAYS = 40
PRICE_HISTORY_START = "2018-06-01"


def candidate_pool(client: FinMindClient) -> pd.DataFrame:
    """回傳 [stock_id, stock_name, sector, type, delisted_date]。"""
    info = client.get("TaiwanStockInfo", "", "2000-01-01")
    # 4 碼普通股（00 開頭為 ETF），上市或上櫃（排除興櫃）
    info = info[
        info["stock_id"].str.fullmatch(r"[1-9]\d{3}") & info["type"].isin(["twse", "tpex"])
    ]
    info = info[info["industry_category"].isin(SECTOR_PRIORITY)]
    rank = {s: i for i, s in enumerate(SECTOR_PRIORITY)}
    info = info.assign(_rank=info["industry_category"].map(rank)).sort_values(["stock_id", "_rank"])
    pool = info.drop_duplicates("stock_id")[["stock_id", "stock_name", "industry_category", "type"]]
    pool = pool.rename(columns={"industry_category": "sector"})
    delist = client.get("TaiwanStockDelisting", "", "2000-01-01")
    if not delist.empty:
        pool = pool.merge(
            delist[["stock_id", "date"]].rename(columns={"date": "delisted_date"}).drop_duplicates("stock_id"),
            on="stock_id", how="left",
        )
    return pool.reset_index(drop=True)


def trading_value(client: FinMindClient, stock_id: str) -> pd.Series:
    """每日成交金額（元），index 為日期；收盤價為 0 的資料列（無成交）剔除。"""
    df = client.get("TaiwanStockPrice", stock_id, PRICE_HISTORY_START)
    if df.empty:
        return pd.Series(dtype=float, index=pd.DatetimeIndex([]))
    df = df[df["close"].astype(float) > 0]
    return pd.Series(df["Trading_money"].astype(float).to_numpy(), index=pd.to_datetime(df["date"])).sort_index()


def build_membership(
    client: FinMindClient, years: range, top_n: int = 100, progress: bool = True
) -> pd.DataFrame:
    """回傳每年成員表 [year, rebalance_date, stock_id, stock_name, sector, avg_trading_value, rank]。"""
    pool = candidate_pool(client)
    values = {}
    for i, sid in enumerate(pool["stock_id"]):
        values[sid] = trading_value(client, sid)
        if progress and i % 100 == 0:
            print(f"  成交金額 {i}/{len(pool)}", flush=True)
    calendar = sorted(set().union(*(v.index for v in values.values() if len(v))))
    rows = []
    for year in years:
        days = [d for d in calendar if d.year == year]
        if not days:
            continue
        rebalance = days[0]
        lookback = [d for d in calendar if d < rebalance][-LOOKBACK_DAYS:]
        start = lookback[0]
        scores = []
        for _, r in pool.iterrows():
            v = values[r["stock_id"]]
            window = v[(v.index >= start) & (v.index < rebalance)]
            if len(window) >= MIN_TRADED_DAYS:
                scores.append((r["stock_id"], r["stock_name"], r["sector"], float(window.mean())))
        scores.sort(key=lambda x: -x[3])
        for rank, (sid, name, sector, value) in enumerate(scores[:top_n], start=1):
            rows.append({
                "year": year, "rebalance_date": rebalance.strftime("%Y-%m-%d"), "stock_id": sid,
                "stock_name": name, "sector": sector, "avg_trading_value": round(value), "rank": rank,
            })
    return pd.DataFrame(rows)


def load_membership(path) -> dict[int, set[str]]:
    """成員表 CSV → {年份: {ticker（含 .TW）}}。"""
    df = pd.read_csv(path, dtype={"stock_id": str})
    return {int(y): {f"{s}.TW" for s in g["stock_id"]} for y, g in df.groupby("year")}


# 產業層級的供應鏈預設邊（無公司層級證據）；與 config/supply_chain_graph_expanded.json 的
# 產業預設一致。同一產業內所有股票的供應鏈特徵相同，因此供應鏈 Agent 不影響產業內排序。
ODM = ["2382.TW", "3231.TW", "6669.TW"]
HYPER = ["MSFT.US", "AMZN.US", "GOOGL.US", "META.US"]
SECTOR_EDGES = {
    "半導體業": [("2330.TW", 1.0, "晶圓代工 / 半導體景氣"), ("NVDA.US", 0.5, "AI 運算需求")],
    "電子零組件業": [*[(o, 0.5, "伺服器 ODM") for o in ODM], ("2317.TW", 0.5, "消費性電子 EMS"), ("NVDA.US", 0.5, "AI 伺服器")],
    "電腦及週邊設備業": [("NVDA.US", 1.0, "AI 伺服器 GPU 平台"), *[(h, 0.5, "雲端資本支出") for h in HYPER]],
    "通信網路業": [*[(h, 0.5, "雲端 / 資料中心資本支出") for h in HYPER], ("2317.TW", 0.5, "消費性電子 EMS")],
    "其他電子業": [("2395.TW", 0.5, "工業"), ("2317.TW", 0.5, "消費性電子 EMS")],
    "其他電子類": [("2395.TW", 0.5, "工業"), ("2317.TW", 0.5, "消費性電子 EMS")],
    "電子工業": [*[(o, 0.5, "伺服器 ODM") for o in ODM], ("2317.TW", 0.5, "消費性電子 EMS"), ("NVDA.US", 0.5, "AI 伺服器")],
}


def sector_graph(membership: pd.DataFrame) -> dict:
    """依成員表的產業產生供應鏈圖譜（自己指向自己的邊略過）。"""
    edges = {}
    for sid, sector in membership.drop_duplicates("stock_id")[["stock_id", "sector"]].itertuples(index=False):
        ticker = f"{sid}.TW"
        edges[ticker] = [
            {"to": to, "relation": "downstream", "weight": w, "source": f"產業預設（{sector}）：{why}"}
            for to, w, why in SECTOR_EDGES.get(sector, []) if to != ticker
        ]
    return {
        "_說明": [
            "無選股偏誤股票池的供應鏈圖譜：依 FinMind 產業分類自動產生，全部為產業預設，無公司層級證據。",
            "同一產業內的股票供應鏈特徵相同，供應鏈 Agent 只影響跨產業配置，不影響產業內排序。",
        ],
        "edges": edges,
    }
