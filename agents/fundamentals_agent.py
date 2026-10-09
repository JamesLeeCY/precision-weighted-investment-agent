"""財報 Agent（規格 3.2，MVP 必做）。

流程：
1. 由 FundamentalsDataProvider 取得 as_of_date 以前的月營收與季度財務資料
2. 計算特徵：營收 YoY/MoM、營收 YoY 近 4 期斜率、毛利率近 4 季斜率、
   存貨週轉天數 / 應收帳款天數之 YoY 變化
3. 規則式評分 → signal / confidence / rationale（永遠可用的 fallback）
4. 若 LLM 可用，將數字特徵（與可選的管理層敘述摘要）送入 LLM，
   prompt 明確要求區分「營運數字訊號」與「管理層敘述訊號」，
   兩者矛盾時需在 rationale 說明並降低 confidence（規格 3.2 prompt 要求）
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from agents.base import OUTPUT_MODES, AgentOutput, BaseAgent, continuous_judgement, describe_features, score_components
from agents.llm_client import LLMClient
from data.fetch_financials import FundamentalsDataProvider

SYSTEM_PROMPT = """你是台股基本面分析師。根據提供的財務特徵與管理層敘述，判斷該股票未來 {horizon} 個交易日的方向。

必須區分兩類訊號並分別評估：
1. 營運數字顯示的訊號（營收成長、毛利率趨勢、存貨/應收天數變化）
2. 管理層敘述顯示的訊號（法說會逐字稿摘要，若有提供）

若兩者矛盾，必須在 rationale 中明確說明矛盾點，並降低 confidence。

只回傳 JSON（不要其他文字）：
{{"signal": "bullish|bearish|neutral", "confidence": 0.0-1.0, "rationale": "繁體中文，200字以內"}}"""


FEATURE_LABELS = {
    "revenue_yoy_pct": "最新月營收年增率（%）",
    "revenue_mom_pct": "最新月營收月增率（%）",
    "revenue_yoy_slope": "近 4 個月營收年增率的變化斜率（百分點/月，正值 = 成長加速）",
    "gross_margin_pct": "最新一季毛利率（%）",
    "gross_margin_slope": "近 4 季毛利率變化斜率（百分點/季）",
    "inventory_days": "最新一季存貨週轉天數（天）",
    "inventory_days_yoy_pct": "存貨週轉天數年增率（%，正值 = 存貨去化變慢）",
    "receivable_days": "最新一季應收帳款天數（天）",
    "receivable_days_yoy_pct": "應收帳款天數年增率（%，正值 = 收款變慢）",
}


# 規則評分使用的 5 個分量（資料覆蓋率 = 有值的分量數 / 5）
COMPONENT_KEYS = (
    "revenue_yoy_pct", "revenue_yoy_slope", "gross_margin_slope", "inventory_days_yoy_pct", "receivable_days_yoy_pct",
)


def _slope(values: pd.Series) -> float | None:
    """對最近數期的值做一階線性回歸斜率（每期變化量）。"""
    v = pd.Series(values).dropna().astype(float)
    if len(v) < 2:
        return None
    x = np.arange(len(v), dtype=float)
    return float(np.polyfit(x, v.to_numpy(), 1)[0])


class FundamentalsAgent(BaseAgent):
    agent_id = "fundamentals_agent"

    def __init__(
        self,
        data_provider: FundamentalsDataProvider,
        llm: LLMClient | None = None,
        horizon_days: int = 20,
        transcript_provider=None,
        output_mode: str = "threshold",
    ):
        if output_mode not in OUTPUT_MODES:
            raise ValueError(f"output_mode 必須是 {OUTPUT_MODES}，收到 {output_mode!r}")
        self.output_mode = output_mode
        self.provider = data_provider
        self.llm = llm or LLMClient(enabled=False)
        self.default_horizon_days = horizon_days
        # 可選：callable(ticker, as_of_date) -> str，提供法說會逐字稿摘要
        self.transcript_provider = transcript_provider

    # ---------- 特徵計算 ----------

    def compute_features(self, ticker: str, as_of_date: str) -> dict:
        feats: dict = {}
        rev = self.provider.get_monthly_revenue(ticker, as_of_date)
        if len(rev) >= 13:
            r = rev.set_index("date")["revenue"].astype(float)
            feats["revenue_yoy_pct"] = (r.iloc[-1] / r.iloc[-13] - 1.0) * 100.0
            feats["revenue_mom_pct"] = (r.iloc[-1] / r.iloc[-2] - 1.0) * 100.0
            # 近 4 期 YoY 的斜率（動能是否加速），單位：百分點/月
            yoy = (r / r.shift(12) - 1.0) * 100.0
            feats["revenue_yoy_slope"] = _slope(yoy.tail(4))

        fin = self.provider.get_quarterly_financials(ticker, as_of_date)
        if len(fin) >= 1:
            gm = fin["gross_margin"].dropna()
            if len(gm) >= 1:
                feats["gross_margin_pct"] = float(gm.iloc[-1])
            if len(gm) >= 2:
                # 近 4 季毛利率斜率，單位：百分點/季
                feats["gross_margin_slope"] = _slope(gm.tail(4))
            for col, name in (("inventory_days", "inventory_days"), ("receivable_days", "receivable_days")):
                series = fin[col].dropna()
                if len(series) >= 1:
                    feats[name] = float(series.iloc[-1])
                if len(series) >= 5:
                    prev = float(series.iloc[-5])  # 去年同季
                    if prev > 0:
                        feats[f"{name}_yoy_pct"] = (float(series.iloc[-1]) / prev - 1.0) * 100.0
        return {k: v for k, v in feats.items() if v is not None and not (isinstance(v, float) and math.isnan(v))}

    # ---------- 規則式判斷（fallback，亦作為特徵完整度的 confidence 基礎） ----------

    @staticmethod
    def rule_based_judgement(feats: dict) -> tuple[str, float, str, float]:
        """回傳 (signal, confidence, rationale, score)。score ∈ [-1, 1]。"""
        components: list[tuple[str, float]] = []

        yoy = feats.get("revenue_yoy_pct")
        if yoy is not None:
            components.append(("營收YoY", float(np.clip(yoy / 30.0, -1, 1))))
        slope = feats.get("revenue_yoy_slope")
        if slope is not None:
            components.append(("營收動能", float(np.clip(slope / 10.0, -1, 1))))
        gm_slope = feats.get("gross_margin_slope")
        if gm_slope is not None:
            components.append(("毛利率趨勢", float(np.clip(gm_slope / 2.0, -1, 1))))
        inv = feats.get("inventory_days_yoy_pct")
        if inv is not None:
            # 存貨天數 YoY 上升為負面訊號
            components.append(("存貨天數", float(np.clip(-inv / 30.0, -1, 1))))
        ar = feats.get("receivable_days_yoy_pct")
        if ar is not None:
            components.append(("應收天數", float(np.clip(-ar / 30.0, -1, 1))))

        if not components:
            return "neutral", 0.2, "無足夠財務資料可供判斷", 0.0

        # 訊號內部矛盾（同時有強正與強負分量）時降低信心
        signal, confidence, score, conflict, parts = score_components(components, n_total=5)
        rationale = "營運數字：" + parts
        if conflict:
            rationale += "；正負訊號矛盾，降低信心"
        return signal, confidence, rationale, score

    # ---------- 主流程 ----------

    def analyze(self, ticker: str, as_of_date: str) -> AgentOutput:
        feats = self.compute_features(ticker, as_of_date)
        signal, confidence, rationale, score = self.rule_based_judgement(feats)
        coverage = sum(k in feats for k in COMPONENT_KEYS) / len(COMPONENT_KEYS)
        if self.output_mode == "continuous":
            signal, confidence, p = continuous_judgement(score, coverage)
            rationale = f"{rationale}（連續輸出：分數 {score:+.2f}、資料覆蓋 {coverage:.0%}，看多機率 {p:.2f}）"
        evidence = [f"finmind:monthly_revenue:{ticker}", f"finmind:financial_statements:{ticker}"]

        transcript = ""
        if self.transcript_provider is not None:
            transcript = self.transcript_provider(ticker, as_of_date) or ""
            if transcript:
                evidence.append(f"transcript:{ticker}:{as_of_date}")

        llm_result = None
        if self.llm.available and feats:
            user_prompt = (
                f"股票：{ticker}，判斷基準日：{as_of_date}\n\n"
                f"營運數字特徵：\n{describe_features(feats, FEATURE_LABELS)}\n\n"
                f"管理層敘述（法說會摘要）：\n{transcript or '（本次無逐字稿資料）'}"
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
            raw_features={**feats, "rule_score": score, "evidence": coverage, "output_mode": self.output_mode,
                          "llm_used": llm_result is not None},
        )
