"""抓公司事件公告：重大訊息主旨全文檢索（現金增資、可轉債的董事會決議；點子卡 I012）與內部人持股轉讓事前申報（I011）。

用法（於專案根目錄）：
    .venv/Scripts/python analysis/fetch_corp_events.py            # 兩者都抓
    .venv/Scripts/python analysis/fetch_corp_events.py headlines  # 只抓重大訊息
    .venv/Scripts/python analysis/fetch_corp_events.py insider    # 只抓內部人轉讓
輸出 data_cache/events/corp_headlines.csv、data_cache/events/insider_transfers.csv；原始回應快取在 data_cache/events/corp_raw/。

- 重大訊息：POST mopsov.twse.com.tw/mops/web/ajax_t51sb10（主旨全文檢索），keyWord ∈ {轉換公司債, 現金增資}、keyWord2 = 董事會、
  KIND = L（上市）／O（上櫃）、year = 西元年、全年，每頁 100 筆翻頁；欄位：代號、簡稱、發言日期、序號、主旨、發言時間。
- 內部人轉讓：POST ajax_t56sb21（董監事持股轉讓事前申報彙總），TYPEK = sii／otc、year = 民國年、1–12 月，一次一年。
- 法說會：公開資訊觀測站「法人說明會一覽表」（ajax_t100sb02_1，經 /mops/api/redirectToOld），TYPEK = sii／otc、year = 民國年、全年；
  2016 起（判斷「首次召開」需要前 3 年）；欄位：代號、名稱、召開日期（可能為區間）、時間、地點、擇要訊息、中英文簡報檔名。
- 每次請求間隔 2.5 秒；已快取的頁面不重抓。
"""
import html
import re
import sys
import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data_cache" / "events"
RAW = OUT / "corp_raw"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
YEARS = range(2019, 2027)
_last = [0.0]


def post(url: str, data: dict, referer: str) -> str:
    for k in range(4):
        wait = 2.5 - (time.time() - _last[0])
        if wait > 0:
            time.sleep(wait)
        try:
            r = requests.post(url, data=data, timeout=120, headers={"User-Agent": UA, "Referer": referer, "Origin": "https://mopsov.twse.com.tw",
                                                                   "Accept": "text/html"})
            _last[0] = time.time()
            if r.status_code == 200 and len(r.content) > 1000:
                r.encoding = "utf-8"
                return r.text
            print(f"  HTTP {r.status_code}（{len(r.content)} bytes），重試", flush=True)
        except requests.RequestException as e:
            _last[0] = time.time()
            print(f"  連線錯誤（{type(e).__name__}），重試", flush=True)
        time.sleep(15 * (k + 1))
    raise RuntimeError(f"多次失敗：{url} {data}")


def cached(name: str, fetch) -> str:
    p = RAW / name
    if p.exists():
        return p.read_text(encoding="utf-8")
    t = fetch()
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(t, encoding="utf-8")
    tmp.replace(p)
    return t


def roc(s: str):
    m = re.search(r"(\d{2,3})/(\d{1,2})/(\d{1,2})", s or "")
    return pd.Timestamp(int(m.group(1)) + 1911, int(m.group(2)), int(m.group(3))) if m else pd.NaT


def parse_headlines(t: str) -> list[dict]:
    out = []
    for tr in re.findall(r"<TR class=.*?</TR>", t, flags=re.S | re.I):
        tds = re.findall(r"<TD[^>]*>(.*?)</TD>", tr, flags=re.S | re.I)
        if len(tds) < 6:
            continue
        clean = [re.sub(r"\s+", "", html.unescape(re.sub(r"<[^>]+>", "", x))).replace("\xa0", "") for x in tds[:5]]
        tm = re.search(r'spoke_time\.value="(\d+)"', tds[5])
        typek = re.search(r'TYPEK\.value="(\w+)"', tds[5])
        out.append({"stock_id": clean[0], "name": clean[1], "date": roc(clean[2]), "seq": clean[3], "subject": clean[4],
                    "spoke_time": tm.group(1) if tm else "", "market": typek.group(1) if typek else ""})
    return out


def fetch_headlines() -> pd.DataFrame:
    rows = []
    for kw in ("轉換公司債", "現金增資"):
        for kind in ("L", "O"):
            for y in YEARS:
                page = 1
                while True:
                    data = {"pagenum": str(page), "Stp": "4", "r1": "1", "KIND": kind, "CODE": "", "month1": "0", "begin_day": "1", "end_day": "31",
                            "keyWord": kw, "Condition2": "1", "keyWord2": "董事會", "Orderby": "", "step": "2", "colorchg": "1", "co_id": "",
                            "TYPEK": "", "off": "1", "firstin": "1", "i": "", "year": str(y), "month": "0", "spoke_date": "", "spoke_time": "",
                            "seq_no": "", "b_date": "1", "e_date": "31", "PCount": "100"}
                    t = cached(f"t51_{'cb' if kw == '轉換公司債' else 'seo'}_{kind}_{y}_p{page}.html",
                               lambda: post("https://mopsov.twse.com.tw/mops/web/ajax_t51sb10", data, "https://mopsov.twse.com.tw/mops/web/t51sb10_q1"))
                    got = parse_headlines(t)
                    rows += [r | {"keyword": kw} for r in got]
                    pages = [int(x) for x in re.findall(r"pagenum\.value='(\d+)'", t)]
                    if len(got) < 100 or not pages or page >= max(pages):
                        break
                    page += 1
                print(f"{kw} {kind} {y}：累計 {len(rows)} 筆", flush=True)
    df = pd.DataFrame(rows)
    return df.drop_duplicates(["stock_id", "date", "seq", "subject"]).sort_values("date")


def num(s: str) -> float:
    s = re.sub(r"[^\d.]", "", s or "")
    return float(s) if s else float("nan")


def fetch_insider() -> pd.DataFrame:
    rows = []
    for y in range(107, 116):
        for typek in ("sii", "otc"):
            texts = []
            for sm, em, tag in (("01", "12", ""),):
                data = {"encodeURIComponent": 1, "step": 1, "firstin": 1, "off": 1, "TYPEK": typek, "year": str(y), "smonth": sm, "emonth": em, "sstep": "1"}
                t = cached(f"t56_{typek}_{y}{tag}.html", lambda: post("https://mopsov.twse.com.tw/mops/web/ajax_t56sb21", data, "https://mopsov.twse.com.tw/mops/web/t56sb21_q1"))
                if "資料筆數過多" in t:                       # 一年太多筆：改成每季查詢
                    (RAW / f"t56_{typek}_{y}.html").unlink(missing_ok=True)
                    for q, (a, b) in enumerate((("01", "03"), ("04", "06"), ("07", "09"), ("10", "12")), 1):
                        dq = data | {"smonth": a, "emonth": b}
                        tq = cached(f"t56_{typek}_{y}_q{q}.html", lambda: post("https://mopsov.twse.com.tw/mops/web/ajax_t56sb21", dq, "https://mopsov.twse.com.tw/mops/web/t56sb21_q1"))
                        if "資料筆數過多" in tq:
                            raise RuntimeError(f"{typek} {y} Q{q} 仍然資料過多")
                        texts.append(tq)
                else:
                    texts.append(t)
            t = "".join(texts)
            for tr in re.findall(r"<tr class='(?:odd|even)'>(.*?)</tr>", t, flags=re.S | re.I):
                c = [re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", x))).replace("\xa0", " ").strip() for x in re.findall(r"<td[^>]*>(.*?)</td>", tr, flags=re.S | re.I)]
                if len(c) < 17:
                    continue
                period = re.findall(r"\d{2,3}/\d{1,2}/\d{1,2}", c[16])
                rows.append({"change": c[0], "date": roc(c[1]), "stock_id": c[2], "name": c[3], "role": c[4], "method": c[6],
                             "shares_planned": num(c[7]), "held": num(c[10]), "transfer_total": num(c[12]),
                             "period_start": roc(period[0]) if period else pd.NaT, "period_end": roc(period[1]) if len(period) > 1 else pd.NaT,
                             "market": typek})
            print(f"內部人轉讓 {typek} {y}：累計 {len(rows)} 筆", flush=True)
    return pd.DataFrame(rows).sort_values("date")


def fetch_conferences() -> pd.DataFrame:
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Origin": "https://mops.twse.com.tw", "Referer": "https://mops.twse.com.tw/mops/",
                      "Accept": "application/json, text/plain, */*"})

    def get(typek, y):
        def fetch():
            for k in range(4):
                wait = 2.5 - (time.time() - _last[0])
                if wait > 0:
                    time.sleep(wait)
                try:
                    body = {"apiName": "ajax_t100sb02_1", "parameters": {"TYPEK": typek, "year": str(y), "month": "all",
                                                                          "encodeURIComponent": 1, "step": 1, "firstin": 1, "off": 1}}
                    url = s.post("https://mops.twse.com.tw/mops/api/redirectToOld", json=body, timeout=60).json()["result"]["url"]
                    time.sleep(2.5)
                    h = s.get(url, timeout=120, headers={"Accept": "text/html"})
                    _last[0] = time.time()
                    h.encoding = "utf-8"
                    if h.status_code == 200 and len(h.content) > 1000:
                        return h.text
                except (requests.RequestException, KeyError, ValueError) as e:
                    _last[0] = time.time()
                    print(f"  {type(e).__name__}，重試", flush=True)
                time.sleep(15 * (k + 1))
            raise RuntimeError(f"法說會 {typek} {y} 多次失敗")
        return cached(f"t100_{typek}_{y}.html", fetch)

    rows = []
    for y in range(105, 116):
        for typek in ("sii", "otc"):
            t = get(typek, y)
            if "資料筆數過多" in t:
                raise RuntimeError(f"法說會 {typek} {y} 資料過多")
            for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", t, flags=re.S | re.I):
                c = [re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", x))).strip() for x in re.findall(r"<td[^>]*>(.*?)</td>", tr, flags=re.S | re.I)]
                if len(c) < 10 or not re.fullmatch(r"\d{4}", c[0] or ""):
                    continue
                ds = re.findall(r"\d{2,3}/\d{1,2}/\d{1,2}", c[2])
                rows.append({"stock_id": c[0], "name": c[1], "date": roc(ds[0]) if ds else pd.NaT, "date_end": roc(ds[-1]) if ds else pd.NaT,
                             "time": c[3], "place": c[4], "summary": c[5], "slide_zh": c[6], "slide_en": c[7], "market": typek})
            print(f"法說會 {typek} {y}：累計 {len(rows)} 筆", flush=True)
    return pd.DataFrame(rows).dropna(subset=["date"]).sort_values("date")


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    what = sys.argv[1:] or ["headlines", "insider"]
    if "conference" in what:
        c = fetch_conferences()
        c.to_csv(OUT / "conferences.csv", index=False)
        print(f"法說會：{len(c)} 筆", flush=True)
    if "insider" in what:
        d = fetch_insider()
        d.to_csv(OUT / "insider_transfers.csv", index=False)
        print(f"內部人轉讓：{len(d)} 筆", flush=True)
    if "headlines" in what:
        h = fetch_headlines()
        h.to_csv(OUT / "corp_headlines.csv", index=False)
        print(f"重大訊息：{len(h)} 筆", flush=True)
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
