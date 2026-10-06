"""總經/籌碼 Agent 測試：特徵計算、方向判斷、look-ahead 防護（規格 3.5）。"""
import numpy as np
import pandas as pd
import pytest

from agents.macro_agent import MacroAgent
from data.fetch_macro import FinMindMacroProvider, MacroDataProvider, _net_by_investor

REQUIRED_KEYS = {
    "agent_id", "ticker", "as_of_date", "signal", "confidence",
    "horizon_days", "rationale", "evidence_refs", "raw_features",
}
AS_OF = "2025-06-30"
N = 80  # 足夠涵蓋 60 日的美債窗口


def ramp(start, end, n=N):
    return np.linspace(start, end, n)


class FixtureMacro(MacroDataProvider):
    """以線性序列模擬各指標；trend=+1 全部偏多、-1 全部偏空、0 持平。"""

    def __init__(self, trend=1, chip_trend=None, empty=False):
        self.dates = pd.bdate_range(end=pd.Timestamp(AS_OF) - pd.Timedelta(days=1), periods=N)
        self.t = trend
        self.c = trend if chip_trend is None else chip_trend
        self.empty = empty

    def _df(self, **cols):
        if self.empty:
            return pd.DataFrame(columns=["date", *cols])
        return pd.DataFrame({"date": self.dates, **cols})

    def get_institutional_net(self, ticker, as_of_date):
        return self._df(foreign_net=np.full(N, 1e6 * self.c), trust_net=np.full(N, 1e5 * self.c))

    def get_shareholding(self, ticker, as_of_date):
        return self._df(foreign_ratio_pct=ramp(40, 40 + 8 * self.c), shares_issued=np.full(N, 4e8))

    def get_margin_balance(self, ticker, as_of_date):
        # 融資為反向指標：偏多情境下融資減少
        return self._df(margin_balance=ramp(10000, 10000 * (1 - 0.6 * self.c)))

    def get_usd_twd(self, as_of_date):
        return self._df(rate=ramp(30, 30 * (1 + 0.1 * self.t)))

    def get_us10y(self, as_of_date):
        return self._df(yield_pct=ramp(4.5, 4.5 - 1.0 * self.t))

    def get_market_foreign_net(self, as_of_date):
        return self._df(foreign_net=np.full(N, 1e10 * self.t))


class TestMacroAgent:
    def test_all_positive_is_bullish(self):
        out = MacroAgent(FixtureMacro(trend=1)).analyze("2327.TW", AS_OF)
        assert out.signal == "bullish"
        assert out.agent_id == "macro_agent"
        assert out.confidence > 0.6
        for key in ("foreign_ratio_chg_pp", "trust_net_pct_shares", "margin_balance_chg_pct",
                    "usd_twd_chg_pct", "us10y_chg_bp", "market_foreign_net_e8"):
            assert key in out.raw_features

    def test_all_negative_is_bearish(self):
        assert MacroAgent(FixtureMacro(trend=-1)).analyze("2327.TW", AS_OF).signal == "bearish"

    def test_flat_is_neutral(self):
        assert MacroAgent(FixtureMacro(trend=0)).analyze("2327.TW", AS_OF).signal == "neutral"

    def test_chip_vs_macro_conflict_lowers_confidence(self):
        aligned = MacroAgent(FixtureMacro(trend=1)).analyze("2327.TW", AS_OF)
        conflicted = MacroAgent(FixtureMacro(trend=1, chip_trend=-1)).analyze("2327.TW", AS_OF)
        assert conflicted.confidence < aligned.confidence
        assert "矛盾" in conflicted.rationale

    def test_margin_is_contrarian(self):
        # 只有融資餘額大增 → 偏空分量
        signal, _, rationale, score = MacroAgent.rule_based_judgement({"margin_balance_chg_pct": 40.0})
        assert score == pytest.approx(-1.0)
        assert "融資餘額偏空" in rationale

    def test_feature_values(self):
        feats = MacroAgent(FixtureMacro(trend=1)).compute_features("2327.TW", AS_OF)
        # 投信每日 1e5 股 × 20 日 / 4e8 股 = 0.5%
        assert feats["trust_net_pct_shares"] == pytest.approx(0.5)
        # 大盤外資每日 100 億 × 20 日 = 2000 億
        assert feats["market_foreign_net_e8"] == pytest.approx(2000.0)

    def test_no_data_is_neutral_low_confidence(self):
        out = MacroAgent(FixtureMacro(empty=True)).analyze("2327.TW", AS_OF)
        assert out.signal == "neutral"
        assert out.confidence <= 0.3

    def test_schema_conformance(self):
        out = MacroAgent(FixtureMacro()).analyze("2327.TW", AS_OF)
        assert set(out.to_dict().keys()) == REQUIRED_KEYS


class FakeClient:
    """回傳固定資料的 FinMindClient 替身，記錄呼叫次數。"""

    def __init__(self, tables):
        self.tables = tables
        self.calls = 0

    def get(self, dataset, data_id, start_date, end_date=None):
        self.calls += 1
        return self.tables[dataset].copy()


class TestFinMindMacroProvider:
    def test_excludes_as_of_date_and_later(self):
        # 法人資料收盤後才公布，as_of 當天的資料不可使用
        raw = pd.DataFrame(
            {
                "date": ["2025-06-27", "2025-06-27", "2025-06-30", "2025-06-30"],
                "name": ["Foreign_Investor", "Investment_Trust"] * 2,
                "buy": [100, 50, 999, 999],
                "sell": [40, 10, 0, 0],
            }
        )
        client = FakeClient({"TaiwanStockInstitutionalInvestorsBuySell": raw})
        df = FinMindMacroProvider(client).get_institutional_net("2327.TW", "2025-06-30")
        assert len(df) == 1
        assert df["foreign_net"].iloc[0] == 60
        assert df["trust_net"].iloc[0] == 40

    def test_dataset_loaded_once(self):
        raw = pd.DataFrame({"date": ["2025-01-02"], "currency": ["USD"], "spot_buy": [32.0]})
        client = FakeClient({"TaiwanExchangeRate": raw})
        provider = FinMindMacroProvider(client)
        provider.get_usd_twd("2025-03-01")
        provider.get_usd_twd("2025-04-01")
        assert client.calls == 1

    def test_net_by_investor_missing_column(self):
        raw = pd.DataFrame({"date": ["2025-01-02"], "name": ["Foreign_Investor"], "buy": [5], "sell": [2]})
        out = _net_by_investor(raw)
        assert out["foreign_net"].iloc[0] == 3
        assert out["trust_net"].iloc[0] == 0
