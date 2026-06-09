#!/usr/bin/env python3
"""Read-only summary of CostGuard ledger JSONL under workspace/model_runs (dry-run)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LOG_DIR = REPO_ROOT / "workspace" / "model_runs"


def summarize_ledger(log_dir: Path) -> dict:
    files = sorted(log_dir.glob("**/*.jsonl")) + sorted(log_dir.glob("**/*.json"))
    entries = 0
    total_usd = 0.0
    for fp in files:
        if fp.name.startswith("."):
            continue
        try:
            if fp.suffix == ".jsonl":
                for line in fp.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    obj = json.loads(line)
                    entries += 1
                    total_usd += float(obj.get("cost_usd") or obj.get("spent_usd") or 0)
            else:
                obj = json.loads(fp.read_text(encoding="utf-8"))
                if isinstance(obj, dict):
                    entries += 1
                    total_usd += float(obj.get("spent_usd") or obj.get("cost_usd") or 0)
        except (json.JSONDecodeError, OSError, ValueError):
            continue
    return {
        "log_dir": str(log_dir.relative_to(REPO_ROOT)) if log_dir.is_relative_to(REPO_ROOT) else str(log_dir),
        "files_scanned": len(files),
        "entries": entries,
        "total_usd_estimate": round(total_usd, 6),
        "mode": "read_only_dry_run",
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Inspect cost ledger (read-only)")
    parser.add_argument("--log-dir", type=Path, default=DEFAULT_LOG_DIR)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    log_dir = args.log_dir if args.log_dir.is_absolute() else REPO_ROOT / args.log_dir
    if not log_dir.is_dir():
        payload = {"log_dir": str(log_dir), "entries": 0, "note": "directory missing (ok for dry-run)"}
    else:
        payload = summarize_ledger(log_dir)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"inspect_cost_ledger: {payload.get('entries', 0)} entries, usd~{payload.get('total_usd_estimate', 0)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
