"""LLM 客戶端測試：回應解析、快取、不可用時的 fallback（不需真實模型）。"""
import pytest

from agents.llm_client import LLMClient, parse_judgement


class TestParseJudgement:
    def test_valid_json(self):
        r = parse_judgement('{"signal": "Bullish", "confidence": 0.7, "rationale": "營收成長"}')
        assert r == {"signal": "bullish", "confidence": 0.7, "rationale": "營收成長"}

    def test_json_embedded_in_text(self):
        assert parse_judgement('好的：\n{"signal": "neutral", "confidence": 0.5, "rationale": "x"}\n')["signal"] == "neutral"

    @pytest.mark.parametrize(
        "text",
        [
            "",
            "not json",
            '{"signal": "buy", "confidence": 0.7, "rationale": "x"}',
            '{"signal": "bullish", "confidence": 1.5, "rationale": "x"}',
            '{"signal": "bullish", "confidence": "high", "rationale": "x"}',
            '{"signal": "bullish", "confidence": 0.7',
        ],
    )
    def test_invalid_returns_none(self, text):
        assert parse_judgement(text) is None


def make_ollama(tmp_path, responses):
    llm = LLMClient(model="qwen3:8b", provider="ollama", cache_dir=tmp_path, think=False)
    llm._available = True  # 略過伺服器檢查
    calls = []

    def fake_call(system, user):
        calls.append(user)
        return responses.pop(0)

    llm._call_ollama = fake_call
    return llm, calls


class TestOllamaClient:
    def test_cache_avoids_second_call(self, tmp_path):
        llm, calls = make_ollama(tmp_path, ['{"signal": "bearish", "confidence": 0.6, "rationale": "r"}'])
        first = llm.judge("sys", "user")
        second = llm.judge("sys", "user")
        assert first == second == {"signal": "bearish", "confidence": 0.6, "rationale": "r"}
        assert len(calls) == 1
        assert llm.stats == {"calls": 1, "cache_hits": 1, "failures": 0}

    def test_different_prompt_or_model_not_shared(self, tmp_path):
        ok = '{"signal": "neutral", "confidence": 0.5, "rationale": "r"}'
        llm, calls = make_ollama(tmp_path, [ok, ok])
        llm.judge("sys", "a")
        llm.judge("sys", "b")
        assert len(calls) == 2
        other, other_calls = make_ollama(tmp_path, [ok])
        other.model = "phi4"
        other.judge("sys", "a")
        assert len(other_calls) == 1

    def test_invalid_output_cached_and_counted(self, tmp_path):
        llm, calls = make_ollama(tmp_path, ["亂碼"])
        assert llm.judge("sys", "u") is None
        assert llm.judge("sys", "u") is None  # 讀快取，不再呼叫
        assert len(calls) == 1
        assert llm.stats["failures"] == 2

    def test_connection_error_not_cached(self, tmp_path):
        llm = LLMClient(model="qwen3:8b", provider="ollama", cache_dir=tmp_path)
        llm._available = True

        def boom(system, user):
            raise ConnectionError("down")

        llm._call_ollama = boom
        assert llm.judge("sys", "u") is None
        assert not any(tmp_path.rglob("*.json"))

    def test_unreachable_server_falls_back(self):
        llm = LLMClient(model="qwen3:8b", provider="ollama", base_url="http://127.0.0.1:9")
        assert llm.available is False
        assert llm.judge("sys", "u") is None

    def test_disabled(self):
        assert LLMClient(provider="ollama", enabled=False).available is False

    def test_unknown_provider(self):
        with pytest.raises(ValueError):
            LLMClient(provider="openai")
