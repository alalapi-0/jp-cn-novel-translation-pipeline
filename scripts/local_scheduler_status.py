#!/usr/bin/env python3
"""Local scheduler status CLI (FS-002, spec §9.2).

Usage:
    python3 scripts/local_scheduler_status.py          # human-readable
    python3 scripts/local_scheduler_status.py --json   # machine-readable
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from scheduler.status import collect_status  # noqa: E402


def _human(report: dict) -> str:
    draft = report["draft_progress"]
    refine = report["refinement_progress"]
    lines = [
        f"phase={report['current_phase']} next_task={report['next_task']}"
        f" next_round={report['next_round_id'] or '-'}"
        f" range={report['next_chapter_range'] or '-'}",
        f"draft={draft['completed_chapters']}/{draft['total_chapters']}"
        f" ({draft['percent']}%)"
        f" refine={refine['completed_chapters']}/{refine['total_chapters']}"
        f" ({refine['percent']}%)",
        f"workers active={report['active_worker_count']}"
        f" orphan={report['orphan_worker_count']}"
        f" lock={report['scheduler_lock_status']}"
        f" paused={report['paused']}",
        f"last_tick={report['last_successful_tick'] or '-'}"
        f" last_blocked={report['last_blocked_reason'] or '-'}",
        f"safe_to_run={report['safe_to_run']}"
        + (
            f" blocked_reasons={','.join(report['detail']['blocked_reasons'])}"
            if report["detail"]["blocked_reasons"]
            else ""
        ),
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Local scheduler status")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    args = parser.parse_args()
    report = collect_status(REPO_ROOT)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(_human(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
