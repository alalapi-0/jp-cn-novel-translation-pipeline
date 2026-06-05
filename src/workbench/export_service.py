"""Export status and manifest-based mock export for Workbench UI."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


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
) -> dict[str, Any]:
    from workbench.project_registry import get_project_manifest

    manifest = get_project_manifest(repo_root, project_id)
    if manifest is None:
        raise KeyError(f"unknown project_id: {project_id}")

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
    for idx, seg in enumerate(manifest.segments, start=1):
        source = str(seg.get("source") or seg.get("source_text") or "").strip()
        draft = str(seg.get("draft") or seg.get("draft_text") or seg.get("target_text") or "").strip()
        if not source and not draft:
            continue
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
                "---",
                "",
            ]
        )

    zh_path.write_text("\n".join(zh_lines).strip() + "\n", encoding="utf-8")
    bi_path.write_text("\n".join(bi_lines).strip() + "\n", encoding="utf-8")
    return {
        "source": "manifest",
        "project_id": project_id,
        "segments_exported": len(manifest.segments),
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
        result = export_from_manifest(repo_root, project_id=project_id, overwrite=overwrite)
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
