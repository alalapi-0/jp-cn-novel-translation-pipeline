"""Runtime API key / smoke status for Workbench UI (no .env reads, no secret values)."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from providers.cost_guard import CostGuardConfig
from workbench.local_env import apply_local_env, applied_local_env_keys
from workbench.pipeline_status import build_pipeline_status, resolve_workbench_mode

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


BLOCK_REASON_LABELS: dict[str, str] = {
    "missing_api_key": "未配置 API Key",
    "real_api_tests_disabled": "REAL_API_TESTS_ENABLED 未开启",
    "max_test_cost_usd_zero": "MAX_TEST_COST_USD=0（页面真实 API 需 >0，例如 0.01）",
    "no_openrouter_key": "缺少 OPENROUTER_API_KEY",
}


def workbench_real_api_block_reason_label(reason: str | None) -> str | None:
    if not reason:
        return None
    return BLOCK_REASON_LABELS.get(reason, reason)


def workbench_real_api_fix_command(block_reason: str | None) -> str | None:
    if block_reason == "max_test_cost_usd_zero":
        return "export MAX_TEST_COST_USD=0.01  # 然后重启 npm run dev:frontend"
    if block_reason == "real_api_tests_disabled":
        return "export REAL_API_TESTS_ENABLED=true MAX_TEST_COST_USD=0.01"
    if block_reason == "missing_api_key" or block_reason == "no_openrouter_key":
        return "export OPENROUTER_API_KEY=your_key REAL_API_TESTS_ENABLED=true MAX_TEST_COST_USD=0.01"
    return None


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


def _pipeline_gate_summary(repo_root: Path) -> dict[str, Any] | None:
    gate_script = repo_root / "scripts" / "throughput_gate.py"
    if not gate_script.is_file():
        return None
    try:
        import importlib.util
        import sys

        spec = importlib.util.spec_from_file_location("throughput_gate_status", gate_script)
        if not spec or not spec.loader:
            return None
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
        result = mod.evaluate_gate()
        return {
            "decision": result.get("decision"),
            "exportable_chapters": result.get("exportable_chapters"),
            "draft_completed_chapters": result.get("draft_completed_chapters"),
            "legacy_refined_exportable_chapters": result.get("refined_exportable_chapters"),
            "active_worker_count": result.get("active_worker_count"),
            "blocks": result.get("blocks") or [],
            "soft_blocks": result.get("soft_blocks") or [],
            "hard_blocks": result.get("hard_blocks") or result.get("blocks") or [],
            "warnings": (result.get("warnings") or [])[:8],
            "fix_paths": result.get("fix_paths") or [],
            "stage_state_run_id": result.get("stage_state_run_id"),
            "stage_state_source": result.get("stage_state_source"),
            "has_api_key": result.get("has_api_key"),
        }
    except Exception:
        return None


def build_api_status(repo_root: Path) -> dict[str, Any]:
    dotenv_keys = apply_local_env(repo_root)
    detected = detected_providers()
    real_enabled = _truthy("REAL_API_TESTS_ENABLED")
    mode = resolve_api_mode(real_api_tests_enabled=real_enabled)
    guard = CostGuardConfig.from_env()
    ready, block_reason = workbench_real_api_ready()
    latest = _latest_smoke_report(repo_root)
    runtime_mode = _status_file_api_mode(repo_root)
    configured_env_vars = [
        env_name for env_name in PROVIDER_ENV.values() if os.environ.get(env_name, "").strip()
    ]
    payload: dict[str, Any] = {
        "env_keys_applied_from_dotenv": dotenv_keys,
        "api_mode": mode,
        "detected_providers": detected,
        "real_api_tests_enabled": real_enabled,
        "has_api_key": bool(detected),
        "configured_env_vars": configured_env_vars,
        "max_test_cost_usd": guard.max_test_cost_usd,
        "max_tokens_per_run": guard.max_tokens_per_run,
        "workbench_real_api_ready": ready,
        "workbench_real_api_block_reason": block_reason,
        "workbench_real_api_block_reason_label": workbench_real_api_block_reason_label(block_reason),
        "workbench_real_api_fix_command": workbench_real_api_fix_command(block_reason),
        "api_key_configured": bool(detected),
        "checked_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "config_hint": (
            "Key 在 .env 或 shell 中配置；页面真实 API 另需 REAL_API_TESTS_ENABLED=true 且 MAX_TEST_COST_USD>0；"
            "smoke：python3 scripts/run_real_api_smoke.py --real"
        ),
    }
    if runtime_mode and runtime_mode != mode:
        payload["runner_status_note"] = (
            f"Agent runner 上次记录 api_mode={runtime_mode}（历史状态，不代表当前 shell/env）"
        )
    else:
        payload["runner_status_note"] = None
    env_ready = bool(detected) and real_enabled and guard.max_test_cost_usd > 0
    if latest:
        smoke_success = bool(latest.get("success"))
        ignorable = env_ready and not smoke_success
        payload["last_smoke"] = {
            "mode": latest.get("mode"),
            "success": smoke_success,
            "created_at": latest.get("created_at"),
            "tested_provider": latest.get("tested_provider"),
            "result_summary": latest.get("result_summary"),
            "error_summary": latest.get("error_summary"),
            "historical": True,
            "ignorable": ignorable,
            "ignorable_note": (
                "当前环境已就绪，可忽略历史 smoke 失败"
                if ignorable
                else None
            ),
        }
    else:
        payload["last_smoke"] = None
    pipeline = _pipeline_gate_summary(repo_root)
    if pipeline:
        payload["pipeline_gate"] = pipeline
    payload["workbench_mode"] = resolve_workbench_mode(repo_root)
    payload["pipeline_status"] = build_pipeline_status(repo_root)
    return payload
