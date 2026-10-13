"""彩券型濾網：MAX 與漲停落後一日、做多端排除不影響放空端。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "analysis"))
import max_rec_robust as mr  # noqa: E402


def test_lottery_measures_are_lagged():
    days = pd.bdate_range("2024-01-01", periods=80)
    r = np.zeros(80)
    r[-1] = 0.10                                         # 最後一天漲停
    adj = pd.DataFrame({"A": np.cumprod(1 + r)}, index=days)
    mx, hits = mr.lottery_measures(adj)
    assert mx["A"].iloc[-1] == pytest.approx(0.0) and hits["A"].iloc[-1] == 0   # 當天的漲停隔天才看得到


def test_exclude_long_keeps_shorts():
    sec = pd.Series("s", index=list("ABCDEF"))
    score = pd.Series({"A": 6.0, "B": 5.0, "C": 4.0, "D": 3.0, "E": 2.0, "F": 1.0})
    ok = pd.Series(True, index=sec.index)
    w = mr.ew_ls_exclude_long(score, sec, ok, {"A"})
    assert set(w[w > 0].index) == {"B"} and w["B"] == pytest.approx(1.0)
    assert set(w[w < 0].index) == {"E", "F"}
