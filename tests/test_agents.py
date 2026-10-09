"""Agent 輸出 schema 與兩個 MVP Agent 的行為測試（規格 3.1-3.3）。"""
import numpy as np
import pandas as pd
import pytest

from agents.base import SIGNAL_TO_SCORE, AgentOutput, BaseAgent
from agents.fundamentals_agent import FundamentalsAgent
from agents.news_agent import NewsAgent, extract_events
from data.fetch_financials import FundamentalsDataProvider
from data.fetch_news import (
    TIER_ANNOUNCEMENT,
    TIER_FORUM,
    TIER_MEDIA,
    NewsItem,
    NewsProvider,
    classify_source_tier,
    dedupe_and_sort,
)

REQUIRED_KEYS = {
    "agent_id", "ticker", "as_of_date", "signal", "confidence",
    "horizon_days", "rationale", "evidence_refs", "raw_features",
}


def make_output(**kw):
    base = dict(
        agent_id="x", ticker="2327.TW", as_of_date="2025-01-01", signal="bullish",
        confidence=0.7, horizon_days=20, rationale="r", evidence_refs=[], raw_features={},
    )
    base.update(kw)
    return AgentOutput(**base)


class TestAgentOutputSchema:
    def test_to_dict_has_exact_spec_keys(self):
        assert set(make_output().to_dict().keys()) == REQUIRED_KEYS

    def test_invalid_signal_rejected(self):
        with pytest.raises(ValueError):
            make_output(signal="buy")

    @pytest.mark.parametrize("conf", [-0.1, 1.1])
    def test_confidence_bounds(self, conf):
        with pytest.raises(ValueError):
            make_output(confidence=conf)

    def test_bad_date_rejected(self):
        with pytest.raises(ValueError):
            make_output(as_of_date="2025/01/01")

    def test_rationale_truncated_to_200(self):
        out = make_output(rationale="甲" * 300)
        assert len(out.rationale) <= 200

    def test_score_mapping(self):
        assert make_output(signal="bullish").score == 1
        assert make_output(signal="bearish").score == -1
        assert make_output(signal="neutral").score == 0
        assert SIGNAL_TO_SCORE == {"bullish": 1, "neutral": 0, "bearish": -1}


# ---------------------------------------------------------------------------
# 財報 Agent
# ---------------------------------------------------------------------------

class FixtureFundamentals(FundamentalsDataProvider):
    """可注入任意月營收/季報數列的測試 provider。"""

    def __init__(self, revenues, gross_margins=None, inventory_days=None, receivable_days=None):
        self.revenues = revenues
        self.gross_margins = gross_margins or []
        self.inventory_days = inventory_days or []
        self.receivable_days = receivable_days or []

    def get_monthly_revenue(self, ticker, as_of_date):
        dates = pd.date_range("2022-01-01", periods=len(self.revenues), freq="MS")
        return pd.DataFrame({"date": dates, "revenue": self.revenues})

    def get_quarterly_financials(self, ticker, as_of_date):
        n = max(len(self.gross_margins), len(self.inventory_days), len(self.receivable_days), 1)
        def pad(xs):
            return list(xs) + [np.nan] * (n - len(xs))
        return pd.DataFrame(
            {
                "date": pd.date_range("2022-03-31", periods=n, freq="QE"),
                "gross_margin": pad(self.gross_margins),
                "inventory_days": pad(self.inventory_days),
                "receivable_days": pad(self.receivable_days),
            }
        )


class TestFundamentalsAgent:
    def test_strong_growth_is_bullish(self):
        # 月營收逐月大幅成長、毛利率走升、存貨天數下降
        revenues = [100 * (1.05 ** i) for i in range(24)]
        provider = FixtureFundamentals(
            revenues,
            gross_margins=[20, 21, 22, 24, 25, 27],
            inventory_days=[90, 88, 85, 82, 78, 70],
        )
        out = FundamentalsAgent(provider).analyze("2327.TW", "2025-01-15")
        assert out.signal == "bullish"
        assert out.confidence > 0.4
        assert out.agent_id == "fundamentals_agent"
        assert "revenue_yoy_pct" in out.raw_features

    def test_decline_is_bearish(self):
        revenues = [100 * (0.94 ** i) for i in range(24)]
        provider = FixtureFundamentals(
            revenues,
            gross_margins=[30, 28, 26, 23, 20, 18],
            inventory_days=[70, 78, 85, 95, 110, 130],
        )
        out = FundamentalsAgent(provider).analyze("2327.TW", "2025-01-15")
        assert out.signal == "bearish"

    def test_no_data_is_neutral_low_confidence(self):
        out = FundamentalsAgent(FixtureFundamentals([])).analyze("2327.TW", "2025-01-15")
        assert out.signal == "neutral"
        assert out.confidence <= 0.3

    def test_conflicting_signals_lower_confidence(self):
        # 營收強勁但毛利率崩跌 + 存貨暴增 → 矛盾，信心應下降且 rationale 說明
        revenues = [100 * (1.06 ** i) for i in range(24)]
        conflicted = FixtureFundamentals(
            revenues,
            gross_margins=[30, 27, 24, 20, 16, 12],
            inventory_days=[70, 85, 100, 120, 150, 200],
        )
        aligned = FixtureFundamentals(
            revenues,
            gross_margins=[20, 22, 24, 26, 28, 30],
            inventory_days=[90, 85, 80, 75, 70, 65],
        )
        out_conflict = FundamentalsAgent(conflicted).analyze("2327.TW", "2025-01-15")
        out_aligned = FundamentalsAgent(aligned).analyze("2327.TW", "2025-01-15")
        assert out_conflict.confidence < out_aligned.confidence
        assert "矛盾" in out_conflict.rationale

    def test_schema_conformance(self):
        out = FundamentalsAgent(FixtureFundamentals([100] * 24)).analyze("2327.TW", "2025-01-15")
        assert set(out.to_dict().keys()) == REQUIRED_KEYS


# ---------------------------------------------------------------------------
# 新聞 Agent
# ---------------------------------------------------------------------------

class FixtureNews(NewsProvider):
    def __init__(self, items):
        self.items = items

    def get_news(self, ticker, start_date, end_date):
        return dedupe_and_sort(self.items)


def news(title, source, days_ago=1, as_of="2025-06-30"):
    published = (pd.Timestamp(as_of) - pd.Timedelta(days=days_ago)).to_pydatetime()
    return NewsItem(title=title, source=source, published=published)


class TestNewsAgent:
    AS_OF = "2025-06-30"

    def test_positive_announcements_bullish(self):
        items = [
            news("國巨宣布擴產高階 MLCC 產線", "公開資訊觀測站重大訊息", 2),
            news("外資調升目標價 看好接單暢旺", "經濟日報", 3),
        ]
        out = NewsAgent(FixtureNews(items)).analyze("2327.TW", self.AS_OF)
        assert out.signal == "bullish"
        assert out.raw_features["n_news"] == 2

    def test_negative_news_bearish(self):
        items = [
            news("傳大客戶砍單 產品跌價壓力大", "工商時報", 1),
            news("匯損侵蝕獲利 下修全年展望", "鉅亨網", 2),
        ]
        out = NewsAgent(FixtureNews(items)).analyze("2327.TW", self.AS_OF)
        assert out.signal == "bearish"

    def test_no_news_neutral(self):
        out = NewsAgent(FixtureNews([])).analyze("2327.TW", self.AS_OF)
        assert out.signal == "neutral"
        assert out.confidence <= 0.3

    def test_source_tier_outweighs_forum(self):
        # 高可信度公告(擴產,+1) vs 論壇利空(砍單,-1)：公告 tier 1.0 > 論壇 0.4
        items = [
            news("公司公告擴產計畫", "公開資訊觀測站", 1),
            news("網友爆料客戶砍單", "PTT股板", 1),
        ]
        out = NewsAgent(FixtureNews(items)).analyze("2327.TW", self.AS_OF)
        assert out.raw_features["rule_score"] > 0

    def test_forum_only_low_confidence(self):
        strong_src = [news("宣布擴產", "公開資訊觀測站", 1), news("再宣布擴產新廠", "公開資訊觀測站", 2)]
        forum_src = [news("宣布擴產", "PTT股板", 1), news("再宣布擴產新廠", "Dcard", 2)]
        out_strong = NewsAgent(FixtureNews(strong_src)).analyze("2327.TW", self.AS_OF)
        out_forum = NewsAgent(FixtureNews(forum_src)).analyze("2327.TW", self.AS_OF)
        assert out_forum.confidence < out_strong.confidence

    def test_schema_conformance(self):
        out = NewsAgent(FixtureNews([news("擴產", "經濟日報", 1)])).analyze("2327.TW", self.AS_OF)
        assert set(out.to_dict().keys()) == REQUIRED_KEYS


class TestNewsHelpers:
    def test_source_tiers(self):
        assert classify_source_tier("公開資訊觀測站") == TIER_ANNOUNCEMENT
        assert classify_source_tier("經濟日報") == TIER_MEDIA
        assert classify_source_tier("PTT") == TIER_FORUM

    def test_dedupe_keeps_higher_tier(self):
        a = news("國巨擴產", "PTT", 1)
        b = news("國巨擴產", "公開資訊觀測站", 2)
        kept = dedupe_and_sort([a, b])
        assert len(kept) == 1
        assert kept[0].source_tier == TIER_ANNOUNCEMENT

    def test_longer_keyword_wins(self):
        # 「調降目標價」不應同時再計入「調降」
        events = extract_events(news("外資調降目標價", "經濟日報", 1))
        assert events == [("target_price_down", -1)]


class _StubAgent(BaseAgent):
    agent_id = "stub"

    def __init__(self, signal, confidence):
        self.signal, self.confidence = signal, confidence

    def analyze(self, ticker, as_of_date):
        return self._build_output(ticker, as_of_date, self.signal, self.confidence, "r")


class TestDirectionalConfidenceFloor:
    def test_directional_floored_to_half(self):
        # bullish 但 confidence 0.3 → 機率會落在看空側，需拉到 0.5
        out = _StubAgent("bullish", 0.3).analyze("2327.TW", "2025-01-01")
        assert out.confidence == 0.5
        assert out.raw_features["confidence_raw"] == pytest.approx(0.3)
        assert _StubAgent("bearish", 0.1).analyze("2327.TW", "2025-01-01").confidence == 0.5

    def test_neutral_and_strong_untouched(self):
        neutral = _StubAgent("neutral", 0.2).analyze("2327.TW", "2025-01-01")
        assert neutral.confidence == pytest.approx(0.2)
        assert "confidence_raw" not in neutral.raw_features
        assert _StubAgent("bullish", 0.7).analyze("2327.TW", "2025-01-01").confidence == pytest.approx(0.7)



class TestContinuousOutput:
    def test_mapping_monotonic_and_bounded(self):
        from agents.base import continuous_judgement
        from backtest.metrics import signal_to_probability

        ps = [continuous_judgement(sc, 1.0)[2] for sc in (-1, -0.5, -0.1, 0.1, 0.5, 1)]
        assert ps == sorted(ps)
        assert ps[0] == pytest.approx(0.25) and ps[-1] == pytest.approx(0.75)
        for sc in (-0.7, 0.05, 0.9):
            sig, conf, p = continuous_judgement(sc, 0.8)
            assert conf >= 0.5
            assert signal_to_probability(sig, conf) == pytest.approx(p)  # 規格 6.1 換算還原 p

    def test_zero_score_or_no_evidence_is_neutral(self):
        from agents.base import continuous_judgement

        assert continuous_judgement(0.0, 1.0)[0] == "neutral"
        assert continuous_judgement(0.8, 0.0)[0] == "neutral"

    def test_less_evidence_shrinks_toward_half(self):
        from agents.base import continuous_judgement

        assert continuous_judgement(0.6, 0.4)[2] < continuous_judgement(0.6, 1.0)[2]

    def test_small_score_keeps_direction_unlike_threshold(self):
        # 門檻模式下分數 0.1 會是中性；連續模式保留微弱的看多
        revenues = [100 * (1.005 ** i) for i in range(24)]
        th = FundamentalsAgent(FixtureFundamentals(revenues)).analyze("2327.TW", "2025-01-15")
        co = FundamentalsAgent(FixtureFundamentals(revenues), output_mode="continuous").analyze("2327.TW", "2025-01-15")
        assert th.signal == "neutral"
        assert co.signal == "bullish" and 0.5 < co.confidence < 0.6
        assert co.raw_features["output_mode"] == "continuous"

    def test_invalid_mode(self):
        with pytest.raises(ValueError):
            FundamentalsAgent(FixtureFundamentals([]), output_mode="fuzzy")
