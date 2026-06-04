#!/usr/bin/env python3
"""Unified browser inspection entrypoint.

Detects the existing Playwright setup and runs the repository browser smoke
command when available. It does not install dependencies.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
RUNTIME_DIR = REPO_ROOT / ".agent_runtime"
REPORT_DIR = RUNTIME_DIR / "inspection_reports"
STATUS_PATH = RUNTIME_DIR / "status.json"


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_argv(argv: list[str]) -> list[str]:
    return ["--" + arg[1:] if arg.startswith(("–", "—")) else arg for arg in argv]


def redact_text(text: str | None) -> str:
    if not text:
        return ""
    value = str(text)
    value = re.sub(r"(?i)(bearer)\s+[A-Za-z0-9._\-]+", r"\1 <redacted>", value)
    value = re.sub(r"(?i)(api[_-]?key|token|cookie|password|secret)\s*[:=]\s*[^,\s]+", r"\1=<redacted>", value)
    value = re.sub(r"sk-[A-Za-z0-9_\-]{12,}", "sk-<redacted>", value)
    value = re.sub(r"AIza[0-9A-Za-z_\-]{20,}", "AIza<redacted>", value)
    value = re.sub(r"\b[A-Za-z0-9_\-]{48,}\b", "<redacted-token>", value)
    return value[-2000:]


def summarize_command_failure(output: str) -> str:
    clean = re.sub(r"\x1b\[[0-9;]*m", "", output)
    lines = clean.splitlines()
    useful: list[str] = []
    capture = False
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("[WebServer]") or " HTTP/1.1\" 200 " in stripped:
            continue
        lower = stripped.lower()
        if (
            " failed" in lower
            or "error:" in lower
            or "strict mode violation" in lower
            or stripped.startswith(("1)", "2)", "3)", "4)", "5)"))
            or "tests/ui/" in stripped
            or stripped.startswith(("Locator:", "Expected:", "Timeout:", "Error:"))
        ):
            capture = True
        if capture:
            useful.append(stripped)
        if len(useful) >= 80:
            break
    if not useful:
        useful = [line.strip() for line in lines if line.strip() and not line.strip().startswith("[WebServer]")]
    return redact_text("\n".join(useful))


def load_package_json() -> dict[str, Any]:
    path = REPO_ROOT / "package.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def has_playwright_dependency(package: dict[str, Any]) -> bool:
    for field in ("dependencies", "devDependencies", "optionalDependencies"):
        deps = package.get(field)
        if isinstance(deps, dict) and "@playwright/test" in deps:
            return True
    return False


def detect_e2e_command(package: dict[str, Any]) -> list[str] | None:
    scripts = package.get("scripts")
    if not isinstance(scripts, dict):
        return None
    if "test:e2e" in scripts:
        return ["npm", "run", "test:e2e"]
    if "test:ui" in scripts:
        return ["npm", "run", "test:ui"]
    return None


def detect_dev_server_command(package: dict[str, Any]) -> str | None:
    scripts = package.get("scripts")
    if not isinstance(scripts, dict):
        return None
    for name in ("dev:frontend", "dev", "start", "serve"):
        if name in scripts:
            return f"npm run {name}"
    return None


def write_report(report: dict) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = REPORT_DIR / f"browser_inspection_{ts}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def update_status(*, checked_at: str) -> None:
    if not STATUS_PATH.exists():
        return
    try:
        status = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return
    if not isinstance(status, dict):
        return
    status["last_browser_check_at"] = checked_at
    status["updated_at"] = checked_at
    STATUS_PATH.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_inspection(args: argparse.Namespace) -> tuple[dict, Path]:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    created_at = iso_now()
    package = load_package_json()
    scripts = package.get("scripts") if isinstance(package.get("scripts"), dict) else {}
    detected_playwright = {
        "package_json_has_playwright": has_playwright_dependency(package),
        "tests_e2e_exists": (REPO_ROOT / "tests" / "e2e").is_dir(),
        "tests_ui_exists": (REPO_ROOT / "tests" / "ui").is_dir(),
        "playwright_config_exists": any(
            (REPO_ROOT / name).is_file()
            for name in ("playwright.config.ts", "playwright.config.js")
        ),
    }
    command = detect_e2e_command(package)
    dev_server_command = detect_dev_server_command(package)
    has_existing_script = command is not None
    playwright_available = any(detected_playwright.values())

    report = {
        "mode": "browser_inspection_unavailable",
        "detected_playwright": detected_playwright,
        "detected_e2e_command": " ".join(command) if command else None,
        "detected_dev_server_command": dev_server_command,
        "success": False,
        "error_summary": None,
        "suggested_next_action": None,
        "created_at": created_at,
    }

    if not playwright_available:
        report["error_summary"] = "browser_inspection_unavailable"
        report["suggested_next_action"] = "Add Playwright or a browser inspection script in a later frontend/tooling round."
        path = write_report(report)
        update_status(checked_at=created_at)
        return report, path

    if not has_existing_script:
        report["mode"] = "playwright_detected_no_command"
        report["error_summary"] = "No npm run test:e2e or npm run test:ui command was found."
        report["suggested_next_action"] = "Add package.json script test:e2e or test:ui that runs Playwright."
        path = write_report(report)
        update_status(checked_at=created_at)
        return report, path

    report["mode"] = "playwright_command"
    env = dict(os.environ)
    env.setdefault("CI", "false")
    try:
        proc = subprocess.run(
            command,
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=args.timeout_sec,
        )
        output = "\n".join(part for part in (proc.stdout, proc.stderr) if part)
        report["success"] = proc.returncode == 0
        report["error_summary"] = None if proc.returncode == 0 else summarize_command_failure(output)
        report["suggested_next_action"] = (
            "Browser inspection passed."
            if proc.returncode == 0
            else "Inspect Playwright output and enqueue bugfix when failure is actionable."
        )
        report["command_returncode"] = proc.returncode
    except subprocess.TimeoutExpired as exc:
        report["success"] = False
        report["error_summary"] = redact_text(f"browser inspection timed out after {args.timeout_sec}s: {exc}")
        report["suggested_next_action"] = "Reduce browser smoke scope or check whether the dev server can start cleanly."

    path = write_report(report)
    update_status(checked_at=created_at)
    return report, path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run browser inspection using existing Playwright setup")
    parser.add_argument("--json", action="store_true", help="Print report JSON")
    parser.add_argument("--timeout-sec", type=int, default=180)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(normalize_argv(argv if argv is not None else sys.argv[1:]))
    report, path = run_inspection(args)
    status = "OK" if report.get("success") else str(report.get("error_summary") or "NOT_RUN").splitlines()[0]
    print(f"browser_inspection: {report['mode']} {status}")
    print(f"report: {path.relative_to(REPO_ROOT)}")
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
