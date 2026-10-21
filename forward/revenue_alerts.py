"""月營收驚奇快報：每月營收公告期間，找出市值前 500 名中 SUE ≥ 2 的股票，產生網頁並推送 Telegram。

用法（於專案根目錄）：
    .venv/Scripts/python forward/revenue_alerts.py            # 抓最新營收、更新名單與網頁、推送新出現的股票
    .venv/Scripts/python forward/revenue_alerts.py --no-send  # 只更新，不推送
    （forward/run_forward.py auto 每天呼叫 auto()）

- 資料：公開資訊觀測站營收彙總表 t21sc03（上市／上櫃 × 本國／外國公司，每月 4 頁），歷史頁快取在 data_cache/events/corp_raw/t21/；
  營收月份 m 在 m+1 月 20 日前視為「公告中」，每次都重抓並覆蓋快取。
- SUE：與本專案相同公式（data/revenue_signal.revenue_surprise）：(本月 − 去年同月 − 過去 24 個月年差平均) ÷ 年差標準差，最少 12 個年差。
- 名單：config/universe_mcap_membership.csv 最新年度市值前 500 名，SUE ≥ 2。
- 紀錄：forward/alerts/revenue_alerts.csv（每檔每營收月份一列，第一次出現時間）；網頁 site/revenue-alerts.html。
- Telegram：讀取環境變數（.env）TELEGRAM_BOT_TOKEN、TELEGRAM_CHAT_ID；未設定時略過推送。程式不會輸出金鑰。
研究用途，非投資建議。
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import re
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data_cache" / "events" / "corp_raw" / "t21"
ALERTS = ROOT / "forward" / "alerts" / "revenue_alerts.csv"
PAGE = ROOT / "site" / "revenue-alerts.html"
MEMBERSHIP = ROOT / "config" / "universe_mcap_membership.csv"
PUBLISH_FILES = [str(p.relative_to(ROOT)).replace("\\", "/") for p in (ALERTS, PAGE)]
THRESHOLD = 2.0
TOP_N = 500
START = pd.Period("2018-12", "M")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
COLUMNS = ["rev_month", "stock_id", "name", "sector", "sue", "yoy", "mom", "revenue", "remark", "first_seen"]


def is_open(p: pd.Period, today: dt.date) -> bool:
    nxt = (p + 1).to_timestamp()
    return pd.Timestamp(today) < nxt + pd.Timedelta(days=19)


def page(mkt: str, p: pd.Period, kind: int, refresh: bool) -> str:
    path = RAW / f"{mkt}_{p.year - 1911}_{p.month}_{kind}.html"
    if path.exists() and not refresh:
        return path.read_text(encoding="utf-8")
    url = f"https://mopsov.twse.com.tw/nas/t21/{mkt}/t21sc03_{p.year - 1911}_{p.month}_{kind}.html"
    for k in range(3):
        try:
            r = requests.get(url, headers={"User-Agent": UA}, timeout=60)
            time.sleep(3)
            if r.status_code == 200:
                t = r.content.decode("big5", errors="replace")
                if len(t) > 5000:
                    RAW.mkdir(parents=True, exist_ok=True)
                    path.write_text(t, encoding="utf-8")
                return t
        except requests.RequestException:
            time.sleep(10 * (k + 1))
    return path.read_text(encoding="utf-8") if path.exists() else ""


def parse(t: str) -> list[dict]:
    rows = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", t, flags=re.S | re.I):
        c = [re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", x))).strip() for x in re.findall(r"<td[^>]*>(.*?)</td>", tr, flags=re.S | re.I)]
        if len(c) >= 10 and re.fullmatch(r"\d{4}", c[0]):
            try:
                rev = float(c[2].replace(",", ""))
            except ValueError:
                continue
            rows.append({"stock_id": c[0], "name": c[1], "revenue": rev, "remark": c[-1] if len(c) >= 11 and c[-1] not in ("-", "") else ""})
    return rows


def load(today: dt.date) -> tuple[pd.DataFrame, pd.Period]:
    last = pd.Period(today, "M") - 1
    frames, latest = [], None
    for p in pd.period_range(START, last, freq="M"):
        rows = []
        for mkt in ("sii", "otc"):
            for kind in (0, 1):
                rows += parse(page(mkt, p, kind, refresh=is_open(p, today)))
        if rows:
            frames.append(pd.DataFrame(rows).assign(p=p))
            latest = p
    df = pd.concat(frames).drop_duplicates(["stock_id", "p"], keep="last")
    return df, latest


def sue_table(df: pd.DataFrame) -> pd.DataFrame:
    rev = df.pivot(index="p", columns="stock_id", values="revenue").sort_index()
    rev = rev.reindex(pd.period_range(rev.index.min(), rev.index.max(), freq="M"))
    rev = rev.where(rev > 0)
    diff = rev - rev.shift(12)
    mu = diff.shift(1).rolling(24, min_periods=12).mean()
    sd = diff.shift(1).rolling(24, min_periods=12).std()
    sue = (diff - mu) / sd.where(sd > 0)
    yoy = rev / rev.shift(12) - 1
    mom = rev / rev.shift(1) - 1
    out = pd.concat({"sue": sue.stack(), "yoy": yoy.stack(), "mom": mom.stack(), "revenue": rev.stack()}, axis=1).reset_index()
    out.columns = ["p", "stock_id", "sue", "yoy", "mom", "revenue"]
    return out


def members() -> pd.DataFrame:
    m = pd.read_csv(MEMBERSHIP, dtype={"stock_id": str})
    m = m[(m["year"] == m["year"].max()) & (m["rank"] <= TOP_N)]
    return m.set_index("stock_id")[["stock_name", "sector", "rank"]]


def read_alerts() -> pd.DataFrame:
    if ALERTS.exists() and ALERTS.stat().st_size > 0:
        return pd.read_csv(ALERTS, dtype={"stock_id": str, "rev_month": str})
    return pd.DataFrame(columns=COLUMNS)


def telegram(lines: list[str]) -> str:
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN", ""), os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat:
        return "未設定 TELEGRAM_BOT_TOKEN／TELEGRAM_CHAT_ID，略過推送"
    chunks, cur = [], ""
    for ln in lines:
        if len(cur) + len(ln) + 1 > 3800:
            chunks.append(cur)
            cur = ""
        cur += ln + "\n"
    if cur:
        chunks.append(cur)
    ok = 0
    for ch in chunks:
        try:
            r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", data={"chat_id": chat, "text": ch, "disable_web_page_preview": "true"}, timeout=30)
            ok += r.status_code == 200
        except requests.RequestException:
            pass
        time.sleep(1)
    return f"Telegram 推送 {ok}/{len(chunks)} 則"


def render(alerts: pd.DataFrame, latest: pd.Period, reported: int, universe_reported: int, updated: str) -> None:
    data = alerts.sort_values(["rev_month", "sue"], ascending=[False, False]).to_dict("records")
    for r in data:
        for k in ("sue", "yoy", "mom", "revenue"):
            r[k] = None if pd.isna(r[k]) else float(r[k])
        r["remark"] = "" if pd.isna(r.get("remark")) else str(r["remark"]).replace("�", "")   # big5 無法解碼的字元
        r["name"] = str(r["name"]).replace("�", "")
    meta = {"latest": str(latest), "reported": int(reported), "universe_reported": int(universe_reported), "updated": updated,
            "threshold": THRESHOLD, "top_n": TOP_N}
    tpl = (ROOT / "forward" / "alerts" / "page_template.html").read_text(encoding="utf-8")
    out = tpl.replace("__DATA__", json.dumps(data, ensure_ascii=False)).replace("__META__", json.dumps(meta, ensure_ascii=False))
    PAGE.write_text(out, encoding="utf-8")


def run(send: bool = True) -> bool:
    today = dt.date.today()
    df, latest = load(today)
    S = sue_table(df)
    mem = members()
    S = S[S["stock_id"].isin(mem.index)]
    names = df.drop_duplicates("stock_id", keep="last").set_index("stock_id")["name"]
    remarks = df.set_index(["stock_id", "p"])["remark"]
    hits = S[(S["sue"] >= THRESHOLD) & (S["p"] >= latest - 2)]
    old = read_alerts()
    have = set(zip(old["rev_month"].astype(str), old["stock_id"].astype(str)))
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    new_rows = []
    for r in hits.itertuples():
        key = (str(r.p), r.stock_id)
        if key in have:
            continue
        new_rows.append({"rev_month": str(r.p), "stock_id": r.stock_id, "name": names.get(r.stock_id, mem.at[r.stock_id, "stock_name"]),
                         "sector": mem.at[r.stock_id, "sector"], "sue": round(float(r.sue), 3), "yoy": r.yoy, "mom": r.mom,
                         "revenue": r.revenue, "remark": remarks.get((r.stock_id, r.p), ""), "first_seen": now})
    alerts = pd.concat([old, pd.DataFrame(new_rows, columns=COLUMNS)], ignore_index=True) if new_rows else old
    ALERTS.parent.mkdir(parents=True, exist_ok=True)
    alerts[COLUMNS].to_csv(ALERTS, index=False, encoding="utf-8")
    lat = S[S["p"] == latest]
    render(alerts, latest, int(lat["sue"].notna().sum()), int(len(mem)), now)
    print(f"[alerts] 最新營收月份 {latest}；前 500 名已公告 {lat['sue'].notna().sum()} 檔；新增 SUE ≥ {THRESHOLD} {len(new_rows)} 檔")
    if new_rows and send:
        f = lambda x: "—" if x is None or pd.isna(x) else f"{x:+.1%}"  # noqa: E731
        lines = [f"月營收驚奇快報（SUE ≥ {THRESHOLD:g}，市值前 {TOP_N} 名）新增 {len(new_rows)} 檔："]
        for r in sorted(new_rows, key=lambda x: -x["sue"]):
            lines.append(f"{r['stock_id']} {r['name']}（{r['sector']}）{r['rev_month']} SUE {r['sue']:.2f}，年增 {f(r['yoy'])}，月增 {f(r['mom'])}")
        lines.append("研究用途，非投資建議。")
        print("[alerts]", telegram(lines))
    return bool(new_rows)


def auto() -> bool:
    return run(send=True)


def main(argv=None) -> None:
    import dotenv

    dotenv.load_dotenv(ROOT / ".env")
    ap = argparse.ArgumentParser(description="月營收驚奇快報")
    ap.add_argument("--no-send", action="store_true")
    a = ap.parse_args(argv)
    run(send=not a.no_send)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
