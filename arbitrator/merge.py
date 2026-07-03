"""精度加權合併公式（規格 5.2，強制介面）。

final_score = Σ(precision_i * confidence_i * s_i) / Σ(precision_i * confidence_i)

- s ∈ {-1, 0, +1} 對應 bearish/neutral/bullish
- final_score > 0.3 → bullish；< -0.3 → bearish；否則 neutral
- uncertainty = 1 - (max_precision_i / Σ precision_i)（規格 MVP 簡化版）
  注意：規格 5.2 的文字敘述與公式方向相反——依公式，precision 越集中在
  單一 Agent，uncertainty 越低（區間越窄），這與同節前句「precision 越
  集中在少數高權重 Agent，區間應越窄」一致，故以公式為準。
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

from agents.base import AgentOutput

BULLISH_THRESHOLD = 0.3
BEARISH_THRESHOLD = -0.3


@dataclass
class MergedThesis:
    """仲裁層輸出：投資論點 + 不確定性 + evidence trace（規格第 2 節架構圖）。"""

    ticker: str
    as_of_date: str
    signal: str
    final_score: float
    uncertainty: float
    # 供系統層級 Brier 評估的合併機率：以規格 5.2 的同一組權重
    # w_i = precision_i * confidence_i，對各 Agent 的規格 6.1 機率
    # p_i（bullish→conf、bearish→1-conf、neutral→0.5）做線性意見池：
    # p = Σ(w_i * p_i) / Σ(w_i)
    probability_bullish: float
    horizon_days: int
    contributions: list[dict[str, Any]] = field(default_factory=list)  # evidence trace

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def score_to_signal(
    final_score: float,
    bullish_threshold: float = BULLISH_THRESHOLD,
    bearish_threshold: float = BEARISH_THRESHOLD,
) -> str:
    if final_score > bullish_threshold:
        return "bullish"
    if final_score < bearish_threshold:
        return "bearish"
    return "neutral"


def merge(
    outputs: list[AgentOutput],
    precisions: dict[str, float],
    bullish_threshold: float = BULLISH_THRESHOLD,
    bearish_threshold: float = BEARISH_THRESHOLD,
) -> MergedThesis:
    """合併 N 個 Agent 對同一 ticker 的判斷（規格 5.2）。

    precisions: agent_id -> 有效精度（呼叫端應先經 PrecisionTracker
    套用冷啟動規則）。簡單平均 baseline 只需傳入全為相同值的 precisions。
    """
    if not outputs:
        raise ValueError("至少需要一個 Agent 輸出")
    tickers = {o.ticker for o in outputs}
    dates = {o.as_of_date for o in outputs}
    if len(tickers) != 1 or len(dates) != 1:
        raise ValueError(f"所有輸出必須是同一 ticker 與 as_of_date，收到 {tickers} / {dates}")

    missing = [o.agent_id for o in outputs if o.agent_id not in precisions]
    if missing:
        raise KeyError(f"缺少精度值的 agent: {missing}")

    num = 0.0
    denom = 0.0
    prob_num = 0.0
    for o in outputs:
        w = precisions[o.agent_id] * o.confidence
        num += w * o.score
        denom += w
        # 規格 6.1 的個別機率：bullish→conf、bearish→1-conf、neutral→0.5
        p_i = o.confidence if o.signal == "bullish" else (1 - o.confidence) if o.signal == "bearish" else 0.5
        prob_num += w * p_i

    final_score = num / denom if denom > 0 else 0.0
    probability_bullish = prob_num / denom if denom > 0 else 0.5
    signal = score_to_signal(final_score, bullish_threshold, bearish_threshold)

    prec_sum = sum(precisions[o.agent_id] for o in outputs)
    if denom > 0 and prec_sum > 0:
        uncertainty = 1.0 - max(precisions[o.agent_id] for o in outputs) / prec_sum
    else:
        uncertainty = 1.0  # 無有效權重時完全不確定

    weight_total = denom if denom > 0 else 1.0
    contributions = [
        {
            "agent_id": o.agent_id,
            "signal": o.signal,
            "confidence": o.confidence,
            "precision": precisions[o.agent_id],
            "weight_share": (precisions[o.agent_id] * o.confidence) / weight_total,
            "rationale": o.rationale,
            "evidence_refs": o.evidence_refs,
        }
        for o in outputs
    ]

    return MergedThesis(
        ticker=outputs[0].ticker,
        as_of_date=outputs[0].as_of_date,
        signal=signal,
        final_score=final_score,
        uncertainty=uncertainty,
        probability_bullish=probability_bullish,
        horizon_days=max(o.horizon_days for o in outputs),
        contributions=contributions,
    )
