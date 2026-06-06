"""OpenAI-compatible chat completions adapter (OpenRouter, DeepSeek, Qwen, proxies)."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from http.client import IncompleteRead
from typing import Any

from ..errors import AuthenticationError, NetworkError, ParameterError, TimeoutError, classify_http_error
from ..chat_types import ChatMessage, ChatResult, UsageInfo
from .base import BaseProvider

DEFAULT_BASE_URL = "https://api.openai.com/v1"


class OpenAICompatibleProvider(BaseProvider):
    def __init__(
        self,
        *,
        provider_id: str,
        base_url: str,
        api_key_env: str,
        default_headers: dict[str, str] | None = None,
    ) -> None:
        self.provider_id = provider_id
        self.base_url = base_url.rstrip("/")
        self.api_key_env = api_key_env
        self.default_headers = default_headers or {}

    def _resolve_api_key(self) -> str:
        key = os.environ.get(self.api_key_env, "").strip()
        if not key:
            raise AuthenticationError(
                f"API key env {self.api_key_env} is not set",
                self.provider_id,
            )
        return key

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
        payload: dict[str, Any] = {
            "model": model,
            "messages": [m.to_dict() for m in messages],
            "temperature": temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            **self.default_headers,
        }
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
        choices = data.get("choices") or []
        if not choices:
            raise ParameterError("response missing choices", self.provider_id)

        content = choices[0].get("message", {}).get("content", "") or ""
        usage = self._usage_from_raw(data)
        resolved_model = str(data.get("model") or model)

        return ChatResult(
            content=content,
            model=resolved_model,
            provider=self.provider_id,
            usage=usage,
            raw=data,
            latency_ms=latency_ms,
            finish_reason=str(choices[0].get("finish_reason") or "stop"),
        )
