"""I005：產業訊號（截尾、成員門檻、排除金融）與產業多空權重。"""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "analysis"))
import industry_sue as isue  # noqa: E402


def test_industry_signal_clips_and_filters():
    names = [f"S{i}" for i in range(17)]
    sector = pd.Series(["半導體業"] * 6 + ["金融保險業"] * 6 + ["航運業"] * 5, index=names)
    sue = pd.Series([10, 1, 1, 1, 1, 1] + [5] * 6 + [-1, -1, -1, -1, None], index=names, dtype=float)
    S = isue.industry_signal(sue, sector)
    assert list(S.index) == ["半導體業"]                     # 金融排除；航運有效成員只有 4 檔
    assert S.loc["半導體業", "isue"] == pytest.approx((3 + 5) / 6)
    assert S.loc["半導體業", "breadth"] == pytest.approx(1.0)


def test_industry_ls_equal_weights():
    sig = pd.Series({"A": 1.0, "B": 0.0, "C": -1.0})
    sector = pd.Series({"a1": "A", "a2": "A", "b1": "B", "c1": "C", "c2": "C"})
    w = isue.industry_ls(sig, sector.index, sector, pd.Series({"c1": True, "c2": False}))
    assert w["a1"] == pytest.approx(0.5) and w["a2"] == pytest.approx(0.5)
    assert w["c1"] == pytest.approx(-1.0) and "c2" not in w.index and "b1" not in w.index
