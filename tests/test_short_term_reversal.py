"""短期反轉分析：隔日成交不偷看當天、5 日報酬的起訖、領先股劃分。"""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "analysis"))
import short_term_reversal as st  # noqa: E402


@pytest.fixture
def data():
    dates = pd.bdate_range("2024-01-01", periods=12)
    feats = pd.DataFrame({
        "date": dates, "ticker": "A.TW", "r1": range(12), "r5": [x * 10 for x in range(12)], "r10": 0.0,
        "vol_shock": 0.0, "fwd5": [x / 100 for x in range(12)],
    })
    base = pd.DataFrame({"i": [5], "date": [dates[5]], "ticker": ["A.TW"], "sector": ["S"]})
    return base, feats, dates


def test_skip_uses_previous_day_features(data):
    base, feats, _ = data
    out = st.attach(base, feats, skip=True)
    assert out["r1"].iloc[0] == 4          # 預測日是第 6 天（索引 5），只能看到索引 4
    assert out["rev_1d"].iloc[0] == -4
    assert out["fwd5"].iloc[0] == pytest.approx(0.05)  # 報酬從預測日收盤起算


def test_no_skip_uses_same_day_features(data):
    base, feats, _ = data
    assert st.attach(base, feats, skip=False)["r1"].iloc[0] == 5


def test_lead_lag_uses_top_cap_tercile_as_leaders():
    df = pd.DataFrame({
        "i": 0, "date": pd.Timestamp("2024-01-02"), "sector": "S", "ticker": list("ABCDEF"),
        "cap": [600, 500, 400, 300, 200, 100], "r5": [0.10, 0.08, 0.0, -0.01, 0.02, 0.03], "fwd5": 0.0,
    })
    f = st.lead_lag(df)
    assert set(f["ticker"]) == {"C", "D", "E", "F"}            # A、B 是領先股
    assert f["leader_r5"].iloc[0] == pytest.approx(0.09)
    assert f.set_index("ticker").loc["D", "ll_gap"] == pytest.approx(0.10)
