"""strategy-scout 工具：去重比對、點子卡寫入與編號（不連網）。"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "research"))
import scout  # noqa: E402


def test_registry_and_catalog_load():
    ideas = scout.load_tested()
    assert any(i["id"] == "sue" and i["status"] == "effective" for i in ideas)
    assert all({"id", "name", "status", "keywords", "report"} <= set(i) for i in ideas)
    for i in ideas:
        assert (ROOT / i["report"]).exists(), i["report"]
    import yaml
    cat = yaml.safe_load((ROOT / "research" / "data_catalog.yaml").read_text(encoding="utf-8"))["datasets"]
    assert all({"name", "source", "access", "used", "note"} <= set(d) for d in cat)


def test_dedup_hits_tested_idea(monkeypatch, tmp_path):
    monkeypatch.setattr(scout, "IDEAS_CSV", tmp_path / "ideas.csv")
    m = scout.dedup_matches("A study of post-earnings announcement drift in Taiwan")
    assert m and m[0][1]["id"] == "eps_surprise"
    assert scout.dedup_matches("completely unrelated cooking recipe") == []


def test_card_writes_markdown_and_index(monkeypatch, tmp_path):
    monkeypatch.setattr(scout, "IDEAS_DIR", tmp_path / "ideas")
    monkeypatch.setattr(scout, "IDEAS_CSV", tmp_path / "ideas.csv")
    monkeypatch.setattr(scout, "ROOT", tmp_path)
    draft = {"title": "測試點子", "slug": "test idea", "hypothesis": "分析師覆蓋少的股票，營收驚奇漂移較強",
             "mechanism": "資訊擴散慢", "sources": ["某作者（2020）"], "taiwan_fit": "適用",
             "data": {"access": "free", "api_calls": "約 0", "items": ["月營收"]}, "test_type": "橫斷面 IC",
             "test_plan": ["樣本：前 500 名"], "priority": "B", "keywords": ["analyst coverage", "revenue surprise"]}
    p = tmp_path / "d.json"
    p.write_text(json.dumps(draft, ensure_ascii=False), encoding="utf-8")
    scout.main(["card", str(p)])
    scout.main(["card", str(p)])
    cards = sorted((tmp_path / "ideas").glob("*.md"))
    assert [c.name[:4] for c in cards] == ["I001", "I002"]
    text = cards[0].read_text(encoding="utf-8")
    assert "月營收驚奇 SUE" in text                       # 自動列出與已測點子的關係
    assert (tmp_path / "ideas.csv").read_text(encoding="utf-8").count("測試點子") == 2
