#!/usr/bin/env python3
"""Lightweight continuous-agent runtime state manager.

This script manages local state, queue and blockers only. It does not replace
an AI Agent, call model APIs, read .env files, or print secrets.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

REPO_ROOT = Path(__file__).resolve().parent.parent
RUNTIME_DIR = REPO_ROOT / ".agent_runtime"
STATUS_PATH = RUNTIME_DIR / "status.json"
QUEUE_PATH = RUNTIME_DIR / "queue.jsonl"
BLOCKERS_PATH = RUNTIME_DIR / "blockers.jsonl"

RUNTIME_SUBDIRS = (
    "inspection_reports",
    "real_api_reports",
    "quality_reports",
    "fix_reports",
    "logs",
)

DEFAULT_STATUS = {
    "mode": "continuous_real_api",
    "round": 0,
    "current_role": "runner-agent",
    "last_successful_commit": None,
    "last_push_branch": None,
    "api_mode": "unknown",
    "browser_check_interval_minutes": 5,
    "last_browser_check_at": None,
    "last_real_api_check_at": None,
    "hard_blocked": False,
    "stop_reason": None,
    "updated_at": None,
}

SUPPORTED_TASK_TYPES = {
    "browser_inspection",
    "bugfix",
    "quality_optimization",
    "real_api_smoke",
    "documentation_sync",
    "test_fix",
}


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_argv(argv: list[str]) -> list[str]:
    normalized: list[str] = []
    for arg in argv:
        if arg.startswith(("–", "—")):
            normalized.append("--" + arg[1:])
        else:
            normalized.append(arg)
    return normalized


def redact_text(text: str | None) -> str:
    if not text:
        return ""
    value = str(text)
    value = re.sub(r"(?i)(bearer)\s+[A-Za-z0-9._\-]+", r"\1 <redacted>", value)
    value = re.sub(r"(?i)(api[_-]?key|token|cookie|password|secret)\s*[:=]\s*[^,\s]+", r"\1=<redacted>", value)
    value = re.sub(r"sk-[A-Za-z0-9_\-]{12,}", "sk-<redacted>", value)
    value = re.sub(r"AIza[0-9A-Za-z_\-]{20,}", "AIza<redacted>", value)
    value = re.sub(r"\b[A-Za-z0-9_\-]{48,}\b", "<redacted-token>", value)
    return value


def ensure_runtime() -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    for dirname in RUNTIME_SUBDIRS:
        (RUNTIME_DIR / dirname).mkdir(parents=True, exist_ok=True)
    if not QUEUE_PATH.exists():
        QUEUE_PATH.write_text("", encoding="utf-8")
    if not BLOCKERS_PATH.exists():
        BLOCKERS_PATH.write_text("", encoding="utf-8")
    if not STATUS_PATH.exists():
        write_status(dict(DEFAULT_STATUS))
        return
    status = load_status()
    merged = dict(DEFAULT_STATUS)
    merged.update(status)
    if merged != status:
        write_status(merged)


def load_status() -> dict:
    if not STATUS_PATH.exists():
        return dict(DEFAULT_STATUS)
    try:
        data = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    merged = dict(DEFAULT_STATUS)
    merged.update(data)
    return merged


def write_status(status: dict) -> None:
    STATUS_PATH.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_queue() -> list[dict]:
    if not QUEUE_PATH.exists():
        return []
    by_id: dict[str, dict] = {}
    for raw in QUEUE_PATH.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(item, dict):
            continue
        task_id = str(item.get("id") or "").strip()
        if not task_id:
            continue
        if task_id in by_id:
            merged = dict(by_id[task_id])
            merged.update(item)
            by_id[task_id] = merged
        else:
            by_id[task_id] = item
    return list(by_id.values())


def append_jsonl(path: Path, payload: dict) -> None:
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def pending_tasks() -> list[dict]:
    return [task for task in read_queue() if task.get("status") == "pending"]


def cmd_status(_args: argparse.Namespace) -> int:
    status = load_status()
    pending = pending_tasks()
    print("agent status")
    print(f"  mode: {status.get('mode')}")
    print(f"  round: {status.get('round')}")
    print(f"  current_role: {status.get('current_role')}")
    print(f"  api_mode: {status.get('api_mode')}")
    print(f"  hard_blocked: {status.get('hard_blocked')}")
    if status.get("stop_reason"):
        print(f"  stop_reason: {redact_text(status.get('stop_reason'))}")
    print(f"  pending_tasks: {len(pending)}")
    print(f"  last_browser_check_at: {status.get('last_browser_check_at')}")
    print(f"  last_real_api_check_at: {status.get('last_real_api_check_at')}")
    print(f"  updated_at: {status.get('updated_at')}")
    return 0


def cmd_next(_args: argparse.Namespace) -> int:
    status = load_status()
    try:
        current_round = int(status.get("round") or 0)
    except (TypeError, ValueError):
        current_round = 0
    status["round"] = current_round + 1
    status["updated_at"] = iso_now()
    write_status(status)
    print(f"agent next: round={status['round']} updated_at={status['updated_at']}")
    if status.get("hard_blocked"):
        print("agent next: warning hard_blocked=true; runner should resolve blockers before work")
    return 0


def cmd_enqueue(args: argparse.Namespace) -> int:
    now = iso_now()
    reason = redact_text(args.reason)
    task = {
        "id": f"task-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:8]}",
        "type": args.type,
        "priority": args.priority,
        "reason": reason,
        "status": "pending",
        "created_at": now,
        "updated_at": now,
    }
    append_jsonl(QUEUE_PATH, task)
    print(f"agent enqueue: {task['id']} type={task['type']} priority={task['priority']}")
    return 0


def cmd_queue(_args: argparse.Namespace) -> int:
    tasks = pending_tasks()
    print(f"pending tasks: {len(tasks)}")
    for task in tasks:
        reason = redact_text(task.get("reason", ""))
        print(
            f"  {task.get('id')} type={task.get('type')} "
            f"priority={task.get('priority', 'normal')} reason={reason}"
        )
    return 0


def cmd_dismiss(args: argparse.Namespace) -> int:
    now = iso_now()
    reason = redact_text(args.reason or "manual_dismiss")
    targets: list[dict] = []
    if args.all_pending:
        targets = pending_tasks()
    elif args.id:
        targets = [t for t in read_queue() if t.get("id") == args.id and t.get("status") == "pending"]
    else:
        print("agent dismiss: specify --all-pending or --id")
        return 1
    if not targets:
        print("agent dismiss: no matching pending tasks")
        return 0
    for task in targets:
        append_jsonl(
            QUEUE_PATH,
            {
                "id": task["id"],
                "status": "cancelled",
                "cancel_reason": reason,
                "updated_at": now,
            },
        )
        print(f"agent dismiss: {task['id']} → cancelled ({reason})")
    return 0


def cmd_block(args: argparse.Namespace) -> int:
    now = iso_now()
    reason = redact_text(args.reason)
    status = load_status()
    status["hard_blocked"] = True
    status["stop_reason"] = reason
    status["updated_at"] = now
    write_status(status)
    append_jsonl(
        BLOCKERS_PATH,
        {
            "id": f"blocker-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:8]}",
            "reason": reason,
            "status": "open",
            "created_at": now,
            "updated_at": now,
        },
    )
    print(f"agent block: hard_blocked=true reason={reason}")
    return 0


def cmd_unblock(_args: argparse.Namespace) -> int:
    now = iso_now()
    status = load_status()
    status["hard_blocked"] = False
    status["stop_reason"] = None
    status["updated_at"] = now
    write_status(status)
    append_jsonl(
        BLOCKERS_PATH,
        {
            "id": f"unblock-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:8]}",
            "reason": "manual_unblock",
            "status": "cleared",
            "created_at": now,
            "updated_at": now,
        },
    )
    print("agent unblock: hard_blocked=false")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Continuous Agent runtime state manager")
    sub = parser.add_subparsers(dest="command", required=True)

    status_p = sub.add_parser("status", help="Print current Agent runtime status")
    status_p.set_defaults(func=cmd_status)

    next_p = sub.add_parser("next", help="Advance runtime round counter")
    next_p.set_defaults(func=cmd_next)

    enqueue_p = sub.add_parser("enqueue", help="Append a pending task to queue.jsonl")
    enqueue_p.add_argument("--type", required=True, choices=sorted(SUPPORTED_TASK_TYPES))
    enqueue_p.add_argument("--reason", required=True)
    enqueue_p.add_argument("--priority", default="normal", choices=("low", "normal", "high"))
    enqueue_p.set_defaults(func=cmd_enqueue)

    block_p = sub.add_parser("block", help="Mark runtime as hard blocked")
    block_p.add_argument("--reason", required=True)
    block_p.set_defaults(func=cmd_block)

    unblock_p = sub.add_parser("unblock", help="Clear hard block status")
    unblock_p.set_defaults(func=cmd_unblock)

    queue_p = sub.add_parser("queue", help="Print pending task summary")
    queue_p.set_defaults(func=cmd_queue)

    dismiss_p = sub.add_parser("dismiss", help="Cancel pending queue task(s)")
    dismiss_p.add_argument("--all-pending", action="store_true", help="Cancel all pending tasks")
    dismiss_p.add_argument("--id", help="Cancel one task by id")
    dismiss_p.add_argument("--reason", default="manual_dismiss")
    dismiss_p.set_defaults(func=cmd_dismiss)
    return parser


def main(argv: list[str] | None = None) -> int:
    ensure_runtime()
    args = build_parser().parse_args(normalize_argv(argv if argv is not None else sys.argv[1:]))
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
