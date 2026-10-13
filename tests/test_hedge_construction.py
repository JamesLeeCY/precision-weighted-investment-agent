"""對沖結構差：市值加權做多、市值加權多空、借券費。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "analysis"))
import hedge_construction as hc  # noqa: E402

SECTOR = pd.Series({"A": "s1", "B": "s1", "C": "s1", "D": "s2", "E": "s2", "F": "s2"})
CAP = pd.Series({"A": 300.0, "B": 100.0, "C": 100.0, "D": 50.0, "E": 25.0, "F": 25.0})
SCORE = pd.Series({"A": 3.0, "B": 2.0, "C": 1.0, "D": 1.0, "E": 2.0, "F": 3.0})


def test_cw_long_uses_sector_cap_share_and_cap_within_sector():
    w = hc.cw_long(SCORE, SECTOR, CAP)
    # 產業市值占比 s1 = 500/600、s2 = 100/600；各取前 1/3（1 檔）
    assert w["A"] == pytest.approx(500 / 600)
    assert w["F"] == pytest.approx(100 / 600)
    full = hc.cw_long(SCORE, SECTOR, CAP, q=1.0)       # 全部持有 = 整體市值加權
    assert (full - CAP / CAP.sum()).abs().max() < 1e-12


def test_cw_long_short_is_dollar_neutral_and_skips_unborrowable():
    borrow = pd.Series(True, index=SECTOR.index)
    w = hc.cw_long_short(SCORE, SECTOR, CAP, borrow)
    assert w[w > 0].sum() == pytest.approx(1.0) and w[w < 0].sum() == pytest.approx(-1.0)
    assert w["C"] < 0 and w["D"] < 0
    borrow["D"] = False                                # s2 的後 1/3 借不到 → s2 整個產業不做
    w2 = hc.cw_long_short(SCORE, SECTOR, CAP, borrow)
    assert set(w2.index) == {"A", "C"}


def test_simulate_weights_charges_borrow_fee_and_hedges_beta():
    days = pd.bdate_range("2024-01-01", periods=6)
    rets = pd.DataFrame({"A": 0.0, "C": 0.0}, index=days)
    betas = pd.DataFrame({"A": 1.0, "C": 1.0}, index=days)
    tx = pd.Series(0.01, index=days)
    fee = pd.DataFrame({"A": np.nan, "C": 2.52}, index=days)      # 年化 2.52% → 每日 0.01%
    w = {days[0]: pd.Series({"A": 1.0, "C": -1.0})}
    sim = hc.simulate_weights(w, rets, betas, tx, [days[0]], fee=fee)
    assert sim["beta"].iloc[0] == pytest.approx(0.0)              # 多空 β 相抵，不需期貨
    assert sim["ret"].iloc[1:].to_numpy() == pytest.approx(-0.0001)
    assert sim["borrow"].iloc[1] == pytest.approx(0.0001)


def test_lending_fee_is_volume_weighted_and_lagged():
    days = pd.bdate_range("2024-01-01", periods=5)
    rows = pd.DataFrame({"date": [days[1].strftime("%Y-%m-%d")] * 2, "volume": [100, 300], "fee_rate": [1.0, 3.0]})

    class C:
        def get(self, *a):
            return rows

    fee = hc.lending_fees(C(), ["X.TW"], days)
    assert np.isnan(fee.loc[days[1], "X.TW"])                     # 當天的借券成交到隔天才知道
    assert fee.loc[days[2], "X.TW"] == pytest.approx(2.5)
