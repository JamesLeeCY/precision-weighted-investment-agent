"""月營收驚奇 + 兩日連漲進場、連跌出場：成交時點、單檔上限、減碼一半與全部出清。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "analysis"))
import sue_breakout as sb  # noqa: E402


def run(r, below=None, elig=True):
    days = pd.bdate_range("2024-01-01", periods=len(r))
    rets = pd.DataFrame({"A": r}, index=days)
    E = pd.DataFrame({"A": elig}, index=days)
    adv = pd.DataFrame({"A": 1e8}, index=days)
    B = pd.DataFrame({"A": False if below is None else below}, index=days)
    df, exits = sb.backtest(rets, E, adv, B, days[0], days[-1])
    return df, exits


def test_buys_day_after_two_up_days_and_respects_stock_cap():
    # 兩日 +5%（兩日漲幅 10.25% → 5% × 2.5 = 12.5% → 上限 10%），第 3 日收盤成交
    df, _ = run([0.05, 0.05, 0.0, 0.0, 0.0])
    assert df["exposure"].iloc[1] == 0.0
    assert df["exposure"].iloc[2] == pytest.approx(0.10, rel=1e-3)
    df, _ = run([0.05, 0.05, 0.05, 0.05, 0.05, 0.05, 0.05, 0.0])
    # 買進時補到 20% 為止（之後隨股價上漲可略超過，不強制減碼）
    assert df["exposure"].iloc[5] == pytest.approx(sb.STOCK_MAX, rel=1e-3)
    assert df["turnover"].iloc[6:].sum() == 0.0


def test_two_down_below_ma_sells_half_three_down_sells_all():
    r = [0.05, 0.05, 0.0, -0.01, -0.01, 0.0, 0.0]
    below = [False, False, False, False, True, False, False]
    df, exits = run(r, below)
    before = df["exposure"].iloc[4]
    assert df["exposure"].iloc[5] == pytest.approx(before / 2, rel=0.02)   # 第 5 日收盤訊號 → 第 6 日賣一半
    df, exits = run([0.05, 0.05, 0.0, -0.01, -0.01, -0.01, 0.0, 0.0])
    assert df["exposure"].iloc[6] == pytest.approx(0.0) and exits == 1      # 連跌三日 → 隔日出清


def test_costs_reduce_return_on_trade_day():
    df, _ = run([0.05, 0.05, 0.0, 0.0])
    assert df["ret"].iloc[2] == pytest.approx(-0.10 * sb.lp.STOCK_COST, rel=1e-3)


def test_timing_any_adds_without_up_days_and_tilts_switch_off():
    days = pd.bdate_range("2024-01-01", periods=4)
    rets = pd.DataFrame({"A": [0.0, -0.01, -0.01, 0.0]}, index=days)
    E = pd.DataFrame({"A": True}, index=days)
    adv = pd.DataFrame({"A": 1e8}, index=days)
    B = pd.DataFrame({"A": False}, index=days)
    df, _ = sb.backtest(rets, E, adv, B, days[0], days[-1], tech_exit=False, timing="breakout")
    assert df["exposure"].max() == 0.0                              # 沒有連漲 → 不買
    df, _ = sb.backtest(rets, E, adv, B, days[0], days[-1], tech_exit=False, timing="any", adv_tilt=False, gain_tilt=False)
    assert df["exposure"].iloc[1] == pytest.approx(sb.UNIT, rel=1e-2)   # 第 1 日收盤訊號 → 第 2 日買進 5%


def test_rank_tilt_and_spanning():
    import sue_tilt_momentum as tm

    days = pd.bdate_range("2024-01-01", periods=3)
    x = pd.DataFrame({"A": [1.0] * 3, "B": [2.0] * 3, "C": [3.0] * 3}, index=days)
    E = x.notna()
    E["C"] = False
    t = tm.rank_tilt(x, E)
    assert t.iloc[0]["A"] == pytest.approx(0.25 + 2.25 * 0.5) and t.iloc[0]["B"] == pytest.approx(2.5)
    assert np.isnan(t.iloc[0]["C"])                                  # 不在名單內不排名
    rng = np.random.default_rng(0)
    idx = pd.bdate_range("2020-01-01", periods=2000)
    xs = pd.Series(rng.normal(0, 0.01, len(idx)), index=idx)
    a, tval, b = tm.spanning(2 * xs, xs)                             # y 完全由 x 解釋 → 截距 0、b = 2
    assert abs(a) < 1e-9 and b == pytest.approx(2.0)
