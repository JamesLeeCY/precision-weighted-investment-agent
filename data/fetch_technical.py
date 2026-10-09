"""技術面資料：含息還原的日 K（開高低收量）與技術指標。

FinMind TaiwanStockPrice 是未還原價；以 get_total_return_prices 的含息還原因子（adj_close / close）
同比例調整開高低收，避免除權息、分割造成均線與高低點斷層。成交量不調整（分割當期的量比會失真，影響很小）。

指標（第 t 列只用到 t 日以前（含）的資料；Agent 在預測日 d 取 d 之前最後一列，無前視）：
- ma20、ma60：還原收盤價的 20 / 60 日均線
- trend：close / ma60 − 1（股價相對中期均線）
- ma_spread：ma20 / ma60 − 1（均線排列）
- vol_price：5 日均量 / 60 日均量 − 1，乘上 5 日報酬的正負號（價漲量增為正、價跌量增為負）
- breakout：收盤突破前 60 日最高價（壓力）= +1、跌破前 60 日最低價（支撐）= −1，其餘 0
- candle：近 5 日 K 線實體比例 (close − open) / (high − low) 的平均（買盤力道）
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from data.fetch_financials import FinMindClient, get_total_return_prices, normalize_ticker

INDICATOR_COLUMNS = ("trend", "ma_spread", "vol_price", "breakout", "candle")


def compute_indicators(ohlcv: pd.DataFrame) -> pd.DataFrame:
    """輸入欄位 [date, open, high, low, close, volume]（已還原、依日期排序），回傳加上指標的表。"""
    df = ohlcv.sort_values("date").reset_index(drop=True).copy()
    c = df["close"]
    df["ma20"] = c.rolling(20, min_periods=20).mean()
    df["ma60"] = c.rolling(60, min_periods=60).mean()
    df["trend"] = c / df["ma60"] - 1
    df["ma_spread"] = df["ma20"] / df["ma60"] - 1
    vol_ratio = df["volume"].rolling(5, min_periods=5).mean() / df["volume"].rolling(60, min_periods=60).mean() - 1
    df["vol_price"] = vol_ratio * np.sign(c / c.shift(5) - 1)
    prior_high = df["high"].shift(1).rolling(60, min_periods=60).max()
    prior_low = df["low"].shift(1).rolling(60, min_periods=60).min()
    df["breakout"] = np.where(c > prior_high, 1.0, np.where(c < prior_low, -1.0, 0.0))
    df.loc[prior_high.isna() | prior_low.isna(), "breakout"] = np.nan
    rng = (df["high"] - df["low"]).replace(0, np.nan)
    body = ((df["close"] - df["open"]) / rng).fillna(0.0)
    df["candle"] = body.rolling(5, min_periods=5).mean()
    return df


def technical_components(row) -> list[tuple[str, float]]:
    """一列指標 → 規則評分分量（各 ∈ [-1, 1]）；縮放係數為事先固定的經驗值。"""
    comps = []

    def add(name, value, scale):
        if value is not None and not (isinstance(value, float) and np.isnan(value)):
            comps.append((name, float(np.clip(value / scale, -1, 1))))

    add("均線趨勢", row.get("trend"), 0.10)      # 高於 60 日均線 10% 視為強
    add("均線排列", row.get("ma_spread"), 0.05)  # 20 日線高於 60 日線 5% 視為強
    add("量價", row.get("vol_price"), 1.0)       # 5 日均量為 60 日均量 2 倍且價漲 = +1
    add("支撐壓力", row.get("breakout"), 1.0)
    add("K線", row.get("candle"), 0.5)
    return comps


class FinMindTechnicalProvider:
    """每檔股票只讀一次價量資料並計算全期指標；查詢時回傳預測日之前最後一列。"""

    def __init__(self, client: FinMindClient, start_date: str, end_date: str):
        self.client, self.start, self.end = client, start_date, end_date
        self._cache: dict[str, pd.DataFrame] = {}

    def indicators(self, ticker: str) -> pd.DataFrame:
        if ticker not in self._cache:
            raw = self.client.get("TaiwanStockPrice", normalize_ticker(ticker), self.start, self.end)
            if raw.empty:
                self._cache[ticker] = pd.DataFrame()
                return self._cache[ticker]
            raw = raw[raw["close"].astype(float) > 0].copy()
            raw["date"] = pd.to_datetime(raw["date"])
            adj = get_total_return_prices(self.client, ticker, self.start, self.end).set_index("date")["adj_close"]
            raw = raw.set_index("date").join(adj, how="inner").reset_index()
            f = raw["adj_close"] / raw["close"].astype(float)
            ohlcv = pd.DataFrame({
                "date": raw["date"], "open": raw["open"].astype(float) * f, "high": raw["max"].astype(float) * f,
                "low": raw["min"].astype(float) * f, "close": raw["adj_close"].astype(float),
                "volume": raw["Trading_Volume"].astype(float),
            })
            self._cache[ticker] = compute_indicators(ohlcv)
        return self._cache[ticker]

    def latest_before(self, ticker: str, as_of_date: str) -> dict:
        ind = self.indicators(ticker)
        if ind.empty:
            return {}
        prior = ind[ind["date"] < pd.Timestamp(as_of_date)]
        return {} if prior.empty else prior.iloc[-1].to_dict()
