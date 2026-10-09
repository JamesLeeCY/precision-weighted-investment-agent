"""產業中性組合：產業權重等於股票池、產業內取前段、緩衝續抱、多空只計可排序產業。"""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "analysis"))
import sector_neutral_portfolio as sn  # noqa: E402


@pytest.fixture
def g():
    return pd.DataFrame({
        "ticker": list("ABCDEF") + ["G", "H"],
        "sector": ["S1"] * 6 + ["S2"] * 2,
        "sig": [0.9, 0.8, 0.6, 0.5, 0.3, 0.1, 0.7, 0.2],
        "ret": [0.10, 0.05, 0.0, 0.0, -0.05, -0.10, 0.02, 0.01],
    })


def test_long_only_keeps_sector_weights_and_holds_small_sector(g):
    w = sn.sector_neutral_weights(g, "sig", 1 / 3, 3, +1)
    assert set(w) == {"A", "B", "G", "H"}  # S1 取前 1/3；S2 只有 2 檔 → 整個持有
    assert w["A"] + w["B"] == pytest.approx(6 / 8)
    assert w["G"] + w["H"] == pytest.approx(2 / 8)
    assert sum(w.values()) == pytest.approx(1.0)


def test_buffer_keeps_held_stock_above_threshold(g):
    w = sn.sector_neutral_weights(g, "sig", 1 / 3, 3, +1, held={"C"}, keep=0.5)
    assert {"A", "B", "C"} <= set(w)  # C 百分位 4/6 > 0.5 → 續抱
    w = sn.sector_neutral_weights(g, "sig", 1 / 3, 3, +1, held={"E"}, keep=0.5)
    assert "E" not in w  # E 百分位 2/6 ≤ 0.5 → 賣出


def test_long_short_only_rankable_sectors(g):
    long_w, short_w = sn.long_short_weights(g, "sig", 1 / 3, 3)
    assert set(long_w) == {"A", "B"} and set(short_w) == {"E", "F"}
    assert sum(long_w.values()) == pytest.approx(1.0) and sum(short_w.values()) == pytest.approx(1.0)
    assert sn.portfolio_return(g, long_w) - sn.portfolio_return(g, short_w) == pytest.approx(0.075 - (-0.075))
