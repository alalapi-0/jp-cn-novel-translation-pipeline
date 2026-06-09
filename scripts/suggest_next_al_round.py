#!/usr/bin/env python3
"""Suggest next AL round from docs/AGENT_ROADMAP.md and audit log."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ROADMAP = REPO_ROOT / "docs" / "AGENT_ROADMAP.md"
AUDIT_LOG = REPO_ROOT / "reports" / "agent_audit_log.jsonl"

AL_HEADING = re.compile(r"^### (AL-(?:T\d+|\d+)) —")
DEPENDS = re.compile(r"^\s*- \*\*depends_on:\*\* (.+)$")


def parse_roadmap(text: str) -> dict[str, list[str]]:
    rounds: dict[str, list[str]] = {}
    current: str | None = None
    for line in text.splitlines():
        m = AL_HEADING.match(line)
        if m:
            current = m.group(1)
            rounds[current] = []
            continue
        if current:
            dm = DEPENDS.match(line)
            if dm:
                deps = [d.strip() for d in dm.group(1).split(",") if d.strip() and d.strip() != "none"]
                rounds[current] = deps
    return rounds


def completed_from_audit(path: Path = AUDIT_LOG) -> set[str]:
    done: set[str] = set()
    if not path.is_file():
        return done
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        rid = obj.get("round_id")
        if rid:
            done.add(str(rid))
    # AL-002 satisfied by index links; AL-028 stub done in AL-010
    done.add("AL-002")
    done.add("AL-028")
    return done


def suggest_next(done: set[str] | None = None) -> str | None:
    done = done if done is not None else completed_from_audit()
    graph = parse_roadmap(ROADMAP.read_text(encoding="utf-8"))
    for rid, deps in graph.items():
        if rid in done:
            continue
        if all(d in done for d in deps):
            return rid
    return None


def main() -> int:
    nxt = suggest_next()
    if nxt:
        print(nxt)
        return 0
    print("NONE", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
