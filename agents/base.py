"""Agent 抽象基底類別與共同輸出 schema（規格 3.1，強制介面）。

所有 Agent 的輸出必須是 AgentOutput，欄位與規格 JSON schema 一一對應：
agent_id / ticker / as_of_date / signal / confidence / horizon_days /
rationale / evidence_refs / raw_features
"""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from typing import Any

VALID_SIGNALS = ("bullish", "bearish", "neutral")

# signal -> s ∈ {-1, 0, +1}（規格 5.2）
SIGNAL_TO_SCORE = {"bullish": 1, "neutral": 0, "bearish": -1}

RATIONALE_MAX_LEN = 200
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
        return AgentOutput(
            agent_id=self.agent_id,
            ticker=ticker,
            as_of_date=as_of_date,
            signal=signal,
            confidence=confidence,
            horizon_days=horizon_days or self.default_horizon_days,
            rationale=rationale,
            evidence_refs=evidence_refs or [],
            raw_features=raw_features or {},
        )
