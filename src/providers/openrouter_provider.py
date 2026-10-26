"""OpenRouter provider — legacy adapter delegating to model-router openai_compatible."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from .cost_guard import CostGuard, CostGuardConfig
from .tokens import estimate_cost_usd
from .types import GenerateOptions, Message, ModelResult

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_MODEL_ROUTER_SRC = _REPO_ROOT / "model-router" / "src"
DEFAULT_MODEL = "deepseek/deepseek-v4-pro"


def _ensure_model_router_path() -> None:
    path = str(_MODEL_ROUTER_SRC)
    if path not in sys.path:
        sys.path.insert(0, path)


class OpenRouterProvider:
    provider_id = "openrouter"
    model_name: str

    def __init__(
        self,
        *,
        cost_guard: CostGuard | None = None,
        model_name: str | None = None,
        api_key: str | None = None,
        timeout_sec: int = 600,
        max_tokens: int | None = None,
        temperature: float = 0.3,
    ) -> None:
        _ensure_model_router_path()
        from model_router.providers.openaiCompatible import OpenAICompatibleProvider  # noqa: WPS433

        self.cost_guard = cost_guard or CostGuard(CostGuardConfig.from_env())
        self.model_name = model_name or os.environ.get("DRAFT_MODEL", DEFAULT_MODEL)
        key_env = "OPENROUTER_API_KEY"
        if api_key:
            os.environ.setdefault(key_env, api_key.strip())
        elif not os.environ.get(key_env, "").strip():
            raise RuntimeError(
                "OPENROUTER_API_KEY is not set; configure locally in .env (never commit)"
            )
        self._inner = OpenAICompatibleProvider(
            provider_id=self.provider_id,
            base_url="https://openrouter.ai/api/v1",
            api_key_env=key_env,
            default_headers={
                "HTTP-Referer": "https://github.com/light-novel-pipeline",
                "X-Title": "light_novel controlled draft",
            },
        )
        self.timeout_sec = timeout_sec
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.network_calls = 0

    def generate(self, messages: list[Message], options: GenerateOptions | None = None) -> ModelResult:
        from model_router import ChatMessage  # noqa: WPS433

        options = options or GenerateOptions()
        if not isinstance(options, GenerateOptions):
            raise ValueError('registered content entry requires typed GenerateOptions')
        self.cost_guard.require_content_entry(options.pipeline_stage)

        chat_messages = [ChatMessage(role=m.role, content=m.content) for m in messages]
        with self.cost_guard.attempt(messages, self.max_tokens,
                                     provider_id=self.provider_id, model_name=self.model_name) as reservation:
            self.network_calls += 1
            try:
                result = self._inner.chat(
                    chat_messages,
                    model=self.model_name,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                    stream=False,
                    timeout_sec=min(self.timeout_sec, reservation["timeout_sec"]),
                )
            except Exception as exc:
                raise RuntimeError(str(exc)) from exc
            reservation["observed_usage"] = result.usage.to_dict()

        usage = result.usage.to_dict()
        usage["budget_reserved_tokens"] = reservation["reserved_tokens"]
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
            "finished_at": result.finished_at.isoformat() if result.finished_at else None,
            "raw_output_chars": len(result.raw_output),
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
