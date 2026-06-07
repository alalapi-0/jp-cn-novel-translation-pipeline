#!/usr/bin/env python3
"""Report active/orphan real-API translation workers."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

_spec = importlib.util.spec_from_file_location(
    "pipeline_worker_registry", REPO_ROOT / "scripts" / "pipeline_worker_registry.py"
)
assert _spec and _spec.loader
_registry = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_registry)


def evaluate() -> dict:
    summary = _registry.summarize_registry()
    active = summary.get("active_workers") or []
    orphans = summary.get("orphan_workers") or _registry.find_orphan_api_workers()
    translate_active = [w for w in active if w.get("task_type") == "translate"]
    decision = "CLEAN"
    if orphans:
        decision = "BLOCK"
    elif active:
        decision = "WARN"
    return {
        "decision": decision,
        "active_worker_count": len(active),
        "translate_active_count": len(translate_active),
        "orphan_worker_count": len(orphans),
        "active_workers": active,
        "orphan_workers": orphans,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Check orphan API workers")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = evaluate()
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(
            f"decision={result['decision']} "
            f"active={result['active_worker_count']} "
            f"orphans={result['orphan_worker_count']}"
        )
    return 2 if result["decision"] == "BLOCK" else (1 if result["decision"] == "WARN" else 0)


if __name__ == "__main__":
    raise SystemExit(main())
