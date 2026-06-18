#!/usr/bin/env python3
"""Run fix_terminology_consistency.py across every canonical draft_stage_b
segments.json file covering the whole book (ch1-612), resolving duplicate
chapter-range coverage by latest mtime.

Usage:
    python3 scripts/run_consistency_fix_all.py --dry-run
    python3 scripts/run_consistency_fix_all.py            # writes changes
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def discover_canonical_files() -> list[Path]:
    files = []
    for base in ("workspace/runs", "workspace/archived_runs"):
        files += glob.glob(str(REPO_ROOT / base / "run_*_draft_stage_b_50ch" / "segments.json"))

    ranges: dict[tuple[int, int], list[tuple[str, float]]] = {}
    for f in files:
        try:
            doc = json.loads(Path(f).read_text(encoding="utf-8"))
        except Exception:
            continue
        nums = []
        for ch in doc.get("chapters", []):
            try:
                nums.append(int(ch["chapter_id"].split("-")[-1]))
            except Exception:
                pass
        if not nums:
            continue
        key = (min(nums), max(nums))
        ranges.setdefault(key, []).append((f, os.path.getmtime(f)))

    chosen = []
    for key, candidates in ranges.items():
        candidates.sort(key=lambda c: c[1], reverse=True)
        chosen.append(Path(candidates[0][0]))
    return chosen


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--diff-log", type=Path, default=None)
    args = parser.parse_args()

    canonical_files = discover_canonical_files()
    print(f"canonical files: {len(canonical_files)}", file=sys.stderr)

    total_changed = 0
    total_segments = 0
    total_rule_hits: dict[str, int] = {}
    total_skipped_hits: dict[str, int] = {}
    per_file = []
    diff_logs = []
    for f in sorted(canonical_files):
        tmp_diff = None
        if args.diff_log:
            tmp_diff = args.diff_log.with_name(f"{args.diff_log.stem}.{len(diff_logs):03d}.json")
        cmd = [
            sys.executable,
            str(REPO_ROOT / "scripts" / "fix_terminology_consistency.py"),
            "--segments-file", str(f),
            "--chapters", "1", "612",
        ]
        if tmp_diff:
            cmd.extend(["--diff-log", str(tmp_diff)])
        if args.dry_run:
            cmd.append("--dry-run")
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO_ROOT)
        if result.returncode != 0:
            print(f"FAILED: {f}\n{result.stderr}", file=sys.stderr)
            continue
        summary = json.loads(result.stdout)
        total_changed += summary["changed_segments"]
        total_segments += summary["total_segments"]
        for variant, count in summary.get("rule_hits", {}).items():
            total_rule_hits[variant] = total_rule_hits.get(variant, 0) + int(count)
        for variant, count in summary.get("skipped_ambiguous_hits", {}).items():
            total_skipped_hits[variant] = total_skipped_hits.get(variant, 0) + int(count)
        if summary["changed_segments"]:
            per_file.append({"file": str(f.relative_to(REPO_ROOT)), "changed": summary["changed_segments"]})
        if tmp_diff and tmp_diff.is_file():
            diff_logs.append(tmp_diff)

    if args.diff_log:
        combined = {"summary": {}, "diffs": []}
        for tmp in diff_logs:
            doc = json.loads(tmp.read_text(encoding="utf-8"))
            combined["diffs"].extend(doc.get("diffs", []))
            tmp.unlink()
        args.diff_log.parent.mkdir(parents=True, exist_ok=True)
        combined["summary"] = {
            "files_processed": len(canonical_files),
            "total_segments": total_segments,
            "total_changed_segments": total_changed,
            "rule_hits": dict(sorted(total_rule_hits.items(), key=lambda kv: -kv[1])),
            "skipped_ambiguous_hits": dict(sorted(total_skipped_hits.items(), key=lambda kv: -kv[1])),
            "dry_run": args.dry_run,
        }
        args.diff_log.write_text(json.dumps(combined, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({
        "files_processed": len(canonical_files),
        "total_segments": total_segments,
        "total_changed_segments": total_changed,
        "files_with_changes": per_file,
        "rule_hits": dict(sorted(total_rule_hits.items(), key=lambda kv: -kv[1])),
        "skipped_ambiguous_hits": dict(sorted(total_skipped_hits.items(), key=lambda kv: -kv[1])),
        "dry_run": args.dry_run,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
