"""月營收驚奇：公告期限後的進場日、SUE 計算與可用月份對齊。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "analysis"))
import revenue_surprise as rs  # noqa: E402


def test_entry_is_trading_day_after_the_deadline():
    # 2024-02-10 是週六 → 期限順延到 02-12（週一），進場日為 02-13
    days = pd.bdate_range("2024-02-01", "2024-02-29")
    ev = rs.event_dates(days)
    assert pd.Timestamp("2024-02-13") in ev
    # 2024-04-10 是週三 → 進場日為 04-11
    assert pd.Timestamp("2024-04-11") in rs.event_dates(pd.bdate_range("2024-04-01", "2024-04-30"))


def test_sue_uses_only_past_differences_and_shifts_to_announcement_month():
    months = pd.date_range("2020-01-01", periods=40, freq="MS")
    revenue = 100 + np.arange(40) * 1.0 + np.random.default_rng(0).normal(0, 1, 40)  # 穩定成長 + 雜訊：年差約 12
    revenue[-1] += 30                     # 最後一個月營收驚奇
    rev = pd.DataFrame({"revenue_year": months.year, "revenue_month": months.month, "revenue": revenue})
    out = rs.revenue_surprise(rev).set_index("avail_month")
    last_month = months[-1] + pd.offsets.MonthBegin(1)   # 營收月份的次月才可用
    assert out.index.max() == last_month
    assert out.loc[last_month, "sue"] > 5                # 年差約 42，遠高於過去約 12
    assert np.isnan(out.iloc[11]["sue"])                 # 不足 12 個月年差 → 缺值
