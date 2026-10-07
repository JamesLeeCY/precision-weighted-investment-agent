"""Agent 層級重新校準測試：收縮公式、擬合方向、冷啟動、walk-forward 整合。"""
import numpy as np
import pytest

from agents.base import AgentOutput
from arbitrator.calibration import AgentCalibrator, apply_slope, fit_slope
from arbitrator.precision_tracker import PrecisionTracker
from backtest.run_backtest import PredictionEvent, calibrated_output, run_walk_forward


class TestApplySlope:
    def test_identity_and_full_shrink(self):
        assert apply_slope(0.8, 1.0) == pytest.approx(0.8)
        assert apply_slope(0.8, 0.0) == pytest.approx(0.5)

    def test_neutral_fixed_and_side_preserved(self):
        assert apply_slope(0.5, 0.3) == pytest.approx(0.5)
        assert 0.5 < apply_slope(0.9, 0.3) < 0.9
        assert 0.1 < apply_slope(0.1, 0.3) < 0.5


class TestFitSlope:
    def test_coin_flip_agent_shrinks_to_zero(self):
        # 信心 0.9 但命中率 50% → 毫無判讀能力，a 應收縮到接近 0
        ps = [0.9] * 50 + [0.1] * 50
        os_ = [1, 0] * 25 + [1, 0] * 25
        assert fit_slope(ps, os_, prior_strength=2.0) < 0.05

    def test_calibrated_agent_keeps_slope(self):
        # 說 0.7 時真的 70% 命中 → 不需修正
        rng = np.random.default_rng(0)
        ps = [0.7] * 200 + [0.3] * 200
        os_ = list((rng.random(200) < 0.7).astype(int)) + list((rng.random(200) < 0.3).astype(int))
        assert fit_slope(ps, os_, prior_strength=2.0) > 0.85

    def test_prior_tempers_small_sample(self):
        # 只有 3 筆失準樣本 → 先驗讓 a 收縮得比無先驗時少
        ps, os_ = [0.9, 0.9, 0.9], [0, 1, 0]
        assert fit_slope(ps, os_, prior_strength=2.0) > fit_slope(ps, os_, prior_strength=0.0)


class TestAgentCalibrator:
    def test_cold_start_no_change(self):
        cal = AgentCalibrator(min_n=10)
        for _ in range(9):
            cal.record("a", 0.9, 0)
        assert cal.slope("a") == 1.0
        assert cal.calibrate("a", 0.9) == pytest.approx(0.9)

    def test_refits_after_new_data(self):
        cal = AgentCalibrator(min_n=10, prior_strength=0.0)
        for i in range(20):
            cal.record("a", 0.9, i % 2)
        shrunk = cal.slope("a")
        assert shrunk < 0.1
        for _ in range(200):
            cal.record("a", 0.9, 1)
        assert cal.slope("a") > shrunk

    def test_agents_independent(self):
        cal = AgentCalibrator(min_n=2, prior_strength=0.0)
        for i in range(10):
            cal.record("bad", 0.9, i % 2)
        assert cal.slope("good") == 1.0


def out(agent, signal, conf, ticker, date):
    return AgentOutput(agent_id=agent, ticker=ticker, as_of_date=date, signal=signal,
                       confidence=conf, horizon_days=20, rationale="r")


def test_calibrated_output_keeps_direction():
    o = out("a", "bearish", 0.9, "2327.TW", "2025-01-02")
    c = calibrated_output(o, 0.4)
    assert c.signal == "bearish" and c.confidence == pytest.approx(0.6)
    n = out("a", "neutral", 0.3, "2327.TW", "2025-01-02")
    assert calibrated_output(n, 0.5) is n


def test_walk_forward_shrinks_overconfident_agent_only(tmp_path):
    """過度自信且隨機的 agent 會被校準收縮；校準良好的 agent 幾乎不變，
    且校準只使用已到期的結果。"""
    rng = np.random.default_rng(1)
    dates = [f"2024-{m:02d}-{d:02d}" for m in range(1, 13) for d in (1, 15)]
    events = []
    for i, date in enumerate(dates[:-2]):
        for t in ["A", "B", "C", "D", "E"]:
            outcome = int(rng.random() < 0.5)
            good_conf = 0.65
            good_sig = ("bullish" if outcome else "bearish") if rng.random() < good_conf else (
                "bearish" if outcome else "bullish")
            events.append(PredictionEvent(
                ticker=t, as_of_date=date, resolution_date=dates[i + 2], outcome=outcome,
                outputs={
                    "good": out("good", good_sig, good_conf, t, date),
                    "noisy": out("noisy", "bullish" if rng.random() < 0.5 else "bearish", 0.95, t, date),
                },
            ))
    tracker = PrecisionTracker(tmp_path / "p.json")
    df = run_walk_forward(events, tracker)
    first = df[df["as_of_date"] == dates[0]]
    assert (first["slope_noisy"] == 1.0).all()  # 第一期沒有任何已到期資料
    assert df["slope_noisy"].iloc[-1] < 0.2
    assert df["slope_good"].iloc[-1] > 0.7
    brier = lambda c: float(((df[c] - df["outcome"]) ** 2).mean())  # noqa: E731
    assert brier("pcal_noisy") < brier("p_noisy")
    # 校準後精度應把權重移向 good（EMA 快照有雜訊，比較後半段平均）
    late = df.iloc[len(df) // 2:]
    assert late["calprecision_good"].mean() > late["calprecision_noisy"].mean()
