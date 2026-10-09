"""技術面 Agent：指標定義、突破判斷、無前視、評分方向。"""
import numpy as np
import pandas as pd
import pytest

from agents.technical_agent import TechnicalAgent
from data.fetch_technical import compute_indicators, technical_components


def ohlcv(close, volume=None):
    n = len(close)
    close = np.asarray(close, dtype=float)
    return pd.DataFrame({
        "date": pd.bdate_range("2024-01-01", periods=n), "open": close * 0.99, "high": close * 1.01,
        "low": close * 0.98, "close": close, "volume": volume if volume is not None else np.full(n, 1000.0),
    })


def test_uptrend_is_bullish_and_breaks_out():
    ind = compute_indicators(ohlcv(np.geomspace(100, 400, 80)))
    last = ind.iloc[-1]
    assert last["trend"] > 0 and last["ma_spread"] > 0
    assert last["breakout"] == 1.0  # 每天都創 60 日新高
    assert last["candle"] > 0       # 收盤高於開盤
    signal, conf, _, score, cov = TechnicalAgent.judge(last.to_dict())
    assert signal == "bullish" and score > 0.2 and cov == 1.0


def test_downtrend_breaks_support():
    ind = compute_indicators(ohlcv(np.geomspace(400, 50, 80)))
    last = ind.iloc[-1]
    assert last["trend"] < 0 and last["breakout"] == -1.0


def test_insufficient_history_gives_partial_coverage():
    ind = compute_indicators(ohlcv(np.linspace(100, 110, 30)))
    comps = technical_components(ind.iloc[-1].to_dict())
    names = {n for n, _ in comps}
    assert "均線趨勢" not in names and "K線" in names  # 60 日均線不足，5 日 K 線可算


def test_volume_price_sign():
    vol = np.r_[np.full(75, 1000.0), np.full(5, 3000.0)]
    up = compute_indicators(ohlcv(np.linspace(100, 120, 80), vol)).iloc[-1]
    down = compute_indicators(ohlcv(np.linspace(120, 100, 80), vol)).iloc[-1]
    assert up["vol_price"] > 0 > down["vol_price"]


class FakeProvider:
    def __init__(self, ind):
        self.ind = ind

    def latest_before(self, ticker, as_of_date):
        prior = self.ind[self.ind["date"] < pd.Timestamp(as_of_date)]
        return {} if prior.empty else prior.iloc[-1].to_dict()


def test_agent_uses_only_data_before_as_of():
    # 前 79 天上漲、最後 1 天暴跌：預測日若是最後一天，不應看到暴跌
    close = np.r_[np.geomspace(100, 400, 79), 50.0]
    ind = compute_indicators(ohlcv(close))
    agent = TechnicalAgent(FakeProvider(ind), output_mode="continuous")
    last_day = ind["date"].iloc[-1].strftime("%Y-%m-%d")
    out = agent.analyze("TEST.TW", last_day)
    assert out.signal == "bullish"
    assert out.raw_features["breakout"] == 1.0
    after = (ind["date"].iloc[-1] + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    assert agent.analyze("TEST.TW", after).raw_features["breakout"] == -1.0


def test_no_data_is_neutral():
    agent = TechnicalAgent(FakeProvider(pd.DataFrame({"date": pd.to_datetime([])})))
    out = agent.analyze("X.TW", "2024-01-01")
    assert out.signal == "neutral"
    assert out.raw_features["evidence"] == pytest.approx(0.0)
