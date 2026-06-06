#!/usr/bin/env python3
"""Isolated real-API diagnostic runner (small scale, non-production)."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from translation.chapter_parser import list_chapter_files, parse_chapter_file  # noqa: E402
from translation.draft_runner import run_draft_stage_a  # noqa: E402
from translation.pipeline_events import emit_event  # noqa: E402
from translation.refine_runner import run_refine_controlled  # noqa: E402
from translation.run_progress import atomic_write_json  # noqa: E402

MAX_CHAPTERS = 1
MAX_SEGMENTS = 10
MAX_BATCHES = 3
MAX_RETRY_PER_BATCH = 1
MAX_WALL_TIME_SEC = 15 * 60
REQUEST_HASH_VERSION = 1


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _has_api_key() -> bool:
    for key in ("OPENROUTER_API_KEY", "DEEPSEEK_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        if os.environ.get(key, "").strip():
            return True
    return False


def _diagnostic_run_id(suffix: str) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"run_{ts}_realapi_diagnostic_{suffix}"


def _write_report(out_dir: Path, payload: dict[str, Any]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(out_dir / "real_api_diagnostic_report.json", payload)
    lines = [
        "# Real API Diagnostic Report",
        "",
        f"- generated_at: {payload.get('generated_at')}",
        f"- run_type: {payload.get('run_type')}",
        f"- api_mode: {payload.get('api_mode')}",
        f"- translate_run_id: {payload.get('translate_run_id', 'n/a')}",
        f"- refine_run_id: {payload.get('refine_run_id', 'n/a')}",
        f"- chapters: {payload.get('chapters', 0)}",
        f"- segments: {payload.get('segments', 0)}",
        f"- batches: {payload.get('batches', 0)}",
        f"- retries: {payload.get('retries', 0)}",
        f"- cost_usd: {payload.get('cost_usd', 0)}",
        f"- wall_time_sec: {payload.get('wall_time_sec', 0)}",
        f"- status: {payload.get('status')}",
        "",
        "## Notes",
        "",
        *(f"- {n}" for n in payload.get("notes", [])),
        "",
    ]
    (out_dir / "real_api_diagnostic_report.md").write_text("\n".join(lines), encoding="utf-8")


def run_dry_run_validation(repo_root: Path, out_base: Path) -> dict[str, Any]:
    """Validate diagnostic path with fake provider — no network."""
    run_id = _diagnostic_run_id("translate_dryrun")
    out_dir = out_base / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    input_link = out_dir / "input_jp"
    if not input_link.exists():
        input_link.symlink_to(repo_root / "input_jp", target_is_directory=True)
    input_dir = input_link
    chapter_files = list_chapter_files(input_dir, MAX_CHAPTERS, offset=0)
    if not chapter_files:
        return {
            "status": "skipped",
            "reason": "no_input_chapters",
            "api_mode": "dry_run",
            "run_type": "diagnostic_real_api",
            "production_eligible": False,
            "isolated": True,
            "generated_at": utc_now(),
            "notes": ["No input_jp chapters available for dry-run validation"],
        }

    fixed_items: dict[str, list[dict[str, str]]] = {}

    class StubProvider:
        provider_id = "stub_diagnostic"
        model_name = "stub-diagnostic"
        network_calls = 0

        def __init__(self, cost_guard=None):
            self.cost_guard = cost_guard

        def generate(self, messages, options=None):
            from providers.types import ModelResult

            self.network_calls += 1
            chapter = (options.input_reference if options else "") or "ch-001"
            if chapter not in fixed_items:
                ch_path = chapter_files[0]
                parsed = parse_chapter_file(ch_path)
                fixed_items[chapter] = [
                    {"segment_id": s.segment_id, "translation": f"[diag]{s.source_text[:20]}"}
                    for s in parsed.segments[:MAX_SEGMENTS]
                ]
            payload = {"items": fixed_items.get(chapter, [])[:MAX_SEGMENTS]}
            raw = json.dumps(payload, ensure_ascii=False)
            req_hash = hashlib.sha256(raw.encode()).hexdigest()[:16]
            result = ModelResult(
                provider_id=self.provider_id,
                model_name=self.model_name,
                raw_output=raw,
                parsed_output=payload,
                request_hash=req_hash,
            )
            result.mark_finished("ok")
            if self.cost_guard:
                self.cost_guard.record_call(10, 0.0001)
            return result

    started = time.monotonic()
    os.environ.setdefault("CONTROLLED_RUN_ENABLED", "true")
    summary, run_root = run_draft_stage_a(
        repo_root=out_dir,
        input_dir=input_dir,
        limit_chapters=MAX_CHAPTERS,
        run_id=run_id,
        provider_factory=lambda g: StubProvider(cost_guard=g),
    )
    meta = {
        "run_type": "diagnostic_real_api",
        "production_eligible": False,
        "isolated": True,
        "api_mode": "dry_run",
    }
    atomic_write_json(run_root / "run_metadata.json", {**json.loads((run_root / "run_metadata.json").read_text()), **meta})

    refine_id = run_id.replace("_translate", "_refine").replace("diagnostic_translate", "diagnostic_refine")
    if "diagnostic_translate" in run_id:
        refine_id = run_id.replace("diagnostic_translate", "diagnostic_refine")
    refine_summary, _ = run_refine_controlled(
        repo_root=out_dir,
        run_id=run_id,
        limit_segments=min(MAX_SEGMENTS, summary.translated_segments or MAX_SEGMENTS),
        force_dry_run=True,
        max_batches=MAX_BATCHES,
    )

    emit_event(
        "diagnostic_dry_run_complete",
        run_id=run_id,
        phase="diagnostic",
        stage="dry_run",
        status="ok",
        metadata={"segments": summary.translated_segments},
    )

    report = {
        "generated_at": utc_now(),
        "run_type": "diagnostic_real_api",
        "production_eligible": False,
        "isolated": True,
        "api_mode": "dry_run",
        "translate_run_id": run_id,
        "refine_run_id": refine_id,
        "chapters": MAX_CHAPTERS,
        "segments": summary.translated_segments,
        "batches": min(MAX_BATCHES, max(1, summary.api_calls)),
        "retries": 0,
        "cost_usd": summary.spent_usd + refine_summary.spent_usd,
        "wall_time_sec": round(time.monotonic() - started, 2),
        "status": "dry_run_passed",
        "notes": [
            "Dry-run validation completed; no real API key in environment",
            f"Output isolated under {out_dir.relative_to(repo_root)}",
        ],
    }
    _write_report(out_dir, report)
    return report


def run_real_api_diagnostic(repo_root: Path, out_base: Path) -> dict[str, Any]:
    if not _has_api_key():
        return run_dry_run_validation(repo_root, out_base)

    os.environ.setdefault("REAL_API_TESTS_ENABLED", "true")
    os.environ.setdefault("CONTROLLED_RUN_ENABLED", "true")

    run_id = _diagnostic_run_id("translate")
    out_dir = out_base / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    input_link = out_dir / "input_jp"
    if not input_link.exists():
        input_link.symlink_to(repo_root / "input_jp", target_is_directory=True)
    input_dir = input_link
    started = time.monotonic()
    notes: list[str] = []

    try:
        summary, run_root = run_draft_stage_a(
            repo_root=out_dir,
            input_dir=input_dir,
            limit_chapters=MAX_CHAPTERS,
            run_id=run_id,
        )
        meta_path = run_root / "run_metadata.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta.update(
            {
                "run_type": "diagnostic_real_api",
                "production_eligible": False,
                "isolated": True,
                "api_mode": "real",
                "request_hash_version": REQUEST_HASH_VERSION,
            }
        )
        atomic_write_json(meta_path, meta)

        if time.monotonic() - started > MAX_WALL_TIME_SEC:
            raise TimeoutError("diagnostic wall time exceeded before refine")

        refine_summary, _ = run_refine_controlled(
            repo_root=out_dir,
            run_id=run_id,
            limit_segments=min(MAX_SEGMENTS, summary.translated_segments or MAX_SEGMENTS),
            max_batches=MAX_BATCHES,
            max_retry_per_batch=MAX_RETRY_PER_BATCH,
        )

        report = {
            "generated_at": utc_now(),
            "run_type": "diagnostic_real_api",
            "production_eligible": False,
            "isolated": True,
            "api_mode": "real",
            "translate_run_id": run_id,
            "refine_run_id": run_id.replace("diagnostic_translate", "diagnostic_refine"),
            "chapters": MAX_CHAPTERS,
            "segments": summary.translated_segments,
            "batches": summary.api_calls + refine_summary.api_calls,
            "retries": 0,
            "cost_usd": round(summary.spent_usd + refine_summary.spent_usd, 6),
            "wall_time_sec": round(time.monotonic() - started, 2),
            "status": "passed" if not summary.aborted and not refine_summary.aborted else "failed",
            "notes": notes,
        }
    except Exception as exc:
        report = {
            "generated_at": utc_now(),
            "run_type": "diagnostic_real_api",
            "production_eligible": False,
            "isolated": True,
            "api_mode": "real",
            "translate_run_id": run_id,
            "status": "failed",
            "error_type": type(exc).__name__,
            "notes": [str(exc)[:200]],
            "wall_time_sec": round(time.monotonic() - started, 2),
        }

    _write_report(out_dir, report)
    emit_event(
        "diagnostic_real_api_complete",
        run_id=run_id,
        phase="diagnostic",
        stage="real_api",
        status=report.get("status", "unknown"),
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Isolated real API diagnostic")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--dry-run-only", action="store_true")
    args = parser.parse_args()

    out_base = REPO_ROOT / "workspace" / "diagnostics" / "real_api_runs"
    if args.dry_run_only or not _has_api_key():
        os.environ.setdefault("CONTROLLED_RUN_ENABLED", "true")
        os.environ.setdefault("REAL_API_TESTS_ENABLED", "false")
        report = run_dry_run_validation(REPO_ROOT, out_base)
    else:
        report = run_real_api_diagnostic(REPO_ROOT, out_base)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"diagnostic status={report.get('status')} api_mode={report.get('api_mode')}")
    return 0 if report.get("status") in {"passed", "dry_run_passed"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
