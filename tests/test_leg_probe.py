"""單腿探針：季節性月份對齊、無前視、產業內 z 分數、市值中性化、台指期連續報酬、對沖報酬。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "analysis"))
import leg_probe as lp  # noqa: E402


def test_season_uses_same_calendar_month_of_past_years():
    days = pd.bdate_range("2018-01-01", "2023-12-31")
    # 每年 3 月上旬連漲約 10%，其他月份持平
    adj = pd.DataFrame({"A": np.cumprod(np.where((days.month == 3) & (days.day <= 7), 1.0135, 1.0))}, index=days)
    legs = lp.raw_legs(adj, adj * 0 + 1e6, adj * 0 + 1e8, adj["A"], None)
    s = legs["season"]["A"]
    assert s.loc["2023-03-15"] > 0.05            # 3 月：過去幾年的 3 月報酬約 +10%
    assert abs(s.loc["2023-05-15"]) < 1e-9       # 5 月：過去的 5 月都持平


def test_legs_are_lagged_one_day():
    days = pd.bdate_range("2024-01-01", periods=80)
    r = np.zeros(80)
    r[-1] = 0.5  # 最後一天大漲
    adj = pd.DataFrame({"A": np.cumprod(1 + r)}, index=days)
    legs = lp.raw_legs(adj, adj * 0 + 1e6, adj * 0 + 1e8, adj["A"] * 0 + 1, None)
    assert legs["lowvol20"]["A"].iloc[-1] == pytest.approx(0.0)   # 當天的大漲不會出現在當天的值


def test_wrap_zscores_within_sector_and_neutralize_removes_size():
    days = pd.bdate_range("2024-01-01", periods=30)
    raw = pd.DataFrame({"A": 1.0, "B": 2.0, "C": 3.0, "D": 10.0, "E": 20.0, "F": 30.0}, index=days)
    member = raw.notna()
    sector = pd.Series({"A": "s1", "B": "s1", "C": "s1", "D": "s2", "E": "s2", "F": "s2"})
    z = lp.wrap(raw, member, sector)
    assert z.iloc[-1]["A"] == pytest.approx(z.iloc[-1]["D"])     # 產業內標準化後兩個產業可比
    score = pd.Series(np.arange(30, dtype=float), index=[f"T{k}" for k in range(30)])
    sec = pd.Series(["a", "b", "c"] * 10, index=score.index)
    logcap = score * 2 + 1                                         # 分數完全由市值決定
    res = lp.neutralize(score, sec, logcap)
    assert res.abs().max() < 1e-6


def test_tx_continuous_rolls_on_front_contract():
    rows = [("2024-01-02", "202401", 100, 9), ("2024-01-02", "202402", 101, 1),
            ("2024-01-03", "202401", 102, 9), ("2024-01-03", "202402", 103, 1),
            ("2024-01-04", "202401", 103, 1), ("2024-01-04", "202402", 105.06, 9)]
    df = pd.DataFrame(rows, columns=["date", "contract_date", "close", "volume"]).assign(trading_session="position")

    class C:
        def get(self, *a):
            return df

    tx = lp.tx_continuous(C())
    assert tx.loc["2024-01-03"] == pytest.approx(0.02)            # 102 / 100
    assert tx.loc["2024-01-04"] == pytest.approx(0.02)            # 轉到 202402：105.06 / 103


def test_simulate_hedges_beta_times_futures():
    days = pd.bdate_range("2024-01-01", periods=6)
    rets = pd.DataFrame({"A": 0.01, "B": 0.01, "C": 0.0}, index=days)
    betas = pd.DataFrame({"A": 1.0, "B": 1.0, "C": 1.0}, index=days)
    tx = pd.Series(0.01, index=days)
    sector = pd.Series({"A": "s", "B": "s", "C": "s"})
    score = pd.Series({"A": 3.0, "B": 2.0, "C": 1.0})
    sim = lp.simulate({days[0]: score}, rets, betas, tx, [days[0]], sector)
    # 前 1/3（3 檔取 1 檔 A）：每日 alpha = 0.01 − 1.0 × 0.01 = 0（第一天再扣成本）
    assert sim["alpha"].iloc[1:].abs().max() < 1e-12
    assert sim["alpha"].iloc[0] < 0


def test_enumerate_finds_diversifying_leg():
    import leg_enumerate as le

    days = pd.bdate_range("2019-01-01", "2026-04-30")
    rng = np.random.default_rng(0)
    main = rng.normal(0.002, 0.01, len(days))
    div = rng.normal(0.002, 0.01, len(days))           # 同樣報酬、彼此獨立 → 組合 Sharpe 較高
    junk = rng.normal(-0.002, 0.01, len(days))
    P = pd.DataFrame({"sue": main, "good": div, "bad": junk}, index=days)
    df, base = le.enumerate_combos(P)
    best = df.iloc[0]
    assert "good" in best["legs"] and "bad" not in best["legs"]
    assert best["score"] > min(base["sh_oos"], base["sh_is"])
    assert len(df) == (2 + 1) * len(le.MAIN_WEIGHTS)    # C(2,1) + C(2,2) 種腿組合
