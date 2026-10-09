"""供應鏈 Agent（規格 3.4，Phase 2）。

依據：經濟關聯公司之間的報酬可預測性——市場對上下游消息的反應有遲滯，
下游客戶的股價動能會領先供應商（Cohen & Frazzini 2008, "Economic Links and
Predictable Returns"）；產業龍頭的動能亦領先同業。

知識圖譜：config/supply_chain_graph.json（手動整理）。被動元件廠的實際客戶
名單未公開，downstream 節點是下游終端市場的代表性公司（需求代理），不是已確認
的直接客戶；權重為人工假設，未經回測最佳化。

特徵（近 window 個交易日，皆相對大盤）：
- 下游需求代理的超額報酬（%，依邊權重加權）：下游走強 → 偏多
- 下游需求代理的最新月營收年增率（%，依邊權重加權）：下游營收成長 → 偏多
- 龍頭 / 同集團公司的超額報酬（%）：龍頭走強 → 偏多

規則式評分與其他 Agent 共用（agents/base.py:score_components）；LLM 可用時改由
LLM 判讀（規格 3.4：推論上下游事件對目標個股的傳導效應與時間遞延）。
注意：大盤以加權指數（未含息）計算，超額報酬略為高估（約每 20 日 0.2 個百分點）。
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from agents.base import OUTPUT_MODES, AgentOutput, BaseAgent, continuous_judgement, describe_features, score_components
from agents.llm_client import LLMClient
from data.fetch_supply_chain import MARKET_INDEX, SupplyChainDataProvider, load_graph, market_index_for

SYSTEM_PROMPT = """你是台股產業鏈分析師，專長是上下游傳導。根據提供的供應鏈特徵（下游需求代理公司的股價動能與營收成長、產業龍頭的股價動能），判斷這家被動元件公司未來 {horizon} 個交易日的方向。

背景：市場對上下游消息的反應常有遲滯，下游需求變化通常會在之後傳導到上游零組件供應商。請說明傳導路徑與可能的時間遞延。

只回傳 JSON（不要其他文字）：
{{"signal": "bullish|bearish|neutral", "confidence": 0.0-1.0, "rationale": "繁體中文，200字以內"}}"""

# (特徵名, 顯示名稱, 強訊號門檻)：分量 = clip(特徵 / 門檻, -1, 1)
SCALES = [
    ("downstream_excess_ret_pct", "下游動能", 10.0),
    ("downstream_revenue_yoy_pct", "下游營收", 30.0),
    ("leader_excess_ret_pct", "龍頭動能", 10.0),
]

FEATURE_LABELS = {
    "downstream_excess_ret_pct": "下游需求代理公司的加權超額報酬（%，台股相對加權指數、美股相對 S&P 500，正值 = 跑贏大盤）",
    "downstream_revenue_yoy_pct": "下游需求代理公司的加權最新月營收年增率（%）",
    "leader_excess_ret_pct": "產業龍頭／同集團公司的超額報酬（%，相對大盤）",
}


def _window_return(closes: pd.Series, window: int) -> float | None:
    s = closes.dropna()
    if len(s) <= window:
        return None
    prev = float(s.iloc[-1 - window])
    return (float(s.iloc[-1]) / prev - 1.0) * 100.0 if prev > 0 else None


def _weighted_mean(pairs: list[tuple[float, float]]) -> float | None:
    """[(值, 權重)] 的加權平均；值為 None 的項目略過。"""
    valid = [(v, w) for v, w in pairs if v is not None]
    total = sum(w for _, w in valid)
    return sum(v * w for v, w in valid) / total if total > 0 else None


class SupplyChainAgent(BaseAgent):
    agent_id = "supply_chain_agent"

    def __init__(
        self,
        data_provider: SupplyChainDataProvider,
        graph: dict | None = None,
        llm: LLMClient | None = None,
        horizon_days: int = 20,
        window_days: int = 20,
        output_mode: str = "threshold",
    ):
        if output_mode not in OUTPUT_MODES:
            raise ValueError(f"output_mode 必須是 {OUTPUT_MODES}，收到 {output_mode!r}")
        self.output_mode = output_mode
        self.provider = data_provider
        self.graph = graph if graph is not None else load_graph()
        self.llm = llm or LLMClient(enabled=False)
        self.default_horizon_days = horizon_days
        self.window = window_days

    def _excess_return(self, ticker: str, as_of_date: str, markets: dict[str, float | None]) -> float | None:
        """相對各自市場的超額報酬：台股對加權指數、美股（.US）對 SPY。"""
        r = _window_return(self.provider.get_closes(ticker, as_of_date), self.window)
        market = markets.get(market_index_for(ticker))
        return r - market if r is not None and market is not None else None

    def _revenue_yoy(self, ticker: str, as_of_date: str) -> float | None:
        rev = self.provider.get_monthly_revenue(ticker, as_of_date)
        if len(rev) < 13:
            return None
        r = rev["revenue"].astype(float)
        return (float(r.iloc[-1]) / float(r.iloc[-13]) - 1.0) * 100.0 if float(r.iloc[-13]) > 0 else None

    # ---------- 特徵計算 ----------

    def compute_features(self, ticker: str, as_of_date: str) -> dict:
        edges = self.graph.get("edges", {}).get(ticker, [])
        markets = {
            index: _window_return(self.provider.get_closes(index, as_of_date), self.window)
            for index in {market_index_for(e["to"]) for e in edges} | {MARKET_INDEX}
        }
        downstream = [e for e in edges if e["relation"] == "downstream"]
        leaders = [e for e in edges if e["relation"] in ("leader", "group")]
        feats = {
            "downstream_excess_ret_pct": _weighted_mean(
                [(self._excess_return(e["to"], as_of_date, markets), float(e["weight"])) for e in downstream]
            ),
            "downstream_revenue_yoy_pct": _weighted_mean(
                [(self._revenue_yoy(e["to"], as_of_date), float(e["weight"])) for e in downstream]
            ),
            "leader_excess_ret_pct": _weighted_mean(
                [(self._excess_return(e["to"], as_of_date, markets), float(e["weight"])) for e in leaders]
            ),
        }
        return {k: v for k, v in feats.items() if v is not None and not (isinstance(v, float) and math.isnan(v))}

    # ---------- 規則式判斷 ----------

    @staticmethod
    def rule_based_judgement(feats: dict) -> tuple[str, float, str, float]:
        """回傳 (signal, confidence, rationale, score)。score ∈ [-1, 1]。"""
        components = [
            (label, float(np.clip(feats[key] / scale, -1, 1))) for key, label, scale in SCALES if key in feats
        ]
        if not components:
            return "neutral", 0.2, "知識圖譜中無可用的關聯公司資料", 0.0
        signal, confidence, score, conflict, parts = score_components(components, n_total=len(SCALES))
        rationale = "供應鏈傳導：" + parts
        if conflict:
            rationale += "；正負訊號矛盾，降低信心"
        return signal, confidence, rationale, score

    # ---------- 主流程 ----------

    def analyze(self, ticker: str, as_of_date: str) -> AgentOutput:
        feats = self.compute_features(ticker, as_of_date)
        signal, confidence, rationale, score = self.rule_based_judgement(feats)
        coverage = sum(1 for key, _, _ in SCALES if key in feats) / len(SCALES)
        if self.output_mode == "continuous":
            signal, confidence, p = continuous_judgement(score, coverage)
            rationale = f"{rationale}（連續輸出：分數 {score:+.2f}、資料覆蓋 {coverage:.0%}，看多機率 {p:.2f}）"
        edges = self.graph.get("edges", {}).get(ticker, [])
        evidence = [f"graph:{ticker}->{e['to']}({e['relation']})" for e in edges]

        llm_result = None
        if self.llm.available and feats:
            proxies = self.graph.get("proxies", {})
            relations = "\n".join(
                f"- {e['to']} {proxies.get(e['to'], {}).get('name', '')}"
                f"（{ {'downstream': '下游需求代理', 'leader': '產業龍頭', 'group': '同集團'}[e['relation']] }，權重 {e['weight']}）"
                for e in edges
            )
            user_prompt = (
                f"股票：{ticker}，判斷基準日：{as_of_date}\n\n"
                f"供應鏈關聯：\n{relations}\n\n"
                f"特徵（近 {self.window} 個交易日）：\n{describe_features(feats, FEATURE_LABELS)}"
            )
            llm_result = self.llm.judge(SYSTEM_PROMPT.format(horizon=self.default_horizon_days), user_prompt)
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
            raw_features={**feats, "rule_score": score, "evidence": coverage, "output_mode": self.output_mode,
                          "llm_used": llm_result is not None},
        )
