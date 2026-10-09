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


def test_zero_close_rows_are_dropped():
    # FinMind 偶有收盤價為 0 的資料列；若保留，報酬會變成 −100% 或除以零
    prices = pd.DataFrame({"date": ["2025-07-29", "2025-07-30", "2025-07-31"], "close": [200.0, 0.0, 202.0]})
    client = FakeClient({("TaiwanStockPrice", "2317"): prices})
    closes = FinMindSupplyChainProvider(client).get_closes("2317.TW", "2025-08-01")
    assert list(closes.index.strftime("%Y-%m-%d")) == ["2025-07-29", "2025-07-31"]

    from data.fetch_financials import get_daily_prices
    daily = get_daily_prices(client, "2317.TW", "2025-07-01", "2025-08-01")
    assert (daily["close"] > 0).all() and len(daily) == 2


def test_us_proxy_uses_adj_close_and_spy_as_market():
    dates = pd.bdate_range(end="2025-06-27", periods=21).strftime("%Y-%m-%d")
    nvda = pd.DataFrame({"date": dates, "Adj_Close": np.linspace(100, 120, 21), "Close": np.linspace(100, 120, 21)})
    spy = pd.DataFrame({"date": dates, "Adj_Close": np.linspace(100, 105, 21), "Close": np.linspace(100, 105, 21)})
    taiex = pd.DataFrame({"date": dates, "close": np.linspace(100, 150, 21)})
    client = FakeClient({("USStockPrice", "NVDA"): nvda, ("USStockPrice", "SPY"): spy, ("TaiwanStockPrice", "TAIEX"): taiex})
    graph = {"edges": {"2382.TW": [{"to": "NVDA.US", "relation": "downstream", "weight": 1.0}]}}
    agent = SupplyChainAgent(FinMindSupplyChainProvider(client), graph=graph)
    feats = agent.compute_features("2382.TW", "2025-06-30")
    # NVDA +20% 對 SPY +5% → 超額 15%（不是對加權指數的 +50%）
    assert feats["downstream_excess_ret_pct"] == pytest.approx(15.0)
    assert "downstream_revenue_yoy_pct" not in feats  # 美股沒有月營收
