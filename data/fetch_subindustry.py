"""子產業分類：櫃買中心「產業價值鏈資訊平台」（ic.tpex.org.tw）。

資料結構：
- 公司頁 company_chain.php?stk_code=XXXX：公司自行申報的所屬產業鏈，每筆為「產業鏈 > 細項」
  （例如 2330 台積電：半導體 > 晶圓製造；鴻海列了 14 筆）。
- 產業鏈介紹頁 introduce.php?ic=XXXX：產業鏈的中層分類（例如半導體的 IC設計、IC/晶圓製造、IC封裝測試），
  以及每個中層分類底下的細項（例如 IC設計 底下有電源管理IC、記憶體IC…）。
公司申報的各筆產業鏈沒有依重要性排序（台達電列了 60 多筆、第一筆是「休閒娛樂 > 休閒車業」），主要子產業依下列規則選
（看回測結果前固定）：
1. 只考慮電子核心產業鏈（CORE_CHAINS）；
2. 優先選與 FinMind 大產業對應的產業鏈（SECTOR_CHAINS）；
3. 候選產業鏈中取申報筆數最多者（代表主要業務；同筆數依優先順序），再取該鏈申報順序的第一筆；
   都不符合時退回核心產業鏈，再退回第一筆。
子產業 = 「產業鏈 / 中層分類」；細項對不到中層分類時用細項本身。

限制：分類是公司「現在」的申報內容，套用到 2019 年起的回測有輕微前視（公司業務可能轉變）；
已下市公司查不到，標為未分類並退回 FinMind 的大產業。
禮貌抓取：每次請求間隔 ≥ 1.2 秒，原始網頁快取於 data_cache/subindustry/（不進版控）。
"""
from __future__ import annotations

import html
import re
import time
from pathlib import Path

import requests

BASE = "https://ic.tpex.org.tw"
CACHE = Path(__file__).resolve().parent.parent / "data_cache" / "subindustry"
DELAY_SEC = 1.2
_last = [0.0]


def fetch(path: str) -> str:
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / (re.sub(r"[^0-9A-Za-z]+", "_", path) + ".html")
    if f.exists():
        return f.read_text(encoding="utf-8")
    wait = DELAY_SEC - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    r = requests.get(f"{BASE}/{path}", timeout=30, headers={"User-Agent": "precision-weighted-investment-agent research"})
    _last[0] = time.time()
    r.raise_for_status()
    r.encoding = "utf-8"
    f.write_text(r.text, encoding="utf-8")
    return r.text


def _clean(s: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", s)).replace("►", "").replace("\xa0", " ").strip()


def parse_company(page: str) -> list[tuple[str, str, str]]:
    """回傳 [(產業鏈代碼, 產業鏈名稱, 細項)]，依公司申報順序。"""
    m = re.search(r"所屬產業鏈如下:(.*?)</div>", page, re.S)
    if not m:
        return []
    out = []
    for code, chain, seg in re.findall(r'introduce\.php\?ic=(\w+)">([^<]+)</a>&nbsp;&gt;&nbsp;([^<]+)</h4>', m.group(1)):
        out.append((code, _clean(chain), _clean(seg)))
    return out


def parse_chain(page: str) -> dict[str, str]:
    """細項名稱 → 中層分類名稱（中層分類本身也對應到自己）。"""
    mapping = {}
    for gid, gname in re.findall(r'id="ic_link_(\w+)"[^>]*>([^<]+)', page):
        gname = _clean(gname)
        mapping.setdefault(gname, gname)
        m = re.search(r'id="sc_industry_%s">(.*?)</table>' % gid, page, re.S)
        if not m:
            continue
        for _, cell in re.findall(r'id="sc_link_(\w+)"[^>]*>(.*?)</td', m.group(1), re.S):
            for seg in re.split(r"\(\d+家\)", _clean(cell)):
                seg = re.sub(r"(本國|外國)(上市|上櫃|興櫃)公司.*$", "", seg).strip()
                if seg:
                    mapping.setdefault(seg, gname)
    return mapping


CORE_CHAINS = ("半導體", "電腦及週邊設備", "通信網路", "印刷電路板", "被動元件", "連接器", "平面顯示器", "觸控面板",
               "LED照明產業", "太陽能產業", "能源元件")
SECTOR_CHAINS = {
    "半導體業": ("半導體",),
    "電腦及週邊設備業": ("電腦及週邊設備",),
    "通信網路業": ("通信網路",),
    "光電業": ("平面顯示器", "觸控面板", "LED照明產業", "太陽能產業"),
    "電子零組件業": ("被動元件", "連接器", "印刷電路板", "電腦及週邊設備", "通信網路", "平面顯示器", "觸控面板", "能源元件"),
}


def primary_entry(entries: list[tuple[str, str, str]], broad_sector: str) -> tuple[str, str, str]:
    """在候選產業鏈中選公司申報筆數最多的那條（代表主要業務），同筆數依優先順序；再取該鏈的第一筆。"""
    preferred = SECTOR_CHAINS.get(broad_sector, CORE_CHAINS)
    for pool in (preferred, CORE_CHAINS):
        hit = [e for e in entries if e[1] in pool]
        if hit:
            counts = {c: sum(e[1] == c for e in hit) for c in {e[1] for e in hit}}
            best = max(counts, key=lambda c: (counts[c], -pool.index(c)))
            return next(e for e in hit if e[1] == best)
    return entries[0]


def classify(stock_id: str, chain_maps: dict[str, dict[str, str]], broad_sector: str = "") -> dict:
    entries = parse_company(fetch(f"company_chain.php?stk_code={stock_id}"))
    if not entries:
        return {"stock_id": stock_id, "chain": "", "group": "", "segment": "", "all_entries": "", "found": False}
    for code, _, _ in entries:
        if code not in chain_maps:
            chain_maps[code] = parse_chain(fetch(f"introduce.php?ic={code}"))
    code, chain, seg = primary_entry(entries, broad_sector)
    group = chain_maps[code].get(seg, seg)
    return {"stock_id": stock_id, "chain": chain, "group": group, "segment": seg,
            "all_entries": "；".join(f"{c}>{s}" for _, c, s in entries), "found": True}
