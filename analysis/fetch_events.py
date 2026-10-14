"""抓事件資料：處置有價證券（證交所、櫃買中心）與庫藏股買回（公開資訊觀測站）。

用法（於專案根目錄）：
    .venv/Scripts/python analysis/fetch_events.py
輸出 data_cache/events/disposition.csv、data_cache/events/buyback.csv；原始回應快取在 data_cache/events/raw/（已抓的月份／季度不重抓）。

- 處置：證交所 /rwd/zh/announcement/punish（JSON，依公布日期查詢）、櫃買 /www/zh-tw/bulletin/disposal（JSON）；只保留 4 碼股票代號。
- 庫藏股：公開資訊觀測站「上市／上櫃公司買回自己公司股份彙總統計表」（t35sc09，依董事會決議日期查詢）。
  新版網站先呼叫 /mops/api/redirectToOld 取得舊站網址；日期格式為民國年 7 碼（例如 1080101）。
- 每次請求間隔 3 秒。
"""
import json
import re
import sys
import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data_cache" / "events"
RAW = OUT / "raw"
START, END = pd.Timestamp("2018-07-01"), pd.Timestamp("2026-10-14")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
_last = [0.0]


def _get(session, method, url, **kw):
    for k in range(4):
        wait = 3.0 - (time.time() - _last[0])
        if wait > 0:
            time.sleep(wait)
        try:
            r = session.request(method, url, timeout=60, **kw)
            _last[0] = time.time()
            if r.status_code == 200:
                return r
            print(f"  HTTP {r.status_code}，重試", flush=True)
        except requests.RequestException as e:
            _last[0] = time.time()
            print(f"  連線錯誤（{type(e).__name__}），重試", flush=True)
        time.sleep(10 * (k + 1))
    raise RuntimeError(f"多次失敗：{url}")


def _cached(name: str, fetch) -> str:
    p = RAW / name
    if p.exists():
        return p.read_text(encoding="utf-8")
    text = fetch()
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(p)
    return text


def roc(d: pd.Timestamp, sep: str = "") -> str:
    return f"{d.year - 1911}{sep}{d.month:02d}{sep}{d.day:02d}"


def parse_roc(s: str) -> pd.Timestamp:
    y, m, d = re.findall(r"\d+", s)[:3]
    return pd.Timestamp(int(y) + 1911, int(m), int(d))


def months():
    m = START
    while m <= END:
        yield m, min(m + pd.offsets.MonthEnd(0), END)
        m = m + pd.offsets.MonthBegin(1)


# ---------------------------------------------------------------------------
# 處置
# ---------------------------------------------------------------------------

def period_dates(text: str):
    ds = re.findall(r"(\d{2,3})[/年](\d{1,2})[/月](\d{1,2})", text)
    if len(ds) >= 2:
        return [pd.Timestamp(int(y) + 1911, int(m), int(d)) for y, m, d in ds[:2]]
    return [pd.NaT, pd.NaT]


def fetch_disposition(s) -> pd.DataFrame:
    rows = []
    for a, b in months():
        key = a.strftime("%Y%m")
        tw = json.loads(_cached(f"twse_punish_{key}.json", lambda: _get(
            s, "GET", "https://www.twse.com.tw/rwd/zh/announcement/punish",
            params={"startDate": a.strftime("%Y%m%d"), "endDate": b.strftime("%Y%m%d"), "response": "json"}).text))
        f = tw.get("fields") or []
        for r in tw.get("data") or []:
            x = dict(zip(f, r))
            p0, p1 = period_dates(x.get("處置起迄時間", ""))
            rows.append({"market": "sii", "announce": parse_roc(x["公布日期"]), "stock_id": str(x["證券代號"]).strip(),
                         "count": x.get("累計"), "measure": x.get("處置措施", ""), "start": p0, "end": p1})
        tp = json.loads(_cached(f"tpex_disposal_{key}.json", lambda: _get(
            s, "GET", "https://www.tpex.org.tw/www/zh-tw/bulletin/disposal",
            params={"startDate": a.strftime("%Y/%m/%d"), "endDate": b.strftime("%Y/%m/%d"), "response": "json"}).text))
        for t in tp.get("tables") or []:
            f = t.get("fields") or []
            for r in t.get("data") or []:
                x = dict(zip(f, r))
                code = str(x.get("證券代號", "")).strip()
                if not code:
                    continue
                p0, p1 = period_dates(str(x.get("處置起訖時間", "")))
                rows.append({"market": "otc", "announce": parse_roc(x["公布日期"]), "stock_id": code,
                             "count": x.get("累計"), "measure": str(x.get("處置措施", "")), "start": p0, "end": p1})
        print(f"處置 {key}：累計 {len(rows)} 筆", flush=True)
    df = pd.DataFrame(rows)
    df = df[df["stock_id"].str.fullmatch(r"\d{4}")]
    df["second"] = df["measure"].str.contains("第二次|第三次|再次")
    return df.drop_duplicates(["market", "announce", "stock_id"]).sort_values("announce")


# ---------------------------------------------------------------------------
# 庫藏股
# ---------------------------------------------------------------------------

BB_COLS = ["seq", "stock_id", "name", "board_date", "purpose", "cap_amount", "plan_shares", "price_lo", "price_hi",
           "period_start", "period_end", "done", "bought", "cancelled", "exec_pct", "amount", "avg_price", "pct_out"]


def parse_buyback(html: str) -> list[dict]:
    out = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, flags=re.S):
        cells = [re.sub(r"<[^>]+>|&nbsp;", " ", c).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, flags=re.S)]
        if len(cells) < 15 or not re.fullmatch(r"\d+", cells[0] or "") or not re.fullmatch(r"\d{4}", cells[1] or ""):
            continue
        x = dict(zip(BB_COLS, cells))
        num = lambda v: float(v.replace(",", "")) if v and re.fullmatch(r"[\d,\.]+", v.replace(" ", "")) else float("nan")  # noqa: E731
        out.append({"stock_id": x["stock_id"], "board_date": parse_roc(x["board_date"]), "purpose": x["purpose"],
                    "plan_shares": num(x["plan_shares"]), "price_lo": num(x["price_lo"]), "price_hi": num(x["price_hi"]),
                    "period_start": parse_roc(x["period_start"]), "period_end": parse_roc(x["period_end"])})
    return out


def fetch_buyback(s) -> pd.DataFrame:
    rows = []
    q = START
    while q <= END:
        e = min(q + pd.offsets.QuarterEnd(0), END)
        for typek in ("sii", "otc"):
            def fetch():
                body = {"apiName": "ajax_t35sc09", "parameters": {"d1": roc(q), "d2": roc(e), "TYPEK": typek, "RD": "1",
                                                                   "encodeURIComponent": 1, "step": 1, "firstin": 1, "off": 1}}
                url = _get(s, "POST", "https://mops.twse.com.tw/mops/api/redirectToOld", json=body).json()["result"]["url"]
                h = _get(s, "GET", url, headers={"Accept": "text/html"})
                h.encoding = "utf-8"
                if "日期必需" in h.text or "買回自己公司股份" not in h.text:
                    raise RuntimeError("公開資訊觀測站回應異常")
                return h.text
            got = parse_buyback(_cached(f"buyback_{typek}_{q.strftime('%Y%m')}.html", fetch))
            rows += [r | {"market": typek} for r in got]
        print(f"庫藏股 {q.strftime('%Y-%m')} 季：累計 {len(rows)} 筆", flush=True)
        q = q + pd.offsets.QuarterBegin(1, startingMonth=1)
    return pd.DataFrame(rows).drop_duplicates(["stock_id", "board_date"]).sort_values("board_date")


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Origin": "https://mops.twse.com.tw", "Referer": "https://mops.twse.com.tw/mops/",
                      "Accept": "application/json, text/plain, */*"})
    what = sys.argv[1:] or ["disposition", "buyback"]
    if "disposition" in what:
        d = fetch_disposition(s)
        d.to_csv(OUT / "disposition.csv", index=False)
        print(f"處置：{len(d)} 筆、{d['stock_id'].nunique()} 檔", flush=True)
    if "buyback" in what:
        b = fetch_buyback(s)
        b.to_csv(OUT / "buyback.csv", index=False)
        print(f"庫藏股：{len(b)} 筆、{b['stock_id'].nunique()} 檔", flush=True)
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
