"""除息濾網：只排除做多端、做多總權重不變。"""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "analysis"))
import sue_exdiv_filter as sf  # noqa: E402


def test_filter_long_keeps_shorts_and_total_long():
    w = pd.Series({"A": 0.25, "B": 0.25, "C": 0.5, "S1": -0.6, "S2": -0.4})
    flagged = pd.Series({"A": True, "S1": True})
    out, share = sf.filter_long(w, flagged)
    assert share == pytest.approx(0.25)
    assert "A" not in out.index and out["S1"] == -0.6               # 放空端不受影響
    assert out[out > 0].sum() == pytest.approx(1.0)
    assert out["C"] / out["B"] == pytest.approx(2.0)
