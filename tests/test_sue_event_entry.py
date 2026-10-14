"""依公告日進場：進場日的計算、習慣日。"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "analysis"))
import sue_event_entry as ee  # noqa: E402


def test_entry_date_rolls_forward_and_caps():
    days = pd.bdate_range("2026-06-01", "2026-06-30")
    m = pd.Timestamp("2026-06-01")
    fixed = pd.Timestamp("2026-06-11")
    assert ee.entry_date(days, m, 6, 0, fixed) == pd.Timestamp("2026-06-08")   # 6/6 週六 → 週一
    assert ee.entry_date(days, m, 6, 1, fixed) == pd.Timestamp("2026-06-09")
    assert ee.entry_date(days, m, 15, 1, fixed) == fixed                       # 不晚於統一進場日


def test_habit_days():
    ann = pd.DataFrame({"ticker": ["A"] * 3 + ["B"] * 2,
                        "avail": pd.to_datetime(["2026-05-01", "2026-06-01", "2026-07-01", "2026-05-01", "2026-06-01"]),
                        "ct": pd.to_datetime(["2026-05-05", "2026-06-06", "2026-07-09", "2026-05-10", "2026-06-10"])})
    h = ee.habit_days(ann)
    assert h.at["A", "median"] == 6 and h.at["A", "latest"] == 9 and h.at["B", "n"] == 2
