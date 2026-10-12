"""盈餘驚奇：法定期限的可用日、單季年差標準化。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "analysis"))
import revenue_surprise_plus as rp  # noqa: E402


def test_quarter_available_uses_statutory_deadlines():
    assert rp.quarter_available(pd.Timestamp("2024-03-31")) == pd.Timestamp("2024-05-15")
    assert rp.quarter_available(pd.Timestamp("2024-06-30")) == pd.Timestamp("2024-08-14")
    assert rp.quarter_available(pd.Timestamp("2024-09-30")) == pd.Timestamp("2024-11-14")
    assert rp.quarter_available(pd.Timestamp("2024-12-31")) == pd.Timestamp("2025-03-31")


def test_earnings_surprise_flags_jump_in_latest_quarter():
    q = pd.date_range("2020-03-31", periods=20, freq="QE-DEC")
    ni = 100 + np.arange(20) * 2.0 + np.random.default_rng(1).normal(0, 1, 20)
    ni[-1] += 40
    fs = pd.DataFrame({"date": q.strftime("%Y-%m-%d"), "type": "EquityAttributableToOwnersOfParent", "value": ni})
    out = rp.earnings_surprise(fs).set_index("avail_date")
    last = rp.quarter_available(q[-1])
    assert out.index.max() == last
    assert out.loc[last, "sue_e"] > 5
