"""事件研究：事件日對齊、CAR 視窗、日曆時間組合；事件資料的日期解析。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "analysis"))
import event_study as es  # noqa: E402
import fetch_events as fe  # noqa: E402


def test_event_index_uses_last_trading_day_on_or_before():
    days = pd.bdate_range("2026-03-02", "2026-03-13")
    assert days[es.event_index(days, pd.Timestamp("2026-03-07"))] == pd.Timestamp("2026-03-06")   # 週六 → 週五
    assert days[es.event_index(days, pd.Timestamp("2026-03-09"))] == pd.Timestamp("2026-03-09")


def test_car_window_and_limit():
    ar = np.arange(10, dtype=float) / 100
    assert es.car(ar, 3, 2, 4, 10) == pytest.approx(0.05 + 0.06 + 0.07)
    assert np.isnan(es.car(ar, 3, 2, 7, 10))          # 超出可用資料 → NaN


def test_calendar_portfolio_enters_after_day_one():
    days = pd.bdate_range("2026-03-02", periods=40)
    ev = pd.DataFrame({"ticker": ["A", "B"], "k0": [0, 1]})
    w = es.calendar_portfolio(ev, -1.0, days, len(days))
    assert days[0] not in w                                        # 事件當天不持有
    assert list(w[days[1]].index) == ["A"] and w[days[1]]["A"] == -1.0
    assert w[days[2]].sum() == pytest.approx(-1.0) and len(w[days[2]]) == 2
    assert days[1 + es.HOLD] not in w or "A" not in w[days[1 + es.HOLD]].index


def test_fetch_date_parsers():
    assert fe.parse_roc("108/01/25") == pd.Timestamp("2019-01-25")
    assert fe.roc(pd.Timestamp("2019-01-01")) == "1080101"
    p0, p1 = fe.period_dates("108/01/28～108/02/19")
    assert p0 == pd.Timestamp("2019-01-28") and p1 == pd.Timestamp("2019-02-19")
