"""期貨執行擇時：完全避險時報酬 ≈ 0050 − 台指期、轉倉日標記、成本只在變動與轉倉時扣。"""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "analysis"))
import timing_futures as tf  # noqa: E402


def test_roll_days_third_wednesday():
    idx = pd.bdate_range("2026-10-01", "2026-10-31")
    f = tf.roll_days(idx)
    assert list(idx[f.to_numpy()]) == [pd.Timestamp("2026-10-21")]


def test_overlay_full_hedge_and_costs():
    idx = pd.bdate_range("2026-10-01", "2026-10-09")
    r = pd.Series(0.01, index=idx)
    tx = pd.Series(0.008, index=idx)
    e = pd.Series(0.0, index=idx)                      # 淨曝險 0 → 放空 100% 台指期
    out = tf.futures_overlay(e, r, tx)
    assert out.iloc[0] == pytest.approx(0.01 - 0.008 - tf.FUT_COST)   # 第一天建立部位
    assert out.iloc[1] == pytest.approx(0.002)                        # 之後只剩基差差異
    full = tf.futures_overlay(pd.Series(1.0, index=idx), r, tx)
    assert (full == r).all()                                           # 曝險 100% → 不用期貨、沒有成本
