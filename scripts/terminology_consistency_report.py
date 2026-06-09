#!/usr/bin/env python3
"""Dry-run glossary term usage diff report (fixture-based)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_GLOSSARY = REPO_ROOT / "data" / "examples" / "review_glossary.fixture.json"
DEFAULT_SEGMENTS = REPO_ROOT / "data" / "examples" / "review_segments.fixture.json"


def build_report(glossary: dict[str, Any], segments: dict[str, Any]) -> dict[str, Any]:
    terms = {t.get("term_id"): t for t in glossary.get("terms") or [] if isinstance(t, dict)}
    hits: dict[str, int] = {tid: 0 for tid in terms}
    mismatches: list[dict[str, str]] = []
    for para in segments.get("paragraphs") or []:
        for seg in (para.get("segments") or []) if isinstance(para, dict) else []:
            target = str(seg.get("target_text") or "")
            for tid, term in terms.items():
                src = str(term.get("source") or term.get("source_term") or "")
                expected = str(term.get("canonical_zh") or term.get("target") or term.get("target_term") or "")
                if src and src in target:
                    hits[tid] = hits.get(tid, 0) + 1
                    if expected and expected not in target:
                        mismatches.append(
                            {"term_id": tid, "segment_id": str(seg.get("segment_id")), "expected": expected}
                        )
    return {
        "project_id": segments.get("project_id"),
        "term_hits": hits,
        "mismatch_count": len(mismatches),
        "mismatches": mismatches[:20],
        "mode": "dry_run_fixture",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Terminology consistency report")
    parser.add_argument("--glossary", type=Path, default=DEFAULT_GLOSSARY)
    parser.add_argument("--segments", type=Path, default=DEFAULT_SEGMENTS)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    g_path = args.glossary if args.glossary.is_absolute() else REPO_ROOT / args.glossary
    s_path = args.segments if args.segments.is_absolute() else REPO_ROOT / args.segments
    report = build_report(
        json.loads(g_path.read_text(encoding="utf-8")),
        json.loads(s_path.read_text(encoding="utf-8")),
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"terminology_report: mismatches={report['mismatch_count']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
