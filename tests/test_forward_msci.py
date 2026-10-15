"""前瞻記錄 msci：進出場日、納入 − 刪除與成本。"""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from forward import run_forward_msci as fm  # noqa: E402


def test_trade_dates_roll():
    days = pd.bdate_range("2026-11-02", "2026-11-30")
    d = fm.trade_dates(days, pd.Timestamp("2026-11-07"), pd.Timestamp("2026-11-29"))   # 週六公布、週日生效
    assert d == (pd.Timestamp("2026-11-09"), pd.Timestamp("2026-11-27"))
    assert fm.trade_dates(days, pd.Timestamp("2026-11-30"), pd.Timestamp("2026-11-30")) is None


def test_review_return_spread_and_costs():
    r = fm.review_return({"A": 0.10, "B": 0.06}, {"C": -0.02}, 0.01)
    assert r["add_excess"] == pytest.approx(0.07) and r["del_excess"] == pytest.approx(-0.03)
    assert r["spread"] == pytest.approx(0.10)
    assert r["net"] == pytest.approx(0.10 - 4 * fm.STOCK_COST)
    only_del = fm.review_return({}, {"C": -0.02}, 0.01)
    assert only_del["spread"] == pytest.approx(0.03) and only_del["net"] == pytest.approx(0.03 - 2 * fm.STOCK_COST)


def test_frozen_hashes_stable():
    assert fm.source_hashes() == fm.source_hashes()
