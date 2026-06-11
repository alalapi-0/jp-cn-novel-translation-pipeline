#!/usr/bin/env python3
"""Build the term usage index over draft runs (FS-015).

Scans workspace/runs + workspace/archived_runs segments.json files (streaming,
chapter by chapter), counts per-term source/target/co/divergent hits, marks
divergent_translation (同源多译) and shared_target (同译多源) conflicts.

Incremental: per-file fingerprint buckets reused when unchanged.
Output: workspace/indexes/term_usage_index.json (gitignored).
Stdout: statistics only - never source/draft text.

Usage:
    python3 scripts/build_term_usage_index.py --chapter-range 1-50 --json
    python3 scripts/build_term_usage_index.py --rebuild
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from glossary import GlossaryStore  # noqa: E402
from glossary.usage_index import build_usage_index  # noqa: E402

DEFAULT_GLOSSARY = REPO_ROOT / "workspace" / "configs" / "glossary.yaml"
DEFAULT_OUTPUT = REPO_ROOT / "workspace" / "indexes" / "term_usage_index.json"
DEFAULT_RUN_DIRS = (
    REPO_ROOT / "workspace" / "runs",
    REPO_ROOT / "workspace" / "archived_runs",
)


def parse_chapter_range(raw: str | None) -> tuple[int | None, int | None]:
    if not raw:
        return None, None
    parts = raw.split("-", 1)
    try:
        low = int(parts[0])
        high = int(parts[1]) if len(parts) > 1 else low
    except ValueError as exc:
        raise SystemExit(f"invalid --chapter-range: {raw!r} (expected e.g. 1-50)") from exc
    return low, high


def find_segments_files(run_dirs: list[Path]) -> list[Path]:
    files: list[Path] = []
    for run_dir in run_dirs:
        if run_dir.is_dir():
            files.extend(sorted(run_dir.glob("run_*/segments.json")))
    return files


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build term usage index (stats only on stdout)")
    parser.add_argument("--glossary", type=Path, default=DEFAULT_GLOSSARY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--runs-dir",
        type=Path,
        action="append",
        default=None,
        help="Run directory containing run_*/segments.json (repeatable; default workspace/runs + archived_runs)",
    )
    parser.add_argument("--chapter-range", default=None, help="e.g. 1-50 (default: all chapters)")
    parser.add_argument("--rebuild", action="store_true", help="Ignore previous index (no incremental reuse)")
    parser.add_argument("--json", action="store_true", help="Print machine-readable summary")
    args = parser.parse_args(argv)

    glossary_path = args.glossary if args.glossary.is_absolute() else REPO_ROOT / args.glossary
    output_path = args.output if args.output.is_absolute() else REPO_ROOT / args.output
    run_dirs = [
        (d if d.is_absolute() else REPO_ROOT / d) for d in (args.runs_dir or [])
    ] or list(DEFAULT_RUN_DIRS)

    if not glossary_path.is_file():
        print(f"build_term_usage_index: FAIL glossary not found: {glossary_path}")
        return 2

    chapter_min, chapter_max = parse_chapter_range(args.chapter_range)
    terms = GlossaryStore(glossary_path).entries()
    segments_files = find_segments_files(run_dirs)

    previous = None
    if not args.rebuild and output_path.is_file():
        try:
            previous = json.loads(output_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            previous = None  # corrupt previous index -> full rebuild

    index = build_usage_index(
        terms,
        segments_files,
        previous_index=previous,
        chapter_min=chapter_min,
        chapter_max=chapter_max,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    try:
        display_output = str(output_path.relative_to(REPO_ROOT))
    except ValueError:
        display_output = str(output_path)
    summary = {
        "status": "PASS",
        "output": display_output,
        **index["stats"],
    }
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        s = index["stats"]
        print(
            f"build_term_usage_index: PASS files={s['files_total']} "
            f"(scanned={s['files_scanned']} reused={s['files_reused']}) "
            f"terms={s['terms_indexed']} hits={s['terms_with_hits']} "
            f"chapters={s['chapters_covered']} conflicts={s['conflict_count']} "
            f"-> {summary['output']}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
