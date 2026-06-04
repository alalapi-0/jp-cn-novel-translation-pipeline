#!/usr/bin/env python3
"""Export refined workspace runs to output_cn/translated (zh-only) and output_cn/bilingual."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _chapter_num(chapter_id: str) -> int:
    m = re.search(r"(\d+)", chapter_id)
    return int(m.group(1)) if m else 0


def _load_runs(runs_root: Path) -> list[tuple[int, str, dict]]:
    out: list[tuple[int, str, dict]] = []
    for meta_path in sorted(runs_root.glob("run_*_draft_stage_b_50ch/run_metadata.json")):
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        offset = int(meta.get("chapter_offset") or 0)
        run_id = meta.get("run_id") or meta_path.parent.name
        seg_path = meta_path.parent / "segments.json"
        if not seg_path.is_file():
            continue
        doc = json.loads(seg_path.read_text(encoding="utf-8"))
        out.append((offset, run_id, doc))
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


def _export_zh(ch: dict, out_path: Path) -> None:
    lines = [f"# {ch['chapter_label']}", ""]
    for seg in ch["segments"]:
        text = _cn_text(seg)
        if text:
            lines.append(text)
            lines.append("")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def _export_bilingual(ch: dict, out_path: Path) -> None:
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
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def export_all(
    repo_root: Path,
    *,
    require_refined: bool = False,
) -> dict:
    runs_root = repo_root / "workspace" / "runs"
    runs = _load_runs(runs_root)
    if not runs:
        raise FileNotFoundError("no completed draft runs with segments.json found")

    merged = _merge_chapters(runs)
    zh_dir = repo_root / "output_cn" / "translated"
    bi_dir = repo_root / "output_cn" / "bilingual"
    zh_dir.mkdir(parents=True, exist_ok=True)
    bi_dir.mkdir(parents=True, exist_ok=True)

    exported = 0
    incomplete = 0
    for cid in sorted(merged.keys(), key=_chapter_num):
        ch = merged[cid]
        num = _chapter_num(cid)
        segs = ch["segments"]
        if not segs:
            continue
        missing = sum(1 for s in segs if not _cn_text(s))
        refined_missing = sum(
            1 for s in segs if not (s.get("refined_text") or "").strip()
        )
        if require_refined and refined_missing:
            incomplete += 1
            continue
        if missing:
            incomplete += 1
            continue
        stem = f"chapter_{num:03d}"
        _export_zh(ch, zh_dir / f"{stem}_cn.md")
        _export_bilingual(ch, bi_dir / f"{stem}_bilingual.md")
        exported += 1

    full_lines: list[str] = []
    for path in sorted(zh_dir.glob("chapter_*_cn.md")):
        full_lines.append(path.read_text(encoding="utf-8").strip())
        full_lines.append("")
    if full_lines:
        (zh_dir / "full_volume_cn.md").write_text(
            "\n\n".join(full_lines).strip() + "\n",
            encoding="utf-8",
        )

    return {
        "runs_merged": len(runs),
        "chapters_exported": exported,
        "chapters_incomplete": incomplete,
        "zh_dir": str(zh_dir.relative_to(repo_root)),
        "bilingual_dir": str(bi_dir.relative_to(repo_root)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Export refined runs to output_cn")
    parser.add_argument(
        "--require-refined",
        action="store_true",
        help="Only export chapters with all segments refined (no draft fallback)",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        summary = export_all(REPO_ROOT, require_refined=args.require_refined)
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
