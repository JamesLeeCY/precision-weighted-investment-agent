"""新聞抓取與解析（規格 3.3 / 第 4 節）。

兩個來源：
- RSSNewsProvider：Google News RSS（即時使用，免付費 API）
- FinMindNewsProvider：FinMind TaiwanStockNews（有歷史資料，回測用）

來源可信度分級（規格 3.3：公司公告 > 財經媒體 > 論壇/社群）以
classify_source_tier() 實作，回傳 tier 權重 ∈ {1.0, 0.7, 0.4}。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import feedparser
import pandas as pd

# 來源可信度分級規則（規格 9.3：簡化假設，需視實際資料品質調整）
TIER_ANNOUNCEMENT = 1.0   # 公司公告 / 證交所重大訊息
TIER_MEDIA = 0.7          # 財經媒體
TIER_FORUM = 0.4          # 論壇 / 社群 / 未知來源

_ANNOUNCEMENT_KEYWORDS = ("公開資訊觀測站", "mops", "twse", "證交所", "重大訊息", "公告")
_MEDIA_KEYWORDS = (
    "經濟日報", "工商時報", "中央社", "鉅亨", "anue", "moneydj", "財訊",
    "天下", "今周刊", "自由財經", "yahoo", "聯合新聞", "digitimes", "科技新報",
    "reuters", "bloomberg", "路透",
    # FinMind TaiwanStockNews 常見來源
    "中時", "旺得富", "cmoney", "富聯網", "時報", "日報", "新聞網", "經濟通",
)


def classify_source_tier(source: str) -> float:
    s = (source or "").lower()
    if any(k in s for k in _ANNOUNCEMENT_KEYWORDS):
        return TIER_ANNOUNCEMENT
    if any(k in s for k in _MEDIA_KEYWORDS):
        return TIER_MEDIA
    return TIER_FORUM


@dataclass
class NewsItem:
    title: str
    published: datetime
    source: str = ""
    summary: str = ""
    url: str = ""
    source_tier: float = field(default=TIER_FORUM)

    def __post_init__(self):
        if not self.source_tier or self.source_tier == TIER_FORUM:
            self.source_tier = classify_source_tier(self.source)

    @property
    def text(self) -> str:
        return f"{self.title} {self.summary}".strip()


def dedupe_and_sort(items: list[NewsItem]) -> list[NewsItem]:
    """去重（正規化標題）並按時間排序（新→舊）。同標題保留可信度較高者。"""
    best: dict[str, NewsItem] = {}
    for it in items:
        key = "".join(it.title.split()).lower()
        if key not in best or it.source_tier > best[key].source_tier:
            best[key] = it
    return sorted(best.values(), key=lambda x: x.published, reverse=True)


class NewsProvider(ABC):
    @abstractmethod
    def get_news(self, ticker: str, start_date: str, end_date: str) -> list[NewsItem]:
        """回傳 [start_date, end_date] 區間內的新聞（已去重、按時間排序）。"""


class RSSNewsProvider(NewsProvider):
    """Google News RSS 檢索（即時新聞用；RSS 無法取得深度歷史）。"""

    RSS_URL = "https://news.google.com/rss/search?q={query}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"

    def __init__(self, ticker_names: dict[str, str] | None = None):
        # ticker -> 公司名稱，檢索時用名稱效果遠比代號好
        self.ticker_names = ticker_names or {}

    def get_news(self, ticker: str, start_date: str, end_date: str) -> list[NewsItem]:
        name = self.ticker_names.get(ticker, ticker.split(".")[0])
        query = f"{name} 股"
        feed = feedparser.parse(self.RSS_URL.format(query=query))
        start = pd.Timestamp(start_date)
        end = pd.Timestamp(end_date) + pd.Timedelta(days=1)
        items = []
        for e in feed.entries:
            try:
                published = datetime(*e.published_parsed[:6])
            except (AttributeError, TypeError):
                continue
            if not (start <= pd.Timestamp(published) < end):
                continue
            source = getattr(getattr(e, "source", None), "title", "") or ""
            items.append(
                NewsItem(
                    title=e.get("title", ""),
                    summary=e.get("summary", ""),
                    source=source,
                    url=e.get("link", ""),
                    published=published,
                )
            )
        return dedupe_and_sort(items)


class FinMindNewsProvider(NewsProvider):
    """FinMind TaiwanStockNews：有歷史新聞，供回測期間查詢。

    此資料集限制一次只能查一天（不可帶 end_date），因此逐日請求；
    FinMindClient 的每日快取確保同一天不會重複扣 API 額度。
    欄位僅有 date/stock_id/link/source/title（無內文摘要）。
    """

    def __init__(self, client):
        self.client = client  # FinMindClient

    def get_news(self, ticker: str, start_date: str, end_date: str) -> list[NewsItem]:
        from data.fetch_financials import normalize_ticker

        data_id = normalize_ticker(ticker)
        items = []
        for day in pd.date_range(start_date, end_date, freq="D"):
            df = self.client.get("TaiwanStockNews", data_id, day.strftime("%Y-%m-%d"))
            for _, row in df.iterrows():
                try:
                    published = pd.Timestamp(row["date"]).to_pydatetime()
                except (KeyError, ValueError):
                    continue
                items.append(
                    NewsItem(
                        title=str(row.get("title", "")),
                        summary="",
                        source=str(row.get("source", "")),
                        url=str(row.get("link", "") or ""),
                        published=published,
                    )
                )
        return dedupe_and_sort(items)
