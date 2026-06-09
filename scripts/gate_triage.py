#!/usr/bin/env python3
"""Map agent_gate / gate_result.json failures to P0–P3 severity buckets."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
GATE_RESULT = REPO_ROOT / "reports" / "gate_result.json"

P0_PATTERNS = (
    re.compile(r"env_not_tracked|\.env"),
    re.compile(r"secret|api.?key|token", re.I),
    re.compile(r"real.?api|real.?publish", re.I),
)
P1_PATTERNS = (
    re.compile(r"quality_review|frontend_mvp|protocol"),
    re.compile(r"docs_exist_agents|agent_layer"),
)


def classify_check(check_id: str, message: str = "") -> str:
    blob = f"{check_id} {message}".lower()
    if any(p.search(blob) for p in P0_PATTERNS):
        return "p0"
    if any(p.search(blob) for p in P1_PATTERNS):
        return "p1"
    if check_id.startswith("round_") or "roadmap" in blob:
        return "p3"
    return "p2"


def triage_gate_result(payload: dict[str, Any]) -> dict[str, Any]:
    failed = payload.get("failed") or payload.get("blocked") or []
    checks = payload.get("checks") or []
    by_id = {c.get("id", ""): c.get("message", "") for c in checks if isinstance(c, dict)}

    summary = {"p0": 0, "p1": 0, "p2": 0, "p3": 0}
    items: list[dict[str, str]] = []
    for cid in failed:
        sev = classify_check(str(cid), by_id.get(str(cid), ""))
        summary[sev] += 1
        items.append({"check_id": str(cid), "severity": sev, "message": by_id.get(str(cid), "")})
    return {"gate_status": payload.get("status", "unknown"), "severity_summary": summary, "items": items}


def load_gate_result(path: Path = GATE_RESULT) -> dict[str, Any]:
    if not path.is_file():
        return {"status": "not_run", "failed": [], "checks": []}
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Triage gate failures to severity")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--gate-result", type=Path, default=GATE_RESULT)
    args = parser.parse_args(argv)
    path = args.gate_result if args.gate_result.is_absolute() else REPO_ROOT / args.gate_result
    result = triage_gate_result(load_gate_result(path))
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        s = result["severity_summary"]
        print(f"gate_triage: p0={s['p0']} p1={s['p1']} p2={s['p2']} p3={s['p3']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
