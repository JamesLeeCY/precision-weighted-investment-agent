"""前瞻規格 fv3 的規則函式：分數中性化、可借條件、段落報酬（避險、借券費、只在第一段扣換倉成本）。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from forward import run_forward_fv3 as fv3  # noqa: E402


def frame(n=9):
    rng = np.random.default_rng(0)
    return pd.DataFrame({"ticker": [f"T{i}" for i in range(n)], "sector": ["a", "b", "c"] * (n // 3),
                         "sue": rng.normal(size=n), "logcap": rng.normal(10, 1, n), "close": 100.0,
                         "quota": 1e9, "lend60": 1e9, "fee": 1.0, "beta": 1.0})


def test_shortable_requires_quota_depth_fee_and_activity():
    g = frame()
    g.loc[0, "lend60"] = 0                 # 沒有借券成交
    g.loc[1, "quota"] = 10                 # 額度不足
    g.loc[2, "fee"] = 6.0                  # 費率 > 5%
    g.loc[3, "fee"] = np.nan               # 費率缺值 → 視為不可借
    g.loc[4, "lend60"] = 1000              # 深度不足（需借 2 億 / 3 / 100 元 ≫ 100 股）
    f = fv3.shortable_flags(g)
    assert not f[["T0", "T1", "T2", "T3", "T4"]].any() and f[["T5", "T6", "T7", "T8"]].all()


def test_tranche_weights_are_dollar_neutral():
    w = fv3.tranche_weights(frame(30))      # 中性化至少要 20 檔
    assert w[w > 0].sum() == pytest.approx(1.0) and w[w < 0].sum() == pytest.approx(-1.0)


def test_segment_return_hedges_charges_fee_and_cost_only_on_first_segment():
    days = pd.bdate_range("2026-05-01", periods=6)
    rets = pd.DataFrame({"L": 0.01, "S": 0.0}, index=days)
    tx = pd.Series(0.01, index=days)
    w = pd.Series({"L": 1.0, "S": -1.0})
    fees = pd.Series({"S": 2.52})
    r = fv3.segment_return(w, 0.5, fees, rets, tx, days[0], days[-1], first=True, prev_weights=None, prev_beta=0.0)
    daily = r["daily"]
    assert len(daily) == 5
    assert daily.iloc[1] == pytest.approx(0.01 - 0.5 * 0.01 - 0.0001)               # 多 − β·台指期 − 借券費
    assert daily.iloc[0] == pytest.approx(daily.iloc[1] - (2.0 * fv3.STOCK_COST + 0.5 * fv3.FUT_COST))
    r2 = fv3.segment_return(w, 0.5, fees, rets, tx, days[0], days[-1], first=False, prev_weights=None, prev_beta=0.0)
    assert r2["cost"] == 0.0


def test_frozen_sources_cover_rules():
    keys = set(fv3.frozen_sources())
    assert {"fv3.score_members", "fv3.shortable_flags", "fv3.segment_return", "ls_turnover.ew_ls_buffer",
            "leg_probe.neutralize", "data.revenue_signal"} <= keys
