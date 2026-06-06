"""Runtime API key / smoke status for Workbench UI (no .env reads, no secret values)."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from providers.cost_guard import CostGuardConfig

PROVIDER_ENV = {
    "openai": "OPENAI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "stability": "STABILITY_API_KEY",
    "xai": "XAI_API_KEY",
}


def _truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def detected_providers() -> list[str]:
    return [
        provider
        for provider, env_name in PROVIDER_ENV.items()
        if bool(os.environ.get(env_name, "").strip())
    ]


def resolve_api_mode(*, real_api_tests_enabled: bool | None = None) -> str:
    detected = detected_providers()
    if not detected:
        return "missing_api_key"
    enabled = _truthy("REAL_API_TESTS_ENABLED") if real_api_tests_enabled is None else real_api_tests_enabled
    return "dry_run" if not enabled else "real_api"


def workbench_real_api_ready() -> tuple[bool, str | None]:
    """Return whether Workbench page/API may call real providers, and block reason if not."""
    mode = resolve_api_mode()
    if mode == "missing_api_key":
        return False, "missing_api_key"
    if mode == "dry_run":
        return False, "real_api_tests_disabled"
    guard = CostGuardConfig.from_env()
    if guard.max_test_cost_usd <= 0:
        return False, "max_test_cost_usd_zero"
    if "openrouter" not in detected_providers():
        return False, "no_openrouter_key"
    return True, None


def _latest_smoke_report(repo_root: Path) -> dict[str, Any] | None:
    report_dir = repo_root / ".agent_runtime" / "real_api_reports"
    if not report_dir.is_dir():
        return None
    paths = sorted(report_dir.glob("real_api_smoke_*.json"))
    if not paths:
        return None
    try:
        data = json.loads(paths[-1].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _status_file_api_mode(repo_root: Path) -> str | None:
    path = repo_root / ".agent_runtime" / "status.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    mode = str(data.get("api_mode") or "").strip()
    return mode or None


def build_api_status(repo_root: Path) -> dict[str, Any]:
    detected = detected_providers()
    real_enabled = _truthy("REAL_API_TESTS_ENABLED")
    mode = resolve_api_mode(real_api_tests_enabled=real_enabled)
    guard = CostGuardConfig.from_env()
    ready, block_reason = workbench_real_api_ready()
    latest = _latest_smoke_report(repo_root)
    runtime_mode = _status_file_api_mode(repo_root)
    configured_env_vars = [env_name for env_name in PROVIDER_ENV.values() if os.environ.get(env_name, "").strip()]
    payload: dict[str, Any] = {
        "api_mode": mode,
        "detected_providers": detected,
        "real_api_tests_enabled": real_enabled,
        "has_api_key": bool(detected),
        "configured_env_vars": configured_env_vars,
        "max_test_cost_usd": guard.max_test_cost_usd,
        "max_tokens_per_run": guard.max_tokens_per_run,
        "workbench_real_api_ready": ready,
        "workbench_real_api_block_reason": block_reason,
        "checked_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "config_hint": (
            "Put OPENROUTER_API_KEY in repo .env (local only) or export it; "
            "set REAL_API_TESTS_ENABLED=true and MAX_TEST_COST_USD>0; run: "
            "python3 scripts/run_real_api_smoke.py --real"
        ),
    }
    if runtime_mode and runtime_mode != mode:
        payload["runner_status_note"] = (
            f"Agent runner 上次记录 api_mode={runtime_mode}（历史状态，不代表当前 shell/env）"
        )
    else:
        payload["runner_status_note"] = None
    if latest:
        payload["last_smoke"] = {
            "mode": latest.get("mode"),
            "success": latest.get("success"),
            "created_at": latest.get("created_at"),
            "tested_provider": latest.get("tested_provider"),
            "result_summary": latest.get("result_summary"),
            "error_summary": latest.get("error_summary"),
            "historical": True,
        }
    else:
        payload["last_smoke"] = None
    return payload
