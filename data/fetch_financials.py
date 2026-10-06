"""FinMind 財報 / 價量資料抓取（規格第 4 節）。

- 優先使用 FinMind API（免爬 MOPS，降低維護成本與封鎖風險）
- 所有請求皆做本地快取（data_cache/）與請求頻率控制
- FundamentalsDataProvider 是財報 Agent 依賴的抽象介面，
  測試時可用 fixture provider 替換，不需真實 API
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from abc import ABC, abstractmethod
from pathlib import Path

import pandas as pd
import requests

FINMIND_API_URL = "https://api.finmindtrade.com/api/v4/data"
# 免費方案約 300 req/hr，保守控制請求間隔
MIN_REQUEST_INTERVAL_SEC = 0.5

DEFAULT_CACHE_DIR = Path(__file__).resolve().parent.parent / "data_cache"


def normalize_ticker(ticker: str) -> str:
    """'2327.TW' -> '2327'（FinMind 的 data_id 不含交易所後綴）。"""
    return ticker.split(".")[0]


class FinMindClient:
    """FinMind REST API 的薄封裝，含本地 JSON 快取與節流。"""

    def __init__(
        self,
        token: str | None = None,
        cache_dir: str | Path = DEFAULT_CACHE_DIR,
        use_cache: bool = True,
    ):
        self.token = token or os.environ.get("FINMIND_API_TOKEN", "")
        self.cache_dir = Path(cache_dir)
        self.use_cache = use_cache
        self._last_request_ts = 0.0

    def _cache_path(self, params: dict) -> Path:
        key = json.dumps(params, sort_keys=True, ensure_ascii=False)
        digest = hashlib.md5(key.encode("utf-8")).hexdigest()[:16]
        name = f"{params.get('dataset', 'unknown')}_{params.get('data_id', '')}_{digest}.json"
        return self.cache_dir / name

    def get(self, dataset: str, data_id: str, start_date: str, end_date: str | None = None) -> pd.DataFrame:
        params = {
            "dataset": dataset,
            "data_id": data_id,
            "start_date": start_date,
        }
        if end_date:
            params["end_date"] = end_date

        cache_path = self._cache_path(params)
        if self.use_cache and cache_path.exists():
            return pd.DataFrame(json.loads(cache_path.read_text(encoding="utf-8")))

        rows = self._request_with_quota_retry(params)

        if self.use_cache:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
        return pd.DataFrame(rows)

    # 免費 register 等級約 600 req/hr；超額時 FinMind 回覆 402/400 與
    # 「Requests reach the upper limit」訊息。這裡自動等待額度重置後重試，
    # 讓長時間回測可以無人值守跑完。
    QUOTA_WAIT_SEC = 300
    QUOTA_MAX_RETRIES = 20

    def _request_with_quota_retry(self, params: dict) -> list:
        for attempt in range(self.QUOTA_MAX_RETRIES + 1):
            elapsed = time.monotonic() - self._last_request_ts
            if elapsed < MIN_REQUEST_INTERVAL_SEC:
                time.sleep(MIN_REQUEST_INTERVAL_SEC - elapsed)
            resp = requests.get(FINMIND_API_URL, params={**params, "token": self.token}, timeout=60)
            self._last_request_ts = time.monotonic()
            try:
                payload = resp.json()
            except ValueError:
                payload = {}
            msg = str(payload.get("msg", ""))
            if resp.status_code == 200:
                return payload.get("data", [])
            if "upper limit" in msg.lower() or resp.status_code in (402, 429):
                print(f"[quota] FinMind 額度已滿（{msg}），等待 {self.QUOTA_WAIT_SEC}s 後重試 "
                      f"({attempt + 1}/{self.QUOTA_MAX_RETRIES})", flush=True)
                time.sleep(self.QUOTA_WAIT_SEC)
                continue
            raise RuntimeError(f"FinMind API 錯誤 (HTTP {resp.status_code}): {msg or resp.text[:200]}")
        raise RuntimeError("FinMind 額度等待逾時，請稍後再試")


class FundamentalsDataProvider(ABC):
    """財報 Agent 依賴的資料介面（可用 fixture 替換以利測試）。"""

    @abstractmethod
    def get_monthly_revenue(self, ticker: str, as_of_date: str) -> pd.DataFrame:
        """回傳月營收，欄位至少含 [date, revenue]，且只含 as_of_date 以前的資料。"""

    @abstractmethod
    def get_quarterly_financials(self, ticker: str, as_of_date: str) -> pd.DataFrame:
        """回傳季度財務特徵，欄位至少含
        [date, gross_margin, inventory_days, receivable_days]（可含 NaN），
        且只含 as_of_date 以前公告的資料。"""


class FinMindFundamentalsProvider(FundamentalsDataProvider):
    """以 FinMind 資料組出財報 Agent 需要的特徵表。

    look-ahead 防護：
    - 月營收：公告約在次月 10 日，僅保留 date + 40 天 <= as_of_date 的資料（保守）
    - 季報：公告最遲約在季末後 45-90 天，僅保留 date + 75 天 <= as_of_date（保守近似）
    """

    REVENUE_LAG_DAYS = 40
    STATEMENT_LAG_DAYS = 75

    def __init__(self, client: FinMindClient, history_start: str = "2020-01-01"):
        self.client = client
        self.history_start = history_start

    def get_monthly_revenue(self, ticker: str, as_of_date: str) -> pd.DataFrame:
        df = self.client.get("TaiwanStockMonthRevenue", normalize_ticker(ticker), self.history_start)
        if df.empty:
            return pd.DataFrame(columns=["date", "revenue"])
        df = df[["date", "revenue"]].copy()
        df["date"] = pd.to_datetime(df["date"])
        cutoff = pd.Timestamp(as_of_date) - pd.Timedelta(days=self.REVENUE_LAG_DAYS)
        return df[df["date"] <= cutoff].sort_values("date").reset_index(drop=True)

    def get_quarterly_financials(self, ticker: str, as_of_date: str) -> pd.DataFrame:
        data_id = normalize_ticker(ticker)
        income = self.client.get("TaiwanStockFinancialStatements", data_id, self.history_start)
        balance = self.client.get("TaiwanStockBalanceSheet", data_id, self.history_start)

        if income.empty:
            return pd.DataFrame(columns=["date", "gross_margin", "inventory_days", "receivable_days"])

        inc = income.pivot_table(index="date", columns="type", values="value", aggfunc="first")
        out = pd.DataFrame(index=inc.index)

        revenue = inc.get("Revenue")
        gross = inc.get("GrossProfit")
        cogs = inc.get("CostOfGoodsSold")
        if gross is None and revenue is not None and cogs is not None:
            gross = revenue - cogs
        if revenue is not None and gross is not None:
            out["gross_margin"] = (gross / revenue.replace(0, pd.NA)) * 100.0

        if not balance.empty:
            bal = balance.pivot_table(index="date", columns="type", values="value", aggfunc="first")
            inventory = bal.get("Inventories")
            receivable = bal.get("AccountsReceivableNet")
            if receivable is None:
                receivable = bal.get("NotesAndAccountsReceivableNet")
            # 以季營收/季銷貨成本估算週轉天數（一季約 91 天）
            if inventory is not None and cogs is not None:
                out["inventory_days"] = (inventory / cogs.replace(0, pd.NA)) * 91.0
            if receivable is not None and revenue is not None:
                out["receivable_days"] = (receivable / revenue.replace(0, pd.NA)) * 91.0

        out = out.reset_index()
        out["date"] = pd.to_datetime(out["date"])
        cutoff = pd.Timestamp(as_of_date) - pd.Timedelta(days=self.STATEMENT_LAG_DAYS)
        out = out[out["date"] <= cutoff].sort_values("date").reset_index(drop=True)
        for col in ("gross_margin", "inventory_days", "receivable_days"):
            if col not in out.columns:
                out[col] = pd.NA
        return out[["date", "gross_margin", "inventory_days", "receivable_days"]]


def get_daily_prices(client: FinMindClient, ticker: str, start_date: str, end_date: str) -> pd.DataFrame:
    """回測用日收盤價，欄位 [date, close]。"""
    df = client.get("TaiwanStockPrice", normalize_ticker(ticker), start_date, end_date)
    if df.empty:
        return pd.DataFrame(columns=["date", "close"])
    df = df[["date", "close"]].copy()
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values("date").reset_index(drop=True)


def get_adjustment_events(client: FinMindClient, ticker: str, start_date: str, end_date: str) -> pd.DataFrame:
    """除權息與分割事件，欄位 [date, before_price, after_price]。

    FinMind 的 TaiwanStockPrice 是未還原股價：配股（如國巨 2024-08-15）
    與分割（如 0050 2025-06-18 一拆四）會造成價格斷層。還原股價資料集
    （TaiwanStockPriceAdj）需付費等級，因此改以這兩個免費資料集自行還原。
    """
    data_id = normalize_ticker(ticker)
    frames = []
    for dataset in ("TaiwanStockDividendResult", "TaiwanStockSplitPrice"):
        df = client.get(dataset, data_id, start_date, end_date)
        if not df.empty:
            frames.append(df[["date", "before_price", "after_price"]])
    if not frames:
        return pd.DataFrame(columns=["date", "before_price", "after_price"])
    events = pd.concat(frames, ignore_index=True)
    events["date"] = pd.to_datetime(events["date"])
    events = events[(events["before_price"] > 0) & (events["after_price"] > 0)]
    return events.sort_values("date").reset_index(drop=True)


def total_return_index(prices: pd.DataFrame, events: pd.DataFrame) -> pd.Series:
    """含息還原收盤價（股利於除權息日以參考價再投入）。

    adj_close[t] = close[t] × Π(before/after)，連乘所有 date <= t 的事件。
    任意兩日的 adj_close 比值即為期間總報酬（含現金股利、配股、分割）。
    """
    factor = pd.Series(1.0, index=prices.index)
    for _, ev in events.iterrows():
        factor[prices["date"] >= ev["date"]] *= float(ev["before_price"]) / float(ev["after_price"])
    return prices["close"].astype(float) * factor


def get_total_return_prices(client: FinMindClient, ticker: str, start_date: str, end_date: str) -> pd.DataFrame:
    """回測用日收盤價，欄位 [date, close, adj_close]（adj_close 為含息還原價）。"""
    prices = get_daily_prices(client, ticker, start_date, end_date)
    if prices.empty:
        return prices.assign(adj_close=pd.Series(dtype=float))
    events = get_adjustment_events(client, ticker, start_date, end_date)
    prices["adj_close"] = total_return_index(prices, events)
    return prices
