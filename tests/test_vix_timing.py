"""VIX 規則：持股只用前一日資訊、波動率管理不加槓桿、官方檔解析。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "analysis"))
import vix_timing as vt  # noqa: E402


def test_rules_use_previous_day_and_no_leverage():
    days = pd.bdate_range("2015-01-01", periods=1200)
    rng = np.random.default_rng(0)
    r = pd.Series(rng.normal(0.0003, 0.01, len(days)), index=days)
    vix = pd.Series(20 + 5 * np.sin(np.arange(len(days)) / 30), index=days)
    R = vt.rules(vix, r)
    assert (R["B 波動率管理（VIX）"].dropna() <= 1.0 + 1e-12).all()
    bumped = vix.copy()
    bumped.iloc[-1] = 80.0                                   # 最後一天 VIX 飆高
    R2 = vt.rules(bumped, r)
    for k in R:
        assert R[k].iloc[-1] == R2[k].iloc[-1] or (np.isnan(R[k].iloc[-1]) and np.isnan(R2[k].iloc[-1]))
