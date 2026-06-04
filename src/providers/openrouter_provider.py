"""OpenRouter real provider: OpenAI-compatible chat completions."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from http.client import IncompleteRead
from typing import Any

from .cost_guard import CostGuard
from .tokens import estimate_cost_usd, estimate_tokens
from .types import GenerateOptions, Message, ModelResult

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "deepseek/deepseek-v4-pro"


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
        self.cost_guard = cost_guard
        self.model_name = model_name or os.environ.get("DRAFT_MODEL", DEFAULT_MODEL)
        key = api_key or os.environ.get("OPENROUTER_API_KEY", "")
        if not key.strip():
            raise RuntimeError(
                "OPENROUTER_API_KEY is not set; configure locally in .env (never commit)"
            )
        self._api_key = key.strip()
        self.timeout_sec = timeout_sec
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.network_calls = 0

    def generate(self, messages: list[Message], options: GenerateOptions | None = None) -> ModelResult:
        options = options or GenerateOptions()
        est_tokens, est_cost = (0, 0.0)
        if self.cost_guard is not None:
            est_tokens, est_cost = self.cost_guard.check_before_call(messages)

        payload = {
            "model": self.model_name,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": self.temperature,
        }
        if self.max_tokens is not None:
            payload["max_tokens"] = self.max_tokens
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/light-novel-pipeline",
            "X-Title": "light_novel controlled draft",
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(OPENROUTER_URL, data=body, headers=headers, method="POST")

        started = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_sec) as resp:
                raw_bytes = resp.read()
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"OpenRouter HTTP {exc.code}: {err_body}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"OpenRouter network error: {exc.reason}") from exc
        except (IncompleteRead, TimeoutError, OSError) as exc:
            raise RuntimeError(f"OpenRouter network error: {exc}") from exc

        latency_ms = int((time.perf_counter() - started) * 1000)
        self.network_calls += 1
        data: dict[str, Any] = json.loads(raw_bytes.decode("utf-8"))
        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError("OpenRouter response missing choices")
        raw_output = choices[0].get("message", {}).get("content", "") or ""
        usage = data.get("usage") or {}
        prompt_tokens = int(usage.get("prompt_tokens") or est_tokens)
        completion_tokens = int(usage.get("completion_tokens") or max(1, len(raw_output) // 4))
        total_tokens = int(usage.get("total_tokens") or prompt_tokens + completion_tokens)
        cost = estimate_cost_usd(
            total_tokens,
            self.cost_guard.config.cost_per_million_tokens if self.cost_guard else 0.5,
        )

        if self.cost_guard is not None:
            self.cost_guard.record_call(total_tokens, cost)

        result = ModelResult(
            provider_id=self.provider_id,
            model_name=self.model_name,
            raw_output=raw_output,
            parsed_output={"raw": raw_output},
            usage={
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
            },
            cost_estimate_usd=cost,
            estimated_tokens=total_tokens,
            latency_ms=latency_ms,
            dry_run=False,
        )
        result.mark_finished("ok")
        self._write_model_run(result, options)
        return result

    def _write_model_run(self, result: ModelResult, options: GenerateOptions) -> None:
        log_dir = (
            self.cost_guard.config.log_dir
            if self.cost_guard is not None
            else __import__("pathlib").Path("workspace/model_runs")
        )
        log_dir.mkdir(parents=True, exist_ok=True)
        path = log_dir / f"{result.model_run_id}.json"
        payload = {
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
