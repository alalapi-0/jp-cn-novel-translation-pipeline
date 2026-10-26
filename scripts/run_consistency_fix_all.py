#!/usr/bin/env python3
"""Read-only work-policy preview across legacy run files.

Explicit version/binding and chapter selection are required. Existing mtime
discovery is historical and cannot authorize production canonical switching.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT/'src'))
from consistency.work_rules import add_work_rule_arguments, policy_from_arguments, selected_chapter_range, selected_target_paths


def discover_canonical_files() -> list[Path]:
    raise ValueError('explicit accepted revision required; ambient canonical discovery disabled')


def discover_all_run_files() -> list[Path]:
    files: set[Path] = set()
    for base in ("workspace/runs", "workspace/archived_runs"):
        root = REPO_ROOT / base
        if root.is_dir():
            files.update(path for path in root.rglob("segments.json") if path.is_file())
    return sorted(files)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--diff-log", type=Path, default=None)
    parser.add_argument('--chapters', type=int, nargs=2, default=None)
    add_work_rule_arguments(parser)
    parser.add_argument(
        "--scope",
        choices=("canonical", "all-runs"),
        default="canonical",
        help="legacy compatibility option; only explicit manifest files are read",
    )
    parser.add_argument(
        "--update-all-target-fields",
        action="store_true",
        help="include historical target fields in read-only preview",
    )
    args = parser.parse_args()
    if not args.dry_run:
        parser.error('legacy direct target writes disabled; safe canonical apply is P2.R03')
    try:
        policy = policy_from_arguments(args, REPO_ROOT)
        start, end = selected_chapter_range(args, policy)
        if policy is None:
            raise ValueError('explicit version-pinned work policy required for legacy preview')
    except ValueError as error:
        parser.error(str(error))

    target_files = selected_target_paths(REPO_ROOT, policy)
    print(f"selected manifest files: {len(target_files)}", file=sys.stderr)

    total_changed = 0
    total_segments = 0
    total_rule_hits: dict[str, int] = {}
    total_skipped_hits: dict[str, int] = {}
    per_file = []
    diff_logs = []
    failed_files = 0
    for f in sorted(target_files):
        tmp_diff = None
        if args.diff_log:
            tmp_diff = args.diff_log.with_name(f"{args.diff_log.stem}.{len(diff_logs):03d}.json")
        cmd = [
            sys.executable,
            str(REPO_ROOT / "scripts" / "fix_terminology_consistency.py"),
            "--segments-file", str(f),
            "--chapters", str(start), str(end),
            '--work-rules', str(args.work_rules), '--work-rules-sha256', policy.sha256,
            '--work-id', policy.work_id, '--source-revision', policy.source_revision,
            '--language-direction', policy.language_direction,
        ]
        if tmp_diff:
            cmd.extend(["--diff-log", str(tmp_diff)])
        if args.update_all_target_fields:
            cmd.append("--update-all-target-fields")
        if args.dry_run:
            cmd.append("--dry-run")
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO_ROOT)
        if result.returncode != 0:
            print(f"FAILED: {f}\n{result.stderr}", file=sys.stderr)
            failed_files += 1
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
            "files_processed": len(target_files),
            "total_segments": total_segments,
            "total_changed_segments": total_changed,
            "rule_hits": dict(sorted(total_rule_hits.items(), key=lambda kv: -kv[1])),
            "skipped_ambiguous_hits": dict(sorted(total_skipped_hits.items(), key=lambda kv: -kv[1])),
            "scope": "selected_manifest",
            "target_field_mode": "historical_preview_all_fields" if args.update_all_target_fields else "draft_preview",
            "dry_run": args.dry_run,
        }
        args.diff_log.write_text(json.dumps(combined, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({
        'status': 'failed' if failed_files else 'preview',
        'failed_files': failed_files,
        'work_rules_sha256': policy.sha256,
        "files_processed": len(target_files),
        "total_segments": total_segments,
        "total_changed_segments": total_changed,
        "files_with_changes": per_file,
        "rule_hits": dict(sorted(total_rule_hits.items(), key=lambda kv: -kv[1])),
        "skipped_ambiguous_hits": dict(sorted(total_skipped_hits.items(), key=lambda kv: -kv[1])),
        "scope": "selected_manifest",
        "target_field_mode": "historical_preview_all_fields" if args.update_all_target_fields else "draft_preview",
        "dry_run": args.dry_run,
    }, ensure_ascii=False, indent=2))
    return 2 if failed_files else 0


if __name__ == "__main__":
    raise SystemExit(main())
