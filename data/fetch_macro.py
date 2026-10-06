"""總經 / 籌碼資料抓取（規格 3.5 / 第 4 節）。

MacroDataProvider 是總經/籌碼 Agent 依賴的抽象介面，測試時可用
fixture provider 替換。FinMind 實作以固定 history_start 抓整段歷史
（快取鍵不隨 as_of_date 變動，整個回測每個資料集只打一次 API）。

look-ahead 防護：法人買賣超、融資融券、外資持股皆於收盤後公布，
而回測以 as_of_date 收盤價進場，因此所有序列只保留 date < as_of_date。

半導體庫存週期（規格 3.5 列出的輸入之一）：FinMind 免費層無合適資料，
暫不納入。
"""
from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd

from data.fetch_financials import FinMindClient, normalize_ticker

FOREIGN_INVESTOR = "Foreign_Investor"
INVESTMENT_TRUST = "Investment_Trust"


class MacroDataProvider(ABC):
    """總經/籌碼 Agent 的資料介面。所有方法只回傳 date < as_of_date 的資料。"""

    @abstractmethod
    def get_institutional_net(self, ticker: str, as_of_date: str) -> pd.DataFrame:
        """個股每日法人淨買超（股），欄位 [date, foreign_net, trust_net]。"""

    @abstractmethod
    def get_shareholding(self, ticker: str, as_of_date: str) -> pd.DataFrame:
        """個股外資持股，欄位 [date, foreign_ratio_pct, shares_issued]。"""

    @abstractmethod
    def get_margin_balance(self, ticker: str, as_of_date: str) -> pd.DataFrame:
        """個股融資餘額（張），欄位 [date, margin_balance]。"""

    @abstractmethod
    def get_usd_twd(self, as_of_date: str) -> pd.DataFrame:
        """美元兌台幣即期匯率，欄位 [date, rate]（數值上升 = 台幣貶值）。"""

    @abstractmethod
    def get_us10y(self, as_of_date: str) -> pd.DataFrame:
        """美國 10 年期公債殖利率（%），欄位 [date, yield_pct]。"""

    @abstractmethod
    def get_market_foreign_net(self, as_of_date: str) -> pd.DataFrame:
        """全市場外資每日淨買超（元），欄位 [date, foreign_net]。"""


def _before(df: pd.DataFrame, as_of_date: str) -> pd.DataFrame:
    if df.empty:
        return df
    return df[df["date"] < pd.Timestamp(as_of_date)].sort_values("date").reset_index(drop=True)


def _net_by_investor(raw: pd.DataFrame) -> pd.DataFrame:
    """法人買賣超長表 → 每日外資/投信淨買超寬表。"""
    df = raw.assign(net=raw["buy"].astype(float) - raw["sell"].astype(float))
    wide = df.pivot_table(index="date", columns="name", values="net", aggfunc="sum")
    out = pd.DataFrame(index=wide.index)
    out["foreign_net"] = wide.get(FOREIGN_INVESTOR, 0.0)
    out["trust_net"] = wide.get(INVESTMENT_TRUST, 0.0)
    out = out.reset_index()
    out["date"] = pd.to_datetime(out["date"])
    return out


class FinMindMacroProvider(MacroDataProvider):
    def __init__(self, client: FinMindClient, history_start: str = "2023-01-01"):
        self.client = client
        self.history_start = history_start
        self._memo: dict[tuple[str, str], pd.DataFrame] = {}

    def _load(self, dataset: str, data_id: str) -> pd.DataFrame:
        # 回測每個時點都會呼叫，記憶體內再快取一層避免重複解析 JSON
        key = (dataset, data_id)
        if key not in self._memo:
            df = self.client.get(dataset, data_id, self.history_start)
            if not df.empty:
                df["date"] = pd.to_datetime(df["date"])
            self._memo[key] = df
        return self._memo[key]

    def get_institutional_net(self, ticker, as_of_date):
        raw = self._load("TaiwanStockInstitutionalInvestorsBuySell", normalize_ticker(ticker))
        if raw.empty:
            return pd.DataFrame(columns=["date", "foreign_net", "trust_net"])
        return _before(_net_by_investor(raw), as_of_date)

    def get_shareholding(self, ticker, as_of_date):
        raw = self._load("TaiwanStockShareholding", normalize_ticker(ticker))
        if raw.empty:
            return pd.DataFrame(columns=["date", "foreign_ratio_pct", "shares_issued"])
        df = raw.rename(
            columns={"ForeignInvestmentSharesRatio": "foreign_ratio_pct", "NumberOfSharesIssued": "shares_issued"}
        )[["date", "foreign_ratio_pct", "shares_issued"]]
        return _before(df, as_of_date)

    def get_margin_balance(self, ticker, as_of_date):
        raw = self._load("TaiwanStockMarginPurchaseShortSale", normalize_ticker(ticker))
        if raw.empty:
            return pd.DataFrame(columns=["date", "margin_balance"])
        df = raw.rename(columns={"MarginPurchaseTodayBalance": "margin_balance"})[["date", "margin_balance"]]
        return _before(df, as_of_date)

    def get_usd_twd(self, as_of_date):
        raw = self._load("TaiwanExchangeRate", "USD")
        if raw.empty:
            return pd.DataFrame(columns=["date", "rate"])
        df = raw.rename(columns={"spot_buy": "rate"})[["date", "rate"]]
        df = df[df["rate"].astype(float) > 0]  # 假日列以 -1 表示
        return _before(df, as_of_date)

    def get_us10y(self, as_of_date):
        raw = self._load("GovernmentBondsYield", "United States 10-Year")
        if raw.empty:
            return pd.DataFrame(columns=["date", "yield_pct"])
        return _before(raw.rename(columns={"value": "yield_pct"})[["date", "yield_pct"]], as_of_date)

    def get_market_foreign_net(self, as_of_date):
        raw = self._load("TaiwanStockTotalInstitutionalInvestors", "")
        if raw.empty:
            return pd.DataFrame(columns=["date", "foreign_net"])
        df = raw[raw["name"] == FOREIGN_INVESTOR]
        df = df.assign(foreign_net=df["buy"].astype(float) - df["sell"].astype(float))[["date", "foreign_net"]]
        return _before(df, as_of_date)
