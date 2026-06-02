"""Dry-run provider: record request metadata, never send network."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from .cost_guard import CostGuard
from .tokens import estimate_cost_usd, estimate_tokens
from .types import GenerateOptions, Message, ModelResult


@dataclass
class DryRunRecord:
    messages: list[Message]
    options: GenerateOptions
    estimated_tokens: int
    cost_estimate_usd: float
    request_hash: str
    metadata: dict[str, Any] = field(default_factory=dict)


class DryRunProvider:
    provider_id = "dry_run_provider"
    model_name = "dry-run-no-network"

    def __init__(self, cost_guard: CostGuard | None = None) -> None:
        self.cost_guard = cost_guard
        self.records: list[DryRunRecord] = []
        self.network_calls = 0

    def generate(self, messages: list[Message], options: GenerateOptions | None = None) -> ModelResult:
        options = options or GenerateOptions()
        tokens = estimate_tokens(messages)
        cost = estimate_cost_usd(tokens)

        if self.cost_guard is not None:
            self.cost_guard.check_before_call(messages)
            self.cost_guard.record_call(tokens, cost)

        req_hash = hashlib.sha256("|".join(m.content for m in messages).encode()).hexdigest()[:16]
        record = DryRunRecord(
            messages=list(messages),
            options=options,
            estimated_tokens=tokens,
            cost_estimate_usd=cost,
            request_hash=req_hash,
            metadata={
                "provider_id": self.provider_id,
                "model_name": self.model_name,
                "pipeline_stage": options.pipeline_stage,
                "prompt_version": options.prompt_version,
            },
        )
        self.records.append(record)

        summary = {
            "dry_run": True,
            "request_hash": req_hash,
            "estimated_tokens": tokens,
            "cost_estimate_usd": cost,
            "message_count": len(messages),
        }
        raw = json.dumps(summary, ensure_ascii=False)

        result = ModelResult(
            provider_id=self.provider_id,
            model_name=self.model_name,
            raw_output=raw,
            parsed_output=summary,
            usage={"prompt_tokens": tokens, "completion_tokens": 0, "total_tokens": tokens},
            cost_estimate_usd=cost,
            estimated_tokens=tokens,
            request_hash=req_hash,
            dry_run=True,
            finish_reason="dry_run",
        )
        result.mark_finished("dry_run")
        return result
