"""精度加權合併公式（規格 5.2，2026-10-07 修訂）。

修訂後（使用者決策 2026-10-07）：
    κ_i = |2·p_i − 1|          確信度；p_i 為規格 6.1 機率
                                （bullish→conf、bearish→1−conf、neutral→0.5）
    final_score = Σ(precision_i · κ_i · s_i) / Σ(precision_i)
                = 2·p − 1，p = Σ(precision_i · p_i) / Σ(precision_i)
- s ∈ {-1, 0, +1} 對應 bearish/neutral/bullish
- final_score > 0.1 → bullish；< -0.1 → bearish；否則 neutral
  （等同合併機率 > 0.55 / < 0.45，門檻事先設定、不依回測調整）

修訂原因：原公式 Σ(precision·confidence·s)/Σ(precision·confidence) 以 confidence
為投票權重，而有方向的訊號 confidence 下限 0.5，因此「毫無把握」（confidence
0.5、p = 0.5）的 Agent 仍以 0.5 的權重投票；Agent 層級校準把某 Agent 收縮到
p' = 0.5 後，它仍持續左右合併訊號。改用確信度 κ 後，p = 0.5 的 Agent 不投票；
分母用 Σprecision（而非 Σprecision·κ），避免只有一個 Agent 表態時極小的確信度
也被放大成 ±1。修訂後訊號與合併機率完全一致（final_score = 2p − 1）。

- uncertainty = 1 - (max_precision_i / Σ precision_i)（規格 MVP 簡化版）
  注意：規格 5.2 的文字敘述與公式方向相反——依公式，precision 越集中在
  單一 Agent，uncertainty 越低（區間越窄），這與同節前句「precision 越
  集中在少數高權重 Agent，區間應越窄」一致，故以公式為準。
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

from agents.base import AgentOutput

BULLISH_THRESHOLD = 0.1
BEARISH_THRESHOLD = -0.1


@dataclass
class MergedThesis:
    """仲裁層輸出：投資論點 + 不確定性 + evidence trace（規格第 2 節架構圖）。"""

    ticker: str
    as_of_date: str
    signal: str
    final_score: float
    uncertainty: float
    # 合併機率：各 Agent 規格 6.1 機率的精度加權線性意見池
    # p = Σ(precision_i * p_i) / Σ(precision_i)，恆有 final_score = 2p − 1
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

    prec_sum = sum(precisions[o.agent_id] for o in outputs)
    probs = {
        o.agent_id: o.confidence if o.signal == "bullish" else (1 - o.confidence) if o.signal == "bearish" else 0.5
        for o in outputs
    }
    if prec_sum > 0:
        probability_bullish = sum(precisions[a] * p for a, p in probs.items()) / prec_sum
        uncertainty = 1.0 - max(precisions[o.agent_id] for o in outputs) / prec_sum
    else:
        probability_bullish = 0.5
        uncertainty = 1.0  # 無有效權重時完全不確定
    # Σ(precision·κ·s)/Σprecision，κ·s = 2p − 1
    final_score = 2.0 * probability_bullish - 1.0
    signal = score_to_signal(final_score, bullish_threshold, bearish_threshold)

    vote_total = sum(precisions[a] * abs(2 * p - 1) for a, p in probs.items())
    contributions = [
        {
            "agent_id": o.agent_id,
            "signal": o.signal,
            "confidence": o.confidence,
            "conviction": abs(2 * probs[o.agent_id] - 1),
            "precision": precisions[o.agent_id],
            # 該 Agent 佔總投票權重（precision·κ）的比例；全體皆無確信度時為 0
            "weight_share": precisions[o.agent_id] * abs(2 * probs[o.agent_id] - 1) / vote_total
            if vote_total > 0 else 0.0,
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
