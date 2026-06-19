#!/usr/bin/env python3
"""Check that the final translation handoff has exactly one canonical text file."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def check_singleton(output_root: Path) -> dict:
    manifest_path = output_root / "final_export_manifest.json"
    findings: list[dict] = []
    manifest: dict = {}
    if not manifest_path.is_file():
        findings.append({"severity": "blocked", "code": "missing_manifest", "path": _rel(manifest_path)})
    else:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    canonical_rel = manifest.get("canonical_final_translation") or manifest.get("full_volume_cn")
    canonical_path = REPO_ROOT / canonical_rel if canonical_rel else output_root / "translated" / "full_volume_cn.md"
    if not canonical_path.is_file():
        findings.append({"severity": "blocked", "code": "missing_canonical_translation", "path": _rel(canonical_path)})

    translated_dir = output_root / "translated"
    bilingual_dir = output_root / "bilingual"
    translated_md = sorted(path for path in translated_dir.glob("*.md") if path.name != ".gitkeep")
    bilingual_md = sorted(path for path in bilingual_dir.glob("*.md") if path.name != ".gitkeep")

    extra_translated = [path for path in translated_md if path.resolve() != canonical_path.resolve()]
    if extra_translated:
        findings.append(
            {
                "severity": "blocked",
                "code": "extra_final_translation_copies",
                "count": len(extra_translated),
                "samples": [_rel(path) for path in extra_translated[:10]],
            }
        )

    chapter_files = sorted(translated_dir.glob("chapter_*_cn.md"))
    if chapter_files:
        findings.append(
            {
                "severity": "blocked",
                "code": "per_chapter_final_copies_present",
                "count": len(chapter_files),
                "samples": [_rel(path) for path in chapter_files[:10]],
            }
        )

    old_workbench = sorted(bilingual_dir.glob("workbench_*_bilingual.md"))
    if old_workbench:
        findings.append(
            {
                "severity": "blocked",
                "code": "old_workbench_bilingual_exports_present",
                "count": len(old_workbench),
                "samples": [_rel(path) for path in old_workbench[:10]],
            }
        )

    if bilingual_md and not manifest.get("include_bilingual"):
        findings.append(
            {
                "severity": "blocked",
                "code": "bilingual_final_copies_present_without_manifest_flag",
                "count": len(bilingual_md),
                "samples": [_rel(path) for path in bilingual_md[:10]],
            }
        )

    manifest_count = manifest.get("canonical_final_translation_count")
    if manifest_count not in (None, 1):
        findings.append(
            {
                "severity": "blocked",
                "code": "manifest_canonical_count_not_one",
                "count": manifest_count,
            }
        )

    status = "passed" if not findings else "blocked"
    return {
        "schema": "final_translation_singleton_check_v1",
        "status": status,
        "output_root": _rel(output_root),
        "canonical_final_translation": _rel(canonical_path),
        "translated_markdown_files": [_rel(path) for path in translated_md],
        "bilingual_markdown_file_count": len(bilingual_md),
        "findings": findings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Check singleton final translation export")
    parser.add_argument("--output-root", type=Path, default=REPO_ROOT / "output_cn")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    output_root = args.output_root if args.output_root.is_absolute() else REPO_ROOT / args.output_root
    report = check_singleton(output_root)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"final_translation_singleton: {report['status']} {report['canonical_final_translation']}")
        for finding in report["findings"]:
            print(f"  - {finding['code']}: {finding.get('count', finding.get('path', ''))}")
    return 0 if report["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
