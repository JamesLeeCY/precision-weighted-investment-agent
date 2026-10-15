"""I006：股利分派彙總表解析（19／21 欄）與分群標準誤迴歸。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "analysis"))
import dividend_surprise as ds  # noqa: E402


def row(cells):
    return "<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>"


def test_parse_table_both_formats():
    new = ["2317 - 鴻海", "董事會決議", "109年 年度", "109/01/01~109/12/31", "1", "110/03/30", "不適用", "1", "101,794,807,191",
           "1", "1", "4.00000000", "0.0", "0.5", "55,451,962,436", "0", "0", "0", "0", "章程", "無"]
    old = ["2412 - 中華電", "股東會確認", "107年 年度", "107/01/01~107/12/31", "1", "108/03/19", "108/06/21", "1", "35,501,621,178",
           "1", "1", "4.47900000", "0.1", "34,745,603,075", "0", "0", "0", "章程", "無"]
    q = ["2330 - 台積電", "董事會決議", "115年 第1季", "115/01/01~115/03/31", "1", "115/05/12", "不適用", "1", "5", "1", "1", "6", "0", "0", "1", "0", "0", "0", "0", "x", "y"]
    out = ds.parse_table(row(new) + row(old) + row(q) + row(["1101B - 台泥乙特"] + old[1:]))
    a, b, c = out[0], out[1], out[2]
    assert a["stock_id"] == "2317" and a["annual"] and a["fy"] == 2020 and a["board"] == pd.Timestamp("2021-03-30")
    assert a["cash_ps"] == pytest.approx(4.5) and a["cash_total"] == 55451962436 and a["ni"] == 101794807191
    assert b["cash_ps"] == pytest.approx(4.579) and b["cash_total"] == 34745603075 and b["board"] == pd.Timestamp("2019-03-19")
    assert not c["annual"]
    assert out[3]["stock_id"] == "1101B"


def test_ols_cluster_recovers_slope():
    rng = np.random.default_rng(1)
    x = rng.normal(size=400)
    y = 2.0 * x + rng.normal(size=400)
    X = np.column_stack([np.ones(400), x])
    beta, se = ds.ols_cluster(y, X, np.repeat(np.arange(40), 10))
    assert beta[1] == pytest.approx(2.0, abs=0.15) and 0 < se[1] < 0.2
