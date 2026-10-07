"""Agent 層級的重新校準（技術筆記第 6 節）。

動機：LLM 判讀實驗中各 Agent 嚴重過度自信（信心 ≥ 0.8 的命中率約 50%），
而線性意見池會繼承來源的過度自信。合併前先把每個 Agent 的原始機率
修正到它歷史上實際的命中水準。

方法：收縮型 logit 校準
    p' = σ(a · logit(p))，a ∈ [0, 1]
- a = 1 不修正；a = 0 代表毫無判讀能力，p' 一律 0.5
- neutral（p = 0.5）校準後仍為 0.5，訊號方向不會翻轉（a ≥ 0）
- 只收縮不放大：本專案的問題是過度自信，且樣本少時放大風險高

擬合：對已到期（walk-forward）的 (p, outcome) 做最大概似，加上往 a = 1 的
二次先驗 prior_strength · (a − 1)²，樣本少時保守不修正；a 以網格搜尋求解。
每個 Agent 跨股票合併成一個樣本池（每檔僅約 27 筆，單檔估不穩）。
超參數（min_n、prior_strength）事先固定，不依回測結果調整。
"""
from __future__ import annotations

import math

import numpy as np

P_CLIP = 1e-3
SLOPE_GRID = np.linspace(0.0, 1.0, 101)


def _logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(p, P_CLIP, 1 - P_CLIP)
    return np.log(p / (1 - p))


def apply_slope(p: float, slope: float) -> float:
    """p' = σ(slope · logit(p))。"""
    z = slope * float(_logit(np.asarray(p)))
    return 1.0 / (1.0 + math.exp(-z))


def fit_slope(ps: list[float], outcomes: list[int], prior_strength: float) -> float:
    """在 [0, 1] 網格上最大化 Σ log-likelihood − prior_strength·(a−1)²。"""
    z = _logit(np.asarray(ps, dtype=float))
    o = np.asarray(outcomes, dtype=float)
    best_a, best_obj = 1.0, -math.inf
    for a in SLOPE_GRID:
        q = 1.0 / (1.0 + np.exp(-a * z))
        q = np.clip(q, P_CLIP, 1 - P_CLIP)
        ll = float(np.sum(o * np.log(q) + (1 - o) * np.log(1 - q)))
        obj = ll - prior_strength * (a - 1.0) ** 2
        if obj > best_obj:
            best_a, best_obj = float(a), obj
    return best_a


class AgentCalibrator:
    """逐 Agent 累積已到期預測、提供校準後機率。"""

    def __init__(self, min_n: int = 10, prior_strength: float = 2.0):
        self.min_n = min_n
        self.prior_strength = prior_strength
        self._history: dict[str, tuple[list[float], list[int]]] = {}
        self._slopes: dict[str, float] = {}

    def record(self, agent_id: str, p_raw: float, outcome: int) -> None:
        ps, os_ = self._history.setdefault(agent_id, ([], []))
        ps.append(float(p_raw))
        os_.append(int(outcome))
        self._slopes.pop(agent_id, None)  # 有新資料，下次查詢時重擬合

    def n(self, agent_id: str) -> int:
        return len(self._history.get(agent_id, ([], []))[0])

    def slope(self, agent_id: str) -> float:
        """目前的收縮係數；樣本不足 min_n 時回傳 1（不修正）。"""
        if self.n(agent_id) < self.min_n:
            return 1.0
        if agent_id not in self._slopes:
            ps, os_ = self._history[agent_id]
            self._slopes[agent_id] = fit_slope(ps, os_, self.prior_strength)
        return self._slopes[agent_id]

    def calibrate(self, agent_id: str, p_raw: float) -> float:
        return apply_slope(p_raw, self.slope(agent_id))
