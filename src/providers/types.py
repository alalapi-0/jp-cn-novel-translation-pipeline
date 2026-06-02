"""Shared types for provider adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class Message:
    role: str
    content: str


@dataclass
class GenerateOptions:
    project_id: str = "default"
    language_direction: str = "JP_TO_CN"
    pipeline_stage: str = "translation"
    prompt_version: str = "v1"
    input_reference: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelResult:
    provider_id: str
    model_name: str
    model_run_id: str = field(default_factory=lambda: str(uuid4()))
    raw_output: str = ""
    parsed_output: dict[str, Any] | None = None
    usage: dict[str, int] = field(default_factory=dict)
    cost_estimate_usd: float = 0.0
    latency_ms: int = 0
    finish_reason: str = "stop"
    error: str | None = None
    status: str = "ok"
    started_at: datetime = field(default_factory=utc_now)
    finished_at: datetime | None = None
    estimated_tokens: int = 0
    request_hash: str = ""
    dry_run: bool = False

    def mark_finished(self, status: str = "ok") -> None:
        self.status = status
        self.finished_at = utc_now()
