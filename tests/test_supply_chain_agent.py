"""供應鏈 Agent 測試：圖譜載入、超額報酬計算、方向判斷、look-ahead 防護。"""
import json

import numpy as np
import pandas as pd
import pytest

from agents.supply_chain_agent import SupplyChainAgent
from data.fetch_supply_chain import MARKET_INDEX, FinMindSupplyChainProvider, SupplyChainDataProvider, load_graph

AS_OF = "2025-06-30"
REQUIRED_KEYS = {
    "agent_id", "ticker", "as_of_date", "signal", "confidence",
    "horizon_days", "rationale", "evidence_refs", "raw_features",
}
GRAPH = {
    "edges": {
        "2492.TW": [
            {"to": "2382.TW", "relation": "downstream", "weight": 1.0},
            {"to": "2317.TW", "relation": "downstream", "weight": 0.5},
            {"to": "2327.TW", "relation": "leader", "weight": 1.0},
        ],
        "9999.TW": [],
    },
    "proxies": {},
}


class FixtureChain(SupplyChainDataProvider):
    """各公司 30 日內線性漲跌 total_pct%；大盤持平。營收年增 yoy_pct%。"""

    def __init__(self, moves: dict[str, float], yoy_pct: float = 0.0, market_pct: float = 0.0):
        self.moves, self.yoy, self.market = moves, yoy_pct, market_pct

    def get_closes(self, ticker, as_of_date):
        pct = self.market if ticker == MARKET_INDEX else self.moves.get(ticker, 0.0)
        idx = pd.bdate_range(end=pd.Timestamp(as_of_date) - pd.Timedelta(days=1), periods=21)
        return pd.Series(np.linspace(100, 100 * (1 + pct / 100), 21), index=idx)

    def get_monthly_revenue(self, ticker, as_of_date):
        rev = [100.0] * 12 + [100.0 * (1 + self.yoy / 100)]
        return pd.DataFrame({"date": pd.date_range("2024-01-31", periods=13, freq="ME"), "revenue": rev})


class TestSupplyChainAgent:
    def test_strong_downstream_and_leader_is_bullish(self):
        agent = SupplyChainAgent(FixtureChain({"2382.TW": 15, "2317.TW": 15, "2327.TW": 12}, yoy_pct=40), graph=GRAPH)
        out = agent.analyze("2492.TW", AS_OF)
        assert out.signal == "bullish" and out.agent_id == "supply_chain_agent"
        assert out.raw_features["downstream_excess_ret_pct"] == pytest.approx(15.0)
        assert out.raw_features["leader_excess_ret_pct"] == pytest.approx(12.0)
        assert out.raw_features["downstream_revenue_yoy_pct"] == pytest.approx(40.0)

    def test_weak_chain_is_bearish(self):
        agent = SupplyChainAgent(FixtureChain({"2382.TW": -15, "2317.TW": -15, "2327.TW": -12}, yoy_pct=-30), graph=GRAPH)
        assert agent.analyze("2492.TW", AS_OF).signal == "bearish"

    def test_excess_is_relative_to_market(self):
        # 下游與大盤同漲 10% → 超額報酬 0
        agent = SupplyChainAgent(FixtureChain({"2382.TW": 10, "2317.TW": 10, "2327.TW": 10}, market_pct=10), graph=GRAPH)
        assert agent.compute_features("2492.TW", AS_OF)["downstream_excess_ret_pct"] == pytest.approx(0.0)

    def test_edge_weights(self):
        # 2382 權重 1.0 漲 20%、2317 權重 0.5 跌 10% → (20 − 5) / 1.5 = 10
        agent = SupplyChainAgent(FixtureChain({"2382.TW": 20, "2317.TW": -10}), graph=GRAPH)
        assert agent.compute_features("2492.TW", AS_OF)["downstream_excess_ret_pct"] == pytest.approx(10.0)

    def test_no_edges_neutral(self):
        out = SupplyChainAgent(FixtureChain({}), graph=GRAPH).analyze("9999.TW", AS_OF)
        assert out.signal == "neutral" and out.confidence <= 0.3

    def test_schema_conformance(self):
        out = SupplyChainAgent(FixtureChain({}), graph=GRAPH).analyze("2492.TW", AS_OF)
        assert set(out.to_dict().keys()) == REQUIRED_KEYS


class TestGraph:
    def test_project_graph_is_valid_and_covers_universe(self):
        graph = load_graph()
        assert {"2327.TW", "2492.TW", "3026.TW", "2375.TW", "2478.TW"} <= set(graph["edges"])

    def test_invalid_relation_rejected(self, tmp_path):
        path = tmp_path / "g.json"
        path.write_text(json.dumps({"edges": {"A": [{"to": "B", "relation": "friend", "weight": 1}]}}), encoding="utf-8")
        with pytest.raises(ValueError):
            load_graph(path)


class FakeClient:
    def __init__(self, tables):
        self.tables = tables

    def get(self, dataset, data_id, start_date, end_date=None):
        return self.tables.get((dataset, data_id), pd.DataFrame()).copy()


def test_provider_excludes_as_of_and_adjusts_split():
    prices = pd.DataFrame({"date": ["2025-08-21", "2025-08-25", "2025-08-26"], "close": [546.0, 136.5, 140.0]})
    split = pd.DataFrame({"date": ["2025-08-25"], "before_price": [546.0], "after_price": [136.5]})
    client = FakeClient({("TaiwanStockPrice", "2327"): prices, ("TaiwanStockSplitPrice", "2327"): split})
    closes = FinMindSupplyChainProvider(client).get_closes("2327.TW", "2025-08-26")
    assert list(closes.index.strftime("%Y-%m-%d")) == ["2025-08-21", "2025-08-25"]  # 不含 as_of 當日
    assert closes.iloc[1] / closes.iloc[0] == pytest.approx(1.0)  # 一拆四不是 −75%
