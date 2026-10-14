"""除權息事件研究：持有視窗的日曆時間組合。"""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "analysis"))
import dividend_events as de  # noqa: E402


def test_window_portfolio_holds_from_start_to_end_close():
    days = pd.bdate_range("2026-03-02", periods=30)
    ev = pd.DataFrame({"ticker": ["A", "B"], "k0": [15, 16]})
    w = de.window_portfolio(ev, -11, -1, days, len(days))
    assert days[3] not in w and list(w[days[4]].index) == ["A"]     # 第 −11 日收盤建立
    assert w[days[5]].sum() == pytest.approx(1.0) and len(w[days[5]]) == 2
    assert "A" not in w.get(days[14], pd.Series(dtype=float)).index  # 第 −1 日收盤賣出
