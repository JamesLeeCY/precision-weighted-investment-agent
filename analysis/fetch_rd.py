"""I081 研發費用資料：公開資訊觀測站 ajax_t164sb04（綜合損益表，第 4 季＝年度），逐家抓取。

用法（於專案根目錄）：
    .venv/Scripts/python analysis/fetch_rd.py
輸出 data_cache/events/rd_expense.csv：[stock_id, fy（西元會計年度）, rd, revenue]（千元；rd 為 0 表示損益表沒有研究發展費用列）。
每頁有當年度與前一年度兩欄，所以只查民國 107、109、111、113 年度（得到 2017–2024），每家 4 次請求；可中斷後續抓。
名單：市值成員檔 2019–2025 年前 1000 名、排除金融保險業。
"""
import re
import sys
import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "analysis"))
import fetch_corp_events as fc  # noqa: E402

OUT = ROOT / "data_cache" / "events" / "rd_expense.csv"
DONE = ROOT / "data_cache" / "events" / "rd_expense_done.csv"
YEARS = (113, 111, 109, 107)
FIN = ("金融保險", "金融業")
URL = "https://mopsov.twse.com.tw/mops/web/ajax_t164sb04"


def universe() -> list[str]:
    m = pd.read_csv(ROOT / "config" / "universe_mcap_membership_1500.csv", dtype={"stock_id": str})
    m = m[(m["rank"] <= 1000) & m["year"].between(2019, 2025) & ~m["sector"].isin(FIN)]
    return sorted(m["stock_id"].unique())


def num(s: str) -> float:
    s = s.replace(",", "").strip()
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    try:
        return float(s)
    except ValueError:
        return float("nan")


def parse(t: str, y: int) -> list[dict] | None:
    """回傳兩個年度的列；頁面沒有損益表（已下市、不繼續公開發行、KY 公司等）回傳 []；疑似被擋回傳 None。"""
    if "會計項目" not in t:
        # 只有連線層級的短回應或「頻繁」才重試；其他狀態頁（已下市、不繼續公開發行、KY 公司的公司清單頁等）視為無資料
        if len(t) < 1000 or "頻繁" in t:
            return None
        return []
    rd = [0.0, 0.0]
    rev = [float("nan"), float("nan")]
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", t, re.S):
        cells = [re.sub(r"<[^>]+>|&nbsp;", "", c).strip() for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S)]
        if len(cells) < 4:
            continue
        if cells[0].startswith("研究發展費"):
            rd = [num(cells[1]), num(cells[3])]
        elif cells[0] in ("營業收入合計", "收入合計", "收益合計") and rev[0] != rev[0]:
            rev = [num(cells[1]), num(cells[3])]
    return [{"fy": y + 1911, "rd": rd[0], "revenue": rev[0]}, {"fy": y + 1910, "rd": rd[1], "revenue": rev[1]}]


def fetch(co: str, y: int) -> list[dict]:
    data = {"encodeURIComponent": 1, "step": 1, "firstin": 1, "off": 1, "queryName": "co_id", "inpuType": "co_id",
            "TYPEK": "all", "isnew": "false", "co_id": co, "year": str(y), "season": "4"}
    for k in range(6):
        try:
            r = requests.post(URL, data=data, timeout=60, headers={"User-Agent": fc.UA, "Origin": "https://mopsov.twse.com.tw",
                                                                    "Referer": "https://mopsov.twse.com.tw/mops/web/t164sb04"})
            r.encoding = "utf-8"
            out = parse(r.text, y) if r.status_code == 200 else None
            if out is not None:
                return out
            print(f"  {co} {y}：HTTP {r.status_code}、{len(r.content)} bytes，等待後重試", flush=True)
        except requests.RequestException as e:
            print(f"  {co} {y}：{type(e).__name__}，重試", flush=True)
        time.sleep(30 * (k + 1))
    raise RuntimeError(f"{co} {y} 多次失敗")


def main():
    ids = universe()
    done = set()
    if DONE.exists():
        d = pd.read_csv(DONE, dtype={"stock_id": str})
        done = set(zip(d["stock_id"], d["y"]))
    print(f"{len(ids)} 家，已完成 {len(done)} 次", flush=True)
    t0 = time.time()
    n = 0
    for i, co in enumerate(ids):
        for y in YEARS:
            if (co, y) in done:
                continue
            rows = fetch(co, y)
            if rows:
                pd.DataFrame([{"stock_id": co, **r} for r in rows]).to_csv(OUT, mode="a", header=not OUT.exists(), index=False)
            pd.DataFrame([{"stock_id": co, "y": y}]).to_csv(DONE, mode="a", header=not DONE.exists(), index=False)
            n += 1
            time.sleep(2.2)
        if i % 50 == 0:
            print(f"  {i}/{len(ids)}，{n} 次，{(time.time() - t0) / 60:.0f} 分", flush=True)
    print("完成", flush=True)


if __name__ == "__main__":
    main()
