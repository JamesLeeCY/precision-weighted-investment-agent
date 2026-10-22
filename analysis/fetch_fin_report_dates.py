"""I048 資料：公開資訊觀測站重大訊息中「董事會通過財務報告」的公告（點子卡 research/ideas/I048-margin-surprise-actual-announcement-date.md）。

用法（於專案根目錄；可中斷，已快取的頁不重抓）：
    .venv/Scripts/python analysis/fetch_fin_report_dates.py
輸出 data_cache/events/fin_report_headlines.csv（主旨、發言日期與時間）；原始 HTML 在 data_cache/events/corp_raw/。
- POST ajax_t51sb10，keyWord = 財務報，keyWord2 = 董事會，KIND = L／O，2020-07 ~ 2026-05 逐月、每頁 100 筆翻頁。
研究用資料蒐集，非投資建議。
"""
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "analysis"))
import fetch_corp_events as fc  # noqa: E402

OUT = ROOT / "data_cache" / "events" / "fin_report_headlines.csv"


def month_rows(kind: str, y: int, m: int) -> list[dict]:
    rows, page = [], 1
    while True:
        data = {"pagenum": str(page), "Stp": "4", "r1": "1", "KIND": kind, "CODE": "", "month1": str(m), "begin_day": "1", "end_day": "31",
                "keyWord": "財務報", "Condition2": "1", "keyWord2": "董事會", "Orderby": "", "step": "2", "colorchg": "1", "co_id": "",
                "TYPEK": "", "off": "1", "firstin": "1", "i": "", "year": str(y), "month": str(m), "spoke_date": "", "spoke_time": "",
                "seq_no": "", "b_date": "1", "e_date": "31", "PCount": "100"}
        t = fc.cached(f"t51_finrpt_{kind}_{y}_{m:02d}_p{page}.html",
                      lambda: fc.post("https://mopsov.twse.com.tw/mops/web/ajax_t51sb10", data, "https://mopsov.twse.com.tw/mops/web/t51sb10_q1"))
        if "資料筆數過多" in t:
            raise RuntimeError(f"財務報 {kind} {y}-{m} 資料過多")
        got = fc.parse_headlines(t)
        rows += got
        pages = [int(x) for x in re.findall(r"pagenum\.value='(\d+)'", t)]
        if len(got) < 100 or not pages or page >= max(pages):
            return rows
        page += 1


def main():
    rows = []
    for p in pd.period_range("2020-07", "2026-05", freq="M"):
        for kind in ("L", "O"):
            rows += month_rows(kind, p.year, p.month)
        print(f"{p}：累計 {len(rows)}", flush=True)
    h = pd.DataFrame(rows).drop_duplicates(["stock_id", "date", "seq", "subject"])
    h = h[h["stock_id"].astype(str).str.fullmatch(r"\d{4}")]
    h.to_csv(OUT, index=False)
    print(f"DONE {len(h)}", flush=True)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
