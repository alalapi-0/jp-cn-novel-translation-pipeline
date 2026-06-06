"""Export status and manifest-based mock export for Workbench UI."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
VALID_MANIFEST_EXPORT_MODES = {"approved", "draft"}


def _count_md_files(directory: Path) -> int:
    if not directory.is_dir():
        return 0
    return sum(1 for p in directory.glob("*.md") if p.is_file())


def export_status(repo_root: Path) -> dict[str, Any]:
    zh_dir = repo_root / "output_cn" / "translated"
    bi_dir = repo_root / "output_cn" / "bilingual"
    zh_files = sorted(p.name for p in zh_dir.glob("*.md") if p.is_file()) if zh_dir.is_dir() else []
    bi_files = sorted(p.name for p in bi_dir.glob("*.md") if p.is_file()) if bi_dir.is_dir() else []
    runs_root = repo_root / "workspace" / "runs"
    run_count = sum(1 for _ in runs_root.glob("run_*_draft_stage_b_50ch/run_metadata.json")) if runs_root.is_dir() else 0
    return {
        "translated_dir": str(zh_dir.relative_to(repo_root)),
        "bilingual_dir": str(bi_dir.relative_to(repo_root)),
        "translated_count": len(zh_files),
        "bilingual_count": len(bi_files),
        "translated_files": zh_files[:50],
        "bilingual_files": bi_files[:50],
        "draft_runs_available": run_count,
        "checked_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }


def export_from_manifest(
    repo_root: Path,
    *,
    project_id: str,
    overwrite: bool = True,
    status_mode: str = "approved",
) -> dict[str, Any]:
    from workbench.project_registry import get_project_manifest
    from workbench.review_state import get_project_review_state

    manifest = get_project_manifest(repo_root, project_id)
    if manifest is None:
        raise KeyError(f"unknown project_id: {project_id}")
    mode = str(status_mode or "approved").strip().lower()
    if mode not in VALID_MANIFEST_EXPORT_MODES:
        raise ValueError("status_mode must be 'approved' or 'draft'")
    review_state = get_project_review_state(repo_root, project_id)
    review_segments = review_state.get("segments") if isinstance(review_state, dict) else {}
    if not isinstance(review_segments, dict):
        review_segments = {}

    zh_dir = repo_root / "output_cn" / "translated"
    bi_dir = repo_root / "output_cn" / "bilingual"
    zh_dir.mkdir(parents=True, exist_ok=True)
    bi_dir.mkdir(parents=True, exist_ok=True)

    stem = f"workbench_{project_id}"
    zh_path = zh_dir / f"{stem}_cn.md"
    bi_path = bi_dir / f"{stem}_bilingual.md"
    if not overwrite and zh_path.is_file() and bi_path.is_file():
        return {
            "source": "manifest",
            "project_id": project_id,
            "skipped": True,
            "message": "output files already exist; pass overwrite=true to replace",
            "translated_path": str(zh_path.relative_to(repo_root)),
            "bilingual_path": str(bi_path.relative_to(repo_root)),
        }

    zh_lines = [f"# {manifest.name}", ""]
    bi_lines = [f"# {manifest.name}", ""]
    status_summary: dict[str, int] = {}
    skipped_status_counts: dict[str, int] = {}
    segments_exported = 0
    for idx, seg in enumerate(manifest.segments, start=1):
        seg_id = str(seg.get("id") or seg.get("segment_id") or "")
        state_entry = review_segments.get(seg_id, {}) if seg_id else {}
        merged_status = str(
            (state_entry.get("status") if isinstance(state_entry, dict) else None)
            or seg.get("status")
            or "pending"
        ).strip().lower()
        if not merged_status:
            merged_status = "pending"
        status_summary[merged_status] = int(status_summary.get(merged_status) or 0) + 1
        if mode == "approved" and merged_status != "approved":
            skipped_status_counts[merged_status] = int(skipped_status_counts.get(merged_status) or 0) + 1
            continue
        source = str(seg.get("source") or seg.get("source_text") or "").strip()
        draft = str(seg.get("draft") or seg.get("draft_text") or seg.get("target_text") or "").strip()
        if not source and not draft:
            continue
        segments_exported += 1
        zh_lines.append(draft)
        zh_lines.append("")
        bi_lines.extend(
            [
                f"## 段落 {idx}",
                "**原文：**",
                source,
                "",
                "**译文：**",
                draft,
                "",
                f"_status: {merged_status}_",
                "",
                "---",
                "",
            ]
        )

    if mode == "approved" and segments_exported <= 0:
        raise ValueError(
            "no approved segments available for export; approve at least one segment or use status_mode='draft'"
        )

    zh_path.write_text("\n".join(zh_lines).strip() + "\n", encoding="utf-8")
    bi_path.write_text("\n".join(bi_lines).strip() + "\n", encoding="utf-8")
    return {
        "source": "manifest",
        "project_id": project_id,
        "status_mode": mode,
        "segments_total": len(manifest.segments),
        "segments_exported": segments_exported,
        "segments_skipped_status": skipped_status_counts,
        "status_summary": status_summary,
        "translated_path": str(zh_path.relative_to(repo_root)),
        "bilingual_path": str(bi_path.relative_to(repo_root)),
        "overwrite": overwrite,
    }


def run_export(
    repo_root: Path,
    *,
    source: str,
    project_id: str | None = None,
    require_refined: bool = False,
    overwrite: bool = True,
    status_mode: str = "approved",
    confirm_draft: bool = False,
) -> dict[str, Any]:
    source = str(source or "").strip().lower()
    if source == "manifest":
        if not project_id:
            raise ValueError("project_id is required for manifest export")
        from workbench.project_id import validate_project_id
        from workbench.project_registry import get_project_manifest

        project_id = validate_project_id(project_id)
        if get_project_manifest(repo_root, project_id) is None:
            raise KeyError(f"unknown project_id: {project_id}")
        mode = str(status_mode or "approved").strip().lower()
        if mode not in VALID_MANIFEST_EXPORT_MODES:
            raise ValueError("status_mode must be 'approved' or 'draft'")
        if mode == "draft" and not confirm_draft:
            raise ValueError("draft export requires explicit confirm_draft=true")
        result = export_from_manifest(
            repo_root,
            project_id=project_id,
            overwrite=overwrite,
            status_mode=mode,
        )
        result["status"] = export_status(repo_root)
        return result

    if source != "runs":
        raise ValueError("source must be 'manifest' or 'runs'")

    import importlib.util

    script = repo_root / "scripts" / "export_refined_runs.py"
    spec = importlib.util.spec_from_file_location("export_refined_runs", script)
    if spec is None or spec.loader is None:
        raise RuntimeError("export_refined_runs.py unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    summary = module.export_all(repo_root, require_refined=require_refined)
    summary["source"] = "runs"
    summary["status"] = export_status(repo_root)
    return summary
