#!/usr/bin/env python3
"""Export refined workspace runs to output_cn/translated (zh-only) and output_cn/bilingual."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

EXCLUDED_SEGMENT_STATUSES = frozenset(
    {"validation_failed", "failed", "retry_pending"}
)


def _chapter_num(chapter_id: str) -> int:
    m = re.search(r"(\d+)", chapter_id)
    return int(m.group(1)) if m else 0


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


def _segment_exportable(seg: dict, *, require_refined: bool) -> bool:
    status = str(seg.get("status") or seg.get("refine_status") or "")
    if status in EXCLUDED_SEGMENT_STATUSES:
        return False
    draft = (seg.get("draft_text") or "").strip()
    if not draft:
        return False
    refined = (seg.get("refined_text") or "").strip()
    if require_refined and not refined:
        return False
    if not require_refined and not refined and not draft:
        return False
    return True


def _chapter_exportable(ch: dict, *, require_refined: bool) -> bool:
    segs = ch.get("segments", [])
    if not segs:
        return False
    return all(_segment_exportable(s, require_refined=require_refined) for s in segs)


def _load_runs(
    runs_root: Path,
    *,
    run_id: str | None = None,
    up_to_offset: int | None = None,
) -> list[tuple[int, str, dict]]:
    out: list[tuple[int, str, dict]] = []
    pattern = "run_*_draft_stage_b_50ch/run_metadata.json"
    if run_id:
        meta_path = runs_root / run_id / "run_metadata.json"
        paths = [meta_path] if meta_path.is_file() else []
    else:
        paths = sorted(runs_root.glob(pattern))

    for meta_path in paths:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        offset = int(meta.get("chapter_offset") or 0)
        if up_to_offset is not None and offset > up_to_offset:
            continue
        rid = meta.get("run_id") or meta_path.parent.name
        seg_path = meta_path.parent / "segments.json"
        if not seg_path.is_file():
            continue
        doc = json.loads(seg_path.read_text(encoding="utf-8"))
        out.append((offset, rid, doc))
    out.sort(key=lambda x: x[0])
    return out


def _merge_chapters(runs: list[tuple[int, str, dict]]) -> dict[str, dict]:
    merged: dict[str, dict] = {}
    for _offset, run_id, doc in runs:
        for ch in doc.get("chapters", []):
            cid = ch.get("chapter_id", "")
            if not cid:
                continue
            entry = merged.setdefault(
                cid,
                {
                    "chapter_id": cid,
                    "chapter_label": ch.get("chapter_label", cid),
                    "source_path": ch.get("source_path", ""),
                    "segments": [],
                    "run_id": run_id,
                },
            )
            if ch.get("chapter_label"):
                entry["chapter_label"] = ch["chapter_label"]
            entry["segments"] = ch.get("segments", [])
            entry["run_id"] = run_id
    return merged


def _cn_text(seg: dict) -> str:
    refined = (seg.get("refined_text") or "").strip()
    if refined:
        return refined
    return (seg.get("draft_text") or "").strip()


def _export_zh(ch: dict, out_path: Path, *, overwrite: bool) -> bool:
    if out_path.is_file() and not overwrite:
        existing = out_path.read_text(encoding="utf-8")
        if "<!-- human-edited -->" in existing:
            return False
    lines = [f"# {ch['chapter_label']}", ""]
    for seg in ch["segments"]:
        text = _cn_text(seg)
        if text:
            lines.append(text)
            lines.append("")
    _atomic_write_text(out_path, "\n".join(lines).strip() + "\n")
    return True


def _export_bilingual(ch: dict, out_path: Path, *, overwrite: bool) -> bool:
    if out_path.is_file() and not overwrite:
        existing = out_path.read_text(encoding="utf-8")
        if "<!-- human-edited -->" in existing:
            return False
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
    _atomic_write_text(out_path, "\n".join(lines).strip() + "\n")
    return True


def export_all(
    repo_root: Path,
    *,
    require_refined: bool = False,
    run_id: str | None = None,
    up_to_offset: int | None = None,
    output_root: Path | None = None,
    overwrite: bool = True,
) -> dict:
    runs_root = repo_root / "workspace" / "runs"
    runs = _load_runs(runs_root, run_id=run_id, up_to_offset=up_to_offset)
    if not runs:
        raise FileNotFoundError("no completed draft runs with segments.json found")

    merged = _merge_chapters(runs)
    base = output_root or (repo_root / "output_cn")
    zh_dir = base / "translated"
    bi_dir = base / "bilingual"
    zh_dir.mkdir(parents=True, exist_ok=True)
    bi_dir.mkdir(parents=True, exist_ok=True)

    exported = 0
    skipped = 0
    incomplete = 0
    for cid in sorted(merged.keys(), key=_chapter_num):
        ch = merged[cid]
        num = _chapter_num(cid)
        if not _chapter_exportable(ch, require_refined=require_refined):
            incomplete += 1
            continue
        stem = f"chapter_{num:03d}"
        zh_path = zh_dir / f"{stem}_cn.md"
        bi_path = bi_dir / f"{stem}_bilingual.md"
        if not overwrite and zh_path.is_file() and "<!-- human-edited -->" in zh_path.read_text(encoding="utf-8"):
            skipped += 1
            continue
        did_zh = _export_zh(ch, zh_path, overwrite=overwrite)
        did_bi = _export_bilingual(ch, bi_path, overwrite=overwrite)
        if did_zh or did_bi:
            exported += 1
        else:
            skipped += 1

    full_lines: list[str] = []
    for path in sorted(zh_dir.glob("chapter_*_cn.md")):
        full_lines.append(path.read_text(encoding="utf-8").strip())
        full_lines.append("")
    if full_lines:
        _atomic_write_text(zh_dir / "full_volume_cn.md", "\n\n".join(full_lines).strip() + "\n")

    return {
        "runs_merged": len(runs),
        "chapters_exported": exported,
        "chapters_skipped_human_edited": skipped,
        "chapters_incomplete": incomplete,
        "zh_dir": str(zh_dir.relative_to(repo_root)),
        "bilingual_dir": str(bi_dir.relative_to(repo_root)),
        "run_id_filter": run_id,
        "up_to_offset": up_to_offset,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Export refined runs to output_cn")
    parser.add_argument(
        "--require-refined",
        action="store_true",
        help="Only export chapters with all segments refined (no draft fallback)",
    )
    parser.add_argument("--run-id", default="", help="Export only this run_id")
    parser.add_argument(
        "--up-to-offset",
        type=int,
        default=None,
        help="Export runs with chapter_offset <= this value",
    )
    parser.add_argument(
        "--fixture-dir",
        type=Path,
        default=None,
        help="Write exports to this dir instead of output_cn (for tests)",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        summary = export_all(
            REPO_ROOT,
            require_refined=args.require_refined,
            run_id=args.run_id.strip() or None,
            up_to_offset=args.up_to_offset,
            output_root=args.fixture_dir,
        )
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(
            f"exported={summary['chapters_exported']} "
            f"incomplete={summary['chapters_incomplete']} "
            f"zh={summary['zh_dir']} bi={summary['bilingual_dir']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
