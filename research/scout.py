"""strategy-scout 的工具：搜尋文獻／部落格／論壇、比對已測點子、查資料可得性、寫點子卡。

用法（於專案根目錄）：
    .venv/Scripts/python research/scout.py lit "revenue surprise emerging markets" --since 2010 --n 15
    .venv/Scripts/python research/scout.py blogs --q "dividend" --n 20
    .venv/Scripts/python research/scout.py ptt "填息" --board Stock --pages 2
    .venv/Scripts/python research/scout.py dedup "post-earnings announcement drift with analyst coverage"
    .venv/Scripts/python research/scout.py data "券商分點"              # 查 data_catalog.yaml
    .venv/Scripts/python research/scout.py data --probe TaiwanStockDayTrading   # 向 FinMind 試抓，判斷免費或付費
    .venv/Scripts/python research/scout.py card research/ideas/_draft.json      # 由 JSON 寫點子卡並登錄到 ideas.csv

搜尋結果快取在 data_cache/research/（同一查詢一天內不重抓）；每個網站請求間隔 2 秒。
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import html
import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import requests
import yaml

ROOT = Path(__file__).resolve().parent.parent
RESEARCH = ROOT / "research"
CACHE = ROOT / "data_cache" / "research"
IDEAS_DIR = RESEARCH / "ideas"
IDEAS_CSV = RESEARCH / "ideas.csv"
UA = "Mozilla/5.0 (research-scout; precision-weighted-investment-agent)"
FEEDS = {
    "Quantocracy": "https://quantocracy.com/feed/",
    "Alpha Architect": "https://alphaarchitect.com/feed/",
    "QuantPedia": "https://quantpedia.com/feed/",
    "Robot Wealth": "https://robotwealth.com/feed/",
    "CXO Advisory": "https://www.cxoadvisory.com/feed/",
}
_last = [0.0]


def _get(url: str, **kw) -> requests.Response:
    wait = 2.0 - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    headers = {"User-Agent": UA} | kw.pop("headers", {})
    r = requests.get(url, headers=headers, timeout=60, **kw)
    _last[0] = time.time()
    r.raise_for_status()
    return r


def _cached(key: str, fetch, max_age_h: float = 24.0):
    CACHE.mkdir(parents=True, exist_ok=True)
    p = CACHE / (hashlib.md5(key.encode("utf-8")).hexdigest()[:16] + ".json")
    if p.exists() and time.time() - p.stat().st_mtime < max_age_h * 3600:
        return json.loads(p.read_text(encoding="utf-8"))
    data = fetch()
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)
    return data


def _clip(s: str, n: int) -> str:
    s = re.sub(r"\s+", " ", s or "").strip()
    return s if len(s) <= n else s[: n - 1] + "…"


# ---------------------------------------------------------------------------
# 學術文獻：arXiv（q-fin）、OpenAlex（含 SSRN、期刊、NBER）
# ---------------------------------------------------------------------------

def arxiv(query: str, n: int, since: int) -> list[dict]:
    def fetch():
        q = " AND ".join(f'all:"{w}"' if " " in w else f"all:{w}" for w in query.split())
        r = _get("https://export.arxiv.org/api/query", params={
            "search_query": f"({q}) AND cat:q-fin.*", "start": 0, "max_results": n * 2,
            "sortBy": "relevance"})
        ns = {"a": "http://www.w3.org/2005/Atom"}
        out = []
        for e in ET.fromstring(r.text).findall("a:entry", ns):
            year = int(e.findtext("a:published", "0000", ns)[:4])
            out.append({"source": "arXiv", "title": _clip(e.findtext("a:title", "", ns), 200), "year": year,
                        "venue": "arXiv", "cited": None, "url": e.findtext("a:id", "", ns),
                        "abstract": _clip(e.findtext("a:summary", "", ns), 700)})
        return out
    return [x for x in _cached(f"arxiv|{query}|{n}", fetch) if x["year"] >= since][:n]


def _openalex_abstract(inv: dict | None) -> str:
    if not inv:
        return ""
    pos = sorted((p, w) for w, ps in inv.items() for p in ps)
    return " ".join(w for _, w in pos)


def openalex(query: str, n: int, since: int) -> list[dict]:
    def fetch():
        r = _get("https://api.openalex.org/works", params={
            "search": query, "per-page": n * 2,
            "filter": f"from_publication_date:{since}-01-01,concepts.id:C10138342",   # Finance
            "sort": "relevance_score:desc", "mailto": "research-scout@example.invalid"})
        out = []
        for w in r.json().get("results", []):
            loc = (w.get("primary_location") or {}).get("source") or {}
            out.append({"source": "OpenAlex", "title": _clip(w.get("display_name") or "", 200),
                        "year": w.get("publication_year") or 0, "venue": loc.get("display_name") or "",
                        "cited": w.get("cited_by_count"), "url": w.get("doi") or w.get("id"),
                        "abstract": _clip(_openalex_abstract(w.get("abstract_inverted_index")), 700)})
        return out
    return _cached(f"openalex|{query}|{n}|{since}", fetch)[:n]


def cmd_lit(a):
    rows = []
    for fn in (openalex, arxiv):
        try:
            rows += fn(a.query, a.n, a.since)
        except Exception as e:  # noqa: BLE001
            print(f"[{fn.__name__}] 失敗：{type(e).__name__} {e}", file=sys.stderr)
    for k, x in enumerate(rows, 1):
        cited = f"，引用 {x['cited']}" if x["cited"] is not None else ""
        print(f"## L{k}. {x['title']}（{x['year']}，{x['venue']}{cited}）\n{x['url']}\n{x['abstract']}\n")
    print(f"共 {len(rows)} 筆")


# ---------------------------------------------------------------------------
# 量化部落格（RSS）
# ---------------------------------------------------------------------------

def blog_items(name: str, url: str) -> list[dict]:
    def fetch():
        root = ET.fromstring(_get(url).content)
        out = []
        for it in root.iter("item"):
            desc = re.sub(r"<[^>]+>", " ", html.unescape(it.findtext("description", "") or ""))
            out.append({"source": name, "title": _clip(it.findtext("title", ""), 200), "url": it.findtext("link", ""),
                        "date": it.findtext("pubDate", ""), "summary": _clip(desc, 500)})
        return out
    return _cached(f"feed|{url}", fetch, max_age_h=12)


def cmd_blogs(a):
    rows = []
    for name, url in FEEDS.items():
        try:
            rows += blog_items(name, url)
        except Exception as e:  # noqa: BLE001
            print(f"[{name}] 失敗：{type(e).__name__}", file=sys.stderr)
    if a.q:
        q = a.q.lower()
        rows = [x for x in rows if q in (x["title"] + " " + x["summary"]).lower()]
    for k, x in enumerate(rows[: a.n], 1):
        print(f"## B{k}. [{x['source']}] {x['title']}（{x['date'][:16]}）\n{x['url']}\n{x['summary']}\n")
    print(f"共 {min(len(rows), a.n)} 筆（RSS 只含最近的文章；較舊的文章請用網頁搜尋）")


# ---------------------------------------------------------------------------
# 台灣論壇：PTT
# ---------------------------------------------------------------------------

def cmd_ptt(a):
    def fetch():
        out = []
        for page in range(1, a.pages + 1):
            r = _get(f"https://www.ptt.cc/bbs/{a.board}/search", params={"q": a.query, "page": page},
                     cookies={"over18": "1"})
            for blk in re.findall(r'<div class="r-ent">(.*?)</div>\s*</div>\s*</div>', r.text, flags=re.S):
                m = re.search(r'<a href="([^"]+)">(.*?)</a>', blk)
                if not m:
                    continue
                push = re.search(r'<div class="nrec">(?:<span[^>]*>)?([^<]*)', blk)
                date = re.search(r'<div class="date">\s*([^<]+)', blk)
                out.append({"title": html.unescape(m.group(2)).strip(), "url": "https://www.ptt.cc" + m.group(1),
                            "push": (push.group(1).strip() if push else ""), "date": (date.group(1).strip() if date else "")})
        return out
    rows = _cached(f"ptt|{a.board}|{a.query}|{a.pages}", fetch, max_age_h=12)
    for k, x in enumerate(rows, 1):
        print(f"P{k}. [{x['push'] or '0'}] {x['date']} {x['title']}  {x['url']}")
    print(f"共 {len(rows)} 筆（推文數為熱度參考；內文請用網頁讀取，只當假設來源）")


# ---------------------------------------------------------------------------
# 去重、資料可得性、點子卡
# ---------------------------------------------------------------------------

def load_tested() -> list[dict]:
    return yaml.safe_load((RESEARCH / "tested_ideas.yaml").read_text(encoding="utf-8"))["ideas"]


def dedup_matches(text: str) -> list[tuple[int, dict, list[str]]]:
    t = text.lower()
    out = []
    for idea in load_tested():
        hits = [k for k in idea["keywords"] if k.lower() in t]
        if hits:
            out.append((len(hits), idea, hits))
    if IDEAS_CSV.exists():
        with IDEAS_CSV.open(encoding="utf-8") as f:
            for r in csv.DictReader(f):
                kws = [k.strip() for k in r.get("keywords", "").split(";") if k.strip()]
                hits = [k for k in kws if k.lower() in t]
                if hits:
                    out.append((len(hits), {"id": r["id"], "name": r["title"], "status": "card:" + r["status"], "report": r["path"]}, hits))
    return sorted(out, key=lambda x: -x[0])


def cmd_dedup(a):
    m = dedup_matches(a.text)
    if not m:
        print("沒有符合的已測點子或既有點子卡（仍請人工確認同族變體）")
    for n, idea, hits in m:
        print(f"- {idea['name']}（{idea['id']}，{idea['status']}）命中 {n}：{', '.join(hits)} → {idea['report']}")


def cmd_data(a):
    if a.probe:
        import dotenv

        dotenv.load_dotenv(ROOT / ".env")
        tok = os.environ.get("FINMIND_API_TOKEN", "")
        params = {"dataset": a.probe, "start_date": (dt.date.today() - dt.timedelta(days=10)).isoformat()}
        if a.data_id:
            params["data_id"] = a.data_id
        r = requests.get("https://api.finmindtrade.com/api/v4/data", params=params,
                         headers={"Authorization": f"Bearer {tok}"}, timeout=60)
        j = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        msg = j.get("msg", "")
        verdict = "付費（目前等級無法使用）" if "level" in msg.lower() else ("可用" if r.status_code == 200 else f"HTTP {r.status_code}")
        print(f"{a.probe}：{verdict}；{msg}；回傳 {len(j.get('data', []))} 筆；欄位 {list((j.get('data') or [{}])[0].keys())}")
        return
    cat = yaml.safe_load((RESEARCH / "data_catalog.yaml").read_text(encoding="utf-8"))["datasets"]
    q = (a.keyword or "").lower()
    for d in cat:
        if not q or q in json.dumps(d, ensure_ascii=False).lower():
            print(f"- {d['name']}｜{d['source']}｜{d['access']}｜{'已使用' if d['used'] else '未使用'}｜{d['note']}")


CARD_FIELDS = ["id", "title", "status", "priority", "test_type", "data_access", "est_api_calls", "keywords", "created", "path"]


def cmd_card(a):
    c = json.loads(Path(a.json).read_text(encoding="utf-8"))
    need = ["title", "hypothesis", "sources", "mechanism", "taiwan_fit", "data", "test_plan", "test_type", "priority", "keywords"]
    miss = [k for k in need if k not in c]
    if miss:
        sys.exit(f"缺少欄位：{miss}")
    today = dt.date.today().isoformat()
    slug = re.sub(r"[^a-z0-9]+", "-", c.get("slug", c["title"]).lower()).strip("-")[:40] or "idea"
    IDEAS_DIR.mkdir(parents=True, exist_ok=True)
    existing = []
    if IDEAS_CSV.exists():
        with IDEAS_CSV.open(encoding="utf-8") as f:
            existing = list(csv.DictReader(f))
    cid = f"I{len(existing) + 1:03d}"
    path = IDEAS_DIR / f"{cid}-{slug}.md"
    dd = dedup_matches(" ".join([c["title"], c["hypothesis"], " ".join(c["keywords"])]))
    lines = [f"# {cid} {c['title']}", "",
             f"| 狀態 | 優先度 | 檢定方式 | 資料可得性 | 預估 FinMind 請求 | 建立 |", "|---|---|---|---|---|---|",
             f"| 待確認 | {c['priority']} | {c['test_type']} | {c['data'].get('access', '')} | {c['data'].get('api_calls', '—')} | {today} |", "",
             "## 假設", "", c["hypothesis"], "", "## 機制（為什麼會有超額報酬）", "", c["mechanism"], "",
             "## 出處", ""] + [f"- {s}" for s in c["sources"]] + [
             "", "## 台股適用性", "", c["taiwan_fit"], "", "## 所需資料", ""] + \
            [f"- {x}" for x in c["data"].get("items", [])] + [
             "", "## 檢定計畫（看結果前固定）", ""] + [f"- {x}" for x in c["test_plan"]] + [
             "", "## 與已測點子的關係", ""] + \
            ([f"- {i['name']}（{i['status']}，{i['report']}）：命中 {', '.join(h)}" for _, i, h in dd] or ["- 無關鍵字重疊"]) + \
            ([f"- 補充：{c['related_note']}"] if c.get("related_note") else []) + ["", "研究點子，非投資建議。"]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    row = {"id": cid, "title": c["title"], "status": "待確認", "priority": c["priority"], "test_type": c["test_type"],
           "data_access": c["data"].get("access", ""), "est_api_calls": c["data"].get("api_calls", ""),
           "keywords": ";".join(c["keywords"]), "created": today, "path": str(path.relative_to(ROOT)).replace("\\", "/")}
    new = not IDEAS_CSV.exists()
    with IDEAS_CSV.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CARD_FIELDS)
        if new:
            w.writeheader()
        w.writerow(row)
    print(f"已建立 {row['path']}")


def main(argv=None):
    p = argparse.ArgumentParser(description="strategy-scout 工具")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("lit"); s.add_argument("query"); s.add_argument("--n", type=int, default=10); s.add_argument("--since", type=int, default=2005)
    s = sub.add_parser("blogs"); s.add_argument("--q", default=""); s.add_argument("--n", type=int, default=30)
    s = sub.add_parser("ptt"); s.add_argument("query"); s.add_argument("--board", default="Stock"); s.add_argument("--pages", type=int, default=1)
    s = sub.add_parser("dedup"); s.add_argument("text")
    s = sub.add_parser("data"); s.add_argument("keyword", nargs="?"); s.add_argument("--probe"); s.add_argument("--data-id")
    s = sub.add_parser("card"); s.add_argument("json")
    a = p.parse_args(argv)
    {"lit": cmd_lit, "blogs": cmd_blogs, "ptt": cmd_ptt, "dedup": cmd_dedup, "data": cmd_data, "card": cmd_card}[a.cmd](a)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
