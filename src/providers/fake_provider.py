"""Fake provider: fixed predictable output, no network."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from .cost_guard import CostGuard
from .tokens import estimate_cost_usd, estimate_tokens
from .types import GenerateOptions, Message, ModelResult


DEFAULT_FAKE_OUTPUT = {
    "translation": "[fake] translated segment",
    "notes": "fake provider output for pipeline testing",
    "confidence": 1.0,
}


def _segment_ids_from_messages(messages: list[Message]) -> list[str]:
    text = messages[-1].content if messages else ""
    return re.findall(r'"segment_id"\s*:\s*"([^"]+)"', text)


class FakeProvider:
    provider_id = "fake_provider"
    model_name = "fake-model-v1"

    def __init__(self, cost_guard: CostGuard | None = None, fixed_output: dict[str, Any] | None = None) -> None:
        self.cost_guard = cost_guard
        self.fixed_output = fixed_output or dict(DEFAULT_FAKE_OUTPUT)
        self.network_calls = 0

    def _build_output(self, messages: list[Message]) -> dict[str, Any]:
        segment_ids = _segment_ids_from_messages(messages)
        if len(segment_ids) > 1:
            return {
                "items": [
                    {
                        "segment_id": sid,
                        "translation": f"[fake] {sid}",
                        "notes": "fake provider batch output",
                    }
                    for sid in segment_ids
                ]
            }
        if len(segment_ids) == 1:
            return {
                "segment_id": segment_ids[0],
                "translation": f"[fake] {segment_ids[0]}",
                "notes": "fake provider output for pipeline testing",
            }
        return dict(self.fixed_output)

    def generate(self, messages: list[Message], options: GenerateOptions | None = None) -> ModelResult:
        options = options or GenerateOptions()
        tokens = estimate_tokens(messages)
        cost = estimate_cost_usd(tokens)

        if self.cost_guard is not None:
            self.cost_guard.check_before_call(messages)
            self.cost_guard.record_call(tokens, cost)

        self.network_calls += 0  # intentional: never touches network

        parsed_output = self._build_output(messages)
        raw = json.dumps(parsed_output, ensure_ascii=False)
        req_hash = hashlib.sha256("|".join(m.content for m in messages).encode()).hexdigest()[:16]

        result = ModelResult(
            provider_id=self.provider_id,
            model_name=self.model_name,
            raw_output=raw,
            parsed_output=parsed_output,
            usage={"prompt_tokens": tokens, "completion_tokens": len(raw) // 4, "total_tokens": tokens + len(raw) // 4},
            cost_estimate_usd=cost,
            estimated_tokens=tokens,
            request_hash=req_hash,
            dry_run=False,
        )
        result.mark_finished("ok")
        return result
