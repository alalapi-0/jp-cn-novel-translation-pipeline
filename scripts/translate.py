#!/usr/bin/env python3
"""Controlled translation CLI: draft Stage A/B (bounded chapters)."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from translation.draft_runner import (  # noqa: E402
    STAGE_A_MAX_CHAPTERS,
    STAGE_B_MAX_CHAPTERS,
    run_draft_stage_a,
    run_draft_stage_b,
)

STAGE_STATE_MAP = {
    "stage_a": "draft_stage_a_5ch",
    "stage_b": "draft_stage_b_50ch",
}


def _update_stage_state(
    repo_root: Path,
    stage: str,
    run_id: str,
    status: str,
    summary: dict,
) -> None:
    path = repo_root / "workspace" / "stage_state.json"
    payload = {
        "phase": "draft",
        "stage": STAGE_STATE_MAP[stage],
        "status": status,
        "run_id": run_id,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "refine_blocked": True,
        "summary": summary,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Controlled novel translation")
    parser.add_argument("--phase", choices=["draft"], required=True)
    parser.add_argument("--stage", choices=["stage_a", "stage_b"], required=True)
    parser.add_argument("--limit-chapters", type=int, default=None)
    parser.add_argument("--input-dir", type=Path, default=REPO_ROOT / "input_jp")
    parser.add_argument("--run-id", default="")
    args = parser.parse_args()

    if args.phase != "draft":
        print("Only draft phase is implemented", file=sys.stderr)
        return 2

    if args.stage == "stage_a":
        limit = args.limit_chapters if args.limit_chapters is not None else STAGE_A_MAX_CHAPTERS
        if limit > STAGE_A_MAX_CHAPTERS:
            print(f"Hard limit: max {STAGE_A_MAX_CHAPTERS} chapters per Stage A run", file=sys.stderr)
            return 2
        run_fn = run_draft_stage_a
    else:
        limit = args.limit_chapters if args.limit_chapters is not None else STAGE_B_MAX_CHAPTERS
        if limit > STAGE_B_MAX_CHAPTERS:
            print(f"Hard limit: max {STAGE_B_MAX_CHAPTERS} chapters per Stage B run", file=sys.stderr)
            return 2
        run_fn = run_draft_stage_b

    run_id = args.run_id.strip() or None
    _update_stage_state(
        REPO_ROOT,
        args.stage,
        run_id or "pending",
        "in_progress",
        {"limit_chapters": limit},
    )

    try:
        summary, run_root = run_fn(
            repo_root=REPO_ROOT,
            input_dir=args.input_dir,
            limit_chapters=limit,
            run_id=run_id,
        )
    except Exception as exc:
        _update_stage_state(
            REPO_ROOT,
            args.stage,
            run_id or "failed",
            "failed",
            {"error": str(exc)},
        )
        print(f"translate failed: {exc}", file=sys.stderr)
        return 2

    ok = not summary.aborted and all(c.ok for c in summary.chapters)
    status = "completed" if ok else "failed"
    _update_stage_state(
        REPO_ROOT,
        args.stage,
        summary.run_id,
        status,
        {
            "translated_segments": summary.translated_segments,
            "total_segments": summary.total_segments,
            "provider_mode": summary.provider_mode,
            "model_name": summary.model_name,
            "run_root": str(run_root.relative_to(REPO_ROOT)),
            "api_calls": summary.api_calls,
            "spent_usd": summary.spent_usd,
        },
    )
    print(
        f"run_id={summary.run_id} status={status} "
        f"segments={summary.translated_segments}/{summary.total_segments} "
        f"api_calls={summary.api_calls} cost_usd={summary.spent_usd:.6f}"
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
