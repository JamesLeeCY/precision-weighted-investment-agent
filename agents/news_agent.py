"""新聞事件 Agent（規格 3.3，MVP 必做）。

流程：
1. 由 NewsProvider 取得近 window_days（預設 14）天的新聞，去重、按時間排序
2. 新聞太多時以向量檢索（RAG）挑出與「營運/展望」最相關的 top-k 則
3. 規則式事件抽取：事件類型（擴產、客戶認證、調升目標價、匯率影響…）
   與情緒方向，各事件的貢獻乘上來源可信度權重（公告 > 媒體 > 論壇）
   與時間衰減（半衰期 7 天）
4. 若 LLM 可用，把整理後的新聞清單送入 LLM 做事件/情緒判讀，
   失敗時退回規則式結果；來源可信度同樣反映在 confidence
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from agents.base import AgentOutput, BaseAgent
from agents.llm_client import LLMClient
from data.fetch_news import NewsItem, NewsProvider
from data.vector_store import SimpleVectorStore

SYSTEM_PROMPT = """你是台股新聞事件分析師。根據提供的新聞清單（含來源可信度分級：公司公告1.0 > 財經媒體0.7 > 論壇0.4），判斷該股票未來 {horizon} 個交易日的方向。

要求：
1. 抽取事件類型（擴產、客戶認證、法人調升/調降目標價、漲價/跌價、匯率影響、砍單等）
2. 可信度低的來源（論壇/社群）不可作為主要依據
3. confidence 需反映來源品質：僅有低可信度來源時 confidence 不得超過 0.5

只回傳 JSON（不要其他文字）：
{{"signal": "bullish|bearish|neutral", "confidence": 0.0-1.0, "rationale": "繁體中文，200字以內"}}"""

# 事件類型關鍵詞 → 極性（規格 3.3 列舉的事件類型為核心，另補產業常見事件）
EVENT_LEXICON: dict[str, tuple[str, int]] = {
    # keyword: (event_type, polarity)
    "擴產": ("capacity_expansion", +1),
    "擴廠": ("capacity_expansion", +1),
    "新產能": ("capacity_expansion", +1),
    "認證": ("customer_qualification", +1),
    "打入": ("customer_qualification", +1),
    "調升目標價": ("target_price_up", +1),
    "上修": ("estimate_up", +1),
    "調高": ("estimate_up", +1),
    "漲價": ("price_hike", +1),
    "調漲": ("price_hike", +1),
    "接單暢旺": ("strong_orders", +1),
    "急單": ("strong_orders", +1),
    "營收創": ("record_revenue", +1),
    "創新高": ("record_high", +1),
    "轉盈": ("turnaround", +1),
    "買超": ("institutional_buy", +1),
    "庫存回補": ("restocking", +1),
    "調降目標價": ("target_price_down", -1),
    "下修": ("estimate_down", -1),
    "調降": ("estimate_down", -1),
    "跌價": ("price_cut", -1),
    "砍單": ("order_cut", -1),
    "抽單": ("order_cut", -1),
    "減產": ("production_cut", -1),
    "匯損": ("fx_loss", -1),
    "賣超": ("institutional_sell", -1),
    "衰退": ("decline", -1),
    "虧損": ("loss", -1),
    "停工": ("halt", -1),
    "火災": ("accident", -1),
    "去化不順": ("inventory_glut", -1),
    "庫存調整": ("inventory_correction", -1),
}

RECENCY_HALF_LIFE_DAYS = 7.0
MAX_ITEMS_FOR_JUDGEMENT = 20


def extract_events(item: NewsItem) -> list[tuple[str, int]]:
    """從單則新聞抽取 (event_type, polarity) 清單。

    「調降目標價」等長詞優先於「調降」，避免重複計分。
    """
    text = item.text
    events = []
    matched_spans: list[str] = []
    for kw in sorted(EVENT_LEXICON, key=len, reverse=True):
        if kw in text and not any(kw in m for m in matched_spans):
            events.append(EVENT_LEXICON[kw])
            matched_spans.append(kw)
    return events


class NewsAgent(BaseAgent):
    agent_id = "news_agent"

    def __init__(
        self,
        news_provider: NewsProvider,
        llm: LLMClient | None = None,
        window_days: int = 14,
        horizon_days: int = 20,
        ticker_names: dict[str, str] | None = None,
    ):
        self.provider = news_provider
        self.llm = llm or LLMClient(enabled=False)
        self.window_days = window_days
        self.default_horizon_days = horizon_days
        self.ticker_names = ticker_names or {}

    def _retrieve(self, items: list[NewsItem], ticker: str) -> list[NewsItem]:
        """新聞量過大時，用向量檢索挑出與營運最相關的 top-k（RAG）。"""
        if len(items) <= MAX_ITEMS_FOR_JUDGEMENT:
            return items
        store = SimpleVectorStore()
        store.add([str(i) for i in range(len(items))], [it.text for it in items])
        name = self.ticker_names.get(ticker, ticker)
        query = f"{name} 營收 訂單 產能 展望 目標價 財報"
        hits = store.query(query, k=MAX_ITEMS_FOR_JUDGEMENT)
        return [items[int(h["id"])] for h in hits]

    def rule_based_judgement(
        self, items: list[NewsItem], as_of_date: str
    ) -> tuple[str, float, str, float, list[dict]]:
        """回傳 (signal, confidence, rationale, score, event_log)。"""
        as_of = pd.Timestamp(as_of_date)
        weighted_sum = 0.0
        weight_total = 0.0
        event_log: list[dict] = []

        for it in items:
            events = extract_events(it)
            if not events:
                continue
            age_days = max((as_of - pd.Timestamp(it.published)).days, 0)
            recency = math.pow(0.5, age_days / RECENCY_HALF_LIFE_DAYS)
            for event_type, polarity in events:
                w = it.source_tier * recency
                weighted_sum += w * polarity
                weight_total += w
                event_log.append(
                    {
                        "event_type": event_type,
                        "polarity": polarity,
                        "source_tier": it.source_tier,
                        "recency_weight": round(recency, 3),
                        "title": it.title[:50],
                    }
                )

        if weight_total == 0:
            return "neutral", 0.2, f"近{self.window_days}天無可判讀的新聞事件", 0.0, event_log

        score = weighted_sum / weight_total  # ∈ [-1, 1]
        signal = "bullish" if score > 0.15 else "bearish" if score < -0.15 else "neutral"

        # confidence：事件數量、平均來源可信度、方向一致性共同決定（規格 3.3：
        # 來源可信度必須反映在 confidence）
        avg_tier = float(np.mean([e["source_tier"] for e in event_log]))
        n_events = len(event_log)
        confidence = (0.25 + 0.1 * math.log2(1 + n_events) + 0.3 * abs(score)) * (0.5 + 0.5 * avg_tier)
        confidence = float(np.clip(confidence, 0.05, 0.95))

        top_types = {}
        for e in event_log:
            top_types[e["event_type"]] = top_types.get(e["event_type"], 0) + 1
        summary = "、".join(f"{t}×{c}" for t, c in sorted(top_types.items(), key=lambda x: -x[1])[:4])
        rationale = f"近{self.window_days}天{n_events}個事件（{summary}），加權情緒{score:+.2f}，平均來源可信度{avg_tier:.2f}"
        return signal, confidence, rationale, score, event_log

    def analyze(self, ticker: str, as_of_date: str) -> AgentOutput:
        start = (pd.Timestamp(as_of_date) - pd.Timedelta(days=self.window_days)).strftime("%Y-%m-%d")
        items = self.provider.get_news(ticker, start, as_of_date)
        items = self._retrieve(items, ticker)

        signal, confidence, rationale, score, event_log = self.rule_based_judgement(items, as_of_date)
        evidence = [it.url or it.title[:60] for it in items[:10]]

        if self.llm.available and items:
            lines = [
                f"- [{it.published:%Y-%m-%d}] (可信度{it.source_tier}) {it.title}：{it.summary[:100]}"
                for it in items
            ]
            user_prompt = (
                f"股票：{ticker}（{self.ticker_names.get(ticker, '')}），判斷基準日：{as_of_date}\n\n"
                f"近{self.window_days}天新聞：\n" + "\n".join(lines)
            )
            llm_result = self.llm.judge(
                SYSTEM_PROMPT.format(horizon=self.default_horizon_days), user_prompt
            )
            if llm_result:
                signal = llm_result["signal"]
                confidence = llm_result["confidence"]
                rationale = llm_result["rationale"]

        return self._build_output(
            ticker=ticker,
            as_of_date=as_of_date,
            signal=signal,
            confidence=confidence,
            rationale=rationale,
            evidence_refs=evidence,
            raw_features={
                "n_news": len(items),
                "rule_score": score,
                "events": event_log[:20],
                "llm_used": self.llm.available and bool(items),
            },
        )
