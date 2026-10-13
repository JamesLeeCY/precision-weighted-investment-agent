"""等權多空的權重與可借量資料的時點。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "analysis"))
import borrow_capacity as bc  # noqa: E402

SECTOR = pd.Series({"A": "s1", "B": "s1", "C": "s1", "D": "s2", "E": "s2", "F": "s2", "G": "s3"})
SCORE = pd.Series({"A": 3.0, "B": 2.0, "C": 1.0, "D": 1.0, "E": 2.0, "F": 3.0, "G": 5.0})


def test_ew_long_short_is_dollar_neutral_and_sector_weighted_by_count():
    w = bc.ew_long_short(SCORE, SECTOR)
    assert w[w > 0].sum() == pytest.approx(1.0) and w[w < 0].sum() == pytest.approx(-1.0)
    assert "G" not in w.index                                  # 成員 < 3 的產業不做
    assert w["A"] == pytest.approx(0.5) and w["C"] == pytest.approx(-0.5)


def test_ew_long_short_drops_sector_without_shortable_names():
    shortable = pd.Series({"C": True, "D": False})
    w = bc.ew_long_short(SCORE, SECTOR, shortable)
    assert set(w.index) == {"A", "C"} and w["A"] == pytest.approx(1.0)


def test_short_data_uses_previous_day_and_lots_to_shares():
    days = pd.bdate_range("2024-01-01", periods=3)
    sbl = pd.DataFrame({"date": [d.strftime("%Y-%m-%d") for d in days], "SBLShortSalesQuota": [100, 200, 300]})
    lend = pd.DataFrame({"date": [days[0].strftime("%Y-%m-%d")], "volume": [5]})

    class C:
        def get(self, ds, *a):
            return sbl if ds == "TaiwanDailyShortSaleBalances" else lend

    q, l60 = bc.load_short_data(C(), ["X.TW"], days)
    assert np.isnan(q.iloc[0, 0]) and q.iloc[1, 0] == 100   # 換倉日只看到前一日額度
    assert l60.iloc[1, 0] == 5000                           # 5 張 = 5,000 股
