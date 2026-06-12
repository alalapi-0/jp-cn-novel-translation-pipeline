"""Level 4 model arbitration for rule-undecidable glossary conflicts (FS-037).

Only ``shared_target`` and ``divergent_translation`` findings enter arbitration.
Protected-term violations remain deterministic (Level 2). Outputs statistics only —
never source or draft body text in reports.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Callable

from providers.types import GenerateOptions, Message, ModelResult

ARBITRABLE_KINDS: frozenset[str] = frozenset({"shared_target", "divergent_translation"})
DEFAULT_MAX_API_CALLS = 10

SYSTEM_PROMPT = """你是轻小说翻译术语仲裁助手。给定同一术语冲突的统计信息（不含正文），
请选择应采用的 canonical 译名，并简要说明理由。
严格输出 JSON：{"canonical_target":"...", "rationale":"...", "confidence":"high|medium|low"}"""


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def select_arbitration_candidates(glossary_audit: dict[str, Any]) -> list[dict[str, Any]]:
    """Return rule-undecidable conflicts eligible for Level 4 arbitration."""
    candidates: list[dict[str, Any]] = []
    for row in glossary_audit.get("findings") or []:
        kind = str(row.get("kind") or "")
        if kind not in ARBITRABLE_KINDS:
            continue
        candidates.append(
            {
                "kind": kind,
                "source_term": row.get("source_term"),
                "target_term": row.get("target_term"),
                "source_terms": list(row.get("source_terms") or []),
                "alternate_targets": dict(row.get("alternate_targets") or {}),
                "chapters": list(row.get("chapters") or [])[:10],
                "segment_count": len(row.get("segment_ids") or []),
            }
        )
    candidates.sort(key=lambda row: (row["kind"], str(row.get("source_term") or row.get("target_term"))))
    return candidates


def build_arbitration_messages(candidate: dict[str, Any]) -> list[Message]:
    payload = {
        "kind": candidate["kind"],
        "source_term": candidate.get("source_term"),
        "canonical_glossary_target": candidate.get("target_term"),
        "alternate_source_terms": candidate.get("source_terms"),
        "alternate_targets_with_counts": candidate.get("alternate_targets"),
        "sample_chapters": candidate.get("chapters"),
        "segment_count": candidate.get("segment_count"),
        "instruction": (
            "Pick one canonical Simplified Chinese target for consistency. "
            "Prefer glossary canonical when present unless evidence strongly contradicts."
        ),
    }
    return [
        Message(role="system", content=SYSTEM_PROMPT),
        Message(role="user", content=json.dumps(payload, ensure_ascii=False, indent=2)),
    ]


_JSON_BLOCK_RE = re.compile(r"\{[^{}]*\"canonical_target\"[^{}]*\}", re.DOTALL)


def parse_arbitration_response(raw_output: str) -> dict[str, Any]:
    text = (raw_output or "").strip()
    if not text:
        return {"parse_status": "failed", "error": "empty_response"}
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = _JSON_BLOCK_RE.search(text)
        if not match:
            return {"parse_status": "failed", "error": "json_parse_failed"}
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return {"parse_status": "failed", "error": "json_parse_failed"}
    canonical = str(data.get("canonical_target") or "").strip()
    if not canonical:
        return {"parse_status": "failed", "error": "missing_canonical_target"}
    return {
        "parse_status": "ok",
        "canonical_target": canonical,
        "rationale": str(data.get("rationale") or ""),
        "confidence": str(data.get("confidence") or "medium"),
    }


def run_arbitration(
    candidates: list[dict[str, Any]],
    *,
    provider: Any,
    max_api_calls: int = DEFAULT_MAX_API_CALLS,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Arbitrate up to ``max_api_calls`` conflicts; never exceeds hard cap."""
    cap = max(0, int(max_api_calls or 0))
    decisions: list[dict[str, Any]] = []
    api_calls = 0
    skipped = 0
    budget_exhausted = False

    for candidate in candidates:
        if cap and api_calls >= cap:
            budget_exhausted = True
            skipped = len(candidates) - len(decisions)
            break
        if dry_run:
            decisions.append(
                {
                    "kind": candidate["kind"],
                    "source_term": candidate.get("source_term"),
                    "target_term": candidate.get("target_term"),
                    "dry_run": True,
                    "canonical_target": candidate.get("target_term") or "(dry-run)",
                    "rationale": "dry_run_no_api",
                    "confidence": "n/a",
                }
            )
            api_calls += 1
            continue

        messages = build_arbitration_messages(candidate)
        result: ModelResult = provider.generate(
            messages,
            GenerateOptions(project_id="consistency_arbitration", pipeline_stage="consistency_arbitration"),
        )
        api_calls += 1
        parsed = parse_arbitration_response(result.raw_output)
        decisions.append(
            {
                "kind": candidate["kind"],
                "source_term": candidate.get("source_term"),
                "target_term": candidate.get("target_term"),
                "parse_status": parsed.get("parse_status"),
                "canonical_target": parsed.get("canonical_target"),
                "rationale": parsed.get("rationale"),
                "confidence": parsed.get("confidence"),
                "error": parsed.get("error"),
                "cost_estimate_usd": result.cost_estimate_usd,
            }
        )

    return {
        "generated_at": utc_now_iso(),
        "dry_run": dry_run,
        "candidate_count": len(candidates),
        "arbitrated_count": len(decisions),
        "api_calls": api_calls,
        "max_api_calls": cap,
        "budget_exhausted": budget_exhausted,
        "skipped_count": max(0, skipped),
        "decisions": decisions,
    }


def arbitration_summary(report: dict[str, Any]) -> dict[str, Any]:
    ok = sum(1 for d in report.get("decisions") or [] if d.get("parse_status") in (None, "ok"))
    return {
        "status": "PASS",
        "candidate_count": report.get("candidate_count"),
        "arbitrated_count": report.get("arbitrated_count"),
        "api_calls": report.get("api_calls"),
        "max_api_calls": report.get("max_api_calls"),
        "budget_exhausted": report.get("budget_exhausted"),
        "successful_decisions": ok,
        "dry_run": report.get("dry_run"),
    }


ProviderFactory = Callable[[Any], Any]
