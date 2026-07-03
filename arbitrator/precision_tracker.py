"""各 Agent 精度記錄的維護（規格 5.1 / 5.3）。

每筆記錄對應 (agent_id, ticker)：
{
  "agent_id": "fundamentals_agent",
  "ticker": "2327.TW",
  "n_predictions": 12,
  "brier_score_ema": 0.18,
  "precision": 5.56
}

- precision = 1 / (brier_score_ema + epsilon)，epsilon=0.01（規格 5.1）
- Brier EMA 以 alpha=0.2 更新（規格 5.3）
- 冷啟動：n_predictions < 5 時，該 Agent 精度強制設為「所有已知
  （成熟）Agent 精度的平均值」；完全沒有成熟記錄時所有 Agent
  拿相同的預設精度 → 等同均等權重（loose coupling）
"""
from __future__ import annotations

import json
from pathlib import Path

EPSILON = 0.01
EMA_ALPHA = 0.2
COLD_START_MIN_N = 5
# 「永遠猜 0.5」的預測者 Brier = 0.25；作為無任何歷史時的基準精度
DEFAULT_PRECISION = 1.0 / (0.25 + EPSILON)


class PrecisionTracker:
    def __init__(
        self,
        storage_path: str | Path,
        epsilon: float = EPSILON,
        ema_alpha: float = EMA_ALPHA,
        cold_start_min_n: int = COLD_START_MIN_N,
    ):
        self.storage_path = Path(storage_path)
        self.epsilon = epsilon
        self.ema_alpha = ema_alpha
        self.cold_start_min_n = cold_start_min_n
        self.records: dict[str, dict] = {}
        self._load()

    # ---------- 儲存 ----------

    @staticmethod
    def _key(agent_id: str, ticker: str) -> str:
        return f"{agent_id}|{ticker}"

    def _load(self) -> None:
        if self.storage_path.exists():
            raw = self.storage_path.read_text(encoding="utf-8").strip()
            self.records = json.loads(raw) if raw else {}

    def save(self) -> None:
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.storage_path.write_text(
            json.dumps(self.records, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # ---------- 更新（規格 5.3） ----------

    def record_outcome(self, agent_id: str, ticker: str, brier: float, autosave: bool = True) -> dict:
        """回測管線在 horizon 到期後，以單次 Brier score 更新 EMA。"""
        if not (0.0 <= brier <= 1.0):
            raise ValueError(f"單次 Brier score 必須在 [0,1]，收到 {brier}")
        key = self._key(agent_id, ticker)
        rec = self.records.get(key)
        if rec is None:
            rec = {
                "agent_id": agent_id,
                "ticker": ticker,
                "n_predictions": 0,
                "brier_score_ema": brier,  # 第一筆直接以觀測值初始化
            }
        else:
            rec["brier_score_ema"] = (
                self.ema_alpha * brier + (1.0 - self.ema_alpha) * rec["brier_score_ema"]
            )
        rec["n_predictions"] += 1
        rec["precision"] = 1.0 / (rec["brier_score_ema"] + self.epsilon)
        self.records[key] = rec
        if autosave:
            self.save()
        return rec

    # ---------- 查詢（含冷啟動規則，規格 5.1） ----------

    def _mature_precisions(self, ticker: str | None = None) -> list[float]:
        vals = []
        for rec in self.records.values():
            if rec["n_predictions"] >= self.cold_start_min_n:
                if ticker is None or rec["ticker"] == ticker:
                    vals.append(rec["precision"])
        return vals

    def get_precision(self, agent_id: str, ticker: str) -> float:
        """取得仲裁層使用的有效精度（套用冷啟動規則後）。"""
        rec = self.records.get(self._key(agent_id, ticker))
        if rec is not None and rec["n_predictions"] >= self.cold_start_min_n:
            return rec["precision"]
        # 冷啟動：優先用同 ticker 的成熟記錄均值，其次全體成熟記錄均值，
        # 完全沒有時給所有 Agent 相同的預設值（均等權重）
        mature = self._mature_precisions(ticker) or self._mature_precisions(None)
        if mature:
            return sum(mature) / len(mature)
        return DEFAULT_PRECISION

    def get_precisions(self, agent_ids: list[str], ticker: str) -> dict[str, float]:
        return {a: self.get_precision(a, ticker) for a in agent_ids}

    def get_record(self, agent_id: str, ticker: str) -> dict | None:
        return self.records.get(self._key(agent_id, ticker))
