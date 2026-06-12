#!/usr/bin/env python3
"""Build the entity index over draft runs (FS-033).

Scans glossary entity categories (person / place / org / skill / item / title),
records source→target mapping frequencies, marks divergent_translation /
shared_target conflicts, and ranks high-frequency unlisted source candidates.

Incremental: per-file fingerprint buckets reused when unchanged.
Output: workspace/indexes/entity_index.json (gitignored).
Stdout: statistics only — never source/draft text.

Usage:
    python3 scripts/build_entity_index.py --chapter-range 1-50 --json
    python3 scripts/build_entity_index.py --rebuild --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from consistency.entity_index import build_entity_index, index_summary  # noqa: E402
from consistency.manifest import find_segments_files  # noqa: E402
from glossary import GlossaryStore  # noqa: E402

DEFAULT_GLOSSARY = REPO_ROOT / "workspace" / "configs" / "glossary.yaml"
DEFAULT_OUTPUT = REPO_ROOT / "workspace" / "indexes" / "entity_index.json"
def glob_segments_files(run_dirs: list[Path]) -> list[Path]:
    """Direct glob for explicit --runs-dir (tests / ad-hoc scans)."""
    files: list[Path] = []
    for run_dir in run_dirs:
        if run_dir.is_dir():
            files.extend(sorted(run_dir.glob("run_*/segments.json")))
    return files


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build entity index (stats only on stdout)")
    parser.add_argument("--glossary", type=Path, default=DEFAULT_GLOSSARY)
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
    parser.add_argument("--chapter-range", default=None, help="e.g. 1-50 (default: all chapters)")
    parser.add_argument("--top-n-unlisted", type=int, default=50, help="Top-N unlisted high-freq terms")
    parser.add_argument("--rebuild", action="store_true", help="Ignore previous index (no incremental reuse)")
    parser.add_argument("--json", action="store_true", help="Print machine-readable summary")
    args = parser.parse_args(argv)

    repo_root = args.repo_root if args.repo_root.is_absolute() else REPO_ROOT / args.repo_root
    glossary_path = args.glossary if args.glossary.is_absolute() else repo_root / args.glossary
    output_path = args.output if args.output.is_absolute() else repo_root / args.output
    explicit_run_dirs = args.runs_dir is not None
    if explicit_run_dirs:
        run_dirs = [
            (d if d.is_absolute() else repo_root / d) for d in args.runs_dir
        ]
    else:
        run_dirs = [
            repo_root / "workspace" / "runs",
            repo_root / "workspace" / "archived_runs",
        ]

    if not glossary_path.is_file():
        print(f"build_entity_index: FAIL glossary not found: {glossary_path}")
        return 2

    chapter_min, chapter_max = parse_chapter_range(args.chapter_range)
    store = GlossaryStore(glossary_path)
    terms = store.entries()
    if explicit_run_dirs:
        segments_files = glob_segments_files(run_dirs)
    else:
        segments_files = find_segments_files(repo_root, run_dirs)

    previous = None
    if not args.rebuild and output_path.is_file():
        try:
            previous = json.loads(output_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            previous = None

    index = build_entity_index(
        terms,
        segments_files,
        previous_index=previous,
        chapter_min=chapter_min,
        chapter_max=chapter_max,
        top_n_unlisted=args.top_n_unlisted,
        all_terms=terms,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    try:
        display_output = str(output_path.relative_to(repo_root))
    except ValueError:
        display_output = str(output_path)

    summary = {"output": display_output, **index_summary(index)}
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(
            f"build_entity_index: {summary['status']} "
            f"entities={summary['entities_indexed']} hits={summary['entities_with_hits']} "
            f"chapters={summary['chapters_covered']} conflicts={summary['conflict_count']} "
            f"unlisted_top={summary['unlisted_high_freq_count']} "
            f"scanned={summary['files_scanned']} reused={summary['files_reused']} "
            f"-> {display_output}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
