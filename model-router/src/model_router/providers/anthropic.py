"""Anthropic Messages API adapter."""

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

DEFAULT_BASE_URL = "https://api.anthropic.com/v1"


class AnthropicProvider(BaseProvider):
    def __init__(
        self,
        *,
        provider_id: str = "anthropic",
        base_url: str = DEFAULT_BASE_URL,
        api_key_env: str = "ANTHROPIC_API_KEY",
        api_version: str = "2023-06-01",
    ) -> None:
        self.provider_id = provider_id
        self.base_url = base_url.rstrip("/")
        self.api_key_env = api_key_env
        self.api_version = api_version

    def _resolve_api_key(self) -> str:
        key = os.environ.get(self.api_key_env, "").strip()
        if not key:
            raise AuthenticationError(
                f"API key env {self.api_key_env} is not set",
                self.provider_id,
            )
        return key

    @staticmethod
    def _split_messages(messages: list[ChatMessage]) -> tuple[str | None, list[dict[str, str]]]:
        system_parts: list[str] = []
        converted: list[dict[str, str]] = []
        for msg in messages:
            if msg.role == "system":
                system_parts.append(msg.content)
                continue
            role = "assistant" if msg.role == "assistant" else "user"
            converted.append({"role": role, "content": msg.content})
        system = "\n\n".join(system_parts) if system_parts else None
        return system, converted

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
        system, converted = self._split_messages(messages)
        if not converted:
            raise ParameterError("at least one user/assistant message required", self.provider_id)

        payload: dict[str, Any] = {
            "model": model,
            "messages": converted,
            "temperature": temperature,
            "max_tokens": max_tokens or 4096,
        }
        if system:
            payload["system"] = system

        url = f"{self.base_url}/messages"
        headers = {
            "x-api-key": api_key,
            "anthropic-version": self.api_version,
            "Content-Type": "application/json",
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
        blocks = data.get("content") or []
        content = "".join(
            block.get("text", "")
            for block in blocks
            if isinstance(block, dict) and block.get("type") == "text"
        )
        usage_raw = data.get("usage") or {}
        usage = self._usage_from_raw(
            {
                "usage": {
                    "prompt_tokens": usage_raw.get("input_tokens", 0),
                    "completion_tokens": usage_raw.get("output_tokens", 0),
                    "total_tokens": int(usage_raw.get("input_tokens", 0))
                    + int(usage_raw.get("output_tokens", 0)),
                }
            }
        )

        return ChatResult(
            content=content,
            model=str(data.get("model") or model),
            provider=self.provider_id,
            usage=usage,
            raw=data,
            latency_ms=latency_ms,
            finish_reason=str(data.get("stop_reason") or "stop"),
        )
