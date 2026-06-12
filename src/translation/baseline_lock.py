"""Baseline lock: snapshot draft runs into draft_full_baseline/ (FS-038)."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from consistency.manifest import chapter_number_from_id, find_segments_files
from translation.baseline_guard import (
    BASELINE_DIR_NAME,
    BASELINE_METADATA_NAME,
    baseline_dir,
    baseline_metadata_path,
    baseline_write_override,
    apply_baseline_readonly,
)
from translation.chapter_parser import count_source_chapters
from translation.run_progress import safe_load_json

SCHEMA_VERSION = 1
_CHAPTER_NUM_RE = re.compile(r"(\d+)")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_phase_eval(script_name: str, func_name: str) -> Any:
    repo_root = Path(__file__).resolve().parent.parent.parent
    spec = importlib.util.spec_from_file_location(script_name, repo_root / "scripts" / f"{script_name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return getattr(mod, func_name)


def check_prerequisites(repo_root: Path) -> dict[str, Any]:
    phase_a = _load_phase_eval("phase_a_completion_check", "evaluate")(repo_root)
    phase_b = _load_phase_eval("phase_b_completion_check", "evaluate")(repo_root)
    return {
        "phase_a_pass": bool(phase_a.get("overall_pass")),
        "phase_b_pass": bool(phase_b.get("overall_pass")),
        "phase_a_failed": phase_a.get("failed_criteria") or [],
        "phase_b_failed": phase_b.get("failed_criteria") or [],
        "total_source_chapters": int(phase_a.get("total_source_chapters") or count_source_chapters(repo_root)),
    }


def _chapter_num(chapter_id: str) -> int:
    m = _CHAPTER_NUM_RE.search(chapter_id or "")
    return int(m.group(1)) if m else 0


def collect_merged_chapters(repo_root: Path) -> tuple[dict[int, dict[str, Any]], list[dict[str, Any]]]:
    """Merge completed draft runs; later runs override earlier for same chapter number."""
    by_number: dict[int, dict[str, Any]] = {}
    run_records: dict[str, dict[str, Any]] = {}

    for seg_path in find_segments_files(repo_root):
        run_id = seg_path.parent.name
        doc = json.loads(seg_path.read_text(encoding="utf-8"))
        meta = safe_load_json(seg_path.parent / "run_metadata.json") or {}
        offset = int(meta.get("chapter_offset") or 0)
        rel_seg = str(seg_path.relative_to(repo_root))
        record = run_records.setdefault(
            run_id,
            {
                "run_id": run_id,
                "chapter_offset": offset,
                "segments_file": rel_seg,
                "run_metadata": str((seg_path.parent / "run_metadata.json").relative_to(repo_root)),
                "chapters_contributed": [],
            },
        )
        for ch in doc.get("chapters") or []:
            cid = str(ch.get("chapter_id") or "")
            num = chapter_number_from_id(cid) or _chapter_num(cid)
            if num <= 0:
                continue
            by_number[num] = {
                "chapter_id": cid,
                "chapter_label": str(ch.get("chapter_label") or cid),
                "source_path": str(ch.get("source_path") or ""),
                "segments": list(ch.get("segments") or []),
                "source_run_id": run_id,
            }
            if num not in record["chapters_contributed"]:
                record["chapters_contributed"].append(num)

    for rec in run_records.values():
        rec["chapters_contributed"] = sorted(rec["chapters_contributed"])
    return by_number, sorted(run_records.values(), key=lambda r: (r["chapter_offset"], r["run_id"]))


def _render_chapter_markdown(chapter: dict[str, Any]) -> str:
    lines = [f"# {chapter['chapter_label']}", ""]
    for seg in chapter.get("segments") or []:
        sid = str(seg.get("segment_id") or "")
        draft = (seg.get("draft_text") or "").strip()
        if sid:
            lines.append(f"<!-- {sid} -->")
        lines.append(draft)
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def lock_baseline(
    repo_root: Path,
    *,
    dry_run: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    prereq = check_prerequisites(repo_root)
    if not prereq["phase_a_pass"] or not prereq["phase_b_pass"]:
        raise RuntimeError(
            "Phase A/B prerequisites not met: "
            f"phase_a_pass={prereq['phase_a_pass']} phase_b_pass={prereq['phase_b_pass']} "
            f"failed_a={prereq['phase_a_failed']} failed_b={prereq['phase_b_failed']}"
        )

    if baseline_metadata_path(repo_root).is_file() and baseline_dir(repo_root).is_dir() and not force:
        existing = safe_load_json(baseline_metadata_path(repo_root)) or {}
        if existing.get("locked"):
            return {
                "status": "already_locked",
                "dry_run": dry_run,
                "metadata_path": str(baseline_metadata_path(repo_root).relative_to(repo_root)),
                "chapter_count": int(existing.get("chapter_count") or 0),
                "aggregate_hash": existing.get("aggregate_hash"),
                "prerequisites": prereq,
            }

    chapters_by_num, source_runs = collect_merged_chapters(repo_root)
    total_expected = prereq["total_source_chapters"]
    missing = sorted(n for n in range(1, total_expected + 1) if n not in chapters_by_num)
    if missing:
        raise RuntimeError(f"cannot lock baseline: missing draft chapters {missing[:10]}{'...' if len(missing) > 10 else ''}")

    consistency_ref = "workspace/consistency_audit/draft_consistency_report.json"
    if not (repo_root / consistency_ref).is_file():
        consistency_ref = ""

    out_dir = baseline_dir(repo_root)
    meta_path = baseline_metadata_path(repo_root)
    chapter_entries: list[dict[str, Any]] = []
    hash_parts: list[str] = []

    planned_files: list[tuple[Path, str]] = []
    for num in sorted(chapters_by_num):
        ch = chapters_by_num[num]
        rel_name = f"chapter_{num:03d}_draft_zh.md"
        rel_path = f"{BASELINE_DIR_NAME}/{rel_name}"
        body = _render_chapter_markdown(ch)
        digest = _sha256_text(body)
        hash_parts.append(f"{num}:{digest}")
        chapter_entries.append(
            {
                "chapter_number": num,
                "chapter_id": ch["chapter_id"],
                "chapter_label": ch["chapter_label"],
                "source_path": ch["source_path"],
                "source_run_id": ch["source_run_id"],
                "file": rel_path,
                "sha256": digest,
                "segment_count": len(ch.get("segments") or []),
            }
        )
        planned_files.append((out_dir / rel_name, body))

    aggregate_hash = hashlib.sha256("\n".join(hash_parts).encode("utf-8")).hexdigest()

    metadata: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "locked_at": _utc_now(),
        "round": "FS-038",
        "phase": "baseline_lock",
        "locked": not dry_run,
        "read_only": not dry_run,
        "dry_run": dry_run,
        "prerequisites": prereq,
        "total_chapters": total_expected,
        "chapter_count": len(chapter_entries),
        "aggregate_hash": aggregate_hash,
        "consistency_report_ref": consistency_ref,
        "source_runs": source_runs,
        "chapters": chapter_entries,
    }

    result = {
        "status": "dry_run" if dry_run else "locked",
        "dry_run": dry_run,
        "metadata_path": str(meta_path.relative_to(repo_root)),
        "baseline_dir": str(out_dir.relative_to(repo_root)),
        "chapter_count": len(chapter_entries),
        "aggregate_hash": aggregate_hash,
        "hash_summary": {
            "aggregate_sha256": aggregate_hash,
            "per_chapter_sha256_prefix": {str(e["chapter_number"]): e["sha256"][:16] for e in chapter_entries[:5]},
            "sample_chapters": [e["chapter_number"] for e in chapter_entries[:5]],
        },
        "source_run_count": len(source_runs),
        "prerequisites": prereq,
    }

    if dry_run:
        return result

    with baseline_write_override():
        out_dir.mkdir(parents=True, exist_ok=True)
        for path, body in planned_files:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body, encoding="utf-8")
        meta_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    readonly_files = apply_baseline_readonly(repo_root)
    metadata["read_only_files_touched"] = readonly_files
    result["read_only_files_touched"] = readonly_files
    return result
