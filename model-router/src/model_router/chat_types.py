"""Shared types for the model router."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ChatMessage:
    role: str
    content: str

    def to_dict(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}


@dataclass
class ChatOptions:
    profile: str | None = None
    model: str | None = None
    provider: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    stream: bool = False
    timeout_sec: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class UsageInfo:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
        }


@dataclass
class ChatResult:
    content: str
    model: str
    provider: str
    usage: UsageInfo
    raw: dict[str, Any]
    latency_ms: int = 0
    finish_reason: str = "stop"
    attempted_providers: list[str] = field(default_factory=list)
