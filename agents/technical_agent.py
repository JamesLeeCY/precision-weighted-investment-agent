"""技術面 Agent：K 線、移動平均線、成交量、支撐與壓力。

指標定義見 data/fetch_technical.py；只用預測日之前的含息還原日 K，無前視。
規則評分與財報 Agent 相同（score_components 取 5 個分量平均；連續模式 p = σ(ln3 · score · 覆蓋率)）。
"""
from __future__ import annotations

from agents.base import OUTPUT_MODES, AgentOutput, BaseAgent, continuous_judgement, score_components
from data.fetch_technical import INDICATOR_COLUMNS, FinMindTechnicalProvider, technical_components


class TechnicalAgent(BaseAgent):
    agent_id = "technical_agent"

    def __init__(self, provider: FinMindTechnicalProvider, horizon_days: int = 20, output_mode: str = "threshold"):
        if output_mode not in OUTPUT_MODES:
            raise ValueError(f"output_mode 必須是 {OUTPUT_MODES}，收到 {output_mode!r}")
        self.provider = provider
        self.default_horizon_days = horizon_days
        self.output_mode = output_mode

    @staticmethod
    def judge(row: dict) -> tuple[str, float, str, float, float]:
        """回傳 (signal, confidence, rationale, score, coverage)。"""
        comps = technical_components(row)
        if not comps:
            return "neutral", 0.2, "無足夠價量資料可供判斷", 0.0, 0.0
        signal, confidence, score, conflict, parts = score_components(comps, n_total=len(INDICATOR_COLUMNS))
        rationale = "技術面：" + parts + ("；正負訊號矛盾，降低信心" if conflict else "")
        return signal, confidence, rationale, score, len(comps) / len(INDICATOR_COLUMNS)

    def analyze(self, ticker: str, as_of_date: str) -> AgentOutput:
        row = self.provider.latest_before(ticker, as_of_date)
        signal, confidence, rationale, score, coverage = self.judge(row)
        if self.output_mode == "continuous":
            signal, confidence, p = continuous_judgement(score, coverage)
            rationale = f"{rationale}（連續輸出：分數 {score:+.2f}、資料覆蓋 {coverage:.0%}，看多機率 {p:.2f}）"
        feats = {k: float(row[k]) for k in ("trend", "ma_spread", "vol_price", "breakout", "candle", "ma20", "ma60")
                 if k in row and row[k] == row[k]}
        return self._build_output(
            ticker=ticker, as_of_date=as_of_date, signal=signal, confidence=confidence, rationale=rationale,
            evidence_refs=[f"finmind:daily_price:{ticker}"],
            raw_features={**feats, "rule_score": score, "evidence": coverage, "output_mode": self.output_mode,
                          "llm_used": False},
        )
