"""Base provider protocol."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..chat_types import ChatMessage, ChatResult, UsageInfo


class BaseProvider(ABC):
    provider_id: str

    @abstractmethod
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
        raise NotImplementedError

    @staticmethod
    def _usage_from_raw(raw: dict[str, Any]) -> UsageInfo:
        usage = raw.get("usage") or {}
        prompt = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
        completion = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
        total = int(usage.get("total_tokens") or prompt + completion)
        return UsageInfo(prompt_tokens=prompt, completion_tokens=completion, total_tokens=total)
