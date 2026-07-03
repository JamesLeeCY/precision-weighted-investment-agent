"""Anthropic LLM 客戶端（可插拔）。

設計：Agent 先以規則計算特徵與 fallback 判斷；若 LLM 可用
（ANTHROPIC_API_KEY 已設定且 anthropic 套件已安裝），則把特徵送入
LLM 取得 signal/confidence/rationale，失敗時自動退回規則式結果。
因此整個系統在沒有 API key 的環境（含 CI 測試）也能完整運作。
"""
from __future__ import annotations

import json
import os
import re

DEFAULT_MODEL = "claude-sonnet-4-6"

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


class LLMClient:
    def __init__(self, model: str = DEFAULT_MODEL, enabled: str | bool = "auto"):
        self.model = model
        if enabled == "auto":
            self.enabled = bool(os.environ.get("ANTHROPIC_API_KEY"))
        else:
            self.enabled = bool(enabled)
        self._client = None

    @property
    def available(self) -> bool:
        if not self.enabled:
            return False
        try:
            import anthropic  # noqa: F401
            return True
        except ImportError:
            return False

    def _get_client(self):
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic()
        return self._client

    def judge(self, system_prompt: str, user_prompt: str) -> dict | None:
        """呼叫 LLM，要求回傳 JSON：{signal, confidence, rationale}。

        任何失敗（無 key、網路錯誤、JSON 解析失敗、值不合法）皆回傳 None，
        由呼叫端 fallback 到規則式判斷。
        """
        if not self.available:
            return None
        try:
            resp = self._get_client().messages.create(
                model=self.model,
                max_tokens=1024,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
            match = _JSON_RE.search(text)
            if not match:
                return None
            data = json.loads(match.group(0))
            signal = str(data.get("signal", "")).lower()
            confidence = float(data.get("confidence", -1))
            rationale = str(data.get("rationale", "")).strip()
            if signal not in ("bullish", "bearish", "neutral") or not (0.0 <= confidence <= 1.0):
                return None
            return {"signal": signal, "confidence": confidence, "rationale": rationale}
        except Exception:
            return None
