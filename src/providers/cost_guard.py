"""Budget guard for model runs: token estimate, ceiling, abort on exceed."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .tokens import estimate_cost_usd, estimate_tokens
from .types import Message


class CostGuardError(RuntimeError):
    """Raised when a run would exceed configured budget."""

    def __init__(self, message: str, report: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.report = report or {}


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    return float(raw)


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    return int(raw)


@dataclass
class CostGuardConfig:
    real_api_tests_enabled: bool = False
    max_test_cost_usd: float = 0.0
    max_tokens_per_run: int = 0
    cost_per_million_tokens: float = 0.5
    log_dir: Path = field(default_factory=lambda: Path("workspace/model_runs"))

    @classmethod
    def from_env(cls, log_dir: Path | None = None) -> CostGuardConfig:
        return cls(
            real_api_tests_enabled=_env_bool("REAL_API_TESTS_ENABLED", False),
            max_test_cost_usd=_env_float("MAX_TEST_COST_USD", 0.0),
            max_tokens_per_run=_env_int("MAX_TOKENS_PER_RUN", 0),
            cost_per_million_tokens=_env_float("COST_PER_MILLION_TOKENS", 0.5),
            log_dir=log_dir or Path("workspace/model_runs"),
        )


@dataclass
class CostGuard:
    config: CostGuardConfig
    spent_usd: float = 0.0
    spent_tokens: int = 0
    call_count: int = 0
    aborted: bool = False
    abort_reason: str = ""

    def estimate_call(self, messages: list[Message]) -> tuple[int, float]:
        tokens = estimate_tokens(messages)
        cost = estimate_cost_usd(tokens, self.config.cost_per_million_tokens)
        return tokens, cost

    def check_before_call(self, messages: list[Message]) -> tuple[int, float]:
        if self.aborted:
            raise CostGuardError(
                f"run already aborted: {self.abort_reason}",
                report=self._report_snapshot("already_aborted"),
            )
        tokens, cost = self.estimate_call(messages)
        projected_tokens = self.spent_tokens + tokens
        projected_cost = self.spent_usd + cost

        if self.config.max_tokens_per_run > 0 and projected_tokens > self.config.max_tokens_per_run:
            self._abort(
                "max_tokens_per_run_exceeded",
                tokens=tokens,
                projected_tokens=projected_tokens,
            )
        if self.config.max_test_cost_usd >= 0 and projected_cost > self.config.max_test_cost_usd:
            self._abort(
                "max_test_cost_usd_exceeded",
                tokens=tokens,
                projected_cost=projected_cost,
            )
        return tokens, cost

    def record_call(self, tokens: int, cost_usd: float) -> None:
        self.spent_tokens += tokens
        self.spent_usd = round(self.spent_usd + cost_usd, 8)
        self.call_count += 1

    def allow_real_network(self) -> bool:
        return self.config.real_api_tests_enabled

    def _abort(self, reason: str, **extra: Any) -> None:
        self.aborted = True
        self.abort_reason = reason
        report = self._report_snapshot(reason, **extra)
        self.write_abort_log(report)
        raise CostGuardError(f"cost guard abort: {reason}", report=report)

    def _report_snapshot(self, reason: str, **extra: Any) -> dict[str, Any]:
        return {
            "reason": reason,
            "spent_usd": self.spent_usd,
            "spent_tokens": self.spent_tokens,
            "call_count": self.call_count,
            "max_test_cost_usd": self.config.max_test_cost_usd,
            "max_tokens_per_run": self.config.max_tokens_per_run,
            "real_api_tests_enabled": self.config.real_api_tests_enabled,
            "aborted_at": datetime.now(timezone.utc).isoformat(),
            **extra,
        }

    def write_abort_log(self, report: dict[str, Any]) -> Path:
        self.config.log_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = self.config.log_dir / f"cost_guard_abort_{ts}.json"
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return path
