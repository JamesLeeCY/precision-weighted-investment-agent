"""做多權重（含緩衝）、0050 擇時報酬對齊到實現日。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "analysis"))
import blend_longonly as bl  # noqa: E402


def test_long_weights_sector_share_and_buffer():
    sec = pd.Series({"A": "s", "B": "s", "C": "s", "D": "s", "E": "s", "F": "s", "G": "t"})
    score = pd.Series({"A": 6.0, "B": 5.0, "C": 4.0, "D": 3.0, "E": 2.0, "F": 1.0, "G": 0.0})
    w = bl.long_weights(score, sec)
    assert set(w.index) == {"A", "B", "G"} and w.sum() == pytest.approx(1.0)
    assert w["G"] == pytest.approx(1 / 7)                       # 成員 < 3 檔的產業全部持有
    w2 = bl.long_weights(score, sec, prev=frozenset({"C"}), keep=0.5)
    assert "C" in w2.index                                      # 仍在前 1/2 → 續抱


def test_timed_0050_aligns_to_realization_day():
    days = pd.bdate_range("2023-01-02", periods=300)
    adj = pd.Series(np.linspace(100, 160, 300), index=days)     # 一路上漲 → 200 日後持有
    out = bl.timed_0050(adj, days)
    r = adj.pct_change()
    last = days[-1]
    assert out.loc[last] == pytest.approx(r.loc[last])          # 持有時當日報酬 = 0050 當日報酬（無換手成本）
