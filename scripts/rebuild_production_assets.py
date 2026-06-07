#!/usr/bin/env python3
"""Rebuild production translation-memory asset from real draft/refined paragraphs.

Reads workspace/runs/<run_id>/segments.json (not dry-run manifest placeholders).
Full manual review of output is recommended before replacing pw-user-assets-flow.json.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from local_env import apply_local_env  # noqa: E402
from translation.run_progress import production_stage_state_path, safe_load_json  # noqa: E402

DEFAULT_OUTPUT = REPO_ROOT / "workspace/assets/translation_memory/pw-user-assets-flow.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_asset_from_run(
    *,
    repo_root: Path,
    run_id: str,
    min_draft_chars: int = 8,
    use_refined: bool = True,
) -> dict:
    seg_path = repo_root / "workspace" / "runs" / run_id / "segments.json"
    if not seg_path.is_file():
        raise FileNotFoundError(f"segments.json not found: {seg_path}")
    doc = json.loads(seg_path.read_text(encoding="utf-8"))
    pairs: list[dict] = []
    terms: dict[str, str] = {}
    for ch in doc.get("chapters") or []:
        for seg in ch.get("segments") or []:
            source = (seg.get("source_text") or "").strip()
            draft = (seg.get("draft_text") or "").strip()
            refined = (seg.get("refined_text") or "").strip()
            target = refined if use_refined and refined else draft
            if len(source) < min_draft_chars or len(target) < min_draft_chars:
                continue
            if "dry-run" in target or "占位" in target:
                continue
            pairs.append(
                {
                    "source": source,
                    "target": target,
                    "segment_id": seg.get("segment_id"),
                    "chapter_id": ch.get("chapter_id"),
                }
            )
    return {
        "asset_kind": "translation_memory",
        "mode": "production_run_rebuild",
        "run_id": run_id,
        "created_at": _utc_now(),
        "stats": {
            "pairs": len(pairs),
            "term_candidates": len(terms),
        },
        "pairs": pairs[:500],
        "term_candidates": terms,
        "notes": (
            "从生产 run segments 自动提取；替换 pw-user-assets-flow.json 前请人工抽查术语一致性。"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Rebuild production TM asset from run segments")
    parser.add_argument("--run-id", default="", help="Default: stage_state_production.json run_id")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--dry-run", action="store_true", help="Print JSON to stdout, do not write file")
    parser.add_argument("--apply", action="store_true", help="Write output file (default without --apply is plan only)")
    args = parser.parse_args()

    apply_local_env(REPO_ROOT)
    run_id = (args.run_id or "").strip()
    if not run_id:
        stage = safe_load_json(production_stage_state_path(REPO_ROOT)) or {}
        run_id = str(stage.get("run_id") or "").strip()
    if not run_id:
        print("rebuild_production_assets: no run_id (pass --run-id or set stage_state_production.json)", file=sys.stderr)
        return 2

    try:
        doc = build_asset_from_run(repo_root=REPO_ROOT, run_id=run_id)
    except FileNotFoundError as exc:
        print(f"rebuild_production_assets: {exc}", file=sys.stderr)
        return 2

    if args.dry_run or not args.apply:
        print(json.dumps({k: v for k, v in doc.items() if k != "pairs"}, ensure_ascii=False, indent=2))
        print(f"  pairs={doc['stats']['pairs']} (use --apply to write {args.output})")
        return 0

    out = args.output if args.output.is_absolute() else REPO_ROOT / args.output
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"rebuild_production_assets: wrote {out.relative_to(REPO_ROOT)} pairs={doc['stats']['pairs']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
