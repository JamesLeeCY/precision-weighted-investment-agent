"""新聞內文抓取測試：HTML 擷取、快取、robots.txt、不可解析連結（不連網）。"""
import json

from agents.news_agent import NewsAgent
from data.fetch_article import ArticleFetcher, extract_text
from data.fetch_news import NewsItem, NewsProvider, dedupe_and_sort

PAGE = """<html><head><meta property="og:description" content="國巨公布 1 月營收創同期新高">
<script>var x = "<p>不該出現的腳本段落，長度要超過三十個字才會被當成段落</p>";</script></head>
<body><p>短句</p>
<p>國巨今日公布 1 月合併營收 105 億元，年增 12%，受惠農曆年前備貨潮與 AI 伺服器需求。</p>
<p>法人預期第一季營收將優於季節性，被動元件報價可望持穩。&amp; 其他說明文字補足長度。</p></body></html>"""


class FakeResponse:
    def __init__(self, text, status=200):
        self.text, self.status_code, self.encoding = text, status, "utf-8"
        self.ok = 200 <= status < 300
        self.apparent_encoding = "utf-8"


class FakeSession:
    def __init__(self, pages):
        self.pages, self.calls, self.headers = pages, [], {}

    def get(self, url, timeout=None):
        self.calls.append(url)
        return self.pages.get(url, FakeResponse("", 404))


def make_fetcher(tmp_path, pages, **kw):
    f = ArticleFetcher(cache_dir=tmp_path, **kw)
    f.session = FakeSession(pages)
    f._throttle = lambda host: None
    return f


class TestExtractText:
    def test_meta_and_paragraphs(self):
        text = extract_text(PAGE)
        assert text.startswith("國巨公布 1 月營收創同期新高")
        assert "年增 12%" in text and "& 其他說明" in text
        assert "短句" not in text and "腳本" not in text

    def test_truncated(self):
        assert len(extract_text(PAGE, max_chars=20)) == 20


class TestArticleFetcher:
    URL = "https://news.example.com/a/1"

    def test_fetch_and_cache(self, tmp_path):
        f = make_fetcher(tmp_path, {self.URL: FakeResponse(PAGE), "https://news.example.com/robots.txt": FakeResponse("")})
        first = f.fetch(self.URL)
        assert "年增 12%" in first
        n_calls = len(f.session.calls)
        assert f.fetch(self.URL) == first
        assert len(f.session.calls) == n_calls  # 第二次讀快取
        assert f.coverage() == {"ok": 1}

    def test_robots_disallow(self, tmp_path):
        robots = "User-agent: *\nDisallow: /a/\n"
        f = make_fetcher(tmp_path, {self.URL: FakeResponse(PAGE), "https://news.example.com/robots.txt": FakeResponse(robots)})
        assert f.fetch(self.URL) == ""
        assert self.URL not in f.session.calls
        assert f.coverage() == {"robots_disallowed": 1}

    def test_google_news_unresolvable(self, tmp_path):
        f = make_fetcher(tmp_path, {})
        assert f.fetch("https://news.google.com/rss/articles/CBMiabc?oc=5") == ""
        assert f.session.calls == []
        assert f.coverage() == {"unresolvable": 1}

    def test_offline_reads_cache_only(self, tmp_path):
        f = make_fetcher(tmp_path, {}, offline=True)
        assert f.fetch(self.URL) == ""
        assert f.session.calls == []
        (tmp_path / "x.json").write_text(json.dumps({"url": "u", "status": "ok", "text": "t"}), encoding="utf-8")
        assert f.coverage() == {"ok": 1}

    def test_http_error_cached_as_status(self, tmp_path):
        f = make_fetcher(tmp_path, {"https://news.example.com/robots.txt": FakeResponse("")})
        assert f.fetch(self.URL) == ""
        assert f.coverage() == {"http_404": 1}


class FixtureNews(NewsProvider):
    def __init__(self, items):
        self.items = items

    def get_news(self, ticker, start_date, end_date):
        return dedupe_and_sort([NewsItem(title=i.title, source=i.source, url=i.url, published=i.published) for i in self.items])


def test_news_agent_fills_summary_after_retrieval():
    import datetime as dt

    items = [NewsItem(title="國巨公告", source="經濟日報", url="https://x/1", published=dt.datetime(2025, 6, 29))]
    seen = []

    def fetch(url):
        seen.append(url)
        return "宣布擴產新廠，產能提升"

    with_content = NewsAgent(FixtureNews(items), content_fetcher=fetch).analyze("2327.TW", "2025-06-30")
    title_only = NewsAgent(FixtureNews(items)).analyze("2327.TW", "2025-06-30")
    assert seen == ["https://x/1"]
    assert with_content.raw_features["n_with_content"] == 1
    # 內文中的「擴產」事件讓規則式判斷由中性轉為偏多
    assert title_only.raw_features["rule_score"] == 0
    assert with_content.raw_features["rule_score"] > 0
