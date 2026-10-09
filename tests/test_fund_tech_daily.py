"""基本面選股 + 技術面每日進出場：權重混合保持產業權重、每日濾網只用前一日資料。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "analysis"))
import fund_tech_daily as ftd  # noqa: E402


def members():
    return pd.DataFrame({
        "ticker": list("ABCDEF") + ["G", "H", "I"], "sector": ["S1"] * 6 + ["S2"] * 3,
        "pc_fundamentals_agent": [0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.9, 0.5, 0.1],
        "pc_technical": [0.1, 0.9, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5],
    })


def test_mix_weights_keep_sector_totals_and_tilt_to_technical():
    eq = ftd.select(members(), set(), mix=False)
    mx = ftd.select(members(), set(), mix=True)
    assert set(eq) == set(mx) == {"A", "B", "G"}
    assert eq["A"] == pytest.approx(eq["B"])
    assert mx["B"] > mx["A"]                      # B 技術面較強 → 權重較高
    assert mx["A"] + mx["B"] == pytest.approx(6 / 9)
    assert sum(mx.values()) == pytest.approx(1.0)


def test_daily_stock_filter_uses_previous_close():
    dates = pd.bdate_range("2024-01-01", periods=6)
    close = pd.DataFrame({"A.TW": [10, 10, 10, 5, 5, 5.0]}, index=dates)
    ma = pd.DataFrame({"A.TW": [8.0] * 6}, index=dates)       # 第 4 天（索引 3）收盤跌破均線
    daily = pd.DataFrame({"i": 0, "date": dates[1], "ticker": "A.TW", "sector": "S",
                          "pc_fundamentals_agent": 0.9, "pc_technical": 0.5}, index=[0])
    on = pd.Series(1.0, index=dates)
    bench = pd.Series(0.0, index=dates)
    s = ftd.run(daily, close, ma, ma, on, bench, phase=0, stock_ma=60).set_index("d")
    assert s.loc[dates[3], "expo"] == 1.0         # 第 4 天只看到第 3 天收盤（仍在均線上）
    assert s.loc[dates[4], "expo"] == 0.0         # 第 5 天看到第 4 天跌破 → 出場
    assert s.loc[dates[2], "net"] == pytest.approx(-0.5)  # 第 3 天持有，承受第 3 → 4 天的下跌
