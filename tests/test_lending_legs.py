"""借券腿：比率與增量的定義、取負號、落後一日。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "analysis"))
import lending_legs as ll  # noqa: E402


def test_lending_raw_signs_and_lag():
    days = pd.bdate_range("2024-01-01", periods=30)
    bal = pd.DataFrame({"date": [d.strftime("%Y-%m-%d") for d in days], "SBLShortSalesCurrentDayBalance": np.arange(30) * 1000.0})
    lend = pd.DataFrame({"date": [days[5].strftime("%Y-%m-%d")], "volume": [10]})

    class C:
        def get(self, ds, *a):
            return bal if ds == "TaiwanDailyShortSaleBalances" else lend

    shares = pd.DataFrame({"X.TW": 1e6}, index=days)
    fee = pd.DataFrame({"X.TW": 2.0}, index=days)
    raw = ll.lending_raw(C(), ["X.TW"], days, shares, fee)
    assert raw["sbl_ratio"].iloc[10, 0] == pytest.approx(-9000 / 1e6)        # 第 10 日用第 9 日餘額，取負號
    assert raw["sbl_flow"].iloc[25, 0] == pytest.approx(-20000 / 1e6)
    assert raw["lend_fee"].iloc[10, 0] == pytest.approx(-2.0)
    assert raw["lend_demand"].iloc[20, 0] == pytest.approx(-10000 / 1e6)     # 10 張 = 10,000 股
