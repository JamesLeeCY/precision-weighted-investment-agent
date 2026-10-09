"""Agent 抽象基底類別與共同輸出 schema（規格 3.1，強制介面）。

所有 Agent 的輸出必須是 AgentOutput，欄位與規格 JSON schema 一一對應：
agent_id / ticker / as_of_date / signal / confidence / horizon_days /
rationale / evidence_refs / raw_features
"""
from __future__ import annotations

import math
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from typing import Any

VALID_SIGNALS = ("bullish", "bearish", "neutral")

# signal -> s ∈ {-1, 0, +1}（規格 5.2）
SIGNAL_TO_SCORE = {"bullish": 1, "neutral": 0, "bearish": -1}

RATIONALE_MAX_LEN = 200
# 連續輸出模式：p = σ(CONTINUOUS_SCALE · score · evidence)；分數 ±1 且證據完整時 p = 0.75 / 0.25。
# 事先固定，過度自信交給 Agent 層級校準（arbitrator/calibration.py）收縮
CONTINUOUS_SCALE = math.log(3.0)
OUTPUT_MODES = ("threshold", "continuous")
MIN_DIRECTIONAL_CONFIDENCE = 0.5
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass
class AgentOutput:
    """單一 Agent 對單一 ticker、單一時點的判斷（規格 3.1 schema）。"""

    agent_id: str
    ticker: str
    as_of_date: str
    signal: str
    confidence: float
    horizon_days: int
    rationale: str
    evidence_refs: list[str] = field(default_factory=list)
    raw_features: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.signal not in VALID_SIGNALS:
            raise ValueError(f"signal 必須是 {VALID_SIGNALS}，收到: {self.signal!r}")
        if not (0.0 <= float(self.confidence) <= 1.0):
            raise ValueError(f"confidence 必須在 [0, 1]，收到: {self.confidence}")
        self.confidence = float(self.confidence)
        if int(self.horizon_days) <= 0:
            raise ValueError(f"horizon_days 必須為正整數，收到: {self.horizon_days}")
        self.horizon_days = int(self.horizon_days)
        if not _DATE_RE.match(self.as_of_date):
            raise ValueError(f"as_of_date 必須為 YYYY-MM-DD，收到: {self.as_of_date!r}")
        # 規格要求 rationale <= 200 字
        if len(self.rationale) > RATIONALE_MAX_LEN:
            self.rationale = self.rationale[: RATIONALE_MAX_LEN - 1] + "…"
        self.evidence_refs = list(self.evidence_refs)
        self.raw_features = dict(self.raw_features)

    @property
    def score(self) -> int:
        """signal 的數值形式 s ∈ {-1, 0, +1}。"""
        return SIGNAL_TO_SCORE[self.signal]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def score_components(
    components: list[tuple[str, float]], n_total: int
) -> tuple[str, float, float, bool, str]:
    """規則式 Agent 共用評分：各分量 ∈ [-1, 1] 取平均。

    回傳 (signal, confidence, score, conflict, 分量描述)。
    confidence = 0.3 + 0.2·資料覆蓋率 + 0.35·|score|，同時有強正與強負
    分量（> 0.4 且 < -0.4）時視為內部矛盾、扣 0.15。呼叫端需先處理
    components 為空的情況。
    """
    score = float(sum(v for _, v in components) / len(components))
    signal = "bullish" if score > 0.2 else "bearish" if score < -0.2 else "neutral"

    pos = max((v for _, v in components), default=0.0)
    neg = min((v for _, v in components), default=0.0)
    conflict = pos > 0.4 and neg < -0.4

    confidence = 0.3 + 0.2 * (len(components) / n_total) + 0.35 * abs(score)
    if conflict:
        confidence -= 0.15
    confidence = min(max(confidence, 0.05), 0.95)

    parts = "、".join(
        f"{name}{'偏多' if v > 0.1 else '偏空' if v < -0.1 else '中性'}({v:+.2f})" for name, v in components
    )
    return signal, confidence, score, conflict, parts


def continuous_judgement(score: float, evidence: float) -> tuple[str, float, float]:
    """連續輸出：由規則分數直接映射成看多機率，回傳 (signal, confidence, p)。

    門檻模式會把 |score| 小於門檻的判斷一律歸為中性（p = 0.5），並以另一條公式算
    信心，丟掉了排序資訊（擴大股票池分析：財報 Agent 連續分數的產業內 IC 約 +0.02 ~
    +0.03，門檻化後幾乎消失）。連續模式保留分數的順序：
      p = σ(CONTINUOUS_SCALE · score · evidence)，evidence ∈ [0, 1] 為證據強度
    signal 取 p 在 0.5 的哪一側，confidence = max(p, 1 − p)（≥ 0.5），
    使規格 6.1 的換算 signal_to_probability(signal, confidence) 恰好還原 p。
    """
    z = CONTINUOUS_SCALE * max(-1.0, min(1.0, float(score))) * max(0.0, min(1.0, float(evidence)))
    p = 1.0 / (1.0 + math.exp(-z))
    if z > 0:
        return "bullish", p, p
    if z < 0:
        return "bearish", 1.0 - p, p
    return "neutral", 0.2, 0.5


def describe_features(feats: dict, labels: dict[str, str]) -> str:
    """把特徵字典轉成「中文定義：數值」逐行文字，供 LLM prompt 使用。

    只給定義與單位，不給多空方向提示——判讀交給模型。只送英文欄位名時，
    地端模型會誤讀方向（例如把 USD/TWD 上升當成台幣升值）。
    """
    lines = []
    for key, value in feats.items():
        label = labels.get(key)
        if label is None:
            continue
        lines.append(f"- {label}：{value:.2f}" if isinstance(value, (int, float)) else f"- {label}：{value}")
    return "\n".join(lines) if lines else "（無資料）"


class BaseAgent(ABC):
    """所有專家 Agent 的基底類別。

    子類別必須設定 agent_id 並實作 analyze()。
    """

    agent_id: str = "base_agent"
    default_horizon_days: int = 20

    @abstractmethod
    def analyze(self, ticker: str, as_of_date: str) -> AgentOutput:
        """對 ticker 在 as_of_date 時點產出判斷。

        實作必須保證不使用 as_of_date 之後的資料（避免 look-ahead bias）。
        """

    def _build_output(
        self,
        ticker: str,
        as_of_date: str,
        signal: str,
        confidence: float,
        rationale: str,
        evidence_refs: list[str] | None = None,
        raw_features: dict[str, Any] | None = None,
        horizon_days: int | None = None,
    ) -> AgentOutput:
        # 有方向的訊號 confidence 下限 0.5：規格 6.1 以 p = confidence（bullish）
        # / 1 - confidence（bearish）換算機率，confidence < 0.5 會讓機率落在訊號
        # 的反方向，Brier 與合併公式對同一訊號的解讀因而矛盾。強度以 0.5–1 表示，
        # 0.5 即「有方向但無把握」（Brier 上等同 neutral）。原始值保留於 raw_features。
        raw_features = dict(raw_features or {})
        if signal in ("bullish", "bearish") and confidence < MIN_DIRECTIONAL_CONFIDENCE:
            raw_features["confidence_raw"] = float(confidence)
            confidence = MIN_DIRECTIONAL_CONFIDENCE
        return AgentOutput(
            agent_id=self.agent_id,
            ticker=ticker,
            as_of_date=as_of_date,
            signal=signal,
            confidence=confidence,
            horizon_days=horizon_days or self.default_horizon_days,
            rationale=rationale,
            evidence_refs=evidence_refs or [],
            raw_features=raw_features,
        )
