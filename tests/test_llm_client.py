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


class TestNumCtx:
    def test_num_ctx_not_in_cache_key(self, tmp_path):
        ok = '{"signal": "neutral", "confidence": 0.5, "rationale": "r"}'
        a, calls = make_ollama(tmp_path, [ok])
        a.options["num_ctx"] = 4096
        a.judge("sys", "u")
        b, b_calls = make_ollama(tmp_path, [ok])
        b.options["num_ctx"] = 8192
        b.judge("sys", "u")
        assert len(calls) == 1 and b_calls == []

    def test_legacy_cache_key_still_found(self, tmp_path):
        import json as _json
        llm, calls = make_ollama(tmp_path, [])
        llm.options["num_ctx"] = 4096
        legacy = llm._cache_paths("sys", "u")[-1]  # 舊格式：options 含 num_ctx
        legacy.parent.mkdir(parents=True, exist_ok=True)
        legacy.write_text(_json.dumps({"text": '{"signal": "bullish", "confidence": 0.6, "rationale": "r"}'}), encoding="utf-8")
        assert llm.judge("sys", "u")["signal"] == "bullish"
        assert calls == []

    def test_num_ctx_grows_with_prompt(self, tmp_path, monkeypatch):
        llm = LLMClient(model="qwen3:8b", provider="ollama", options={"num_ctx": 4096})
        sent = {}

        class Resp:
            def raise_for_status(self):
                pass

            def json(self):
                return {"message": {"content": "{}"}}

        import requests

        monkeypatch.setattr(requests, "post", lambda url, json, timeout: sent.update(json) or Resp())
        llm._call_ollama("s", "字" * 7000)
        assert sent["options"]["num_ctx"] == 8192
        llm._call_ollama("s", "短")
        assert sent["options"]["num_ctx"] == 4096


def test_num_thread_not_in_cache_key_and_legacy_still_found(tmp_path):
    import json as _json
    ok = '{"signal": "neutral", "confidence": 0.5, "rationale": "r"}'
    old, calls = make_ollama(tmp_path, [])
    old.options["num_ctx"] = 4096
    legacy = old._cache_paths("sys", "u")[-1]  # 舊格式：含 num_ctx、沒有 num_thread
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text(_json.dumps({"text": ok}), encoding="utf-8")
    limited, limited_calls = make_ollama(tmp_path, [])
    limited.options.update({"num_ctx": 4096, "num_thread": 2})
    assert limited.judge("sys", "u")["signal"] == "neutral"
    assert limited_calls == []
