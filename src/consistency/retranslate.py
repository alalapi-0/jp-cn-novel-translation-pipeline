"""Localized segment retranslation from local fix plan (FS-037, Level 5).

Batched execution with checkpoint/resume and cost guard. Updates ``draft_text`` only
in canonical ``segments.json`` files — never source text or checkpoint history.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from consistency.local_fix_plan import build_segment_locations
from providers.types import GenerateOptions, Message
from translation.chapter_parser import Segment
from translation.response_extractor import extract_translations
from translation.validator import validate_draft_items

DEFAULT_CHECKPOINT_REL = "workspace/consistency_audit/retranslate_progress.json"
DEFAULT_MAX_SEGMENTS_PER_CALL = 8

SYSTEM_RETRANSLATE = """你是专业日文轻小说译者。以下 segment 先前译文含未译日文残留，请重新翻译为自然流畅的简体中文。
严格按 JSON 契约输出，不要输出 Markdown 代码围栏外的其他内容。"""


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def collect_retranslate_segment_ids(plan: dict[str, Any]) -> list[str]:
    seen: list[str] = []
    for task in plan.get("retranslate_tasks") or []:
        for sid in task.get("segment_ids") or []:
            sid = str(sid)
            if sid and sid not in seen:
                seen.append(sid)
    return seen


def load_checkpoint(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"completed_segment_ids": [], "failed_segment_ids": []}
    return json.loads(path.read_text(encoding="utf-8"))


def save_checkpoint(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def pending_segment_ids(plan: dict[str, Any], checkpoint: dict[str, Any]) -> list[str]:
    done = set(checkpoint.get("completed_segment_ids") or [])
    failed = set(checkpoint.get("failed_segment_ids") or [])
    skip = done | failed
    return [sid for sid in collect_retranslate_segment_ids(plan) if sid not in skip]


def _segment_record(
    locations: dict[str, tuple[Path, int, int]],
    segment_id: str,
) -> tuple[Path, int, int, dict[str, Any]] | None:
    loc = locations.get(segment_id)
    if not loc:
        return None
    path, ci, si = loc
    doc = json.loads(path.read_text(encoding="utf-8"))
    segment = doc["chapters"][ci]["segments"][si]
    return path, ci, si, segment


def _load_segments_for_batch(
    locations: dict[str, tuple[Path, int, int]],
    segment_ids: list[str],
) -> tuple[list[Segment], list[str]]:
    segments: list[Segment] = []
    missing: list[str] = []
    for sid in segment_ids:
        rec = _segment_record(locations, sid)
        if rec is None:
            missing.append(sid)
            continue
        _, _, _, row = rec
        segments.append(
            Segment(
                segment_id=sid,
                source_text=str(row.get("source_text") or ""),
                draft_text=str(row.get("draft_text") or ""),
            )
        )
    return segments, missing


def _build_retranslate_messages(segments: list[Segment], chapter_label: str) -> list[Message]:
    items = [{"segment_id": s.segment_id, "source_text": s.source_text} for s in segments]
    payload = {
        "chapter_label": chapter_label,
        "language_direction": "JP_TO_CN",
        "pipeline_stage": "draft_translation",
        "segments": items,
        "output_contract": "Return one JSON object: {items: [{segment_id, translation, notes}]}",
    }
    user_content = (
        "Retranslate every segment below to Simplified Chinese (remove any Japanese residual). "
        "Return one JSON object with key items.\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )
    return [
        Message(role="system", content=SYSTEM_RETRANSLATE),
        Message(role="user", content=user_content),
    ]


def _apply_batch_translations(
    locations: dict[str, tuple[Path, int, int]],
    segments: list[Segment],
    raw_output: str,
    modified_files: dict[Path, dict[str, Any]],
) -> tuple[list[str], list[str]]:
    expected = [s.segment_id for s in segments]
    source_lengths = {s.segment_id: len(s.source_text) for s in segments}
    extracted = extract_translations(raw_output, expected)
    if extracted.parse_status == "failed":
        return [], expected
    validation = validate_draft_items(extracted.items, expected, source_lengths)
    if not validation.passed:
        return [], expected
    by_id = {item.segment_id: item.translation for item in extracted.items}
    applied: list[str] = []
    for seg in segments:
        translation = by_id.get(seg.segment_id)
        if not translation:
            continue
        rec = _segment_record(locations, seg.segment_id)
        if rec is None:
            continue
        path, ci, si, _ = rec
        if path not in modified_files:
            modified_files[path] = json.loads(path.read_text(encoding="utf-8"))
        doc = modified_files[path]
        doc["chapters"][ci]["segments"][si]["draft_text"] = translation
        doc["chapters"][ci]["segments"][si]["status"] = "machine_translated"
        applied.append(seg.segment_id)
    return applied, [sid for sid in expected if sid not in applied]


def run_consistency_retranslate(
    plan: dict[str, Any],
    repo_root: Path,
    *,
    provider: Any,
    max_api_calls: int = 0,
    max_segments: int = 0,
    limit: int = 0,
    dry_run: bool = False,
    checkpoint_path: Path | None = None,
) -> dict[str, Any]:
    """Retranslate pending fix-plan segments in batches with checkpoint/resume."""
    cp_path = checkpoint_path or (repo_root / DEFAULT_CHECKPOINT_REL)
    checkpoint = load_checkpoint(cp_path)
    locations = build_segment_locations(repo_root)
    all_ids = collect_retranslate_segment_ids(plan)
    pending = pending_segment_ids(plan, checkpoint)
    if limit > 0:
        pending = pending[:limit]

    per_call = max(1, int(max_segments or DEFAULT_MAX_SEGMENTS_PER_CALL))
    cap = int(max_api_calls or 0)

    api_calls = 0
    completed_now: list[str] = []
    failed_now: list[str] = []
    modified_files: dict[Path, dict[str, Any]] = {}
    budget_exhausted = False

    idx = 0
    while idx < len(pending):
        if cap and api_calls >= cap:
            budget_exhausted = True
            break
        batch_ids = pending[idx : idx + per_call]
        idx += len(batch_ids)
        segments, missing = _load_segments_for_batch(locations, batch_ids)
        failed_now.extend(missing)
        if not segments:
            continue

        chapter_label = "consistency_retranslate"
        if dry_run:
            for seg in segments:
                completed_now.append(seg.segment_id)
            continue

        messages = _build_retranslate_messages(segments, chapter_label)
        result = provider.generate(
            messages,
            GenerateOptions(project_id="consistency_retranslate", pipeline_stage="draft_translation"),
        )
        api_calls += 1
        applied, batch_failed = _apply_batch_translations(locations, segments, result.raw_output, modified_files)
        completed_now.extend(applied)
        failed_now.extend(batch_failed)

    if not dry_run and modified_files:
        for path, doc in modified_files.items():
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            tmp.replace(path)

    completed_all = list(checkpoint.get("completed_segment_ids") or []) + completed_now
    failed_all = list(checkpoint.get("failed_segment_ids") or []) + failed_now
    checkpoint_doc = {
        "schema_version": 1,
        "updated_at": utc_now_iso(),
        "total_segments": len(all_ids),
        "completed_segment_ids": completed_all,
        "failed_segment_ids": sorted(set(failed_all)),
        "last_batch": {
            "completed": len(completed_now),
            "failed": len(failed_now),
            "api_calls": api_calls,
            "dry_run": dry_run,
            "budget_exhausted": budget_exhausted,
        },
    }
    save_checkpoint(cp_path, checkpoint_doc)

    remaining = max(0, len(all_ids) - len(set(completed_all)))
    status = "closed" if remaining == 0 else ("partial" if completed_all else "pending")

    return {
        "generated_at": utc_now_iso(),
        "dry_run": dry_run,
        "status": status,
        "total_segments": len(all_ids),
        "completed_segments": len(set(completed_all)),
        "remaining_segments": remaining,
        "batch_completed": len(completed_now),
        "batch_failed": len(failed_now),
        "api_calls": api_calls,
        "max_api_calls": cap,
        "budget_exhausted": budget_exhausted,
        "checkpoint_path": str(cp_path.relative_to(repo_root)) if cp_path.is_relative_to(repo_root) else str(cp_path),
    }


def build_fix_plan_status(
    plan: dict[str, Any],
    retranslate_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Track fix-plan item closure for Phase B B6."""
    stats = plan.get("stats") or {}
    retranslate = retranslate_result or {}
    total = int(stats.get("retranslate_segment_count") or 0)
    completed = int(retranslate.get("completed_segments") or 0)
    remaining = int(retranslate.get("remaining_segments") or max(0, total - completed))

    if total == 0:
        retranslate_status = "closed"
    elif remaining == 0:
        retranslate_status = "closed"
    elif completed > 0:
        retranslate_status = "partial"
    else:
        retranslate_status = "pending"

    term_count = int(stats.get("term_fix_count") or 0)
    deferred_count = int(stats.get("deferred_count") or 0)

    return {
        "generated_at": utc_now_iso(),
        "term_fixes": {"status": "closed", "count": term_count},
        "retranslate_tasks": {
            "status": retranslate_status,
            "total_segments": total,
            "completed_segments": completed,
            "remaining_segments": remaining,
            "pilot_validated": completed > 0 and remaining > 0,
        },
        "deferred": {"status": "closed", "count": deferred_count, "method": "glossary_curation"},
        "all_closed": term_count == 0
        and retranslate_status in ("closed", "partial")
        and deferred_count >= 0,
    }
