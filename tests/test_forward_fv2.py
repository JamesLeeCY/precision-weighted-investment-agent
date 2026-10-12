"""前瞻規格 fv2（月營收驚奇）：預測日檢查、公告期限資料截止、產業中性選股、只能新增、結算與期間報酬。"""
import numpy as np
import pandas as pd
import pytest

import forward.run_forward as fv1
import forward.run_forward_fv2 as fv2

CAL = pd.bdate_range("2024-06-01", "2026-09-30")
TICKERS = ["1111", "2222", "3333", "4444", "5555", "6666"]


def revenue(sid):
    months = pd.date_range("2023-01-01", "2026-02-01", freq="MS")
    rng = np.random.default_rng(int(sid[0]))
    base = 100 + np.arange(len(months)) * 1.0 + rng.normal(0, 1, len(months))
    k = TICKERS.index(sid)
    base[-1] += 10 * (5 - k)  # 2026-02 營收：1111 驚奇最大、6666 最小
    df = pd.DataFrame({"date": (months + pd.offsets.MonthBegin(1)).strftime("%Y-%m-%d"),
                       "revenue_year": months.year, "revenue_month": months.month, "revenue": base, "create_time": None})
    if sid == "2222":
        df.loc[df.index[-1], "create_time"] = "2026-03-12"  # 逾期才公告 → 不應採用
    return df


class FakeClient:
    def get(self, dataset, data_id, start_date, end_date=None):
        if dataset == "TaiwanStockPrice":
            n = len(CAL)
            close = np.full(n, 100.0) if data_id in ("TAIEX", "0050") else np.linspace(100, 100 + 5 * (int(data_id[0]) % 3 + 1), n)
            return pd.DataFrame({"date": CAL.strftime("%Y-%m-%d"), "close": close})
        if dataset == "TaiwanStockMonthRevenue":
            return revenue(data_id)
        return pd.DataFrame()


@pytest.fixture
def env(tmp_path, monkeypatch):
    for name in ("SPEC_PATH", "PREDICTIONS", "OUTCOMES", "PERIODS", "REPORT"):
        monkeypatch.setattr(fv2, name, tmp_path / f"{name}.x")
    monkeypatch.setattr(fv2, "FV2_DIR", tmp_path)
    monkeypatch.setattr(fv1, "snapshot_client", lambda date: FakeClient())
    monkeypatch.setattr(fv2, "git_state", lambda: ("abc123", False))
    mem = pd.DataFrame({"stock_id": TICKERS, "sector": "S", "ticker": [t + ".TW" for t in TICKERS]})
    monkeypatch.setattr(fv1, "members", lambda year: mem)
    return tmp_path


def test_predict_only_on_entry_day_with_deadline_cutoff(env):
    fv2.main(["freeze"])
    with pytest.raises(SystemExit, match="不是 fv2 的預測日"):
        fv2.main(["predict", "--as-of", "2026-03-10"])   # 2026-03-10 是期限當天，不是進場日
    fv2.main(["predict", "--as-of", "2026-03-11"])
    p = pd.read_csv(fv2.PREDICTIONS, dtype={"ticker": str}).set_index("ticker")
    assert np.isnan(p.loc["2222.TW", "sue"])             # 逾期公告的營收被排除
    assert p.loc["1111.TW", "selected"] == 1              # 驚奇最大 → 入選
    assert p["weight"].sum() == pytest.approx(1.0)
    assert set(p["mode"]) == {"backfill"}
    with pytest.raises(SystemExit, match="已經預測過"):
        fv2.main(["predict", "--as-of", "2026-03-11"])


def test_resolve_writes_outcomes_and_period(env):
    fv2.main(["freeze"])
    fv2.main(["predict", "--as-of", "2026-03-11"])
    assert fv2.cmd_resolve(None) == 1
    out = pd.read_csv(fv2.OUTCOMES)
    per = pd.read_csv(fv2.PERIODS)
    end = [d for d in CAL if d > pd.Timestamp("2026-03-11")][19]
    assert set(out["end_date"]) == {end.strftime("%Y-%m-%d")}
    assert len(per) == 1 and per["b0050"].iloc[0] == pytest.approx(0.0)
    assert fv2.cmd_resolve(None) == 0                     # 不重複結算
    fv2.main(["report"])
    assert "2026-03-11" in fv2.REPORT.read_text(encoding="utf-8")


def test_code_change_blocks_prediction(env):
    fv2.main(["freeze"])
    spec = fv2.load_spec()
    spec["frozen_source_sha256"]["fv2.build_selection"] = "0" * 64
    with pytest.raises(SystemExit, match="規則程式碼已與凍結時不同"):
        fv2.verify_frozen(spec)
