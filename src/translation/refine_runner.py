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
from translation.refine_prompt_builder import build_refine_batch_messages
from translation.response_extractor import extract_translations

STAGE_C_MAX_SEGMENTS = 30
REFINE_BATCH_SIZE = 4
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


def run_refine_pilot(
    *,
    repo_root: Path,
    run_id: str,
    limit_segments: int,
    provider_factory: Callable[[CostGuard], Any] | None = None,
    force_dry_run: bool = False,
) -> tuple[RefineRunSummary, Path]:
    if limit_segments > STAGE_C_MAX_SEGMENTS:
        raise ValueError(f"Stage C pilot hard limit: max {STAGE_C_MAX_SEGMENTS} segments per run")

    run_root = repo_root / "workspace" / "runs" / run_id
    segments_path = run_root / "segments.json"
    if not segments_path.is_file():
        raise FileNotFoundError(f"missing segments.json for run_id={run_id}")

    quality_path = run_root / "draft_quality_report.json"
    if quality_path.is_file():
        qr = json.loads(quality_path.read_text(encoding="utf-8"))
        if not qr.get("stage_c_eligible"):
            raise RuntimeError("draft run not stage_c_eligible; complete Stage B first")

    doc = load_segments_doc(segments_path)
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

    for chapter_id, segs in by_chapter.items():
        for i in range(0, len(segs), REFINE_BATCH_SIZE):
            batch = segs[i : i + REFINE_BATCH_SIZE]
            if provider_mode == "dry_run":
                _apply_dry_run_passthrough(batch, summary.diffs)
                summary.refined_segments += len(batch)
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
            for attempt in range(1, MAX_API_RETRIES + 1):
                try:
                    result = provider.generate(messages, options)
                except (CostGuardError, RuntimeError, OSError) as exc:
                    if attempt >= MAX_API_RETRIES:
                        summary.aborted = True
                        summary.abort_reason = str(exc)
                        save_segments_doc(doc, segments_path)
                        _write_refine_artifacts(run_root, summary)
                        return summary, run_root
                    time.sleep(min(30, 5 * attempt))
                    continue
                ok, msg, mapping = _extract_refined(result.raw_output, expected_ids)
                summary.api_calls += 1
                if ok:
                    break
                if attempt >= MAX_API_RETRIES:
                    break
                time.sleep(min(30, 5 * attempt))

            if not ok:
                summary.aborted = True
                summary.abort_reason = f"{chapter_id}:{msg}"
                save_segments_doc(doc, segments_path)
                _write_refine_artifacts(run_root, summary)
                return summary, run_root

            for seg in batch:
                sid = seg["segment_id"]
                after = mapping.get(sid, "").strip()
                before = (seg.get("draft_text") or "").strip()
                seg["refined_text"] = after
                seg["refine_status"] = "machine_refined"
                summary.refined_segments += 1
                summary.diffs.append(
                    {
                        "segment_id": sid,
                        "skipped": False,
                        "before": before[:120],
                        "after": after[:120],
                    }
                )

    if guard:
        summary.spent_usd = guard.spent_usd
        summary.spent_tokens = guard.spent_tokens

    save_segments_doc(doc, segments_path)
    _write_refine_artifacts(run_root, summary)
    return summary, run_root


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
        "stage": "stage_c_pilot",
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
