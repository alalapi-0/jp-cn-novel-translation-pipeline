"""Stage C controlled refinement pilot on an existing draft run."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from providers.cost_guard import CostGuard, CostGuardConfig, CostGuardError
from providers.dry_run_provider import DryRunProvider
from providers.types import GenerateOptions
from translation.pipeline_events import classify_error, emit_event
from translation.refine_prompt_builder import build_refine_batch_messages
from translation.response_extractor import extract_translations
from translation.run_progress import write_run_progress

STAGE_C_MAX_SEGMENTS = int(os.environ.get("STAGE_C_MAX_SEGMENTS", "500"))
REFINE_BATCH_MAX_SEGMENTS = int(os.environ.get("REFINE_BATCH_MAX_SEGMENTS", "8"))
REFINE_BATCH_MAX_CHARS = int(os.environ.get("REFINE_BATCH_MAX_CHARS", "6000"))
MAX_API_RETRIES = 3


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class RefineRunSummary:
    run_id: str
    provider_mode: str
    model_name: str
    refined_segments: int = 0
    skipped_human_edited: int = 0
    skipped_already_refined: int = 0
    api_calls: int = 0
    spent_usd: float = 0.0
    spent_tokens: int = 0
    aborted: bool = False
    abort_reason: str = ""
    diffs: list[dict[str, Any]] = field(default_factory=list)


def load_segments_doc(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def save_segments_doc(doc: dict[str, Any], path: Path) -> None:
    doc["pipeline_stage"] = "refinement"
    doc["updated_at"] = _utc_now()
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def iter_refine_candidates(
    doc: dict[str, Any],
    *,
    limit: int,
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """Return (chapter, segment) pairs eligible for refine, capped by limit."""
    out: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for chapter in doc.get("chapters", []):
        for seg in chapter.get("segments", []):
            if len(out) >= limit:
                return out
            if seg.get("human_edited"):
                continue
            draft = (seg.get("draft_text") or "").strip()
            if not draft:
                continue
            if (seg.get("refined_text") or "").strip():
                continue
            out.append((chapter, seg))
    return out


def _extract_refined(raw_output: str, expected_ids: list[str]) -> tuple[bool, str, dict[str, str]]:
    result = extract_translations(raw_output, expected_ids)
    if result.parse_status == "failed" and not result.items:
        return False, ";".join(result.parse_errors) or "extract_failed", {}
    mapping = {item.segment_id: item.translation for item in result.items}
    if result.parse_status != "ok":
        return False, ";".join(result.parse_errors) or "partial_extract", mapping
    return True, "ok", mapping


def _dynamic_batches(segs: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    batches: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    char_count = 0
    for seg in segs:
        seg_len = len((seg.get("draft_text") or "") + (seg.get("source_text") or ""))
        if current and (
            len(current) >= REFINE_BATCH_MAX_SEGMENTS
            or char_count + seg_len > REFINE_BATCH_MAX_CHARS
        ):
            batches.append(current)
            current = []
            char_count = 0
        current.append(seg)
        char_count += seg_len
    if current:
        batches.append(current)
    return batches


def _count_refine_totals(doc: dict[str, Any]) -> tuple[int, int]:
    total = refined = 0
    for chapter in doc.get("chapters", []):
        for seg in chapter.get("segments", []):
            if (seg.get("draft_text") or "").strip():
                total += 1
            if (seg.get("refined_text") or "").strip() or seg.get("human_edited"):
                refined += 1
    return total, refined


def _apply_dry_run_passthrough(
    batch: list[dict[str, Any]],
    diffs: list[dict[str, Any]],
) -> None:
    for seg in batch:
        draft = (seg.get("draft_text") or "").strip()
        seg["refined_text"] = draft
        seg["refine_status"] = "dry_run_passthrough"
        diffs.append(
            {
                "segment_id": seg["segment_id"],
                "skipped": False,
                "mode": "dry_run_passthrough",
                "before": draft[:120],
                "after": draft[:120],
            }
        )


def run_refine_controlled(
    *,
    repo_root: Path,
    run_id: str,
    limit_segments: int,
    provider_factory: Callable[[CostGuard], Any] | None = None,
    force_dry_run: bool = False,
    max_batches: int | None = None,
    max_retry_per_batch: int | None = None,
    heartbeat_cb: Callable[[], None] | None = None,
) -> tuple[RefineRunSummary, Path]:
    if limit_segments > STAGE_C_MAX_SEGMENTS:
        raise ValueError(f"Stage C hard limit: max {STAGE_C_MAX_SEGMENTS} segments per run")

    run_root = repo_root / "workspace" / "runs" / run_id
    segments_path = run_root / "segments.json"
    if not segments_path.is_file():
        raise FileNotFoundError(f"missing segments.json for run_id={run_id}")

    quality_path = run_root / "draft_quality_report.json"
    if quality_path.is_file():
        qr = json.loads(quality_path.read_text(encoding="utf-8"))
        if qr.get("stage_c_eligible") is False:
            raise RuntimeError("draft run not stage_c_eligible; complete Stage B first")

    doc = load_segments_doc(segments_path)
    total_segments, refined_before = _count_refine_totals(doc)
    meta_path = run_root / "run_metadata.json"
    chapter_offset = 0
    if meta_path.is_file():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        chapter_offset = int(meta.get("chapter_offset") or 0)

    write_run_progress(
        run_root,
        run_id=run_id,
        phase="refine",
        stage="refine_stage_c",
        chapter_offset=chapter_offset,
        status="in_progress",
        total_segments=total_segments,
        completed_segments=refined_before,
        started_at=_utc_now(),
    )
    emit_event("refine_start", run_id=run_id, phase="refine", stage="refine_stage_c")
    pairs = iter_refine_candidates(doc, limit=limit_segments)
    if not pairs:
        summary = RefineRunSummary(
            run_id=run_id,
            provider_mode="none",
            model_name="n/a",
        )
        return summary, run_root

    guard = CostGuard(CostGuardConfig.from_env())
    allow_real = guard.allow_real_network() and not force_dry_run

    if provider_factory is not None:
        provider = provider_factory(guard)
        provider_mode = "custom"
        model_name = getattr(provider, "model_name", "unknown")
    elif allow_real:
        from providers.router_provider import RouterProvider

        model_name = os.environ.get("REFINE_MODEL", "x-ai/grok-4.3")
        provider = RouterProvider(cost_guard=guard, profile="refinement", model_name=model_name)
        provider_mode = "real/model_router"
    else:
        provider = DryRunProvider(cost_guard=guard)
        provider_mode = "dry_run"
        model_name = provider.model_name

    summary = RefineRunSummary(
        run_id=run_id,
        provider_mode=provider_mode,
        model_name=model_name,
    )

    by_chapter: dict[str, list[dict[str, Any]]] = {}
    chapter_labels: dict[str, str] = {}
    for chapter, seg in pairs:
        cid = chapter.get("chapter_id", "unknown")
        by_chapter.setdefault(cid, []).append(seg)
        chapter_labels[cid] = chapter.get("chapter_label", cid)

    batch_limit = max_batches if max_batches is not None else 10_000
    retry_limit = max_retry_per_batch if max_retry_per_batch is not None else MAX_API_RETRIES
    batches_done = 0
    last_seg_id = ""

    for chapter_id, segs in by_chapter.items():
        for batch in _dynamic_batches(segs):
            if batches_done >= batch_limit:
                break
            batch_started = time.monotonic()
            if provider_mode == "dry_run":
                _apply_dry_run_passthrough(batch, summary.diffs)
                summary.refined_segments += len(batch)
                batches_done += 1
                last_seg_id = batch[-1]["segment_id"]
                save_segments_doc(doc, segments_path)
                _, refined_now = _count_refine_totals(doc)
                write_run_progress(
                    run_root,
                    run_id=run_id,
                    phase="refine",
                    stage="refine_stage_c",
                    chapter_offset=chapter_offset,
                    status="in_progress",
                    total_segments=total_segments,
                    completed_segments=refined_now,
                    last_completed_segment_id=last_seg_id,
                )
                if heartbeat_cb:
                    heartbeat_cb()
                continue

            messages = build_refine_batch_messages(
                batch,
                chapter_label=chapter_labels.get(chapter_id, chapter_id),
            )
            options = GenerateOptions(
                project_id="light-novel-jp-cn",
                language_direction="JP_TO_CN",
                pipeline_stage="refinement",
                input_reference=chapter_id,
                prompt_version="refine_v2",
            )
            expected_ids = [s["segment_id"] for s in batch]
            ok, msg, mapping = False, "no_attempt", {}
            for attempt in range(1, retry_limit + 1):
                if heartbeat_cb:
                    heartbeat_cb()
                try:
                    result = provider.generate(messages, options)
                except (CostGuardError, RuntimeError, OSError) as exc:
                    err_type = classify_error(str(exc))
                    if attempt >= retry_limit:
                        summary.aborted = True
                        summary.abort_reason = str(exc)
                        save_segments_doc(doc, segments_path)
                        write_run_progress(
                            run_root,
                            run_id=run_id,
                            phase="refine",
                            stage="refine_stage_c",
                            chapter_offset=chapter_offset,
                            status="failed",
                            total_segments=total_segments,
                            completed_segments=refined_before + summary.refined_segments,
                            last_error_type=err_type,
                        )
                        _write_refine_artifacts(run_root, summary)
                        emit_event(
                            "refine_batch_failed",
                            run_id=run_id,
                            phase="refine",
                            stage="refine_stage_c",
                            status="failed",
                            error_type=err_type,
                        )
                        return summary, run_root
                    time.sleep(min(30, 5 * attempt))
                    continue
                ok, msg, mapping = _extract_refined(result.raw_output, expected_ids)
                summary.api_calls += 1
                if ok:
                    break
                if attempt >= retry_limit:
                    break
                time.sleep(min(30, 5 * attempt))

            if not ok:
                summary.aborted = True
                summary.abort_reason = f"{chapter_id}:{msg}"
                save_segments_doc(doc, segments_path)
                write_run_progress(
                    run_root,
                    run_id=run_id,
                    phase="refine",
                    stage="refine_stage_c",
                    chapter_offset=chapter_offset,
                    status="failed",
                    total_segments=total_segments,
                    completed_segments=refined_before + summary.refined_segments,
                    last_error_type=classify_error(msg),
                )
                _write_refine_artifacts(run_root, summary)
                return summary, run_root

            for seg in batch:
                sid = seg["segment_id"]
                after = mapping.get(sid, "").strip()
                before = (seg.get("draft_text") or "").strip()
                seg["refined_text"] = after
                seg["refine_status"] = "machine_refined"
                summary.refined_segments += 1
                last_seg_id = sid
                summary.diffs.append(
                    {
                        "segment_id": sid,
                        "skipped": False,
                        "before": before[:120],
                        "after": after[:120],
                    }
                )

            batches_done += 1
            save_segments_doc(doc, segments_path)
            _, refined_now = _count_refine_totals(doc)
            write_run_progress(
                run_root,
                run_id=run_id,
                phase="refine",
                stage="refine_stage_c",
                chapter_offset=chapter_offset,
                status="in_progress",
                total_segments=total_segments,
                completed_segments=refined_now,
                last_completed_segment_id=last_seg_id,
            )
            emit_event(
                "refine_batch_complete",
                run_id=run_id,
                phase="refine",
                stage="refine_stage_c",
                status="ok",
                duration_ms=int((time.monotonic() - batch_started) * 1000),
                metadata={"batch_segments": len(batch), "api_calls": summary.api_calls},
            )
            if heartbeat_cb:
                heartbeat_cb()

    if guard:
        summary.spent_usd = guard.spent_usd
        summary.spent_tokens = guard.spent_tokens

    save_segments_doc(doc, segments_path)
    _, refined_final = _count_refine_totals(doc)
    final_status = "failed" if summary.aborted else "completed"
    write_run_progress(
        run_root,
        run_id=run_id,
        phase="refine",
        stage="refine_stage_c",
        chapter_offset=chapter_offset,
        status=final_status,
        total_segments=total_segments,
        completed_segments=refined_final,
        last_completed_segment_id=last_seg_id,
        last_error_type=classify_error(summary.abort_reason) if summary.aborted else "",
    )
    _write_refine_artifacts(run_root, summary)
    emit_event(
        "refine_complete",
        run_id=run_id,
        phase="refine",
        stage="refine_stage_c",
        status=final_status,
    )
    return summary, run_root


def run_refine_pilot(
    *,
    repo_root: Path,
    run_id: str,
    limit_segments: int,
    provider_factory: Callable[[CostGuard], Any] | None = None,
    force_dry_run: bool = False,
) -> tuple[RefineRunSummary, Path]:
    """Backward-compatible alias for controlled refine runner."""
    return run_refine_controlled(
        repo_root=repo_root,
        run_id=run_id,
        limit_segments=limit_segments,
        provider_factory=provider_factory,
        force_dry_run=force_dry_run,
    )


def _write_refine_artifacts(run_root: Path, summary: RefineRunSummary) -> None:
    diff_path = run_root / "refine_diff.json"
    diff_path.write_text(
        json.dumps(
            {
                "run_id": summary.run_id,
                "generated_at": _utc_now(),
                "provider_mode": summary.provider_mode,
                "model_name": summary.model_name,
                "diffs": summary.diffs,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    report = {
        "run_id": summary.run_id,
        "phase": "refine",
        "stage": "refine_stage_c",
        "refined_segments": summary.refined_segments,
        "api_calls": summary.api_calls,
        "cost_usd": summary.spent_usd,
        "provider_mode": summary.provider_mode,
        "model_name": summary.model_name,
        "aborted": summary.aborted,
        "abort_reason": summary.abort_reason,
        "generated_at": _utc_now(),
    }
    (run_root / "refine_quality_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
