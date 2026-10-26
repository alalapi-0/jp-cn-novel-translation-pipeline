"""Bridge model-router into legacy provider.generate() interface."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from contextlib import contextmanager

from .cost_guard import CostGuard, CostGuardConfig
from .tokens import estimate_cost_usd
from .types import GenerateOptions, Message, ModelResult

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_MODEL_ROUTER_SRC = _REPO_ROOT / "model-router" / "src"


def _ensure_model_router_path() -> None:
    path = str(_MODEL_ROUTER_SRC)
    if path not in sys.path:
        sys.path.insert(0, path)


class RouterProvider:
    """Real-network provider that delegates to modelRouter.chat()."""

    provider_id = "model_router"

    def __init__(
        self,
        *,
        cost_guard: CostGuard | None = None,
        profile: str | None = None,
        model_name: str | None = None,
        provider: str | None = None,
        timeout_sec: int | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> None:
        _ensure_model_router_path()
        from model_router import ChatOptions, chat  # noqa: WPS433

        self._chat = chat
        self._ChatOptions = ChatOptions
        self.cost_guard = cost_guard or CostGuard(CostGuardConfig.from_env())
        self.profile = profile or os.environ.get("MODEL_ROUTER_DEFAULT_PROFILE") or "draft_translation"
        self.model_name = model_name or os.environ.get("DRAFT_MODEL", "")
        self.provider_override = provider
        self.timeout_sec = timeout_sec
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.network_calls = 0

    def generate(self, messages: list[Message], options: GenerateOptions | None = None) -> ModelResult:
        options = options or GenerateOptions()
        if not isinstance(options, GenerateOptions):
            raise ValueError('registered content entry requires typed GenerateOptions')
        self.cost_guard.require_content_entry(options.pipeline_stage)

        profile = self._resolve_profile(options)
        chat_opts = self._ChatOptions(
            profile=profile,
            model=self.model_name or None,
            provider=self.provider_override,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            timeout_sec=self.timeout_sec,
            attempt_context=self._attempt_context,
        )

        payload = [{"role": m.role, "content": m.content} for m in messages]
        result = self._chat(payload, chat_opts)

        usage = result.usage.to_dict()
        usage["budget_reserved_tokens"] = self._last_reservation["reserved_tokens"]
        usage["budget_cumulative_reserved_tokens"] = self.cost_guard.spent_tokens
        usage["budget_cumulative_attempts"] = self.cost_guard.call_count
        total_tokens = int(usage.get("total_tokens") or usage["budget_reserved_tokens"])
        cost = estimate_cost_usd(
            total_tokens,
            self.cost_guard.config.cost_per_million_tokens if self.cost_guard else 0.5,
        )

        model_result = ModelResult(
            provider_id=result.provider,
            model_name=result.model,
            raw_output=result.content,
            parsed_output={"raw": result.content},
            usage=usage,
            cost_estimate_usd=cost,
            estimated_tokens=total_tokens,
            latency_ms=result.latency_ms,
            dry_run=False,
        )
        model_result.mark_finished("ok")
        self._write_model_run(model_result, options)
        return model_result

    @contextmanager
    def _attempt_context(self, messages, target):
        with self.cost_guard.attempt(messages, target.max_tokens,
                                     provider_id=target.provider_id, model_name=target.model) as reservation:
            self._last_reservation = reservation
            self.network_calls += 1
            yield reservation

    def _resolve_profile(self, options: GenerateOptions) -> str:
        stage = (options.pipeline_stage or "").strip().lower()
        if stage in {"refinement", "refine", "stage_c"}:
            return "legacy_refinement"
        if stage in {"draft_translation", "translation", "draft"}:
            return "draft_translation"
        return self.profile

    def _write_model_run(self, result: ModelResult, options: GenerateOptions) -> None:
        log_dir = (
            self.cost_guard.config.log_dir
            if self.cost_guard is not None
            else Path("workspace/model_runs")
        )
        log_dir.mkdir(parents=True, exist_ok=True)
        path = log_dir / f"{result.model_run_id}.json"
        payload: dict[str, Any] = {
            "model_run_id": result.model_run_id,
            "provider_id": result.provider_id,
            "model_name": result.model_name,
            "pipeline_stage": options.pipeline_stage,
            "input_reference": options.input_reference,
            "usage": result.usage,
            "cost_estimate_usd": result.cost_estimate_usd,
            "latency_ms": result.latency_ms,
            "status": result.status,
            "started_at": result.started_at.isoformat() if result.started_at else None,
            "finished_at": result.finished_at.isoformat() if result.finished_at else None,
            "request_hash": result.request_hash or "",
            "request_hash_version": 1,
            "prompt_version": options.prompt_version,
            "api_mode": "real" if not result.dry_run else "dry_run",
            "production_eligible": options.metadata.get("production_eligible", True),
            "raw_output_chars": len(result.raw_output),
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
