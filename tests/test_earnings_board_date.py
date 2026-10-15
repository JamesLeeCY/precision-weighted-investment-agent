"""I007：年度事件建構（最早決議日、去年淨利、提前天數、3/31 分界、不配息公司保留）。"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "analysis"))
import earnings_board_date as eb  # noqa: E402


def test_annual_events():
    rows = [
        {"stock_id": "1101", "annual": True, "fy": 2019, "board": pd.Timestamp("2020-03-20"), "ni": 100.0, "cash_ps": 1.0, "cash_total": 50.0, "query_year": 109},
        {"stock_id": "1101", "annual": True, "fy": 2020, "board": pd.Timestamp("2021-03-10"), "ni": 150.0, "cash_ps": 0.0, "cash_total": 0.0, "query_year": 110},
        {"stock_id": "1101", "annual": True, "fy": 2020, "board": pd.Timestamp("2021-05-01"), "ni": 150.0, "cash_ps": 0.0, "cash_total": 0.0, "query_year": 110},
        {"stock_id": "2330", "annual": False, "fy": 2020, "board": pd.Timestamp("2021-02-09"), "ni": 1.0, "cash_ps": 1.0, "cash_total": 1.0, "query_year": 110},
        {"stock_id": "1102", "annual": True, "fy": 2020, "board": pd.Timestamp("2021-04-15"), "ni": 10.0, "cash_ps": 0.0, "cash_total": 0.0, "query_year": 110},
        {"stock_id": "1102", "annual": True, "fy": 2019, "board": pd.NaT, "ni": 5.0, "cash_ps": 0.0, "cash_total": 0.0, "query_year": 109},
    ]
    ev = eb.annual_events(pd.DataFrame(rows)).set_index(["stock_id", "fy"])
    a = ev.loc[("1101", 2020)]
    assert a["board"] == pd.Timestamp("2021-03-10") and a["ni_prev"] == 100.0 and a["early"]
    assert a["advance"] == 10                                  # 去年 3/20 → 今年 3/10，提前 10 天
    b = ev.loc[("1102", 2020)]
    assert not b["early"] and b["ni_prev"] == 5.0 and b["cash_total"] == 0.0   # 不配息、晚於 3/31 仍保留
    assert ("2330", 2020) not in ev.index                      # 季配列不算年度事件
