"""無選股偏誤股票池測試：候選池、逐年依成交金額選股、下市股票、圖譜產生。"""
import numpy as np
import pandas as pd

from data.universe import build_membership, candidate_pool, load_membership, sector_graph


class FakeClient:
    def __init__(self, tables):
        self.tables = tables

    def get(self, dataset, data_id, start_date, end_date=None):
        return self.tables.get((dataset, data_id), pd.DataFrame()).copy()


def prices(dates, value, close=10.0):
    return pd.DataFrame({"date": dates.strftime("%Y-%m-%d"), "close": close, "Trading_money": value})


def make_client():
    info = pd.DataFrame({
        "stock_id": ["1111", "1111", "2222", "3333", "4444", "0050", "5555"],
        "stock_name": ["甲", "甲", "乙", "丙", "丁", "ETF", "戊"],
        "industry_category": ["電子工業", "半導體業", "電子零組件業", "半導體業", "電腦及週邊設備業", "半導體業", "生技醫療業"],
        "type": ["twse", "twse", "tpex", "twse", "emerging", "twse", "twse"],
    })
    delist = pd.DataFrame({"date": ["2020-06-30"], "stock_id": ["3333"], "stock_name": ["丙"]})
    d2019 = pd.bdate_range("2018-09-03", "2019-12-31")
    d_all = pd.bdate_range("2018-09-03", "2020-12-31")
    return FakeClient({
        ("TaiwanStockInfo", ""): info,
        ("TaiwanStockDelisting", ""): delist,
        ("TaiwanStockPrice", "1111"): prices(d_all, 1e6),
        ("TaiwanStockPrice", "2222"): prices(d_all, 5e6),
        # 3333：2019 年成交金額最大，2020-06 下市（2020 年初仍在交易，仍應入選）
        ("TaiwanStockPrice", "3333"): prices(pd.bdate_range("2018-09-03", "2020-06-29"), 9e6),
    })


def test_candidate_pool_filters_and_picks_finest_sector():
    pool = candidate_pool(make_client()).set_index("stock_id")
    assert set(pool.index) == {"1111", "2222", "3333"}  # 排除興櫃、ETF、非電子
    assert pool.loc["1111", "sector"] == "半導體業"  # 『電子工業』與『半導體業』取較細者
    assert pool.loc["3333", "delisted_date"] == "2020-06-30"


def test_membership_uses_only_prior_data_and_keeps_later_delisted():
    m = build_membership(make_client(), range(2019, 2022), top_n=2, progress=False)
    y2019 = m[m.year == 2019].sort_values("rank")
    assert list(y2019.stock_id) == ["3333", "2222"]  # 依前 60 日成交金額
    assert "3333" in set(m[m.year == 2020].stock_id)  # 年初還在交易 → 入選，即使年中下市
    assert "3333" not in set(m[m.year == 2021].stock_id)  # 已下市 → 不入選
    assert (m.groupby("year").size() <= 2).all()


def test_load_membership_and_sector_graph(tmp_path):
    m = build_membership(make_client(), range(2019, 2020), top_n=3, progress=False)
    path = tmp_path / "m.csv"
    m.to_csv(path, index=False)
    assert load_membership(path) == {2019: {"1111.TW", "2222.TW", "3333.TW"}}
    g = sector_graph(m)
    assert {e["to"] for e in g["edges"]["3333.TW"]} == {"2330.TW", "NVDA.US"}
    assert all(e["source"].startswith("產業預設") for es in g["edges"].values() for e in es)


def test_finmind_client_retries_network_errors_without_leaking_token(monkeypatch):
    import pytest
    import requests

    from data import fetch_financials
    from data.fetch_financials import FinMindClient

    client = FinMindClient(token="SECRET-TOKEN", use_cache=False)
    client.NETWORK_RETRY_WAITS_SEC = (0, 0)
    monkeypatch.setattr(fetch_financials.time, "sleep", lambda s: None)
    calls = []

    class Ok:
        status_code = 200

        def json(self):
            return {"data": [{"x": 1}]}

    def flaky(url, params, timeout):
        calls.append(1)
        if len(calls) < 3:
            raise requests.ConnectTimeout(f"timed out: {url}?token={params['token']}")
        return Ok()

    monkeypatch.setattr(fetch_financials.requests, "get", flaky)
    assert client.get("TaiwanStockPrice", "2330", "2024-01-01").to_dict("records") == [{"x": 1}]
    assert len(calls) == 3

    def always_fail(url, params, timeout):
        raise requests.ConnectTimeout(f"timed out: {url}?token={params['token']}")

    monkeypatch.setattr(fetch_financials.requests, "get", always_fail)
    with pytest.raises(RuntimeError) as exc:
        client.get("TaiwanStockPrice", "2330", "2024-01-01")
    assert "SECRET-TOKEN" not in str(exc.value)
    assert exc.value.__cause__ is None and exc.value.__suppress_context__
