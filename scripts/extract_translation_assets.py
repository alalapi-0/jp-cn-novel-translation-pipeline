#!/usr/bin/env python3
"""Extract abstract assets from translation run segments (read-only sidecar)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from assets.config import load_asset_extraction_config  # noqa: E402
from assets.model_assisted_extractor import ModelAssistedUnavailable  # noqa: E402
from assets.runner import run_asset_extraction  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Translation-derived asset extraction (does not modify translation runs)."
    )
    parser.add_argument(
        "--source-run",
        required=True,
        help="Source translation run id or path (reads segments.json only).",
    )
    parser.add_argument(
        "--chapters",
        default="1-5",
        help="Chapter range like 1-5 (default: 1-5).",
    )
    parser.add_argument(
        "--mode",
        choices=["rule-based", "model-assisted"],
        default=None,
        help="Extraction mode (default from project.yaml).",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output directory (default: workspace/asset_extraction_runs/<run_id>).",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="Optional extraction run id.",
    )
    parser.add_argument(
        "--dry-run-model",
        action="store_true",
        help="For model-assisted: skip API and exit with clear message.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print summary JSON to stdout.",
    )
    args = parser.parse_args()

    cfg = load_asset_extraction_config(REPO_ROOT)
    mode = args.mode or cfg.default_mode

    output_dir = Path(args.output) if args.output else None

    try:
        summary = run_asset_extraction(
            repo_root=REPO_ROOT,
            source_run=args.source_run,
            output_dir=output_dir,
            mode=mode,
            chapters_spec=args.chapters,
            config=cfg,
            run_id=args.run_id,
            dry_run_model=args.dry_run_model,
        )
    except ModelAssistedUnavailable as exc:
        print(f"model-assisted skipped: {exc}", file=sys.stderr)
        return 2
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(f"asset extraction complete: {summary['run_id']}")
        print(f"output: {summary['output_dir']}")
        print(f"safe/blocked: {summary['safe_assets']}/{summary['blocked_assets']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
