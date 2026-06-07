#!/usr/bin/env python3
"""Minimal OpenRouter smoke test: one short completion under cost guard.

Loads .env into os.environ when variables are unset (never prints values).
Exit: 0=ok (real or dry-run), 2=blocked / misconfiguration.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from local_env import apply_local_env, applied_local_env_keys  # noqa: E402

from providers.cost_guard import CostGuard, CostGuardConfig  # noqa: E402
from providers.dry_run_provider import DryRunProvider  # noqa: E402
from providers.types import GenerateOptions, Message  # noqa: E402

SMOKE_DIR = REPO_ROOT / "workspace" / "smoke"
RUNTIME_DIR = REPO_ROOT / ".agent_runtime"
STATUS_PATH = RUNTIME_DIR / "status.json"
DEFAULT_PROMPT = "Reply with exactly: smoke_ok"


def update_agent_runtime_status(*, api_mode: str, checked_at: str) -> None:
    if not STATUS_PATH.is_file():
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


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def run_smoke(*, max_cost_usd: float, force_dry_run: bool) -> dict:
    applied_keys = apply_local_env(REPO_ROOT)
    has_key = bool(os.environ.get("OPENROUTER_API_KEY", "").strip())
    real_enabled = _env_bool("REAL_API_TESTS_ENABLED", False)

    mode = "dry_run"
    if has_key and real_enabled and not force_dry_run:
        mode = "real"

    SMOKE_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report_path = SMOKE_DIR / f"openrouter_smoke_{ts}.json"

    guard = CostGuard(
        CostGuardConfig(
            real_api_tests_enabled=mode == "real",
            max_test_cost_usd=max_cost_usd,
            max_tokens_per_run=800,
            log_dir=REPO_ROOT / "workspace" / "model_runs",
        )
    )

    payload: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "env_keys_applied_from_dotenv": applied_keys,
        "real_api_tests_enabled": real_enabled,
        "openrouter_key_present": has_key,
        "max_test_cost_usd": max_cost_usd,
    }

    if mode == "dry_run":
        provider = DryRunProvider(cost_guard=guard)
        result = provider.generate(
            [Message(role="user", content=DEFAULT_PROMPT)],
            GenerateOptions(pipeline_stage="openrouter_smoke", input_reference="round_51"),
        )
        payload.update(
            {
                "provider_id": result.provider_id,
                "dry_run": True,
                "estimated_tokens": result.estimated_tokens,
                "cost_estimate_usd": result.cost_estimate_usd,
                "message": "dry-run smoke OK (enable REAL_API_TESTS_ENABLED + OPENROUTER_API_KEY for real)",
            }
        )
        report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return payload

    from providers.openrouter_provider import OpenRouterProvider

    provider = OpenRouterProvider(
        cost_guard=guard,
        model_name=os.environ.get("DRAFT_MODEL", "deepseek/deepseek-v4-flash"),
        timeout_sec=120,
    )
    result = provider.generate(
        [Message(role="user", content=DEFAULT_PROMPT)],
        GenerateOptions(pipeline_stage="openrouter_smoke", input_reference="round_51"),
    )
    snippet = (result.raw_output or "")[:120]
    payload.update(
        {
            "provider_id": result.provider_id,
            "model_name": result.model_name,
            "latency_ms": result.latency_ms,
            "usage": result.usage,
            "cost_estimate_usd": result.cost_estimate_usd,
            "network_calls": provider.network_calls,
            "output_snippet": snippet,
            "message": "real API smoke OK",
        }
    )
    report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if mode == "real":
        update_agent_runtime_status(api_mode="real_api", checked_at=payload["generated_at"])
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="OpenRouter one-shot smoke test")
    parser.add_argument(
        "--max-cost-usd",
        type=float,
        default=0.05,
        help="Cost guard ceiling for this smoke run",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Force dry-run even when REAL_API_TESTS_ENABLED and key are set",
    )
    parser.add_argument("--json", action="store_true", help="Print redacted JSON summary to stdout")
    args = parser.parse_args(argv)

    try:
        summary = run_smoke(max_cost_usd=args.max_cost_usd, force_dry_run=args.dry_run)
    except Exception as exc:  # noqa: BLE001
        print(f"openrouter_smoke: BLOCKED — {exc}", file=sys.stderr)
        return 2

    label = summary.get("mode", "unknown")
    print(f"openrouter_smoke: {label.upper()} — {summary.get('message', 'done')}")
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
