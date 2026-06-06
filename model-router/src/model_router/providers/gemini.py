"""Google Gemini generateContent adapter."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from http.client import IncompleteRead
from typing import Any

from ..errors import AuthenticationError, NetworkError, ParameterError, TimeoutError, classify_http_error
from ..chat_types import ChatMessage, ChatResult
from .base import BaseProvider

DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"


class GeminiProvider(BaseProvider):
    def __init__(
        self,
        *,
        provider_id: str = "gemini",
        base_url: str = DEFAULT_BASE_URL,
        api_key_env: str = "GOOGLE_API_KEY",
    ) -> None:
        self.provider_id = provider_id
        self.base_url = base_url.rstrip("/")
        self.api_key_env = api_key_env

    def _resolve_api_key(self) -> str:
        key = os.environ.get(self.api_key_env, "").strip()
        if not key:
            raise AuthenticationError(
                f"API key env {self.api_key_env} is not set",
                self.provider_id,
            )
        return key

    @staticmethod
    def _to_gemini_contents(messages: list[ChatMessage]) -> tuple[str | None, list[dict[str, Any]]]:
        system_parts: list[str] = []
        contents: list[dict[str, Any]] = []
        for msg in messages:
            if msg.role == "system":
                system_parts.append(msg.content)
                continue
            role = "model" if msg.role == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": msg.content}]})
        system = "\n\n".join(system_parts) if system_parts else None
        return system, contents

    def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str,
        temperature: float,
        max_tokens: int | None,
        stream: bool,
        timeout_sec: int,
    ) -> ChatResult:
        if stream:
            raise ParameterError("stream=true is not supported yet", self.provider_id)

        api_key = self._resolve_api_key()
        system, contents = self._to_gemini_contents(messages)
        if not contents:
            raise ParameterError("at least one user/assistant message required", self.provider_id)

        payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {"temperature": temperature},
        }
        if max_tokens is not None:
            payload["generationConfig"]["maxOutputTokens"] = max_tokens
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}

        model_path = model if model.startswith("models/") else f"models/{model}"
        url = f"{self.base_url}/{model_path}:generateContent?key={api_key}"
        headers = {"Content-Type": "application/json"}
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")

        started = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
                raw_bytes = resp.read()
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")
            raise classify_http_error(self.provider_id, exc.code, err_body) from exc
        except urllib.error.URLError as exc:
            reason = str(getattr(exc, "reason", exc))
            if "timed out" in reason.lower():
                raise TimeoutError(reason, self.provider_id) from exc
            raise NetworkError(reason, self.provider_id) from exc
        except (IncompleteRead, TimeoutError, OSError) as exc:
            if isinstance(exc, TimeoutError):
                raise TimeoutError(str(exc), self.provider_id) from exc
            raise NetworkError(str(exc), self.provider_id) from exc

        latency_ms = int((time.perf_counter() - started) * 1000)
        data: dict[str, Any] = json.loads(raw_bytes.decode("utf-8"))
        candidates = data.get("candidates") or []
        if not candidates:
            raise ParameterError("response missing candidates", self.provider_id)

        parts = candidates[0].get("content", {}).get("parts") or []
        content = "".join(part.get("text", "") for part in parts if isinstance(part, dict))
        usage_meta = data.get("usageMetadata") or {}
        usage = self._usage_from_raw(
            {
                "usage": {
                    "prompt_tokens": usage_meta.get("promptTokenCount", 0),
                    "completion_tokens": usage_meta.get("candidatesTokenCount", 0),
                    "total_tokens": usage_meta.get("totalTokenCount", 0),
                }
            }
        )

        return ChatResult(
            content=content,
            model=model,
            provider=self.provider_id,
            usage=usage,
            raw=data,
            latency_ms=latency_ms,
            finish_reason=str(candidates[0].get("finishReason") or "stop"),
        )
