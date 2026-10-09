"""供應鏈 Agent 的資料層：知識圖譜載入與關聯公司的價量 / 營收序列。

SupplyChainDataProvider 是供應鏈 Agent 依賴的抽象介面，測試時可用 fixture 替換。
look-ahead 防護：
- 股價只用 date < as_of_date 的收盤價（回測以 as_of_date 收盤進場，保守起見不用當日收盤）
- 股價一律用含息還原價：國巨 2025-08 一拆四，未還原價會出現 −75% 的假跌
- 月營收沿用財報 Agent 的公告遞延（date + 40 天 <= as_of_date）

美股代理（代號以 .US 結尾，如 NVDA.US）：使用 FinMind USStockPrice 的還原收盤價
（Adj_Close），超額報酬以 SPY 為市場基準。美股 d 日收盤發生在台灣 d+1 日開盤前，
只用 date < as_of_date 的資料仍不會偷看。美股沒有月營收資料。
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path

import pandas as pd

from data.fetch_financials import FinMindClient, FinMindFundamentalsProvider, normalize_ticker, total_return_index

DEFAULT_GRAPH_PATH = Path(__file__).resolve().parent.parent / "config" / "supply_chain_graph.json"
MARKET_INDEX = "TAIEX"
US_MARKET_INDEX = "SPY.US"


def is_us(ticker: str) -> bool:
    return ticker.endswith(".US")


def market_index_for(ticker: str) -> str:
    """計算超額報酬時使用的市場基準。"""
    return US_MARKET_INDEX if is_us(ticker) else MARKET_INDEX


def load_graph(path: str | Path = DEFAULT_GRAPH_PATH) -> dict:
    """回傳 {"edges": {ticker: [{to, relation, weight}]}, "proxies": {...}}。"""
    graph = json.loads(Path(path).read_text(encoding="utf-8"))
    for ticker, edges in graph.get("edges", {}).items():
        for e in edges:
            if e["relation"] not in ("downstream", "leader", "group"):
                raise ValueError(f"{ticker} 的關係類型不合法：{e['relation']}")
            if float(e["weight"]) <= 0:
                raise ValueError(f"{ticker} → {e['to']} 的權重必須為正")
    return graph


class SupplyChainDataProvider(ABC):
    @abstractmethod
    def get_closes(self, ticker: str, as_of_date: str) -> pd.Series:
        """日收盤價（index 為日期），只含 date < as_of_date。ticker 可為 MARKET_INDEX。"""

    @abstractmethod
    def get_monthly_revenue(self, ticker: str, as_of_date: str) -> pd.DataFrame:
        """月營收 [date, revenue]，已套用公告遞延。"""


class FinMindSupplyChainProvider(SupplyChainDataProvider):
    def __init__(self, client: FinMindClient, history_start: str = "2023-01-01"):
        self.client = client
        self.history_start = history_start
        # 營收歷史需早於回測起點 13 個月以上（年增率），與股價共用同一個起點
        self.revenue = FinMindFundamentalsProvider(client, history_start=history_start)
        self._memo: dict[str, pd.Series] = {}

    def get_closes(self, ticker, as_of_date):
        if is_us(ticker):
            return self._us_closes(ticker, as_of_date)
        data_id = ticker if ticker == MARKET_INDEX else normalize_ticker(ticker)
        if data_id not in self._memo:
            # 固定 history_start、不帶 end_date：快取鍵不隨時點變動，每檔只打一次 API
            df = self.client.get("TaiwanStockPrice", data_id, self.history_start)
            if df.empty:
                self._memo[data_id] = pd.Series(dtype=float)
            else:
                prices = pd.DataFrame({"date": pd.to_datetime(df["date"]), "close": df["close"].astype(float)})
                # 收盤價為 0 的資料列（無成交日）視為缺值，見 get_daily_prices
                prices = prices[prices["close"] > 0].sort_values("date").reset_index(drop=True)
                adj = total_return_index(prices, self._adjustment_events(data_id))
                self._memo[data_id] = pd.Series(adj.to_numpy(), index=prices["date"])
        s = self._memo[data_id]
        return s[s.index < pd.Timestamp(as_of_date)]

    def _us_closes(self, ticker: str, as_of_date: str) -> pd.Series:
        symbol = ticker[: -len(".US")]
        key = f"US:{symbol}"
        if key not in self._memo:
            df = self.client.get("USStockPrice", symbol, self.history_start)
            if df.empty:
                self._memo[key] = pd.Series(dtype=float)
            else:
                df = df[df["Adj_Close"].astype(float) > 0]
                self._memo[key] = pd.Series(
                    df["Adj_Close"].astype(float).to_numpy(), index=pd.to_datetime(df["date"])
                ).sort_index()
        s = self._memo[key]
        return s[s.index < pd.Timestamp(as_of_date)]

    def _adjustment_events(self, data_id: str) -> pd.DataFrame:
        """除權息與分割事件；大盤指數沒有此類事件。"""
        if data_id == MARKET_INDEX:
            return pd.DataFrame(columns=["date", "before_price", "after_price"])
        frames = []
        for dataset in ("TaiwanStockDividendResult", "TaiwanStockSplitPrice"):
            df = self.client.get(dataset, data_id, self.history_start)
            if not df.empty:
                frames.append(df[["date", "before_price", "after_price"]])
        if not frames:
            return pd.DataFrame(columns=["date", "before_price", "after_price"])
        events = pd.concat(frames, ignore_index=True)
        events["date"] = pd.to_datetime(events["date"])
        return events[(events["before_price"] > 0) & (events["after_price"] > 0)]

    def get_monthly_revenue(self, ticker, as_of_date):
        if is_us(ticker):
            return pd.DataFrame(columns=["date", "revenue"])
        return self.revenue.get_monthly_revenue(ticker, as_of_date)
