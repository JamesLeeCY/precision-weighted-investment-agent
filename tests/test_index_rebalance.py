"""指數調整事件研究：第三個星期五、臺灣50 成分推回、事前預測規則。"""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "analysis"))
import index_rebalance as ir  # noqa: E402


def test_third_friday():
    assert ir.third_friday(2025, 9) == pd.Timestamp("2025-09-19")
    assert ir.third_friday(2026, 9) == pd.Timestamp("2026-09-18")
    assert ir.third_friday(2023, 6) == pd.Timestamp("2023-06-16")


def test_tw50_constituents_consistent():
    ch = pd.read_csv(ROOT / "config" / "index_changes" / "tw50_changes.csv", dtype={"stock_id": str})
    base = set((ROOT / "config" / "index_changes" / "tw50_base_2025-09.txt").read_text(encoding="utf-8").split())
    before = ir.tw50_constituents(ch, base)
    for r, s in before.items():
        g = ch[ch["review"] == r]
        assert len(s) == 50, r
        assert set(g.loc[g["action"] == "del", "stock_id"]) <= s, r
        assert not (set(g.loc[g["action"] == "add", "stock_id"]) & s), r


def test_predict_tw50_rules():
    caps = {f"{1000 + i}.TW": 1000 - i for i in range(80)}          # 1000 市值最大
    cap = pd.Series(caps, dtype=float)
    cons = {str(1000 + i) for i in range(50)}
    cons = (cons - {"1030", "1049"}) | {"1065", "1070"}              # 1030 排 31（應納入）、1070 排 71（應刪除）
    adds, dels = ir.predict_tw50(cap, cons)
    assert "1030" in adds and "1070" in dels
    assert len(cons - dels) + len(adds) == 50
    assert "1065" in dels                                             # 排 66 > 60 → 也應刪除
