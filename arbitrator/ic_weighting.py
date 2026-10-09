"""依產業內 IC 加權的合併權重（walk-forward）。

動機：精度加權以 Brier 衡量 Agent 可靠度，但在真實資料上各 Agent 的 Brier 都接近
0.25，分辨不出誰有排序能力；在無選股偏誤股票池上，只有財報 Agent 有產業內排序能力，
總經與供應鏈 Agent 合併進來反而稀釋了它（docs/pit_universe_report.md）。

做法：每個預測時點，只用已到期（resolution_date <= 當下）的預測，對每個 Agent 計算
最近 window 個時點的產業內 IC（各時點：各產業內 Spearman(看多機率, 20 日含息報酬)，
以股票數加權平均；沒有任何產業有 >= 3 檔時退回全體排序），取平均：
    w_a = max(0, 平均產業內 IC_a)
累積不足 min_dates 個時點時各 Agent 等權（冷啟動）。全部權重為 0 時合併機率為 0.5。

參數（window、min_dates）事先固定，不依回測結果調整。
"""
from __future__ import annotations

from collections import defaultdict

import numpy as np
import pandas as pd


def _spearman(x: pd.Series, y: pd.Series) -> float:
    if len(x) < 3 or x.nunique() < 2 or y.nunique() < 2:
        return float("nan")
    return float(x.rank().corr(y.rank()))


def within_sector_ic(df: pd.DataFrame, col: str) -> float:
    """單一時點的產業內 IC（df 欄位：sector、ret、col）。

    只有在「沒有任何產業有 >= 3 檔」時（股票池太小，例如原始 5 檔各屬不同細分類）才退回
    全體排序。若有夠大的產業、但 Agent 在產業內沒有差異（純產業押注），回傳 nan——
    產業押注不算產業內排序能力，不應因此得到權重。
    """
    sizes = df.groupby("sector").size()
    if (sizes < 3).all():
        return _spearman(df[col], df["ret"])
    vals, weights = [], []
    for _, g in df.groupby("sector"):
        ic = _spearman(g[col], g["ret"])
        if not np.isnan(ic):
            vals.append(ic)
            weights.append(len(g))
    return float(np.average(vals, weights=weights)) if vals else float("nan")


class ICWeighter:
    def __init__(self, sectors: dict[str, str] | None = None, window: int = 24, min_dates: int = 6):
        self.sectors = sectors or {}
        self.window = window
        self.min_dates = min_dates
        # as_of_date -> 已到期預測 [{"ticker", "ret", agent_id: p, ...}]
        self._resolved: dict[str, list[dict]] = defaultdict(list)
        self._ic_cache: dict[str, dict[str, float]] = {}

    def record(self, as_of_date: str, ticker: str, probs: dict[str, float], forward_return: float) -> None:
        """登錄一筆已到期的預測（預測當下的各 Agent 看多機率與實現的 20 日報酬）。"""
        if forward_return is None or not np.isfinite(forward_return):
            return
        self._resolved[as_of_date].append({"ticker": ticker, "ret": float(forward_return), **probs})
        self._ic_cache.pop(as_of_date, None)

    def _date_ic(self, as_of_date: str, agent_ids: list[str]) -> dict[str, float]:
        if as_of_date not in self._ic_cache:
            df = pd.DataFrame(self._resolved[as_of_date])
            df["sector"] = df["ticker"].map(lambda t: self.sectors.get(t, "?"))
            self._ic_cache[as_of_date] = {
                a: within_sector_ic(df, a) if a in df else float("nan") for a in agent_ids
            }
        return self._ic_cache[as_of_date]

    def ic_history(self, agent_ids: list[str]) -> pd.DataFrame:
        """最近 window 個已到期時點的各 Agent 產業內 IC（列 = 時點）。"""
        dates = sorted(self._resolved)[-self.window:]
        return pd.DataFrame([self._date_ic(d, agent_ids) for d in dates], index=dates)

    def weights(self, agent_ids: list[str]) -> dict[str, float]:
        hist = self.ic_history(agent_ids)
        if len(hist) < self.min_dates:
            return {a: 1.0 for a in agent_ids}
        means = hist.mean(skipna=True)
        return {a: max(0.0, float(means.get(a, 0.0))) if np.isfinite(means.get(a, np.nan)) else 0.0
                for a in agent_ids}
