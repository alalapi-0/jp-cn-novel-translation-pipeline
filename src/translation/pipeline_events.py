"""Minimal pipeline telemetry — no source text, translations, or prompts."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_EVENTS_PATH = Path("workspace/diagnostics/pipeline_events.jsonl")

# Unified error taxonomy (subset used by draft/refine runners)
ERROR_TAXONOMY = frozenset(
    {
        "provider_timeout",
        "provider_network",
        "provider_rate_limit",
        "provider_auth",
        "cost_guard_exceeded",
        "extract_failed",
        "validation_failed",
        "segment_id_coverage",
        "lock_busy",
        "duplicate_worker",
        "state_conflict",
        "unknown",
    }
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def classify_error(message: str) -> str:
    lower = (message or "").lower()
    if "timeout" in lower or "timed out" in lower:
        return "provider_timeout"
    if "rate limit" in lower or "429" in lower:
        return "provider_rate_limit"
    if "401" in lower or "403" in lower or "auth" in lower or "api key" in lower:
        return "provider_auth"
    if "network" in lower or "connection" in lower:
        return "provider_network"
    if "costguard" in lower or "budget" in lower or "cost guard" in lower:
        return "cost_guard_exceeded"
    if "extract" in lower:
        return "extract_failed"
    if "validate" in lower or "validation" in lower:
        return "validation_failed"
    if "coverage" in lower:
        return "segment_id_coverage"
    if "already running" in lower or "lock" in lower:
        return "lock_busy"
    if "duplicate" in lower:
        return "duplicate_worker"
    if "conflict" in lower:
        return "state_conflict"
    return "unknown"


def emit_event(
    event_type: str,
    *,
    run_id: str = "",
    phase: str = "",
    stage: str = "",
    status: str = "ok",
    duration_ms: int | None = None,
    error_type: str = "",
    metadata: dict[str, Any] | None = None,
    events_path: Path | None = None,
) -> None:
    path = events_path or DEFAULT_EVENTS_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "timestamp": utc_now(),
        "event_type": event_type,
        "run_id": run_id,
        "phase": phase,
        "stage": stage,
        "status": status,
    }
    if duration_ms is not None:
        row["duration_ms"] = duration_ms
    if error_type:
        row["error_type"] = error_type if error_type in ERROR_TAXONOMY else "unknown"
    if metadata:
        safe = {
            k: v
            for k, v in metadata.items()
            if k
            not in {
                "source_text",
                "draft_text",
                "refined_text",
                "raw_output",
                "prompt",
                "messages",
                "api_key",
                "authorization",
            }
        }
        if safe:
            row["metadata"] = safe
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")
