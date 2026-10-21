"""I041 資料：抓 PTT Stock 板索引頁的文章標題（只抓索引頁，不抓內文與推文）。

用法（於專案根目錄；可中斷，重跑會從上次抓到的頁數續抓）：
    .venv/Scripts/python analysis/fetch_ptt_titles.py --start 215 --end 9900
輸出 data_cache/events/ptt_stock_titles.csv：page、aid（文章 ID，例如 M.1546300800.A.123）、ts（ID 內的 Unix 時間，UTC）、
title、push（推文數欄位原字串）、author。已刪除的文章（沒有連結）略過。
每頁間隔 3 秒，連線錯誤自動重試；研究用途。
"""
import argparse
import csv
import html
import re
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data_cache" / "events" / "ptt_stock_titles.csv"
DONE = ROOT / "data_cache" / "events" / "ptt_stock_pages_done.txt"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
COLS = ["page", "aid", "ts", "title", "push", "author"]
ENT = re.compile(r'<div class="r-ent">(.*?)<div class="mark">', re.S)


def parse(t: str, page: int) -> list[dict]:
    rows = []
    for blk in ENT.findall(t):
        m = re.search(r'<a href="/bbs/Stock/(M\.(\d+)\.A\.[0-9A-F]+)\.html">(.*?)</a>', blk, re.S)
        if not m:
            continue
        push = re.search(r'<div class="nrec">(?:<span[^>]*>)?([^<]*)', blk)
        au = re.search(r'<div class="author">([^<]*)</div>', blk)
        rows.append({"page": page, "aid": m.group(1), "ts": int(m.group(2)), "title": html.unescape(m.group(3)).strip(),
                     "push": push.group(1).strip() if push else "", "author": au.group(1).strip() if au else ""})
    return rows


def get(sess: requests.Session, page: int) -> str | None:
    url = f"https://www.ptt.cc/bbs/Stock/index{page}.html"
    for k in range(6):
        try:
            r = sess.get(url, timeout=30)
            if r.status_code == 200:
                return r.text
            if r.status_code == 404:
                return ""
        except requests.RequestException:
            pass
        time.sleep(15 * (k + 1))
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=int, default=215)
    ap.add_argument("--end", type=int, default=9900)
    ap.add_argument("--sleep", type=float, default=3.0)
    a = ap.parse_args()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    done = set(int(x) for x in DONE.read_text().split()) if DONE.exists() else set()
    new = not OUT.exists()
    sess = requests.Session()
    sess.headers["User-Agent"] = UA
    sess.cookies.set("over18", "1", domain=".ptt.cc")
    todo = [p for p in range(a.start, a.end + 1) if p not in done]
    print(f"[ptt] 待抓 {len(todo)} 頁（已完成 {len(done)}）", flush=True)
    failed = 0
    with open(OUT, "a", newline="", encoding="utf-8") as f, open(DONE, "a") as fd:
        w = csv.DictWriter(f, COLS)
        if new:
            w.writeheader()
        for i, p in enumerate(todo):
            t = get(sess, p)
            if t is None:
                failed += 1
                print(f"[ptt] index{p} 失敗", flush=True)
            else:
                w.writerows(parse(t, p))
                f.flush()
                fd.write(f"{p}\n")
                fd.flush()
            if i % 200 == 0:
                print(f"[ptt] {i}/{len(todo)}（index{p}）", flush=True)
            time.sleep(a.sleep)
    print(f"[ptt] 完成；失敗 {failed} 頁（重跑會補抓）", flush=True)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
