"""擇時樣本外驗證：與 allocation_study 的規則與報酬計算一致。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "analysis"))
import allocation_study as al  # noqa: E402
import timing_oos as to  # noqa: E402


def test_band_rule_matches_allocation_study():
    days = pd.bdate_range("2018-01-01", periods=600)
    rng = np.random.default_rng(3)
    adj = pd.Series(np.cumprod(1 + rng.normal(0.0004, 0.012, 600)) * 100, index=days)
    mine = to.positions(adj, ("ma", 200, 0.02))
    ref = al.timing_positions(adj, "band")
    pd.testing.assert_series_equal(mine.fillna(-1), ref.fillna(-1), check_names=False)
    s = al.timing_series(adj, "band", start="2018-01-01", end="2030-01-01")
    net = to.net_returns(adj, ("ma", 200, 0.02))
    assert net.iloc[:-1].to_numpy() == pytest.approx(s["net"].to_numpy()[:-2])   # 同一筆報酬，只是索引移到實現日
