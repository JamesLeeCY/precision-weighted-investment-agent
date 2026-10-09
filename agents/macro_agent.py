"""總經/籌碼 Agent（規格 3.5，Phase 2）。

流程：
1. 由 MacroDataProvider 取得 as_of_date 以前的籌碼與總經序列
2. 計算特徵（每項皆為近 window 個交易日的變化，總經利率用較長窗口）：
   籌碼（個股）
   - 外資持股比變化（百分點）：外資加碼 → 偏多
   - 投信淨買超佔發行股數（%）：投信認養 → 偏多
   - 融資餘額變化（%）：散戶追價、籌碼凌亂 → 反向，偏空
   總經（全市場，同一時點各檔相同）
   - 美元兌台幣變化（%）：台幣貶值有利被動元件出口 → 偏多
   - 美 10 年債殖利率變化（bp）：利率上行壓抑科技股評價 → 偏空
   - 全市場外資淨買超（億元）：資金流入台股 → 偏多
3. 規則式評分 → signal / confidence / rationale（與財報 Agent 同一套評分）
4. 若 LLM 可用，將特徵送入 LLM 產出判斷（規格 3.5：之後再視需要加入 LLM 解讀層）

各分量以 clip(x / scale, -1, 1) 轉換，scale 是「視為強訊號」的變化量，
屬經驗設定（見 SCALES），未經最佳化以避免過度擬合回測期間。
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from agents.base import OUTPUT_MODES, AgentOutput, BaseAgent, continuous_judgement, describe_features, score_components
from agents.llm_client import LLMClient
from data.fetch_macro import MacroDataProvider

SYSTEM_PROMPT = """你是台股籌碼與總經分析師。根據提供的籌碼特徵（外資持股、投信買賣超、融資餘額）與總經特徵（匯率、美債殖利率、全市場外資動向），判斷該股票未來 {horizon} 個交易日的方向。

注意：融資餘額大增通常代表散戶追價，屬反向指標；總經特徵對同族群個股的影響相近，個股差異主要來自籌碼面。

只回傳 JSON（不要其他文字）：
{{"signal": "bullish|bearish|neutral", "confidence": 0.0-1.0, "rationale": "繁體中文，200字以內"}}"""

# (特徵名, 顯示名稱, 強訊號門檻, 方向)：分量 = clip(方向 × 特徵 / 門檻, -1, 1)
SCALES = [
    ("foreign_ratio_chg_pp", "外資持股", 2.0, 1),
    ("trust_net_pct_shares", "投信買超", 0.5, 1),
    ("margin_balance_chg_pct", "融資餘額", 20.0, -1),
    ("usd_twd_chg_pct", "台幣匯率", 2.0, 1),
    ("us10y_chg_bp", "美債殖利率", 50.0, -1),
    ("market_foreign_net_e8", "外資大盤", 1000.0, 1),
]


FEATURE_LABELS = {
    "foreign_ratio_chg_pp": "外資持股比例變化（百分點，正值 = 外資持股增加）",
    "trust_net_pct_shares": "投信累計淨買超佔發行股數（%，正值 = 淨買進）",
    "margin_balance_chg_pct": "融資餘額變化（%，正值 = 融資增加）",
    "usd_twd_chg_pct": "美元兌台幣匯率變化（%，正值 = 美元升值、台幣貶值）",
    "us10y_chg_bp": "美國 10 年期公債殖利率變化（基點，正值 = 殖利率上升）",
    "market_foreign_net_e8": "全市場外資累計淨買超（億元，正值 = 淨買進）",
}


def _change(series: pd.Series, window: int, pct: bool) -> float | None:
    """最後一筆相對 window 筆之前的變化；資料不足回傳 None。"""
    s = pd.Series(series).dropna().astype(float)
    if len(s) <= window:
        return None
    prev, last = float(s.iloc[-1 - window]), float(s.iloc[-1])
    if pct:
        return (last / prev - 1.0) * 100.0 if prev > 0 else None
    return last - prev


class MacroAgent(BaseAgent):
    agent_id = "macro_agent"

    def __init__(
        self,
        data_provider: MacroDataProvider,
        llm: LLMClient | None = None,
        horizon_days: int = 20,
        window_days: int = 20,
        rate_window_days: int = 60,
        output_mode: str = "threshold",
    ):
        if output_mode not in OUTPUT_MODES:
            raise ValueError(f"output_mode 必須是 {OUTPUT_MODES}，收到 {output_mode!r}")
        self.output_mode = output_mode
        self.provider = data_provider
        self.llm = llm or LLMClient(enabled=False)
        self.default_horizon_days = horizon_days
        self.window = window_days
        self.rate_window = rate_window_days

    # ---------- 特徵計算 ----------

    def compute_features(self, ticker: str, as_of_date: str) -> dict:
        w = self.window
        feats: dict = {}

        holding = self.provider.get_shareholding(ticker, as_of_date)
        if not holding.empty:
            feats["foreign_ratio_chg_pp"] = _change(holding["foreign_ratio_pct"], w, pct=False)

        inst = self.provider.get_institutional_net(ticker, as_of_date)
        if len(inst) >= w and not holding.empty:
            shares = float(holding["shares_issued"].iloc[-1])
            if shares > 0:
                feats["trust_net_pct_shares"] = float(inst["trust_net"].tail(w).sum()) / shares * 100.0

        margin = self.provider.get_margin_balance(ticker, as_of_date)
        if not margin.empty:
            feats["margin_balance_chg_pct"] = _change(margin["margin_balance"], w, pct=True)

        fx = self.provider.get_usd_twd(as_of_date)
        if not fx.empty:
            feats["usd_twd_chg_pct"] = _change(fx["rate"], w, pct=True)

        rates = self.provider.get_us10y(as_of_date)
        if not rates.empty:
            chg = _change(rates["yield_pct"], self.rate_window, pct=False)
            feats["us10y_chg_bp"] = chg * 100.0 if chg is not None else None

        mkt = self.provider.get_market_foreign_net(as_of_date)
        if len(mkt) >= w:
            feats["market_foreign_net_e8"] = float(mkt["foreign_net"].tail(w).sum()) / 1e8

        return {k: v for k, v in feats.items() if v is not None and not (isinstance(v, float) and math.isnan(v))}

    # ---------- 規則式判斷 ----------

    @staticmethod
    def rule_based_judgement(feats: dict) -> tuple[str, float, str, float]:
        """回傳 (signal, confidence, rationale, score)。score ∈ [-1, 1]。"""
        components = [
            (label, float(np.clip(sign * feats[key] / scale, -1, 1)))
            for key, label, scale, sign in SCALES
            if key in feats
        ]
        if not components:
            return "neutral", 0.2, "無足夠籌碼/總經資料可供判斷", 0.0

        signal, confidence, score, conflict, parts = score_components(components, n_total=len(SCALES))
        rationale = "籌碼與總經：" + parts
        if conflict:
            rationale += "；正負訊號矛盾，降低信心"
        return signal, confidence, rationale, score

    # ---------- 主流程 ----------

    def analyze(self, ticker: str, as_of_date: str) -> AgentOutput:
        feats = self.compute_features(ticker, as_of_date)
        signal, confidence, rationale, score = self.rule_based_judgement(feats)
        coverage = sum(1 for key, _, _, _ in SCALES if key in feats) / len(SCALES)
        if self.output_mode == "continuous":
            signal, confidence, p = continuous_judgement(score, coverage)
            rationale = f"{rationale}（連續輸出：分數 {score:+.2f}、資料覆蓋 {coverage:.0%}，看多機率 {p:.2f}）"
        evidence = [
            f"finmind:institutional_investors:{ticker}",
            f"finmind:shareholding:{ticker}",
            f"finmind:margin_purchase:{ticker}",
            "finmind:exchange_rate:USD",
            "finmind:government_bonds_yield:US10Y",
            "finmind:total_institutional_investors",
        ]

        llm_result = None
        if self.llm.available and feats:
            user_prompt = (
                f"股票：{ticker}，判斷基準日：{as_of_date}\n\n"
                f"特徵（近 {self.window} 個交易日的累計或變化；美債為近 {self.rate_window} 個交易日）：\n"
                f"{describe_features(feats, FEATURE_LABELS)}"
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
