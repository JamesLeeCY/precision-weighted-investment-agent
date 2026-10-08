"""新聞內文抓取（FinMind 新聞只有標題，補上內文摘要供新聞 Agent 使用）。

- 只抓直接連結的來源；Google News 轉址連結（news.google.com/rss/articles/...）
  的原始網址只能經由 Google 未公開的內部 API 解碼，且其格式已變動，因此不處理，
  維持只有標題
- 遵守 robots.txt；同一網域請求間隔至少 MIN_INTERVAL_SEC
- 擷取 og:description 與 <p> 段落，清理後截斷為 MAX_CHARS 字
- 快取（ARTICLE_CACHE_DIR）只存在本機、不納入版控：新聞內文受著作權保護，
  不可隨公開 repo 散布。版控中只保留由內文推導出的結果（LLM 判讀快取、回測數字）

台灣部分網站的憑證缺少 Subject Key Identifier，Python 3.13 預設的嚴格 X509
檢查會拒絕連線；這裡只關閉 VERIFY_X509_STRICT 這一項，憑證鏈驗證維持開啟。
"""
from __future__ import annotations

import hashlib
import html
import json
import re
import ssl
import time
from pathlib import Path
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import requests
from requests.adapters import HTTPAdapter

ARTICLE_CACHE_DIR = Path(__file__).resolve().parent.parent / "article_cache"
USER_AGENT = (
    "Mozilla/5.0 (compatible; precision-weighted-investment-agent/0.1; "
    "academic research; +https://github.com/JamesLeeCY/precision-weighted-investment-agent)"
)
MIN_INTERVAL_SEC = 1.0
MAX_CHARS = 600
UNRESOLVABLE_HOSTS = {"news.google.com"}

_TAG_RE = re.compile(r"<[^>]+>")
_SCRIPT_RE = re.compile(r"<(script|style|noscript)[^>]*>.*?</\1>", re.S | re.I)
_P_RE = re.compile(r"<p[^>]*>(.*?)</p>", re.S | re.I)
_META_RE = re.compile(
    r'<meta[^>]+(?:property|name)=["\'](?:og:description|description)["\'][^>]+content=["\']([^"\']*)["\']',
    re.I,
)


class _LenientX509Adapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        ctx = ssl.create_default_context()
        ctx.verify_flags &= ~ssl.VERIFY_X509_STRICT
        kwargs["ssl_context"] = ctx
        return super().init_poolmanager(*args, **kwargs)


def _clean(text: str) -> str:
    text = html.unescape(_TAG_RE.sub(" ", text))
    return re.sub(r"\s+", " ", text).strip()


def extract_text(page: str, max_chars: int = MAX_CHARS) -> str:
    """從 HTML 擷取文章摘要：og:description 加上主要段落（≥ 30 字的 <p>）。"""
    page = _SCRIPT_RE.sub(" ", page)
    meta = _META_RE.search(page)
    parts = [_clean(meta.group(1))] if meta else []
    for p in _P_RE.findall(page):
        para = _clean(p)
        if len(para) >= 30 and para not in parts and not any(para in x for x in parts):
            parts.append(para)
    return " ".join(x for x in parts if x)[:max_chars]


class ArticleFetcher:
    """以 URL 為鍵快取的內文抓取器；fetch() 永不拋例外，失敗回傳空字串。"""

    def __init__(self, cache_dir: str | Path = ARTICLE_CACHE_DIR, offline: bool = False, timeout: float = 20.0):
        self.cache_dir = Path(cache_dir)
        self.offline = offline  # True：只讀快取，不連網（重現回測用）
        self.timeout = timeout
        self.session = requests.Session()
        self.session.mount("https://", _LenientX509Adapter())
        self.session.headers["User-Agent"] = USER_AGENT
        self._robots: dict[str, RobotFileParser | None] = {}
        self._last_hit: dict[str, float] = {}
        self.stats = {"fetched": 0, "cache_hits": 0, "skipped": 0, "failed": 0}

    def _cache_path(self, url: str) -> Path:
        return self.cache_dir / f"{hashlib.sha256(url.encode('utf-8')).hexdigest()[:24]}.json"

    def _throttle(self, host: str) -> None:
        wait = MIN_INTERVAL_SEC - (time.monotonic() - self._last_hit.get(host, 0.0))
        if wait > 0:
            time.sleep(wait)
        self._last_hit[host] = time.monotonic()

    def _allowed(self, url: str) -> bool:
        parts = urlparse(url)
        base = f"{parts.scheme}://{parts.netloc}"
        if base not in self._robots:
            parser = RobotFileParser()
            try:
                self._throttle(parts.netloc)
                resp = self.session.get(f"{base}/robots.txt", timeout=self.timeout)
                # 非 2xx 或回傳的是 HTML（多數網站以首頁頂替不存在的 robots.txt）視為無限制
                if resp.ok and "<html" not in resp.text[:500].lower():
                    parser.parse(resp.text.splitlines())
                else:
                    parser.parse([])
            except requests.RequestException:
                parser = None  # robots.txt 無法取得時保守處理：不抓
            self._robots[base] = parser
        parser = self._robots[base]
        return parser is not None and parser.can_fetch(USER_AGENT, url)

    def _store(self, path: Path, url: str, status: str, text: str) -> str:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"url": url, "status": status, "text": text}, ensure_ascii=False), encoding="utf-8")
        return text

    def fetch(self, url: str) -> str:
        if not url:
            return ""
        path = self._cache_path(url)
        if path.exists():
            self.stats["cache_hits"] += 1
            return json.loads(path.read_text(encoding="utf-8")).get("text", "")
        if self.offline:
            return ""
        host = urlparse(url).netloc
        if host in UNRESOLVABLE_HOSTS:
            self.stats["skipped"] += 1
            return self._store(path, url, "unresolvable", "")
        if not self._allowed(url):
            self.stats["skipped"] += 1
            return self._store(path, url, "robots_disallowed", "")
        try:
            self._throttle(host)
            resp = self.session.get(url, timeout=self.timeout)
            if resp.encoding is None or resp.encoding.lower() == "iso-8859-1":
                resp.encoding = resp.apparent_encoding
            if not resp.ok:
                self.stats["failed"] += 1
                return self._store(path, url, f"http_{resp.status_code}", "")
            text = extract_text(resp.text)
            self.stats["fetched"] += 1
            return self._store(path, url, "ok" if text else "empty", text)
        except requests.RequestException as exc:
            # 網路錯誤不快取，下次重跑會再試
            print(f"[warn] 內文抓取失敗 {host}：{type(exc).__name__}")
            self.stats["failed"] += 1
            return ""

    def coverage(self) -> dict[str, int]:
        """快取中各狀態的篇數。"""
        counts: dict[str, int] = {}
        for f in self.cache_dir.glob("*.json"):
            status = json.loads(f.read_text(encoding="utf-8")).get("status", "?")
            counts[status] = counts.get(status, 0) + 1
        return counts
