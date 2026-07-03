"""仲裁層測試：合併公式精確值、閾值、冷啟動、EMA 更新（規格 5.1-5.3）。"""
import pytest

from agents.base import AgentOutput
from arbitrator.merge import merge, score_to_signal
from arbitrator.precision_tracker import DEFAULT_PRECISION, PrecisionTracker


def out(agent_id, signal, confidence, ticker="2327.TW", date="2025-01-01"):
    return AgentOutput(
        agent_id=agent_id, ticker=ticker, as_of_date=date, signal=signal,
        confidence=confidence, horizon_days=20, rationale="t",
        evidence_refs=[], raw_features={},
    )


class TestMergeFormula:
    def test_exact_weighted_average(self):
        # 規格 5.2：final = Σ(prec*conf*s) / Σ(prec*conf)
        outputs = [out("a", "bullish", 0.8), out("b", "bearish", 0.5)]
        precisions = {"a": 5.0, "b": 2.0}
        # num = 5*0.8*1 + 2*0.5*(-1) = 3.0；denom = 4+1 = 5 → 0.6
        merged = merge(outputs, precisions)
        assert merged.final_score == pytest.approx(0.6)
        assert merged.signal == "bullish"

    def test_neutral_contributes_zero_to_numerator(self):
        outputs = [out("a", "bullish", 0.6), out("b", "neutral", 0.9)]
        precisions = {"a": 1.0, "b": 1.0}
        # num = 0.6；denom = 0.6+0.9 = 1.5 → 0.4
        assert merge(outputs, precisions).final_score == pytest.approx(0.4)

    def test_thresholds(self):
        # 規格 5.2：> 0.3 bullish、< -0.3 bearish、否則 neutral（邊界含 0.3）
        assert score_to_signal(0.31) == "bullish"
        assert score_to_signal(0.3) == "neutral"
        assert score_to_signal(-0.3) == "neutral"
        assert score_to_signal(-0.31) == "bearish"

    def test_zero_confidence_denominator(self):
        merged = merge([out("a", "bullish", 0.0)], {"a": 5.0})
        assert merged.final_score == 0.0
        assert merged.signal == "neutral"
        assert merged.uncertainty == 1.0

    def test_uncertainty_formula(self):
        # uncertainty = 1 - max_precision / Σprecision
        outputs = [out("a", "bullish", 0.5), out("b", "bullish", 0.5)]
        merged = merge(outputs, {"a": 8.0, "b": 2.0})
        assert merged.uncertainty == pytest.approx(1 - 8.0 / 10.0)
        # 精度均等時 uncertainty 較高（loose coupling）
        merged_eq = merge(outputs, {"a": 5.0, "b": 5.0})
        assert merged_eq.uncertainty == pytest.approx(0.5)
        assert merged.uncertainty < merged_eq.uncertainty

    def test_probability_bullish_mapping(self):
        merged = merge([out("a", "bullish", 1.0)], {"a": 1.0})
        assert merged.probability_bullish == pytest.approx(1.0)
        merged = merge([out("a", "bearish", 1.0)], {"a": 1.0})
        assert merged.probability_bullish == pytest.approx(0.0)

    def test_probability_is_weighted_opinion_pool(self):
        # p = Σ(prec*conf*p_i) / Σ(prec*conf)，p_i 為規格 6.1 機率
        outputs = [out("a", "bullish", 0.8), out("b", "bearish", 0.5)]
        precisions = {"a": 5.0, "b": 2.0}
        # w_a=4, w_b=1；p_a=0.8, p_b=0.5 → (4*0.8 + 1*0.5)/5 = 0.74
        merged = merge(outputs, precisions)
        assert merged.probability_bullish == pytest.approx(0.74)

    def test_mixed_ticker_rejected(self):
        with pytest.raises(ValueError):
            merge([out("a", "bullish", 0.5), out("b", "bullish", 0.5, ticker="2492.TW")], {"a": 1, "b": 1})

    def test_missing_precision_rejected(self):
        with pytest.raises(KeyError):
            merge([out("a", "bullish", 0.5)], {})

    def test_evidence_trace_present(self):
        merged = merge([out("a", "bullish", 0.8), out("b", "bearish", 0.4)], {"a": 3.0, "b": 1.0})
        assert len(merged.contributions) == 2
        shares = [c["weight_share"] for c in merged.contributions]
        assert sum(shares) == pytest.approx(1.0)


class TestPrecisionTracker:
    def test_cold_start_equal_weights(self, tmp_path):
        # 完全無歷史 → 所有 Agent 拿相同精度（loose coupling）
        t = PrecisionTracker(tmp_path / "p.json")
        p = t.get_precisions(["a", "b"], "2327.TW")
        assert p["a"] == p["b"] == DEFAULT_PRECISION

    def test_ema_update_math(self, tmp_path):
        t = PrecisionTracker(tmp_path / "p.json", ema_alpha=0.2)
        t.record_outcome("a", "2327.TW", 0.10)  # 第一筆直接初始化
        rec = t.get_record("a", "2327.TW")
        assert rec["brier_score_ema"] == pytest.approx(0.10)
        t.record_outcome("a", "2327.TW", 0.30)
        # 0.2*0.30 + 0.8*0.10 = 0.14
        rec = t.get_record("a", "2327.TW")
        assert rec["brier_score_ema"] == pytest.approx(0.14)
        assert rec["n_predictions"] == 2

    def test_precision_definition(self, tmp_path):
        # 規格 5.1：precision = 1 / (brier_ema + 0.01)
        t = PrecisionTracker(tmp_path / "p.json")
        for _ in range(6):
            t.record_outcome("a", "2327.TW", 0.18)
        rec = t.get_record("a", "2327.TW")
        assert rec["precision"] == pytest.approx(1.0 / (0.18 + 0.01))

    def test_cold_start_uses_mature_mean(self, tmp_path):
        # a 已成熟（n>=5，低 Brier）；b 尚未成熟 → b 拿成熟記錄的均值，
        # 不因單筆好運被高估、也不搶走 a 的主導權
        t = PrecisionTracker(tmp_path / "p.json", cold_start_min_n=5)
        for _ in range(6):
            t.record_outcome("a", "2327.TW", 0.05)
        t.record_outcome("b", "2327.TW", 0.01)  # b 只有 1 筆
        pa = t.get_precision("a", "2327.TW")
        pb = t.get_precision("b", "2327.TW")
        assert pb == pytest.approx(pa)  # 唯一成熟記錄的均值 = a 的精度

    def test_mature_agent_earns_higher_precision(self, tmp_path):
        t = PrecisionTracker(tmp_path / "p.json", cold_start_min_n=5)
        for _ in range(10):
            t.record_outcome("good", "2327.TW", 0.05)
            t.record_outcome("bad", "2327.TW", 0.45)
        assert t.get_precision("good", "2327.TW") > t.get_precision("bad", "2327.TW")

    def test_persistence_roundtrip(self, tmp_path):
        path = tmp_path / "p.json"
        t1 = PrecisionTracker(path)
        for _ in range(6):
            t1.record_outcome("a", "2327.TW", 0.2)
        t2 = PrecisionTracker(path)
        assert t2.get_record("a", "2327.TW")["n_predictions"] == 6
        assert t2.get_precision("a", "2327.TW") == t1.get_precision("a", "2327.TW")

    def test_record_schema_matches_spec(self, tmp_path):
        t = PrecisionTracker(tmp_path / "p.json")
        rec = t.record_outcome("fundamentals_agent", "2327.TW", 0.18)
        assert set(rec.keys()) == {"agent_id", "ticker", "n_predictions", "brier_score_ema", "precision"}

    def test_invalid_brier_rejected(self, tmp_path):
        t = PrecisionTracker(tmp_path / "p.json")
        with pytest.raises(ValueError):
            t.record_outcome("a", "2327.TW", 1.5)
