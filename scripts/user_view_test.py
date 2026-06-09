#!/usr/bin/env python3
"""User-view smoke checks for light_novel workbench (dry-run, no real API/publish)."""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REPORT_PATH = REPO_ROOT / "reports" / "user_view_test.json"
DEFAULT_URL = "http://127.0.0.1:5174/"
FRONTEND_FILES = (
    REPO_ROOT / "frontend" / "index.html",
    REPO_ROOT / "frontend" / "review.html",
    REPO_ROOT / "frontend" / "issues.html",
)


def _port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1.5):
            return True
    except OSError:
        return False


def _http_get(url: str) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            body = resp.read(8000).decode("utf-8", errors="replace")
            return resp.status, body
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(2000).decode("utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001
        return 0, str(exc)


def _spawn_dev_server(timeout_sec: int = 45) -> subprocess.Popen[str] | None:
    """Start serve_frontend.py in background; caller must terminate."""
    cmd = [sys.executable, str(REPO_ROOT / "scripts" / "serve_frontend.py"), "--port", "5174"]
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=REPO_ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except OSError:
        return None
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            return None
        if _port_open("127.0.0.1", 5174):
            return proc
        time.sleep(0.3)
    proc.terminate()
    return None


def run_checks(base_url: str = DEFAULT_URL, *, spawned_server: bool = False) -> dict:
    checks: list[dict] = []
    for path in FRONTEND_FILES:
        ok = path.is_file()
        checks.append(
            {
                "name": f"static_file_{path.name}",
                "passed": ok,
                "detail": str(path.relative_to(REPO_ROOT)) if ok else "missing",
            }
        )

    host = "127.0.0.1"
    port = 5174
    server_up = _port_open(host, port)
    checks.append(
        {
            "name": "dev_server_port",
            "passed": server_up,
            "detail": f"{host}:{port} {'open' if server_up else 'closed — run npm run dev:frontend'}",
        }
    )

    if server_up:
        status, body = _http_get(base_url)
        checks.append(
            {
                "name": "homepage_http",
                "passed": status == 200,
                "detail": f"status={status}, len={len(body)}",
            }
        )
        checks.append(
            {
                "name": "homepage_has_title",
                "passed": "<title" in body.lower() or "workbench" in body.lower(),
                "detail": "basic HTML content present",
            }
        )
    else:
        checks.append(
            {
                "name": "homepage_http",
                "passed": False,
                "skipped": True,
                "detail": "dev server not running",
            }
        )

    pw_config = REPO_ROOT / "playwright.config.ts"
    checks.append(
        {
            "name": "playwright_config",
            "passed": pw_config.is_file(),
            "detail": _rel(pw_config),
        }
    )

    passed = sum(1 for c in checks if c.get("passed"))
    failed = [c["name"] for c in checks if not c.get("passed") and not c.get("skipped")]
    return {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "base_url": base_url,
        "spawned_dev_server": spawned_server,
        "status": "passed" if not failed else "partial",
        "passed_count": passed,
        "failed": failed,
        "checks": checks,
        "next_steps": [
            "Start dev server: npm run dev:frontend",
            "Run browser MCP or npm run test:ui for full user-view validation",
        ],
    }


def _rel(p: Path) -> str:
    try:
        return str(p.relative_to(REPO_ROOT))
    except ValueError:
        return str(p)


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="User-view smoke checks")
    parser.add_argument("--spawn-dev-server", action="store_true", help="Start dev server (bounded wait)")
    parser.add_argument("--spawn-timeout", type=int, default=45)
    args = parser.parse_args()

    proc: subprocess.Popen[str] | None = None
    spawned = False
    try:
        if args.spawn_dev_server and not _port_open("127.0.0.1", 5174):
            proc = _spawn_dev_server(timeout_sec=args.spawn_timeout)
            spawned = proc is not None
        report = run_checks(spawned_server=spawned)
    finally:
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"user_view_test: {report['status']} ({report['passed_count']} checks OK)")
    print(f"report: {REPORT_PATH.relative_to(REPO_ROOT)}")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
