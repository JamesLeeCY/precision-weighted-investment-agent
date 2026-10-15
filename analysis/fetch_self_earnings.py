"""I015 每月自結損益：抓重大訊息主旨與內文（點子卡 research/ideas/I015-monthly-self-reported-earnings-surprise.md）。

用法（於專案根目錄；可中斷，已快取的請求不重抓）：
    .venv/Scripts/python analysis/fetch_self_earnings.py headlines   # 主旨（約 100 次）
    .venv/Scripts/python analysis/fetch_self_earnings.py contents    # 內文（逐則，約 2,500–4,500 次，每次間隔 3 秒）
輸出 data_cache/events/self_earnings_headlines.csv；內文原始 HTML 在 data_cache/events/corp_raw/t05/。

- 主旨：POST ajax_t51sb10，keyWord = 自結，keyWord2 ∈ {損益, 盈餘, 獲利, 淨利}，KIND = L／O，year = 2017 ~ 2026（西元），全年、每頁 100 筆翻頁。
  只保留主旨含「自結」且含「損益」「盈餘」「獲利」「淨利」「EPS」之一者。
- 內文：POST ajax_t05st01（step=2、co_id、TYPEK、spoke_date、spoke_time、seq_no）；解析規則在分析程式中逐家撰寫。
研究用資料蒐集，非投資建議。
"""
import re
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "analysis"))
import fetch_corp_events as fc  # noqa: E402

OUT = ROOT / "data_cache" / "events"
T05 = fc.RAW / "t05"
KW2 = ("損益", "盈餘", "獲利", "淨利")
KEEP = re.compile(r"自結.*(損益|盈餘|獲利|淨利|EPS)|(損益|盈餘|獲利|淨利|EPS).*自結")


def headlines() -> pd.DataFrame:
    rows = []
    for kw2 in KW2:
        for kind in ("L", "O"):
            for y in range(2017, 2027):
                page = 1
                while True:
                    data = {"pagenum": str(page), "Stp": "4", "r1": "1", "KIND": kind, "CODE": "", "month1": "0", "begin_day": "1", "end_day": "31",
                            "keyWord": "自結", "Condition2": "1", "keyWord2": kw2, "Orderby": "", "step": "2", "colorchg": "1", "co_id": "",
                            "TYPEK": "", "off": "1", "firstin": "1", "i": "", "year": str(y), "month": "0", "spoke_date": "", "spoke_time": "",
                            "seq_no": "", "b_date": "1", "e_date": "31", "PCount": "100"}
                    t = fc.cached(f"t51_self_{kw2}_{kind}_{y}_p{page}.html",
                                  lambda: fc.post("https://mopsov.twse.com.tw/mops/web/ajax_t51sb10", data, "https://mopsov.twse.com.tw/mops/web/t51sb10_q1"))
                    got = fc.parse_headlines(t)
                    rows += got
                    pages = [int(x) for x in re.findall(r"pagenum\.value='(\d+)'", t)]
                    if len(got) < 100 or not pages or page >= max(pages):
                        break
                    page += 1
            print(f"主旨 {kw2} {kind}：累計 {len(rows)} 筆", flush=True)
    h = pd.DataFrame(rows).drop_duplicates(["stock_id", "date", "seq", "subject"])
    h = h[h["subject"].astype(str).str.contains(KEEP) & h["stock_id"].astype(str).str.fullmatch(r"\d{4}")]
    return h.sort_values("date").reset_index(drop=True)


def contents(h: pd.DataFrame) -> None:
    T05.mkdir(parents=True, exist_ok=True)
    n_new = 0
    for i, r in enumerate(h.itertuples()):
        d = pd.Timestamp(r.date).strftime("%Y%m%d")
        name = f"{r.stock_id}_{d}_{r.seq}_{r.spoke_time}.html"
        if (T05 / name).exists():
            continue
        data = {"encodeURIComponent": 1, "step": 2, "firstin": 1, "off": 1, "co_id": r.stock_id, "TYPEK": r.market or "sii",
                "spoke_date": d, "spoke_time": str(r.spoke_time), "seq_no": str(r.seq)}
        fc.cached(f"t05/{name}", lambda: fc.post("https://mopsov.twse.com.tw/mops/web/ajax_t05st01", data, "https://mopsov.twse.com.tw/mops/web/t05st01"))
        n_new += 1
        if n_new % 50 == 0:
            print(f"內文 {i + 1}/{len(h)}（本次新抓 {n_new}）", flush=True)
        time.sleep(0.5)                                            # fc.post 已間隔 2.5 秒，再加 0.5 秒
    print(f"內文完成：{len(h)} 則（本次新抓 {n_new}）", flush=True)


def main():
    fc.RAW.mkdir(parents=True, exist_ok=True)
    what = sys.argv[1:] or ["headlines", "contents"]
    if "headlines" in what:
        h = headlines()
        h.to_csv(OUT / "self_earnings_headlines.csv", index=False)
        print(f"主旨：{len(h)} 則、{h['stock_id'].nunique()} 家", flush=True)
    if "contents" in what:
        h = pd.read_csv(OUT / "self_earnings_headlines.csv", dtype={"stock_id": str, "seq": str, "spoke_time": str}, parse_dates=["date"])
        contents(h)
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
