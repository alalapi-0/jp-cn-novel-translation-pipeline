#!/usr/bin/env python3
"""Unified real API smoke-test entrypoint.

Default mode is dry-run or missing_api_key. Real network calls require --real
and a supported project provider key. This script never reads .env files and
never prints API keys.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RUNTIME_DIR = REPO_ROOT / ".agent_runtime"
REPORT_DIR = RUNTIME_DIR / "real_api_reports"
STATUS_PATH = RUNTIME_DIR / "status.json"
sys.path.insert(0, str(REPO_ROOT / "src"))

from workbench.api_status import build_api_status, detected_providers  # noqa: E402

SMOKE_MESSAGES = [{"role": "user", "content": "Reply exactly: smoke_ok"}]


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
    return value[:1000]


def ensure_runtime() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (RUNTIME_DIR / "logs").mkdir(parents=True, exist_ok=True)


def write_report(report: dict) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = REPORT_DIR / f"real_api_smoke_{ts}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def update_status(*, api_mode: str, checked_at: str) -> None:
    if not STATUS_PATH.exists():
        return
    try:
        status = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return
    if not isinstance(status, dict):
        return
    status["api_mode"] = api_mode
    status["last_real_api_check_at"] = checked_at
    status["updated_at"] = checked_at
    STATUS_PATH.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def base_report(*, mode: str, detected: list[str], created_at: str) -> dict:
    return {
        "mode": mode,
        "detected_providers": detected,
        "tested_provider": None,
        "success": False,
        "error_summary": None,
        "result_summary": None,
        "created_at": created_at,
    }


def run_dry_run(report: dict, *, max_cost_usd: float, max_tokens: int) -> dict:
    sys.path.insert(0, str(REPO_ROOT / "src"))
    from providers.cost_guard import CostGuard, CostGuardConfig
    from providers.dry_run_provider import DryRunProvider
    from providers.types import GenerateOptions, Message

    guard = CostGuard(
        CostGuardConfig(
            real_api_tests_enabled=False,
            max_test_cost_usd=max_cost_usd,
            max_tokens_per_run=max_tokens,
            log_dir=RUNTIME_DIR / "logs",
        )
    )
    provider = DryRunProvider(cost_guard=guard)
    result = provider.generate(
        [Message(**message) for message in SMOKE_MESSAGES],
        GenerateOptions(pipeline_stage="real_api_smoke", input_reference="agent_foundation"),
    )
    report.update(
        {
            "tested_provider": provider.provider_id,
            "success": True,
            "result_summary": {
                "dry_run": True,
                "estimated_tokens": result.estimated_tokens,
                "cost_estimate_usd": result.cost_estimate_usd,
                "network_calls": provider.network_calls,
            },
        }
    )
    return report


def run_openrouter_real(report: dict, *, max_cost_usd: float, max_tokens: int, timeout_sec: int) -> dict:
    sys.path.insert(0, str(REPO_ROOT / "src"))
    from providers.cost_guard import CostGuard, CostGuardConfig
    from providers.openrouter_provider import OpenRouterProvider
    from providers.types import GenerateOptions, Message

    guard = CostGuard(
        CostGuardConfig(
            real_api_tests_enabled=True,
            max_test_cost_usd=max_cost_usd,
            max_tokens_per_run=max_tokens,
            log_dir=RUNTIME_DIR / "logs",
        )
    )
    provider = OpenRouterProvider(
        cost_guard=guard,
        model_name=os.environ.get("OPENROUTER_SMOKE_MODEL") or os.environ.get("DRAFT_MODEL"),
        timeout_sec=timeout_sec,
        max_tokens=min(max_tokens, 64),
        temperature=0.0,
    )
    result = provider.generate(
        [Message(**message) for message in SMOKE_MESSAGES],
        GenerateOptions(pipeline_stage="real_api_smoke", input_reference="agent_foundation"),
    )
    report.update(
        {
            "tested_provider": provider.provider_id,
            "success": True,
            "result_summary": {
                "model_name": result.model_name,
                "usage": result.usage,
                "cost_estimate_usd": result.cost_estimate_usd,
                "latency_ms": result.latency_ms,
                "output_chars": len(result.raw_output or ""),
                "output_preview": redact_text((result.raw_output or "")[:80]),
            },
        }
    )
    return report


def run_smoke(args: argparse.Namespace) -> tuple[dict, Path]:
    ensure_runtime()
    created_at = iso_now()
    detected = detected_providers()
    if not detected:
        report = base_report(mode="missing_api_key", detected=detected, created_at=created_at)
        report["error_summary"] = "missing_api_key"
        report["result_summary"] = "No supported API key was found in environment variables; no network attempted."
        path = write_report(report)
        update_status(api_mode="missing_api_key", checked_at=created_at)
        return report, path

    if not args.real:
        report = base_report(mode="dry_run", detected=detected, created_at=created_at)
        try:
            report = run_dry_run(report, max_cost_usd=args.max_cost_usd, max_tokens=args.max_tokens)
        except Exception as exc:  # noqa: BLE001
            report["error_summary"] = redact_text(str(exc))
            report["result_summary"] = "Dry-run smoke failed before any network call."
        path = write_report(report)
        update_status(api_mode="dry_run", checked_at=created_at)
        return report, path

    report = base_report(mode="real_api", detected=detected, created_at=created_at)
    if "openrouter" not in detected:
        report["error_summary"] = "no_supported_project_real_api_client"
        report["result_summary"] = (
            "Detected key(s), but this repository currently exposes only a safe OpenRouter "
            "project provider for real smoke tests. No network attempted."
        )
        path = write_report(report)
        update_status(api_mode="real_api_unavailable", checked_at=created_at)
        return report, path

    try:
        report = run_openrouter_real(
            report,
            max_cost_usd=args.max_cost_usd,
            max_tokens=args.max_tokens,
            timeout_sec=args.timeout_sec,
        )
    except Exception as exc:  # noqa: BLE001
        report["tested_provider"] = "openrouter"
        report["error_summary"] = redact_text(str(exc))
        report["result_summary"] = "Real OpenRouter smoke failed; full response body was not saved."
    path = write_report(report)
    update_status(api_mode="real_api", checked_at=created_at)
    return report, path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Unified real API smoke-test entrypoint")
    parser.add_argument("--real", action="store_true", help="Allow one low-cost real API smoke call")
    parser.add_argument("--status-only", action="store_true", help="Print current API key / mode probe only")
    parser.add_argument("--json", action="store_true", help="Print redacted report JSON")
    parser.add_argument("--max-cost-usd", type=float, default=0.01)
    parser.add_argument("--max-tokens", type=int, default=64)
    parser.add_argument("--timeout-sec", type=int, default=45)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(normalize_argv(argv if argv is not None else sys.argv[1:]))
    status_probe = build_api_status(REPO_ROOT)
    if args.status_only:
        if args.json:
            print(json.dumps(status_probe, ensure_ascii=False, indent=2))
        else:
            print(
                f"api_status: mode={status_probe['api_mode']} "
                f"has_key={status_probe['has_api_key']} "
                f"real_enabled={status_probe['real_api_tests_enabled']} "
                f"providers={','.join(status_probe['detected_providers']) or 'none'}"
            )
        return 0

    report, path = run_smoke(args)
    ok = report.get("success")
    status = "OK" if ok else str(report.get("error_summary") or report.get("mode") or "NOT_RUN")
    print(f"real_api_smoke: {report['mode']} {status}")
    print(
        f"api_status: mode={status_probe['api_mode']} "
        f"has_key={status_probe['has_api_key']} "
        f"real_enabled={status_probe['real_api_tests_enabled']}"
    )
    print(f"report: {path.relative_to(REPO_ROOT)}")
    summary = report.get("result_summary")
    if summary and not args.json:
        print(f"summary: {summary}")
    if args.json:
        print(json.dumps({"smoke": report, "api_status": status_probe}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
