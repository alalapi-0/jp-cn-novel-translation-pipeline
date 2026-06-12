#!/usr/bin/env python3
"""Build the chapter manifest (FS-031, Level 0).

Metadata-only index: chapter_id, title, segment counts, draft status,
source run, content hash. Never writes source/draft body text.

Output: workspace/manifests/chapter_manifest.json (gitignored).

Usage:
    python3 scripts/build_chapter_manifest.py --json
    python3 scripts/build_chapter_manifest.py --rebuild --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from consistency.manifest import build_chapter_manifest, manifest_summary  # noqa: E402

DEFAULT_OUTPUT = REPO_ROOT / "workspace" / "manifests" / "chapter_manifest.json"
DEFAULT_RUN_DIRS = (
    REPO_ROOT / "workspace" / "runs",
    REPO_ROOT / "workspace" / "archived_runs",
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build chapter manifest (stats only on stdout)")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=REPO_ROOT,
        help="Repository root (default: script parent directory)",
    )
    parser.add_argument(
        "--runs-dir",
        type=Path,
        action="append",
        default=None,
        help="Run directory containing run_*/segments.json (repeatable)",
    )
    parser.add_argument("--rebuild", action="store_true", help="Ignore previous manifest (no incremental reuse)")
    parser.add_argument("--json", action="store_true", help="Print machine-readable summary")
    args = parser.parse_args(argv)

    repo_root = args.repo_root if args.repo_root.is_absolute() else REPO_ROOT / args.repo_root
    output_path = args.output if args.output.is_absolute() else repo_root / args.output
    run_dirs = [
        (d if d.is_absolute() else repo_root / d) for d in (args.runs_dir or [])
    ] or [repo_root / "workspace" / "runs", repo_root / "workspace" / "archived_runs"]

    previous = None
    if not args.rebuild and output_path.is_file():
        try:
            previous = json.loads(output_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            previous = None

    manifest = build_chapter_manifest(repo_root, previous_index=previous, run_dirs=run_dirs)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    try:
        display_output = str(output_path.relative_to(repo_root))
    except ValueError:
        display_output = str(output_path)

    summary = {"output": display_output, **manifest_summary(manifest)}
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(
            f"build_chapter_manifest: {summary['status']} "
            f"chapters={summary['chapters_indexed']}/{summary['total_expected_chapters']} "
            f"scanned={summary['segment_files_scanned']} reused={summary['segment_files_reused']} "
            f"-> {display_output}"
        )
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
