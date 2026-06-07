#!/usr/bin/env python3
"""Hydrate run artifacts (run_metadata, run_progress, segments) from checkpoint + draft files.

Resume strategy
---------------
1. Checkpoint ``status=in_progress`` with ``completed_segments`` is the source of truth for
   which segments already finished (never invent completed chapters).
2. Draft markdown under ``workspace/runs/<run_id>/draft/`` supplies ``draft_text`` when present.
3. Input chapter files supply ``source_text`` and segment structure.
4. After dry-run review, pass ``--apply`` to write artifacts; then resume with::

     python3 scripts/translate.py --phase draft --stage stage_b \\
       --chapter-offset <offset> --limit-chapters <n> --run-id <run_id> \\
       --asset-context workspace/assets/translation_memory/pw-user-assets-flow.json \\
       --stage-state-path workspace/stage_state_production.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from local_env import apply_local_env  # noqa: E402
from translation.chapter_parser import (  # noqa: E402
    ParsedChapter,
    list_chapter_files,
    parse_chapter_file,
)
from translation.exporter import export_segments_doc  # noqa: E402
from translation.run_progress import atomic_write_json, safe_load_json, write_run_progress  # noqa: E402

_SEGMENT_ID_RE = re.compile(r"<!--\s*(\S+)\s*-->")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _chapter_offset_from_segment(segment_id: str) -> int | None:
    m = re.match(r"ch-(\d+)-seg-", segment_id or "")
    if not m:
        return None
    return max(0, int(m.group(1)) - 1)


def _valid_segment_ids(chapters: list[ParsedChapter]) -> set[str]:
    return {seg.segment_id for ch in chapters for seg in ch.segments}


def _filter_completed_segments(
    completed_ids: list[str],
    chapters: list[ParsedChapter],
) -> tuple[list[str], list[str]]:
    """Keep checkpoint segments that belong to the hydrated chapter batch only."""
    valid = _valid_segment_ids(chapters)
    kept = [sid for sid in completed_ids if sid in valid]
    dropped = [sid for sid in completed_ids if sid not in valid]
    return kept, dropped


def _hydrate_from_draft_md(run_root: Path, chapters: list[ParsedChapter]) -> int:
    draft_dir = run_root / "draft"
    if not draft_dir.is_dir():
        return 0
    hydrated = 0
    for chapter in chapters:
        md_path = draft_dir / f"{chapter.chapter_id}_draft_zh.md"
        if not md_path.is_file():
            continue
        by_id: dict[str, str] = {}
        current_id: str | None = None
        buf: list[str] = []
        for line in md_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("# "):
                continue
            match = _SEGMENT_ID_RE.match(line.strip())
            if match:
                if current_id and buf:
                    by_id[current_id] = "\n".join(buf).strip()
                current_id = match.group(1)
                buf = []
            elif current_id is not None:
                buf.append(line)
        if current_id and buf:
            by_id[current_id] = "\n".join(buf).strip()
        for seg in chapter.segments:
            text = by_id.get(seg.segment_id, "")
            if text:
                seg.draft_text = text
                seg.status = "machine_translated"
                hydrated += 1
    return hydrated


def _count_translated(chapters: list[ParsedChapter]) -> int:
    return sum(1 for ch in chapters for s in ch.segments if (s.draft_text or "").strip())


def plan_hydrate(
    *,
    repo_root: Path,
    run_id: str,
    input_dir: Path,
    chapter_offset: int | None,
    limit_chapters: int,
) -> dict:
    cp_path = repo_root / "workspace" / "checkpoints" / f"{run_id}.json"
    if not cp_path.is_file():
        raise FileNotFoundError(f"checkpoint not found: {cp_path}")
    checkpoint = json.loads(cp_path.read_text(encoding="utf-8"))
    run_root = repo_root / "workspace" / "runs" / run_id
    run_root.mkdir(parents=True, exist_ok=True)

    raw_completed_ids = list(checkpoint.get("completed_segments") or [])
    if chapter_offset is None:
        if raw_completed_ids:
            chapter_offset = _chapter_offset_from_segment(raw_completed_ids[0]) or 0
        else:
            chapter_offset = 0

    chapter_paths = list_chapter_files(input_dir, limit_chapters, offset=chapter_offset)
    if not chapter_paths:
        raise FileNotFoundError(
            f"no chapters under {input_dir} (offset={chapter_offset}, limit={limit_chapters})"
        )

    chapters = [parse_chapter_file(p) for p in chapter_paths]
    completed_ids, dropped_completed = _filter_completed_segments(raw_completed_ids, chapters)
    from_draft = _hydrate_from_draft_md(run_root, chapters)
    completed_set = set(completed_ids)
    for ch in chapters:
        for seg in ch.segments:
            if seg.segment_id in completed_set and (seg.draft_text or "").strip():
                seg.status = "machine_translated"

    total_segments = sum(len(ch.segments) for ch in chapters)
    translated = _count_translated(chapters)
    cp_status = str(checkpoint.get("status") or "in_progress").split(":", 1)[0]
    progress_status = "in_progress" if cp_status == "in_progress" else cp_status

    meta = {
        "run_id": run_id,
        "phase": "draft",
        "stage": "stage_b",
        "scope": "draft_stage_b_50ch",
        "started_at": checkpoint.get("updated_at") or _utc_now(),
        "provider_mode": "real/model_router",
        "model_name": "",
        "asset_context_path": "",
        "language_direction": "JP_TO_CN",
        "chapter_files": [str(p.relative_to(repo_root)) for p in chapter_paths],
        "input_dir": str(input_dir.relative_to(repo_root)),
        "limit_chapters": len(chapter_paths),
        "chapter_offset": chapter_offset,
        "real_api_called": True,
        "summary": {
            "total_segments": total_segments,
            "translated_segments": translated,
            "api_calls": 0,
            "spent_usd": float(checkpoint.get("spent_usd") or 0.0),
            "spent_tokens": int(checkpoint.get("spent_tokens") or 0),
            "aborted": cp_status != "completed",
            "abort_reason": "" if cp_status == "completed" else cp_status,
        },
        "hydrated_from_checkpoint": True,
        "hydrated_at": _utc_now(),
    }

    existing = {
        "run_metadata.json": safe_load_json(run_root / "run_metadata.json") is not None,
        "run_progress.json": safe_load_json(run_root / "run_progress.json") is not None,
        "segments.json": (run_root / "segments.json").is_file(),
    }

    return {
        "run_id": run_id,
        "run_root": str(run_root.relative_to(repo_root)),
        "checkpoint_status": checkpoint.get("status"),
        "chapter_offset": chapter_offset,
        "limit_chapters": limit_chapters,
        "total_segments": total_segments,
        "translated_segments": translated,
        "completed_checkpoint_segments": len(completed_ids),
        "dropped_checkpoint_segments": len(dropped_completed),
        "dropped_segment_ids_sample": dropped_completed[:5],
        "draft_md_hydrated_segments": from_draft,
        "progress_status": progress_status,
        "existing_artifacts": existing,
        "would_write": ["run_metadata.json", "run_progress.json", "segments.json"],
        "meta": meta,
        "chapters": chapters,
    }


def _trim_checkpoint_completed_segments(
    repo_root: Path,
    *,
    run_id: str,
    chapters: list[ParsedChapter],
) -> int:
    """Remove checkpoint segments outside the current offset/limit window."""
    cp_path = repo_root / "workspace" / "checkpoints" / f"{run_id}.json"
    if not cp_path.is_file():
        return 0
    checkpoint = json.loads(cp_path.read_text(encoding="utf-8"))
    raw = list(checkpoint.get("completed_segments") or [])
    kept, dropped = _filter_completed_segments(raw, chapters)
    if not dropped:
        return 0
    checkpoint["completed_segments"] = kept
    checkpoint["hydrate_trimmed_at"] = _utc_now()
    checkpoint["hydrate_trimmed_count"] = len(dropped)
    atomic_write_json(cp_path, checkpoint)
    return len(dropped)


def apply_hydrate(plan: dict, *, repo_root: Path, run_id: str, chapter_offset: int) -> None:
    run_root = repo_root / "workspace" / "runs" / run_id
    chapters = plan["chapters"]
    meta = plan["meta"]
    atomic_write_json(run_root / "run_metadata.json", meta)
    write_run_progress(
        run_root,
        run_id=run_id,
        phase="draft",
        stage="draft_stage_b_50ch",
        chapter_offset=chapter_offset,
        status=plan["progress_status"],
        total_segments=plan["total_segments"],
        completed_segments=plan["translated_segments"],
    )
    export_segments_doc(chapters, run_root / "segments.json")
    _trim_checkpoint_completed_segments(repo_root, run_id=run_id, chapters=chapters)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Hydrate run artifacts from checkpoint + draft markdown (dry-run by default)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--run-id", required=True, help="Run id matching workspace/checkpoints/<run_id>.json")
    parser.add_argument("--input-dir", type=Path, default=REPO_ROOT / "input_jp")
    parser.add_argument("--chapter-offset", type=int, default=None, help="Auto-detect from checkpoint when omitted")
    parser.add_argument("--limit-chapters", type=int, default=50, help="Chapter batch size (Stage B default 50)")
    parser.add_argument("--apply", action="store_true", help="Write artifacts (default is dry-run plan only)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    apply_local_env(REPO_ROOT)
    input_dir = args.input_dir if args.input_dir.is_absolute() else (REPO_ROOT / args.input_dir)

    try:
        plan = plan_hydrate(
            repo_root=REPO_ROOT,
            run_id=args.run_id.strip(),
            input_dir=input_dir,
            chapter_offset=args.chapter_offset,
            limit_chapters=args.limit_chapters,
        )
    except (FileNotFoundError, ValueError) as exc:
        print(f"hydrate_checkpoint: {exc}", file=sys.stderr)
        return 2

    if args.apply:
        apply_hydrate(
            plan,
            repo_root=REPO_ROOT,
            run_id=args.run_id.strip(),
            chapter_offset=int(plan["chapter_offset"]),
        )
        plan = {k: v for k, v in plan.items() if k != "chapters"}
        plan["applied"] = True

    output = {k: v for k, v in plan.items() if k != "chapters"}
    if args.json:
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        print(
            f"hydrate_checkpoint: run_id={output['run_id']} "
            f"offset={output['chapter_offset']} "
            f"segments={output['translated_segments']}/{output['total_segments']} "
            f"checkpoint_done={output['completed_checkpoint_segments']} "
            f"{'APPLIED' if args.apply else 'DRY-RUN'}"
        )
        if not args.apply:
            print("  下一步: 确认后加 --apply，再运行 scripts/resume_production.py 或 translate.py --run-id ...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
