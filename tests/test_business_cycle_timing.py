"""景氣燈號擇時：連續燈號規則、兩個月落後使用。"""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "analysis"))
import business_cycle_timing as bc  # noqa: E402


def test_rule_b_needs_two_consecutive_lights_and_holds():
    months = pd.date_range("2020-01-01", periods=6, freq="MS")
    lights = pd.Series(["藍", "藍", "綠", "紅", "紅", "綠"], index=months)
    e = bc.exposure_rule_b(lights)
    assert e.tolist() == [0.7, 1.0, 1.0, 1.0, 0.4, 0.4]


def test_lights_apply_two_months_later():
    monthly = pd.Series([1.0, 0.4], index=pd.to_datetime(["2020-01-01", "2020-02-01"]))
    days = pd.bdate_range("2020-03-02", "2020-04-30")
    e = bc.daily_exposure(monthly, days)
    assert e.loc["2020-03-02"] == pytest.approx(1.0)     # 1 月燈號 3 月起用
    assert e.loc["2020-04-01"] == pytest.approx(0.4)     # 2 月燈號 4 月起用
