"""產業內 IC 加權測試：權重方向、冷啟動、產業內 vs 全體、walk-forward 不偷看。"""
import numpy as np
import pandas as pd
import pytest

from agents.base import AgentOutput
from arbitrator.ic_weighting import ICWeighter, within_sector_ic
from arbitrator.precision_tracker import PrecisionTracker
from backtest.run_backtest import PredictionEvent, run_walk_forward

SECTORS = {f"S{i}.TW": ("A" if i < 5 else "B") for i in range(10)}


def fill(w, n_dates, rng):
    """skill：機率與報酬同向；noise：無關；anti：反向。"""
    for d in range(n_dates):
        date = f"2024-{d // 28 + 1:02d}-{d % 28 + 1:02d}"
        for t in SECTORS:
            ret = rng.normal()
            w.record(date, t, {"skill": 0.5 + 0.05 * ret + rng.normal(0, 0.02), "noise": rng.uniform(0.3, 0.7),
                               "anti": 0.5 - 0.05 * ret}, ret)


def test_weights_follow_within_sector_skill():
    w = ICWeighter(SECTORS, window=24, min_dates=6)
    fill(w, 30, np.random.default_rng(0))
    wt = w.weights(["skill", "noise", "anti"])
    assert wt["skill"] > 0.5
    assert wt["anti"] == 0.0
    assert wt["noise"] < 0.15


def test_cold_start_equal_weights():
    w = ICWeighter(SECTORS, min_dates=6)
    fill(w, 5, np.random.default_rng(1))
    assert w.weights(["skill", "noise"]) == {"skill": 1.0, "noise": 1.0}


def test_window_uses_only_recent_dates():
    w = ICWeighter(SECTORS, window=3, min_dates=1)
    fill(w, 10, np.random.default_rng(2))
    assert len(w.ic_history(["skill"])) == 3


def test_sector_fallback_to_cross_section():
    # 每個產業只有 2 檔 → 無法算產業內 IC，退回全體排序
    df = pd.DataFrame({"sector": ["A", "A", "B", "B"], "p": [0.4, 0.6, 0.45, 0.7], "ret": [-1, 1, 0, 2]})
    assert within_sector_ic(df, "p") == pytest.approx(1.0)


def test_sector_neutral_ignores_sector_level_signal():
    # 機率只反映產業（A 全高、B 全低），產業內無差異 → 產業內 IC 為 nan → 權重 0
    w = ICWeighter(SECTORS, window=24, min_dates=1)
    rng = np.random.default_rng(3)
    for d in range(10):
        for t, s in SECTORS.items():
            w.record(f"2024-01-{d + 1:02d}", t, {"sector_bet": 0.6 if s == "A" else 0.4}, rng.normal() + (1 if s == "A" else 0))
    assert w.weights(["sector_bet"])["sector_bet"] == 0.0


def out(agent, p, ticker, date):
    sig = "bullish" if p > 0.5 else "bearish" if p < 0.5 else "neutral"
    return AgentOutput(agent_id=agent, ticker=ticker, as_of_date=date, signal=sig,
                       confidence=max(p, 1 - p) if sig != "neutral" else 0.2, horizon_days=20, rationale="r")


def test_walk_forward_shifts_weight_to_skilled_agent(tmp_path):
    rng = np.random.default_rng(4)
    dates = pd.bdate_range("2023-01-02", periods=40, freq="21B").strftime("%Y-%m-%d").tolist()
    events = []
    for i, date in enumerate(dates[:-1]):
        for t in SECTORS:
            ret = rng.normal(0, 0.05)
            events.append(PredictionEvent(
                ticker=t, as_of_date=date, resolution_date=dates[i + 1], outcome=int(ret > 0), forward_return=ret,
                outputs={"skill": out("skill", 0.5 + 2 * ret, t, date), "noise": out("noise", rng.uniform(0.3, 0.7), t, date)},
            ))
    df = run_walk_forward(events, PrecisionTracker(tmp_path / "p.json"), ic_weighter=ICWeighter(SECTORS, window=24, min_dates=6))
    first, last = df[df.as_of_date == dates[0]].iloc[0], df.iloc[-1]
    assert first["icw_skill"] == first["icw_noise"] == 1.0  # 冷啟動
    assert last["icw_skill"] > 0.5 and last["icw_noise"] < 0.2
    # 權重只依已到期的資料：第 k 個時點最多只有 k−1 個已到期時點
    assert (df[df.as_of_date == dates[5]]["icw_skill"] == 1.0).all()
