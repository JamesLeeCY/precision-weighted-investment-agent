"""反轉輔助換倉：延後賣出近期跌深的持股、選股邊際偏好跌深股、產業權重不變。"""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "analysis"))
import reversal_execution as rx  # noqa: E402


@pytest.fixture
def g():
    # 6 檔同產業：財報排名 A > B > C > D > E > F；反轉訊號（近 5 日跌幅）D 最大
    return pd.DataFrame({
        "ticker": list("ABCDEF"), "sector": "S",
        "pc_fundamentals_agent": [0.9, 0.8, 0.7, 0.6, 0.5, 0.4],
        "rev_1w": [0.00, -0.01, 0.01, 0.10, 0.02, -0.02],
    })


def test_baseline_takes_top_third(g):
    assert set(rx.target_weights(g, held=set())) == {"A", "B"}


def test_delay_sell_keeps_recent_loser(g):
    w = rx.target_weights(g, held={"D", "F"}, delay_sell=True)
    assert set(w) == {"A", "B", "D"}         # D 近 5 日跌最多 → 續抱；F 照常賣出
    assert sum(w.values()) == pytest.approx(1.0)


def test_tilt_only_changes_the_margin():
    # 30 檔：財報第 10 名（剛好入選）與第 11 名（剛好落選），第 11 名近 5 日跌最多 → 加權後互換
    n = 30
    tick = [f"T{k:02d}" for k in range(n)]
    rev = [0.0] * n
    rev[9], rev[10] = -0.10, 0.10
    g = pd.DataFrame({"ticker": tick, "sector": "S", "pc_fundamentals_agent": [1 - k / 100 for k in range(n)], "rev_1w": rev})
    base = set(rx.target_weights(g, held=set()))
    tilted = set(rx.target_weights(g, held=set(), tilt=True))
    assert base == set(tick[:10])
    assert tilted == set(tick[:9]) | {"T10"}   # 只有邊際的兩檔互換，入選檔數不變
