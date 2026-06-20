#!/usr/bin/env python3
"""Isolated A/B model comparison for draft translation (non-production)."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from local_env import apply_local_env  # noqa: E402
from translation.chapter_parser import list_chapter_files, parse_chapter_file  # noqa: E402
from providers.types import GenerateOptions, Message  # noqa: E402
from translation.run_progress import atomic_write_json  # noqa: E402
from translation.validator import validate_draft_items  # noqa: E402
from translation.response_extractor import extract_translations  # noqa: E402

JP_RE = re.compile(r"[\u3040-\u30ff]")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _has_api_key() -> bool:
    return bool(os.environ.get("OPENROUTER_API_KEY", "").strip())


def _run_variant(
    *,
    repo_root: Path,
    out_root: Path,
    model: str,
    profile: str,
    max_chapters: int,
    chapter_offset: int,
    label: str,
) -> dict[str, Any]:
    os.environ["DRAFT_MODEL"] = model
    os.environ["MODEL_ROUTER_DEFAULT_PROFILE"] = profile
    os.environ["REAL_API_TESTS_ENABLED"] = "1"
    os.environ["CONTROLLED_RUN_ENABLED"] = "1"

    run_id = f"ab_{label}_{uuid4().hex[:8]}"
    input_dir = repo_root / "input_jp"
    started = time.monotonic()

    from providers.cost_guard import CostGuard, CostGuardConfig
    from providers.router_provider import RouterProvider

    guard = CostGuard(CostGuardConfig.from_env())
    provider = RouterProvider(
        cost_guard=guard,
        profile=profile,
        model_name=model,
        timeout_sec=90,
    )

    chapter_paths = list_chapter_files(input_dir, max_chapters, offset=chapter_offset)
    if not chapter_paths:
        return {"label": label, "model": model, "status": "skipped", "reason": "no_chapters"}

    parsed = [parse_chapter_file(p) for p in chapter_paths]
    segments_tested = 0
    validation_failed = 0
    parse_failed = 0
    source_residual = 0
    api_calls = 0
    retries = 0
    latencies: list[float] = []

    max_seg = int(os.environ.get("MODEL_AB_MAX_SEGMENTS", "20"))
    for chapter in parsed:
        for seg in chapter.segments[:max_seg]:
            if segments_tested >= max_seg:
                break
            messages = [
                Message(
                    role="system",
                    content="Translate JP light novel segment to zh-CN. Return JSON items with segment_id and translation.",
                ),
                Message(
                    role="user",
                    content=f"segment_id: {seg.segment_id}\nsource:\n{seg.source_text}",
                ),
            ]
            opts = GenerateOptions(
                project_id="light-novel-jp-cn",
                language_direction="JP_TO_CN",
                pipeline_stage="draft_translation",
                input_reference=chapter.chapter_id,
            )
            t0 = time.monotonic()
            try:
                result = provider.generate(messages, opts)
                api_calls += 1
                latencies.append((time.monotonic() - t0) * 1000)
            except Exception as exc:
                return {
                    "label": label,
                    "model": model,
                    "status": "provider_error",
                    "error": str(exc),
                    "api_calls": api_calls,
                }
            extracted = extract_translations(result.raw_output, [seg.segment_id])
            if extracted.parse_status == "failed":
                parse_failed += 1
            draft = ""
            if extracted.items:
                draft = str(extracted.items[0].translation or "")
            val = validate_draft_items(
                extracted.items,
                [seg.segment_id],
                {seg.segment_id: len(seg.source_text)},
            )
            if not val.passed:
                validation_failed += 1
            if draft and JP_RE.search(draft):
                source_residual += 1
            segments_tested += 1
        if segments_tested >= max_seg:
            break

    wall = time.monotonic() - started
    return {
        "label": label,
        "model": model,
        "profile": profile,
        "status": "ok",
        "segments_tested": segments_tested,
        "api_calls": api_calls,
        "retries": retries,
        "validation_failed": validation_failed,
        "parse_failed": parse_failed,
        "source_residual": source_residual,
        "spent_usd": round(guard.spent_usd, 6),
        "avg_latency_ms": round(sum(latencies) / len(latencies), 1) if latencies else None,
        "wall_time_sec": round(wall, 1),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Draft translation model A/B test")
    parser.add_argument("--baseline-model", default="deepseek/deepseek-v4-pro")
    parser.add_argument("--candidate-model", default="nvidia/nemotron-3-ultra-550b-a55b:free")
    parser.add_argument("--max-chapters", type=int, default=1)
    parser.add_argument("--max-segments", type=int, default=20)
    parser.add_argument("--chapter-offset", type=int, default=190)
    parser.add_argument("--isolated", action="store_true", default=True)
    parser.add_argument(
        "--user-confirmed-model-ab",
        action="store_true",
        help="required for any real model comparison; model switches/A-B tests need explicit user confirmation",
    )
    args = parser.parse_args()
    if not args.user_confirmed_model_ab and os.environ.get("ALLOW_MODEL_AB_TEST") != "1":
        print(
            "model_ab_test: blocked; real model A/B requires --user-confirmed-model-ab "
            "or ALLOW_MODEL_AB_TEST=1",
            file=sys.stderr,
        )
        return 2
    apply_local_env(REPO_ROOT)
    os.environ["MODEL_AB_MAX_SEGMENTS"] = str(args.max_segments)

    ab_id = f"model_ab_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    out_dir = REPO_ROOT / "workspace" / "diagnostics" / "model_ab_tests" / ab_id
    out_dir.mkdir(parents=True, exist_ok=True)

    if not _has_api_key():
        report = {
            "generated_at": _utc_now(),
            "status": "missing_api_key",
            "decision": "keep_baseline",
            "baseline_model": args.baseline_model,
            "candidate_model": args.candidate_model,
            "notes": ["OPENROUTER_API_KEY not configured"],
        }
        atomic_write_json(out_dir / "model_ab_report.json", report)
        (out_dir / "model_ab_report.md").write_text(
            "# Model A/B Report\n\n- status: missing_api_key\n- decision: keep_baseline\n",
            encoding="utf-8",
        )
        print("model_ab_test: missing_api_key")
        return 2

    os.environ.setdefault("MAX_TEST_COST_USD", "1.0")
    baseline = _run_variant(
        repo_root=REPO_ROOT,
        out_root=out_dir,
        model=args.baseline_model,
        profile="draft_translation",
        max_chapters=args.max_chapters,
        chapter_offset=args.chapter_offset,
        label="baseline",
    )
    candidate = _run_variant(
        repo_root=REPO_ROOT,
        out_root=out_dir,
        model=args.candidate_model,
        profile="draft_translation_nemotron_candidate",
        max_chapters=args.max_chapters,
        chapter_offset=args.chapter_offset,
        label="candidate",
    )

    decision = "keep_baseline"
    reasons: list[str] = []
    if candidate.get("status") != "ok":
        reasons.append(f"candidate_unavailable: {candidate.get('error') or candidate.get('status')}")
    elif candidate.get("parse_failed", 0) > baseline.get("parse_failed", 0):
        reasons.append("candidate_parse_failed_higher")
    elif candidate.get("validation_failed", 0) > baseline.get("validation_failed", 0) + 2:
        reasons.append("candidate_validation_failed_higher")
    elif candidate.get("source_residual", 0) > baseline.get("source_residual", 0) + 3:
        reasons.append("candidate_source_residual_higher")
    else:
        decision = "candidate_eligible"
        reasons.append("candidate_passed_min_quality_gate")

    report = {
        "generated_at": _utc_now(),
        "ab_run_id": ab_id,
        "baseline": baseline,
        "candidate": candidate,
        "decision": decision,
        "reasons": reasons,
        "production_switch_allowed": decision == "candidate_eligible",
    }
    atomic_write_json(out_dir / "model_ab_report.json", report)
    lines = [
        "# Model A/B Report",
        "",
        f"- ab_run_id: {ab_id}",
        f"- baseline: {args.baseline_model}",
        f"- candidate: {args.candidate_model}",
        f"- decision: **{decision}**",
        "",
        "## Baseline",
        json.dumps(baseline, ensure_ascii=False, indent=2),
        "",
        "## Candidate",
        json.dumps(candidate, ensure_ascii=False, indent=2),
        "",
        "## Reasons",
        *(f"- {r}" for r in reasons),
    ]
    (out_dir / "model_ab_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"model_ab_test: decision={decision} report={out_dir}/model_ab_report.json")
    return 0 if candidate.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
