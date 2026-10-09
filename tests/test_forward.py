"""前瞻驗證流程測試：凍結、程式碼變動偵測、只能新增、結算時點與報酬。"""
import numpy as np
import pandas as pd
import pytest

import forward.run_forward as fw


class FakeClient:
    def __init__(self, calendar, prices):
        self.calendar, self.prices = calendar, prices

    def get(self, dataset, data_id, start_date, end_date=None):
        if dataset == "TaiwanStockPrice" and data_id == "TAIEX":
            return pd.DataFrame({"date": self.calendar.strftime("%Y-%m-%d"), "close": 100.0})
        if dataset == "TaiwanStockPrice":
            px = self.prices[data_id]
            return pd.DataFrame({"date": self.calendar.strftime("%Y-%m-%d"), "close": px})
        if dataset == "TaiwanStockMonthRevenue":
            dates = pd.date_range("2024-01-01", periods=30, freq="MS")
            growth = 1.05 if data_id == "1111" else 0.95
            return pd.DataFrame({"date": dates.strftime("%Y-%m-%d"), "revenue": [100 * growth ** i for i in range(30)]})
        return pd.DataFrame()


@pytest.fixture
def env(tmp_path, monkeypatch):
    calendar = pd.bdate_range("2026-05-01", "2026-08-31")
    n = len(calendar)
    prices = {"1111": np.linspace(100, 150, n), "2222": np.linspace(100, 80, n), "3333": np.full(n, 100.0)}
    client = FakeClient(calendar, prices)
    membership = tmp_path / "m.csv"
    pd.DataFrame({"year": 2026, "stock_id": ["1111", "2222", "3333"], "sector": "半導體業",
                  "stock_name": ["甲", "乙", "丙"]}).to_csv(membership, index=False)
    for name, path in (("SPEC_PATH", tmp_path / "spec.yaml"), ("PREDICTIONS", tmp_path / "p.csv"),
                       ("OUTCOMES", tmp_path / "o.csv"), ("REPORT", tmp_path / "R.md"), ("MEMBERSHIP", membership)):
        monkeypatch.setattr(fw, name, path)
    monkeypatch.setattr(fw, "snapshot_client", lambda date: client)
    monkeypatch.setattr(fw, "git_state", lambda: ("abc123", False))
    return tmp_path


def run(*argv):
    fw.main(list(argv))


def test_freeze_once_and_detect_code_change(env, monkeypatch):
    run("freeze")
    with pytest.raises(SystemExit):
        run("freeze")
    spec = fw.load_spec()
    fw.verify_frozen(spec)  # 未改動 → 通過
    spec["frozen_source_sha256"]["base.continuous_judgement"] = "0" * 64
    with pytest.raises(SystemExit, match="規則程式碼已與凍結時不同"):
        fw.verify_frozen(spec)


def test_predict_append_only_and_no_future(env):
    run("freeze")
    run("predict", "--as-of", "2026-06-01", "--mode", "backfill")
    preds = pd.read_csv(fw.PREDICTIONS)
    assert len(preds) == 3 and set(preds["mode"]) == {"backfill"}
    assert preds.set_index("ticker").loc["1111.TW", "p"] > 0.5  # 營收成長 → 看多
    with pytest.raises(SystemExit, match="已經預測過"):
        run("predict", "--as-of", "2026-06-01")
    with pytest.raises(SystemExit, match="未來"):
        run("predict", "--as-of", "2099-01-02")


def test_resolve_after_20_trading_days_and_report(env):
    run("freeze")
    run("predict", "--as-of", "2026-06-01", "--mode", "backfill")
    run("predict", "--as-of", "2026-08-10", "--mode", "backfill")  # 到 8/31 不足 20 個交易日 → 不結算
    run("resolve")
    out = pd.read_csv(fw.OUTCOMES)
    assert set(out["as_of_date"]) == {"2026-06-01"}
    cal = pd.bdate_range("2026-05-01", "2026-08-31")
    end = [d for d in cal if d > pd.Timestamp("2026-06-01")][19]
    assert (out["end_date"] == end.strftime("%Y-%m-%d")).all()
    r1111 = out.set_index("ticker").loc["1111.TW", "forward_return"]
    px = np.linspace(100, 150, len(cal))
    assert r1111 == pytest.approx(px[list(cal).index(end)] / px[list(cal).index(pd.Timestamp("2026-06-01"))] - 1)
    run("resolve")  # 再跑一次不會重複結算
    assert len(pd.read_csv(fw.OUTCOMES)) == 3
    run("report")
    text = fw.REPORT.read_text(encoding="utf-8")
    assert "2026-06-01" in text and "待結算：2026-08-10" in text


def test_period_metrics_sign():
    df = pd.DataFrame({
        "as_of_date": "2026-06-01", "mode": "live", "ticker": list("ABCD"), "sector": "S",
        "p": [0.6, 0.55, 0.45, 0.4], "forward_return": [0.1, 0.05, -0.02, -0.08],
    })
    m = fw.period_metrics(df).iloc[0]
    assert m["ic_within"] == pytest.approx(1.0)
    assert m["excess_long"] == pytest.approx(0.075 - 0.0125)


def test_auto_predicts_current_month_once_and_skips_publish_without_push(env, monkeypatch):
    import datetime as dt

    class Today(dt.date):
        @classmethod
        def today(cls):
            return cls(2026, 8, 20)

    monkeypatch.setattr(fw.dt, "date", Today)
    published = []
    monkeypatch.setattr(fw, "git_publish", lambda msg, push: published.append((msg, push)))
    run("freeze")
    run("auto")
    preds = pd.read_csv(fw.PREDICTIONS)
    assert set(preds["as_of_date"]) == {"2026-08-03"}  # 當月第一個交易日
    assert published == [("forward: auto update 2026-08-20", False)]
    run("auto")  # 再跑一次：已預測、沒有可結算的 → 不重複、不 publish
    assert len(pd.read_csv(fw.PREDICTIONS)) == 3
    assert len(published) == 1
