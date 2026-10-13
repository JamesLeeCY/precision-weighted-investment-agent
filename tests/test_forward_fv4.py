"""前瞻規格 fv4：營收創新高的 create_time 截止、合成分數需兩者皆有、與 fv3 共用快照、凍結來源。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from forward import run_forward_fv3 as fv3  # noqa: E402
from forward import run_forward_fv4 as fv4  # noqa: E402


def test_rec24_respects_create_time_cutoff():
    months = pd.date_range("2024-01-01", periods=26, freq="MS")
    rev = pd.DataFrame({"revenue_year": months.year, "revenue_month": months.month,
                        "revenue": [100.0] * 25 + [200.0], "create_time": [None] * 25 + ["2026-03-15 10:00:00"]})
    early = fv4.rec24_signal(rev, pd.Timestamp("2026-03-10"))
    late = fv4.rec24_signal(rev, pd.Timestamp("2026-03-20"))
    assert pd.Timestamp("2026-03-01") not in early.dropna().index      # 逾期才收錄的營收不採用
    assert late.loc[pd.Timestamp("2026-03-01")] == pytest.approx(1.0)


def test_composite_needs_both_signals_and_averages_z():
    rng = np.random.default_rng(0)
    n = 30
    g = pd.DataFrame({"ticker": [f"T{i}" for i in range(n)], "sector": ["a", "b", "c"] * 10,
                      "sue": rng.normal(size=n), "rec24": rng.normal(size=n), "logcap": rng.normal(10, 1, n)})
    g.loc[0, "rec24"] = np.nan
    s = fv4.score_members(g)
    assert "T0" not in s.index and len(s) == n - 1
    import leg_probe as lp                                      # 與研究版（revmom_persist）相同的合成方式

    x = g.set_index("ticker")

    def one(col):
        z = x[col].groupby(x["sector"]).transform(lambda v: (v - v.mean()) / v.std())
        r = lp.neutralize(z, x["sector"], x["logcap"]).dropna()
        return (r - r.mean()) / r.std()

    expect = ((one("sue") + one("rec24")) / 2).dropna()
    assert (s - expect.reindex(s.index)).abs().max() < 1e-12


def test_fv4_shares_fv3_snapshot_and_has_own_records():
    assert fv4.snapshot("2026-10-13").cache_dir == fv3.snapshot("2026-10-13").cache_dir
    assert fv4.PREDICTIONS.parent.name == "fv4" and fv3.PREDICTIONS.parent.name == "fv3"
    assert {"fv4.rec24_signal", "fv4.score_members", "ls_turnover.ew_ls_buffer"} <= set(fv4.frozen_sources())
