"""營收延伸訊號的定義與時點、持續性排名不含最近一個月。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "analysis"))
import revmom_persist as rp  # noqa: E402


def rev_frame(values, start="2020-01-01"):
    months = pd.date_range(start, periods=len(values), freq="MS")
    return pd.DataFrame({"revenue_year": months.year, "revenue_month": months.month, "revenue": values})


def test_record_high_and_acceleration_and_availability():
    vals = [100.0] * 24 + [150.0]                       # 第 25 個月創新高
    out = rp.revenue_extensions(rev_frame(vals)).set_index("avail_month")
    last = out.iloc[-1]
    assert out.index[-1] == pd.Timestamp("2022-02-01")  # 2022-01 營收於 2022-02 可用
    assert last["rec24"] == pytest.approx(0.5)
    assert last["accel"] == pytest.approx(0.5)           # 年增率 50% − 前 3 個月 0%
    assert last["yoy3"] == pytest.approx(350 / 300 - 1)


def test_persistence_excludes_latest_month():
    days = pd.bdate_range("2023-01-02", "2024-06-28")
    rng = np.random.default_rng(0)
    adj = pd.DataFrame(np.cumprod(1 + rng.normal(0, 0.01, (len(days), 4)), axis=0), index=days, columns=list("ABCD"))
    member = adj.notna()
    sector = pd.Series("s", index=adj.columns)
    base = rp.persistence_signals(adj, member, sector)["persist"]
    bumped = adj.copy()
    bumped.loc[bumped.index >= "2024-05-01", "A"] *= 3.0     # 只改 2024-05 的報酬
    after = rp.persistence_signals(bumped, member, sector)["persist"]
    d = pd.Timestamp("2024-06-14")
    assert after.loc[d, "A"] == pytest.approx(base.loc[d, "A"])   # 6 月的訊號不含 5 月（t−1 月）
