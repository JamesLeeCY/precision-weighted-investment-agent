"""I004：傾斜權重保持產業內多空總權重；Newey-West t。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "analysis"))
import sue_attention as sa  # noqa: E402


def test_tilt_preserves_sector_side_totals_and_favours_low_attention():
    sector = pd.Series({"A": "x", "B": "x", "C": "x", "D": "x", "E": "y", "F": "y"})
    w = pd.Series({"A": 0.2, "B": 0.2, "C": -0.2, "D": -0.2, "E": 0.1, "F": -0.1})
    att = pd.Series({"A": -1.0, "B": 1.0, "C": -1.0, "D": 1.0, "E": 0.0, "F": 0.5})   # A、C 低關注
    t = sa.tilt_weights(w, att, sector)
    for sec in ("x", "y"):
        idx = sector[sector == sec].index
        assert t[idx][t[idx] > 0].sum() == pytest.approx(w[idx][w[idx] > 0].sum())
        assert t[idx][t[idx] < 0].sum() == pytest.approx(w[idx][w[idx] < 0].sum())
    assert t["A"] > t["B"] and abs(t["C"]) > abs(t["D"])


def test_nw_t_matches_plain_t_without_lags():
    rng = np.random.default_rng(0)
    x = pd.Series(rng.normal(0.1, 1, 200))
    plain = x.mean() / (x.std(ddof=0) / np.sqrt(len(x)))
    assert sa.nw_t(x, 0) == pytest.approx(plain)
