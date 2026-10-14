"""自算 VIX：到期日、在 Black-Scholes 價格下還原出已知波動率。"""
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "analysis"))
import txo_vix as tv  # noqa: E402


def bs(F, K, T, sig, cp):
    d1 = (math.log(F / K) + 0.5 * sig ** 2 * T) / (sig * math.sqrt(T))
    d2 = d1 - sig * math.sqrt(T)
    N = lambda x: 0.5 * (1 + math.erf(x / math.sqrt(2)))  # noqa: E731
    return F * N(d1) - K * N(d2) if cp == "call" else K * N(-d2) - F * N(-d1)


def test_third_wednesday():
    assert tv.third_wednesday("202610") == pd.Timestamp("2026-10-21")
    assert tv.third_wednesday("202606") == pd.Timestamp("2026-06-17")


def test_term_variance_recovers_flat_volatility():
    F, T, sig = 20000.0, 30 / 365, 0.20
    rows = [{"strike_price": float(k), "call_put": cp, "settlement_price": round(bs(F, k, T, sig, cp), 4)}
            for k in range(14000, 26100, 100) for cp in ("call", "put")]
    var, n = tv.term_variance(pd.DataFrame(rows), T)
    assert math.sqrt(var) == pytest.approx(sig, abs=0.005)
    assert n > 50
