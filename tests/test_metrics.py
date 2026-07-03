"""評估指標測試：Brier、機率轉換、ECE、方向準確率、校準曲線（規格第 6 節）。"""
import math

import pytest

from backtest.metrics import (
    brier_score,
    calibration_bins,
    directional_accuracy,
    ece,
    mean_brier,
    reliability_diagram,
    signal_to_probability,
)


class TestSignalToProbability:
    def test_spec_mapping(self):
        # 規格 6.1：bullish → conf、bearish → 1-conf、neutral → 0.5
        assert signal_to_probability("bullish", 0.8) == pytest.approx(0.8)
        assert signal_to_probability("bearish", 0.8) == pytest.approx(0.2)
        assert signal_to_probability("neutral", 0.99) == 0.5

    def test_unknown_signal(self):
        with pytest.raises(ValueError):
            signal_to_probability("hold", 0.5)


class TestBrier:
    def test_known_values(self):
        assert brier_score(1.0, 1) == 0.0
        assert brier_score(0.0, 1) == 1.0
        assert brier_score(0.7, 1) == pytest.approx(0.09)
        assert brier_score(0.7, 0) == pytest.approx(0.49)

    def test_mean(self):
        assert mean_brier([1.0, 0.0], [1, 0]) == 0.0
        assert mean_brier([0.5, 0.5], [1, 0]) == pytest.approx(0.25)

    def test_invalid_inputs(self):
        with pytest.raises(ValueError):
            brier_score(0.5, 2)
        with pytest.raises(ValueError):
            brier_score(1.2, 1)


class TestDirectionalAccuracy:
    def test_neutral_excluded(self):
        acc, n = directional_accuracy(["bullish", "neutral", "bearish"], [1, 1, 1])
        # bullish 命中、bearish 未命中，neutral 不計
        assert n == 2
        assert acc == pytest.approx(0.5)

    def test_all_neutral_nan(self):
        acc, n = directional_accuracy(["neutral"], [1])
        assert n == 0
        assert math.isnan(acc)


class TestECE:
    def test_perfectly_calibrated_bin(self):
        # 10 筆 p=0.75，其中 7.5 成命中不可能 → 用 0.8：8 筆命中 → |0.75-0.8|=0.05...
        # 改用精確可整除的例子：p=0.7 十筆、7 筆命中 → ECE = 0
        ps = [0.7] * 10
        os_ = [1] * 7 + [0] * 3
        assert ece(ps, os_) == pytest.approx(0.0, abs=1e-9)

    def test_known_miscalibration(self):
        # 全部 p=0.9 但命中率 0.5 → ECE = 0.4
        ps = [0.9] * 10
        os_ = [1] * 5 + [0] * 5
        assert ece(ps, os_) == pytest.approx(0.4)

    def test_weighted_across_bins(self):
        # 桶1：4 筆 p=0.25、命中率 0.25（偏差 0）
        # 桶2：6 筆 p=0.85、命中率 0.5（偏差 0.35）→ ECE = 0.6*0.35 = 0.21
        ps = [0.25] * 4 + [0.85] * 6
        os_ = [1, 0, 0, 0] + [1, 1, 1, 0, 0, 0]
        assert ece(ps, os_) == pytest.approx(0.21)

    def test_empty(self):
        assert math.isnan(ece([], []))


class TestReliabilityDiagram:
    def test_bins_structure(self):
        rows = calibration_bins([0.05, 0.15, 0.95], [0, 0, 1])
        assert all(len(r) == 3 for r in rows)
        assert sum(r[2] for r in rows) == 3

    def test_last_bin_includes_one(self):
        rows = calibration_bins([1.0], [1], n_bins=10)
        assert rows == [(1.0, 1.0, 1)]

    def test_writes_png(self, tmp_path):
        path = tmp_path / "calib.png"
        result = reliability_diagram([0.2, 0.5, 0.8, 0.9], [0, 1, 1, 1], str(path), title="test")
        assert path.exists()
        assert path.stat().st_size > 0
        assert result == str(path)
