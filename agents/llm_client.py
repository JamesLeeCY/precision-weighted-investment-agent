"""LLM 客戶端（可插拔：Anthropic API 或地端 Ollama）。

設計：Agent 先以規則計算特徵與 fallback 判斷；若 LLM 可用，則把特徵送入
LLM 取得 signal/confidence/rationale，失敗時自動退回規則式結果。
因此整個系統在沒有 LLM 的環境（含 CI 測試）也能完整運作。

provider：
- anthropic：需 ANTHROPIC_API_KEY 與 anthropic 套件
- ollama：地端模型（如 phi4、qwen3），以 HTTP 呼叫 Ollama 伺服器；
  使用 JSON schema 結構化輸出、temperature 0 + 固定 seed 求可重現

回應快取（cache_dir）：以 (provider, model, options, prompt) 雜湊為鍵存原始
回應文字。地端模型在 CPU 上每次呼叫可能要數十秒，快取讓回測可中斷續跑、
重跑不必重算；失敗的回應也會快取，避免同一 prompt 反覆失敗。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

DEFAULT_MODEL = "claude-sonnet-4-6"
DEFAULT_OLLAMA_URL = "http://localhost:11434"

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)

# Ollama 結構化輸出：強制回傳符合此 schema 的 JSON
JUDGEMENT_SCHEMA = {
    "type": "object",
    "properties": {
        "signal": {"type": "string", "enum": ["bullish", "bearish", "neutral"]},
        "confidence": {"type": "number"},
        "rationale": {"type": "string"},
    },
    "required": ["signal", "confidence", "rationale"],
}


def parse_judgement(text: str) -> dict | None:
    """從模型輸出擷取 {signal, confidence, rationale}；不合法回傳 None。"""
    match = _JSON_RE.search(text or "")
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
        signal = str(data.get("signal", "")).lower().strip()
        confidence = float(data.get("confidence", -1))
    except (ValueError, TypeError, AttributeError):
        return None
    rationale = str(data.get("rationale", "")).strip()
    if signal not in ("bullish", "bearish", "neutral") or not (0.0 <= confidence <= 1.0):
        return None
    return {"signal": signal, "confidence": confidence, "rationale": rationale}


class LLMClient:
    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        enabled: str | bool = "auto",
        provider: str = "anthropic",
        base_url: str = DEFAULT_OLLAMA_URL,
        cache_dir: str | Path | None = None,
        timeout: float = 900.0,
        options: dict | None = None,
        think: bool | None = None,
    ):
        if provider not in ("anthropic", "ollama"):
            raise ValueError(f"未知的 LLM provider：{provider!r}")
        self.model = model
        self.provider = provider
        self.base_url = base_url.rstrip("/")
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.timeout = timeout
        # temperature 0 + 固定 seed：同一 prompt 盡量得到相同輸出
        self.options = {"temperature": 0, "seed": 42, **(options or {})}
        # qwen3 等推理模型的思考模式；None 表示不傳此參數（非推理模型傳了會報錯）
        self.think = think
        if enabled == "auto":
            self.enabled = bool(os.environ.get("ANTHROPIC_API_KEY")) if provider == "anthropic" else True
        else:
            self.enabled = bool(enabled)
        self._client = None
        self._available: bool | None = None
        self.stats = {"calls": 0, "cache_hits": 0, "failures": 0}

    @property
    def available(self) -> bool:
        if not self.enabled:
            return False
        if self._available is None:
            self._available = self._check_available()
        return self._available

    def _check_available(self) -> bool:
        if self.provider == "anthropic":
            try:
                import anthropic  # noqa: F401
                return True
            except ImportError:
                return False
        import requests

        try:
            tags = requests.get(f"{self.base_url}/api/tags", timeout=5).json()
        except Exception:
            print(f"[warn] 連不上 Ollama（{self.base_url}），改用規則式判斷")
            return False
        names = {m.get("name") for m in tags.get("models", [])}
        if self.model not in names and f"{self.model}:latest" not in names:
            print(f"[warn] Ollama 沒有模型 {self.model}（可用：{sorted(names)}），改用規則式判斷")
            return False
        return True

    # ---------- 快取 ----------

    def _cache_path(self, system_prompt: str, user_prompt: str) -> Path | None:
        if self.cache_dir is None:
            return None
        key = json.dumps(
            [self.provider, self.model, self.options, self.think, system_prompt, user_prompt],
            ensure_ascii=False, sort_keys=True,
        )
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]
        safe_model = re.sub(r"[^A-Za-z0-9._-]", "_", self.model)
        return self.cache_dir / safe_model / f"{digest}.json"

    # ---------- 呼叫 ----------

    def _call_anthropic(self, system_prompt: str, user_prompt: str) -> str:
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic()
        resp = self._client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")

    def _call_ollama(self, system_prompt: str, user_prompt: str) -> str:
        import requests

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "format": JUDGEMENT_SCHEMA,
            "options": self.options,
        }
        if self.think is not None:
            payload["think"] = self.think
        resp = requests.post(f"{self.base_url}/api/chat", json=payload, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json().get("message", {}).get("content", "")

    def judge(self, system_prompt: str, user_prompt: str) -> dict | None:
        """呼叫 LLM，要求回傳 JSON：{signal, confidence, rationale}。

        任何失敗（不可用、網路錯誤、JSON 解析失敗、值不合法）皆回傳 None，
        由呼叫端 fallback 到規則式判斷。
        """
        if not self.available:
            return None
        cache_path = self._cache_path(system_prompt, user_prompt)
        if cache_path is not None and cache_path.exists():
            self.stats["cache_hits"] += 1
            text = json.loads(cache_path.read_text(encoding="utf-8")).get("text", "")
        else:
            self.stats["calls"] += 1
            try:
                if self.provider == "anthropic":
                    text = self._call_anthropic(system_prompt, user_prompt)
                else:
                    text = self._call_ollama(system_prompt, user_prompt)
            except Exception as exc:
                # 連線/逾時錯誤不快取，下次重跑會再試
                print(f"[warn] LLM 呼叫失敗（{self.model}）：{exc}")
                self.stats["failures"] += 1
                return None
            if cache_path is not None:
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cache_path.write_text(
                    json.dumps({"model": self.model, "text": text}, ensure_ascii=False), encoding="utf-8"
                )
        result = parse_judgement(text)
        if result is None:
            self.stats["failures"] += 1
        return result
