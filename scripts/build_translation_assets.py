#!/usr/bin/env python3
"""Build reusable translation-memory assets from reviewed translation work."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from assets.translation_memory import (  # noqa: E402
    ExternalAssetExtractionUnavailable,
    build_translation_memory_assets,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build translation-memory assets for restart/retry translation context."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--project-id", help="Workbench manifest project id.")
    source.add_argument("--source-run", help="workspace/runs run id or run directory.")
    parser.add_argument(
        "--mode",
        choices=["agent", "external_api"],
        default="agent",
        help="Default agent mode uses deterministic local heuristics and no API.",
    )
    parser.add_argument(
        "--status-mode",
        choices=["approved", "translated"],
        default="approved",
        help="approved uses only reviewed approved pairs; translated also accepts completed run translations.",
    )
    parser.add_argument("--output", type=Path, default=None, help="Optional output JSON path.")
    parser.add_argument("--json", action="store_true", help="Print full summary JSON.")
    args = parser.parse_args()

    try:
        doc = build_translation_memory_assets(
            repo_root=REPO_ROOT,
            project_id=args.project_id,
            source_run=args.source_run,
            output_path=args.output,
            mode=args.mode,
            status_mode=args.status_mode,
        )
    except ExternalAssetExtractionUnavailable as exc:
        print(f"external_api unavailable: {exc}", file=sys.stderr)
        return 2
    except (FileNotFoundError, KeyError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(doc, ensure_ascii=False, indent=2))
    else:
        path = doc.get("asset_path_relative") or doc.get("asset_path")
        stats = doc.get("stats") or {}
        print(f"translation assets built: {path}")
        print(
            f"pairs={stats.get('pairs', 0)} terms={stats.get('term_candidates', 0)} "
            f"proper_nouns={stats.get('proper_noun_candidates', 0)} api_calls={stats.get('api_calls', 0)}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
