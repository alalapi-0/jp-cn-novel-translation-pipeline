#!/usr/bin/env python3
"""Heal stale lock files left behind by dead processes (FS-006, spec §9.4).

Scans two lock families:

- ``workspace/.locks/*.lock`` — flock-style locks written by translate /
  refine runners. The kernel flock dies with its process, so a file whose
  recorded pid is dead is pure residue and safe to delete.
- ``workspace/control/scheduler_running.lock`` — the scheduler tick lock
  (JSON payload). Cleared via scheduler.control.clear_stale_lock, which
  refuses to touch a lock held by a live pid.

Safety rules:
- a lock with a *live* pid is never touched;
- a lock whose pid cannot be parsed is reported (``unknown_pid``) but never
  deleted automatically — inspect by hand;
- run data, checkpoints and stage_state are never touched.

Default is dry-run. Pass --apply to delete.

Usage:
    python3 scripts/heal_stale_locks.py --json
    python3 scripts/heal_stale_locks.py --apply --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from scheduler.control import (  # noqa: E402
    SchedulerLockError,
    clear_stale_lock,
    lock_file_path,
    lock_status,
    pid_alive,
)

LOCKS_DIR_REL = "workspace/.locks"


def _read_pid(path: Path) -> int | None:
    try:
        first = path.read_text(encoding="utf-8").strip().splitlines()
    except OSError:
        return None
    if not first:
        return None
    try:
        return int(first[0].strip())
    except ValueError:
        return None


def scan_flock_locks(repo_root: Path) -> list[dict]:
    out: list[dict] = []
    lock_dir = repo_root / LOCKS_DIR_REL
    if not lock_dir.is_dir():
        return out
    for path in sorted(lock_dir.glob("*.lock")):
        pid = _read_pid(path)
        if pid is None:
            verdict = "unknown_pid"
        elif pid_alive(pid):
            verdict = "held"
        else:
            verdict = "stale"
        out.append({"path": str(path.relative_to(repo_root)), "pid": pid, "verdict": verdict})
    return out


def heal(repo_root: Path, *, apply: bool) -> dict:
    report: dict = {
        "mode": "apply" if apply else "dry_run",
        "flock_locks": scan_flock_locks(repo_root),
        "scheduler_lock": None,
        "healed": [],
        "kept": [],
        "needs_attention": [],
    }

    for entry in report["flock_locks"]:
        if entry["verdict"] == "stale":
            if apply:
                (repo_root / entry["path"]).unlink(missing_ok=True)
                report["healed"].append(entry["path"])
            else:
                report["needs_attention"].append(
                    {"path": entry["path"], "action": "would_delete (run with --apply)"}
                )
        elif entry["verdict"] == "held":
            report["kept"].append(entry["path"])
        else:  # unknown_pid: never auto-delete
            report["needs_attention"].append(
                {"path": entry["path"], "action": "inspect manually (no pid recorded)"}
            )

    sched = lock_status(repo_root)
    report["scheduler_lock"] = {
        "path": str(lock_file_path(repo_root).relative_to(repo_root)),
        "exists": sched["exists"],
        "pid": sched["pid"],
        "alive": sched["alive"],
        "stale": sched["stale"],
    }
    if sched["exists"] and sched["stale"]:
        if apply:
            try:
                clear_stale_lock(repo_root)
                report["healed"].append(report["scheduler_lock"]["path"])
            except SchedulerLockError as exc:  # pragma: no cover - race: became live
                report["needs_attention"].append(
                    {"path": report["scheduler_lock"]["path"], "action": f"refused: {exc.reason}"}
                )
        else:
            report["needs_attention"].append(
                {
                    "path": report["scheduler_lock"]["path"],
                    "action": "would_clear_stale (run with --apply)",
                }
            )
    elif sched["exists"]:
        report["kept"].append(report["scheduler_lock"]["path"])

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Heal stale lock files (dead pids only)")
    parser.add_argument("--apply", action="store_true", help="actually delete stale locks")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT, help=argparse.SUPPRESS)
    args = parser.parse_args()

    report = heal(args.repo_root, apply=args.apply)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"mode={report['mode']}")
        for entry in report["flock_locks"]:
            print(f"flock {entry['verdict']}: {entry['path']} pid={entry['pid']}")
        sched = report["scheduler_lock"]
        print(
            "scheduler_lock: "
            + ("absent" if not sched["exists"] else f"pid={sched['pid']} stale={sched['stale']}")
        )
        for healed in report["healed"]:
            print(f"healed: {healed}")
        for item in report["needs_attention"]:
            print(f"attention: {item['path']} -> {item['action']}")
    # Exit 0 even when attention items exist: this is a reporting tool;
    # gate-level enforcement stays in throughput_gate.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
