"""報酬層級評估測試：含息還原、Rank IC、long/neutral 組合、績效統計。"""
import math

import numpy as np
import pandas as pd
import pytest

from backtest.portfolio import (
    evaluate_returns,
    long_neutral_returns,
    max_drawdown,
    performance_stats,
    rank_ic,
    spearman,
)
from data.fetch_financials import total_return_index


class TestTotalReturnIndex:
    def test_split_is_neutralized(self):
        # 0050 式一拆四：未還原價 200 → 50，含息還原後報酬應為 0
        prices = pd.DataFrame(
            {"date": pd.to_datetime(["2025-06-17", "2025-06-18"]), "close": [200.0, 50.0]}
        )
        events = pd.DataFrame(
            {"date": pd.to_datetime(["2025-06-18"]), "before_price": [200.0], "after_price": [50.0]}
        )
        adj = total_return_index(prices, events)
        assert adj.iloc[1] / adj.iloc[0] - 1 == pytest.approx(0.0)

    def test_cash_dividend_reinvested(self):
        # 除息 5 元（100 → 95），之後股價回到 100 → 總報酬 = 100/95 - 1
        prices = pd.DataFrame(
            {"date": pd.to_datetime(["2024-06-20", "2024-06-24", "2024-07-01"]), "close": [100.0, 95.0, 100.0]}
        )
        events = pd.DataFrame(
            {"date": pd.to_datetime(["2024-06-24"]), "before_price": [100.0], "after_price": [95.0]}
        )
        adj = total_return_index(prices, events)
        assert adj.iloc[2] / adj.iloc[0] - 1 == pytest.approx(100 / 95 - 1)
        # 向後連乘：除息前的價格維持原值，除息日起乘上 before/after
        assert adj.iloc[0] == pytest.approx(100.0)
        assert adj.iloc[1] == pytest.approx(100.0)

    def test_no_events_equals_close(self):
        prices = pd.DataFrame({"date": pd.to_datetime(["2024-01-02"]), "close": [10.0]})
        events = pd.DataFrame(columns=["date", "before_price", "after_price"])
        assert total_return_index(prices, events).iloc[0] == 10.0


class TestRankIC:
    def test_spearman_perfect_and_ties(self):
        assert spearman(pd.Series([1, 2, 3]), pd.Series([10, 20, 30])) == pytest.approx(1.0)
        assert spearman(pd.Series([3, 2, 1]), pd.Series([10, 20, 30])) == pytest.approx(-1.0)
        assert math.isnan(spearman(pd.Series([0.5, 0.5, 0.5]), pd.Series([1, 2, 3])))

    def test_cross_sectional_skips_constant_dates(self):
        df = pd.DataFrame(
            {
                "as_of_date": ["d1"] * 3 + ["d2"] * 3,
                "p": [0.4, 0.5, 0.6, 0.5, 0.5, 0.5],
                "forward_return": [-0.1, 0.0, 0.1, 0.3, -0.2, 0.1],
            }
        )
        out = rank_ic(df, "p")
        assert out["n_cs_dates"] == 1  # d2 機率全相同 → 略過
        assert out["ic_cs_mean"] == pytest.approx(1.0)
        assert out["n_pooled"] == 6


class TestLongNeutral:
    def make_df(self):
        return pd.DataFrame(
            {
                "as_of_date": ["d1", "d1", "d2", "d2"],
                "ticker": ["A", "B", "A", "B"],
                "sig": ["bullish", "neutral", "neutral", "bearish"],
                "forward_return": [0.10, -0.20, 0.05, 0.03],
            }
        )

    def test_gross_turnover_and_cash(self):
        port = long_neutral_returns(self.make_df(), "sig", cost_per_side=0.01)
        d1, d2 = port.iloc[0], port.iloc[1]
        # d1：只持有 A，從空手建倉 → turnover 1
        assert d1["gross"] == pytest.approx(0.10)
        assert d1["turnover"] == pytest.approx(1.0)
        assert d1["net"] == pytest.approx(0.10 - 0.01)
        # d2：沒有 bullish → 持現金，賣出 A → turnover 1
        assert d2["gross"] == 0.0
        assert d2["n_long"] == 0
        assert d2["net"] == pytest.approx(-0.01)

    def test_equal_weight_universe(self):
        port = long_neutral_returns(self.make_df(), None, cost_per_side=0.0)
        assert port["gross"].tolist() == pytest.approx([-0.05, 0.04])
        assert port["turnover"].tolist() == pytest.approx([1.0, 0.0])


class TestPerformance:
    def test_max_drawdown(self):
        # 1 → 1.1 → 0.88 → 0.968：最大回撤 = 0.88/1.1 - 1 = -20%
        assert max_drawdown(np.array([0.1, -0.2, 0.1])) == pytest.approx(-0.2)

    def test_excess_vs_benchmark(self):
        idx = ["d1", "d2"]
        r = pd.Series([0.10, 0.00], index=idx)
        b = pd.Series([0.05, 0.05], index=idx)
        s = performance_stats(r, b, periods_per_year=12)
        assert s["total_return"] == pytest.approx(0.10)
        assert s["bench_total_return"] == pytest.approx(1.05**2 - 1)
        assert s["excess_mean_per_period"] == pytest.approx(0.0)
        assert s["excess_hit_rate"] == pytest.approx(0.5)

    def test_evaluate_returns_end_to_end(self, tmp_path):
        rng = np.random.default_rng(0)
        rows = []
        for d in pd.bdate_range("2024-01-02", periods=12, freq="21B"):
            bench = rng.normal(0.01, 0.04)
            for t in ["A", "B", "C"]:
                p = rng.uniform(0.3, 0.7)
                rows.append(
                    {
                        "as_of_date": d.strftime("%Y-%m-%d"),
                        "ticker": t,
                        "forward_return": rng.normal(0.0, 0.08),
                        "benchmark_return": bench,
                        "s_signal": "bullish" if p > 0.55 else "neutral",
                        "s_p": p,
                    }
                )
        summary, periods = evaluate_returns(
            pd.DataFrame(rows), {"s": "strategy"}, step_days=21, plot_path=str(tmp_path / "eq.png")
        )
        assert set(summary["strategy"]) == {"s", "equal_weight", "benchmark_0050"}
        assert len(periods) == 12
        assert (tmp_path / "eq.png").exists()
        assert math.isfinite(summary.set_index("strategy").loc["s", "ic_pooled"])
