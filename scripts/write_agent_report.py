#!/usr/bin/env python3
"""Write or update reports/latest-agent-report.json from a schema-safe template.

Optionally append a one-line summary to reports/agent_audit_log.jsonl.
Validates output via validate_agent_report before write (unless --skip-validate).
Does not read .env. Exit: 0=ok, 1=validation failed, 2=IO/usage error.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REPORT = REPO_ROOT / "reports" / "latest-agent-report.json"
AUDIT_LOG = REPO_ROOT / "reports" / "agent_audit_log.jsonl"
PROBE_REPORT = REPO_ROOT / "reports" / "tool_probe_report.json"
GATE_RESULT = REPO_ROOT / "reports" / "gate_result.json"
SCHEMA_PATH = REPO_ROOT / "schemas" / "agent_round_report.schema.json"

DEFAULT_AGENT = "cursor-composer"
DEFAULT_SURFACE = "cursor"
DEFAULT_MODE = "implement"


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _git_head_oneline() -> str | None:
    try:
        proc = subprocess.run(
            ["git", "log", "-1", "--oneline"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        line = (proc.stdout or "").strip()
        return line if proc.returncode == 0 and line else None
    except OSError:
        return None


def infer_tool_probe_status() -> str:
    if not PROBE_REPORT.is_file():
        return "not_run"
    try:
        status = _load_json(PROBE_REPORT).get("status", "partial")
        if status in ("passed", "failed", "partial"):
            return status
    except (json.JSONDecodeError, OSError):
        pass
    return "partial"


def infer_gate_status() -> str:
    if not GATE_RESULT.is_file():
        return "not_run"
    try:
        status = _load_json(GATE_RESULT).get("status", "warning")
        if status in ("passed", "failed", "blocked", "not_run", "warning"):
            return status
    except (json.JSONDecodeError, OSError):
        pass
    return "warning"


def build_template(
    *,
    round_id: str,
    goal: str,
    agent: str = DEFAULT_AGENT,
    agent_surface: str = DEFAULT_SURFACE,
    mode: str = DEFAULT_MODE,
    tool_probe_status: str | None = None,
    gate_status: str | None = None,
    next_recommended_round: str | None = None,
    repo_status_before: str | None = None,
    scope: list[str] | None = None,
) -> dict[str, Any]:
    head = _git_head_oneline()
    if repo_status_before is None and head:
        repo_status_before = f"main at {head}"

    report: dict[str, Any] = {
        "round_id": round_id,
        "timestamp": utc_now(),
        "agent": agent,
        "agent_surface": agent_surface,
        "mode": mode,
        "goal": goal,
        "scope": scope or [],
        "repo_status_before": repo_status_before or "",
        "tool_probe_status": tool_probe_status or infer_tool_probe_status(),
        "tools_used": [],
        "tools_not_used": [],
        "web_research": [],
        "changed_files": [],
        "commands_run": [],
        "test_results": [],
        "issues_found": [],
        "issues_fixed": [],
        "remaining_issues": [],
        "severity_summary": {"p0": 0, "p1": 0, "p2": 0, "p3": 0},
        "gate_status": gate_status or infer_gate_status(),
        "blockers": [],
        "risks": [],
        "next_recommended_round": next_recommended_round or "",
        "human_decisions_required": [],
    }
    return report


def merge_report(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """Shallow merge patch into base; nested dicts merge one level for severity_summary."""
    out = dict(base)
    for key, value in patch.items():
        if key == "severity_summary" and isinstance(value, dict) and isinstance(out.get(key), dict):
            merged = dict(out[key])
            merged.update(value)
            out[key] = merged
        else:
            out[key] = value
    return out


def load_base_report(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    if not path.is_file():
        return None
    return _load_json(path)


def validate_report_dict(report: dict[str, Any]) -> tuple[bool, list[str]]:
    scripts_dir = REPO_ROOT / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    from validate_agent_report import validate_with_jsonschema

    schema = _load_json(SCHEMA_PATH)
    errors = validate_with_jsonschema(report, schema)
    return len(errors) == 0, errors


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def write_report_file(report: dict[str, Any], path: Path | None = None) -> None:
    target = path or DEFAULT_REPORT
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def append_audit_log(
    *,
    round_id: str,
    agent: str,
    agent_surface: str,
    gate_status: str,
    summary: str,
    timestamp: str | None = None,
    path: Path | None = None,
) -> None:
    target = path or AUDIT_LOG
    line = {
        "timestamp": timestamp or utc_now(),
        "round_id": round_id,
        "agent": agent,
        "agent_surface": agent_surface,
        "gate_status": gate_status,
        "summary": summary,
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(line, ensure_ascii=False) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write schema-safe agent round report template")
    parser.add_argument("--round-id", required=True, help="e.g. AL-013")
    parser.add_argument("--goal", required=True, help="One-line round goal")
    parser.add_argument("--mode", default=DEFAULT_MODE, help="Report mode enum value")
    parser.add_argument("--agent", default=DEFAULT_AGENT)
    parser.add_argument("--agent-surface", default=DEFAULT_SURFACE, choices=["cursor", "codex", "other"])
    parser.add_argument("--next", dest="next_round", default="", help="next_recommended_round")
    parser.add_argument("--tool-probe-status", default=None)
    parser.add_argument("--gate-status", default=None)
    parser.add_argument("--repo-status-before", default=None)
    parser.add_argument("--scope", action="append", default=[], help="Repeatable scope path")
    parser.add_argument("--merge", type=Path, help="JSON file merged over template (tools_used, etc.)")
    parser.add_argument("--base", type=Path, help="Start from existing report JSON instead of fresh template")
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_REPORT,
        help="Output report path (default: reports/latest-agent-report.json)",
    )
    parser.add_argument("--write", action="store_true", help="Write output file (default: stdout only)")
    parser.add_argument("--append-audit", metavar="SUMMARY", help="Append audit log line with summary")
    parser.add_argument("--skip-validate", action="store_true", help="Skip schema validation before write")
    parser.add_argument("--suggest-next", action="store_true", help="Fill next_recommended_round from roadmap graph")
    parser.add_argument("--json", action="store_true", help="Print report JSON to stdout")
    args = parser.parse_args(argv)

    output_path = args.output if args.output.is_absolute() else REPO_ROOT / args.output
    base_path = args.base if args.base is None else (args.base if args.base.is_absolute() else REPO_ROOT / args.base)
    merge_path = args.merge if args.merge is None else (args.merge if args.merge.is_absolute() else REPO_ROOT / args.merge)

    if base_path and base_path.is_file():
        report = load_base_report(base_path) or build_template(
            round_id=args.round_id,
            goal=args.goal,
            agent=args.agent,
            agent_surface=args.agent_surface,
            mode=args.mode,
            tool_probe_status=args.tool_probe_status,
            gate_status=args.gate_status,
            next_recommended_round=args.next_round or None,
            repo_status_before=args.repo_status_before,
            scope=args.scope or None,
        )
        report = merge_report(
            report,
            {
                "round_id": args.round_id,
                "goal": args.goal,
                "timestamp": utc_now(),
                "mode": args.mode,
                "agent": args.agent,
                "agent_surface": args.agent_surface,
            },
        )
    else:
        report = build_template(
            round_id=args.round_id,
            goal=args.goal,
            agent=args.agent,
            agent_surface=args.agent_surface,
            mode=args.mode,
            tool_probe_status=args.tool_probe_status,
            gate_status=args.gate_status,
            next_recommended_round=args.next_round or None,
            repo_status_before=args.repo_status_before,
            scope=args.scope or None,
        )

    if args.next_round:
        report["next_recommended_round"] = args.next_round
    if merge_path and merge_path.is_file():
        report = merge_report(report, _load_json(merge_path))

    if args.suggest_next and not report.get("next_recommended_round"):
        scripts_dir = REPO_ROOT / "scripts"
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))
        from suggest_next_al_round import suggest_next

        nxt = suggest_next()
        if nxt:
            report["next_recommended_round"] = nxt

    gate_result_path = REPO_ROOT / "reports" / "gate_result.json"
    if gate_result_path.is_file():
        if str(REPO_ROOT / "scripts") not in sys.path:
            sys.path.insert(0, str(REPO_ROOT / "scripts"))
        try:
            from gate_triage import load_gate_result, triage_gate_result

            triage = triage_gate_result(load_gate_result())
            if triage.get("severity_summary"):
                report = merge_report(report, {"severity_summary": triage["severity_summary"]})
        except Exception:
            pass

    if not args.skip_validate:
        ok, errors = validate_report_dict(report)
        if not ok:
            print("write_agent_report: validation FAILED", file=sys.stderr)
            for err in errors:
                print(f"  - {err}", file=sys.stderr)
            return 1

    if args.write:
        write_report_file(report, output_path)
        print(f"write_agent_report: wrote {_display_path(output_path)}")

    if args.append_audit:
        append_audit_log(
            round_id=report["round_id"],
            agent=report["agent"],
            agent_surface=report["agent_surface"],
            gate_status=report["gate_status"],
            summary=args.append_audit,
            timestamp=report["timestamp"],
        )
        print(f"write_agent_report: appended audit log")

    if args.json or not args.write:
        print(json.dumps(report, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
