"""隔夜／盤中拆解的恆等式、除權息歸屬、訊號落後一日。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "analysis"))
import reversal_signals as rs  # noqa: E402


def test_overnight_times_intraday_equals_adjusted_return_and_dividend_goes_overnight():
    days = pd.bdate_range("2024-01-01", periods=3)
    close = pd.DataFrame({"A": [100.0, 95.0, 96.0]}, index=days)
    open_ = pd.DataFrame({"A": [100.0, 94.0, 95.5]}, index=days)
    adj = pd.DataFrame({"A": [100.0, 100.0, 96.0 * 100 / 95]}, index=days)   # 第 2 日除息 5 元，含息報酬 0
    on, intra = rs.split_returns(adj, open_, close)
    total = adj.pct_change()
    assert ((1 + on) * (1 + intra) - 1).iloc[1:, 0].to_numpy() == pytest.approx(total.iloc[1:, 0].to_numpy())
    assert on.iloc[1, 0] == pytest.approx(94 * 100 / 95 / 100 - 1)              # 除息落差不算成隔夜下跌


def test_signals_are_lagged_and_signed():
    days = pd.bdate_range("2023-01-02", periods=300)
    rng = np.random.default_rng(1)
    close = pd.DataFrame(np.cumprod(1 + rng.normal(0, 0.01, (300, 3)), axis=0) * 100, index=days, columns=list("ABC"))
    open_ = close.shift(1).fillna(100.0)
    member = close.notna()
    sector = pd.Series("s", index=close.columns)
    sig = rs.raw_signals(close, open_, close, sector, member, None)
    on, _ = rs.split_returns(close, open_, close)
    expect = -np.log1p(on).rolling(21, min_periods=15).sum().shift(1)        # 隔夜 1 個月取負號並落後一日
    assert sig["omom_1m"].iloc[-1]["A"] == pytest.approx(expect.iloc[-1]["A"])
