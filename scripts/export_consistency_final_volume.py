#!/usr/bin/env python3
"""Export the consistency-audited canonical translation as the final volume."""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from run_consistency_fix_all import discover_canonical_files

REPO_ROOT = Path(__file__).resolve().parent.parent
EXCLUDED_SEGMENT_STATUSES = {"validation_failed", "failed", "retry_pending"}


def _chapter_num(chapter_id: str) -> int:
    match = re.search(r"(\d+)", chapter_id or "")
    return int(match.group(1)) if match else 0


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def _cn_text(seg: dict) -> str:
    return ((seg.get("refined_text") or "").strip() or (seg.get("draft_text") or "").strip())


def _segment_exportable(seg: dict) -> bool:
    if str(seg.get("status") or seg.get("refine_status") or "") in EXCLUDED_SEGMENT_STATUSES:
        return False
    return bool(_cn_text(seg))


def _load_canonical_chapters() -> tuple[dict[str, dict], list[dict]]:
    chapters: dict[str, dict] = {}
    sources: list[dict] = []
    for path in discover_canonical_files():
        doc = json.loads(path.read_text(encoding="utf-8"))
        rel = str(path.relative_to(REPO_ROOT))
        mtime = path.stat().st_mtime
        chapter_ids: list[str] = []
        for ch in doc.get("chapters", []):
            cid = ch.get("chapter_id") or ""
            if not cid:
                continue
            chapter_ids.append(cid)
            current = chapters.get(cid)
            if current is None or mtime >= current["_mtime"]:
                chapters[cid] = {
                    "_mtime": mtime,
                    "_segments_file": rel,
                    "chapter_id": cid,
                    "chapter_label": ch.get("chapter_label") or cid,
                    "source_path": ch.get("source_path") or "",
                    "segments": ch.get("segments", []),
                }
        sources.append(
            {
                "segments_file": rel,
                "chapters": sorted(chapter_ids, key=_chapter_num),
                "mtime": datetime.fromtimestamp(mtime, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
        )
    return chapters, sources


def _cleanup_generated(out_dir: Path, patterns: tuple[str, ...]) -> int:
    removed = 0
    out_dir.mkdir(parents=True, exist_ok=True)
    for pattern in patterns:
        for path in out_dir.glob(pattern):
            if path.name == ".gitkeep":
                continue
            if path.is_file():
                path.unlink()
                removed += 1
    return removed


def _render_cn(ch: dict) -> str:
    lines = [f"# {ch['chapter_label']}", ""]
    for seg in ch["segments"]:
        text = _cn_text(seg)
        if text:
            lines.append(text)
            lines.append("")
    return "\n".join(lines).strip() + "\n"


def _render_bilingual(ch: dict) -> str:
    lines = [f"# {ch['chapter_label']}", ""]
    for idx, seg in enumerate(ch["segments"], start=1):
        src = (seg.get("source_text") or "").strip()
        cn = _cn_text(seg)
        if not src and not cn:
            continue
        lines.extend(
            [
                f"## 段落 {idx}",
                "**原文：**",
                src,
                "",
                "**译文：**",
                cn,
                "",
                "---",
                "",
            ]
        )
    return "\n".join(lines).strip() + "\n"


def export_final(output_root: Path) -> dict:
    chapters, sources = _load_canonical_chapters()
    zh_dir = output_root / "translated"
    bi_dir = output_root / "bilingual"
    removed = {
        "translated": _cleanup_generated(zh_dir, ("chapter_*_cn.md", "full_volume_cn.md")),
        "bilingual": _cleanup_generated(bi_dir, ("chapter_*_bilingual.md", "full_volume_bilingual.md")),
    }

    exported = 0
    incomplete: list[str] = []
    full_cn: list[str] = []
    full_bilingual: list[str] = []
    for cid in sorted(chapters, key=_chapter_num):
        ch = chapters[cid]
        if not ch.get("segments") or any(not _segment_exportable(seg) for seg in ch["segments"]):
            incomplete.append(cid)
            continue
        num = _chapter_num(cid)
        cn = _render_cn(ch)
        bilingual = _render_bilingual(ch)
        _atomic_write_text(zh_dir / f"chapter_{num:03d}_cn.md", cn)
        _atomic_write_text(bi_dir / f"chapter_{num:03d}_bilingual.md", bilingual)
        full_cn.append(cn.strip())
        full_bilingual.append(bilingual.strip())
        exported += 1

    if full_cn:
        _atomic_write_text(zh_dir / "full_volume_cn.md", "\n\n".join(full_cn).strip() + "\n")
    if full_bilingual:
        _atomic_write_text(bi_dir / "full_volume_bilingual.md", "\n\n".join(full_bilingual).strip() + "\n")

    missing = [f"ch-{num:03d}" for num in range(1, 613) if f"ch-{num:03d}" not in chapters]
    manifest = {
        "schema": "consistency_final_export_v1",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "output_root": str(output_root.relative_to(REPO_ROOT)),
        "chapters_discovered": len(chapters),
        "chapters_exported": exported,
        "chapters_incomplete": incomplete,
        "chapters_missing": missing,
        "canonical_files": len(sources),
        "removed_old_generated_files": removed,
        "translated_dir": str(zh_dir.relative_to(REPO_ROOT)),
        "bilingual_dir": str(bi_dir.relative_to(REPO_ROOT)),
        "full_volume_cn": str((zh_dir / "full_volume_cn.md").relative_to(REPO_ROOT)),
        "full_volume_bilingual": str((bi_dir / "full_volume_bilingual.md").relative_to(REPO_ROOT)),
        "sources": sources,
    }
    _atomic_write_text(output_root / "final_export_manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Export consistency-audited final volume")
    parser.add_argument("--output-root", type=Path, default=REPO_ROOT / "output_cn")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    output_root = args.output_root if args.output_root.is_absolute() else REPO_ROOT / args.output_root
    manifest = export_final(output_root)
    if args.json:
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
    else:
        print(
            f"exported={manifest['chapters_exported']} "
            f"missing={len(manifest['chapters_missing'])} "
            f"incomplete={len(manifest['chapters_incomplete'])} "
            f"output={manifest['output_root']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
