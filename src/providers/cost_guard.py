"""Budget guard for model runs: token estimate, ceiling, abort on exceed."""

from __future__ import annotations

import json
import os
import math
import time
import tempfile
import fcntl
import hashlib
from contextlib import contextmanager
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

    # A durable ledger scopes one run. Reuse its path on every resume.
    attempt_ledger_path: Path | None = None
    max_calls_per_run: int = 8
    max_duration_sec: float = 1200.0
    deadline_at_unix: float | None = None

    @classmethod
    def from_env(cls, log_dir: Path | None = None) -> CostGuardConfig:
        return cls(
            real_api_tests_enabled=_env_bool("REAL_API_TESTS_ENABLED", False),
            max_test_cost_usd=_env_float("MAX_TEST_COST_USD", 0.0),
            max_tokens_per_run=_env_int("MAX_TOKENS_PER_RUN", 0),
            max_calls_per_run=_env_int("MAX_CALLS_PER_RUN", 8),
            max_duration_sec=_env_float("MAX_RUN_DURATION_SEC", 1200.0),
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
    # Bound by a trusted local content entrypoint, never from HTTP/model text.
    content_unit_lease: Any = field(default=None, repr=False)

    def require_content_entry(self, stage: str) -> None:
        # Only repository technical probes bypass source admission; their paid
        # permission, tokens, cost, attempts and time still use the real guard.
        if stage not in {'real_api_smoke', 'openrouter_smoke'} and self.content_unit_lease is None:
            raise CostGuardError('content dispatch requires a bound full-source unit budget')

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

    def _attempt_limits(self) -> dict[str, Any]:
        cfg = self.config
        if self.aborted:
            raise CostGuardError(f"run already aborted: {self.abort_reason}")
        if cfg.real_api_tests_enabled is not True:
            raise CostGuardError("real network not authorized: REAL_API_TESTS_ENABLED is false")
        for name in ("max_test_cost_usd", "cost_per_million_tokens", "max_duration_sec"):
            value = getattr(cfg, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise CostGuardError(f"real attempt requires positive finite {name}")
        for name in ("max_tokens_per_run", "max_calls_per_run"):
            value = getattr(cfg, name)
            if type(value) is not int or value <= 0:
                raise CostGuardError(f"real attempt requires positive finite {name}")
        if cfg.deadline_at_unix is not None and (not math.isfinite(cfg.deadline_at_unix) or cfg.deadline_at_unix <= 0):
            raise CostGuardError("invalid absolute attempt deadline")
        return {name: getattr(cfg, name) for name in (
            "max_test_cost_usd", "max_tokens_per_run", "cost_per_million_tokens",
            "max_calls_per_run", "max_duration_sec", "deadline_at_unix")}

    def _save_attempts(self, path: Path, state: dict[str, Any]) -> None:
        """Durable atomic replacement; no dispatch if pre-call persistence fails."""
        fd, temporary = tempfile.mkstemp(prefix=".attempt-", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(state, handle, ensure_ascii=False, allow_nan=False)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
            directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def _load_attempts(self, path: Path, limits: dict[str, Any]) -> dict[str, Any]:
        if not path.exists():
            if self.call_count:
                raise CostGuardError("durable attempt ledger disappeared")
            return {"schema": 1, "limits": limits, "started_at_unix": time.time(),
                    "call_count": 0, "spent_tokens": 0, "spent_usd": 0.0, "attempts": [],
                    "aborted": False, "abort_reason": ""}
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
            if state["schema"] != 1 or state["limits"] != limits:
                raise ValueError("attempt ledger version or budget identity changed")
            if type(state["aborted"]) is not bool or not isinstance(state["abort_reason"], str):
                raise ValueError("missing abort identity")
            attempts = state["attempts"]
            if not isinstance(attempts, list) or type(state["call_count"]) is not int or state["call_count"] != len(attempts):
                raise ValueError("invalid attempt count")
            for number, row in enumerate(attempts, 1):
                if not isinstance(row["request_sha256"], str) or len(row["request_sha256"]) != 64:
                    raise ValueError("missing request identity")
                if type(row["retry_eligible"]) is not bool:
                    raise ValueError("missing retry classification")
                if row["id"] != number or row["status"] not in {"reserved", "succeeded", "failed", "interrupted"}:
                    raise ValueError("invalid attempt identity")
                if type(row["reserved_tokens"]) is not int or row["reserved_tokens"] <= 0:
                    raise ValueError("invalid reserved tokens")
                if not math.isfinite(row["reserved_usd"]) or row["reserved_usd"] <= 0:
                    raise ValueError("invalid reserved cost")
            if state["spent_tokens"] != sum(a["reserved_tokens"] for a in attempts):
                raise ValueError("invalid cumulative tokens")
            if state["spent_usd"] != math.fsum(a["reserved_usd"] for a in attempts):
                raise ValueError("invalid cumulative cost")
            if not math.isfinite(state["started_at_unix"]):
                raise ValueError("invalid start time")
            return state
        except (ValueError, KeyError, TypeError) as exc:
            raise CostGuardError("invalid or incompatible durable attempt ledger") from exc

    @contextmanager
    def attempt(self, messages: list[Message], max_output_tokens: int | None, *,
                provider_id: str = "unknown", model_name: str = "unknown"):
        lease = self.content_unit_lease
        if lease is None:
            with self._physical_attempt(messages, max_output_tokens,
                    provider_id=provider_id, model_name=model_name) as row:
                yield row
        else:
            self._attempt_limits()
            with lease.physical_attempt(messages) as remaining:
                with self._physical_attempt(messages, max_output_tokens,
                        provider_id=provider_id, model_name=model_name) as row:
                    row['timeout_sec'] = min(row['timeout_sec'], remaining)
                    yield row

    @contextmanager
    def _physical_attempt(self, messages: list[Message], max_output_tokens: int | None, *,
                          provider_id: str, model_name: str):
        """Reserve before each physical provider invocation, including retries.

        Failed/unknown usage retains the full reservation. Input UTF-8 bytes plus
        framing is a conservative estimate, not a verified provider tokenizer;
        configured price is an estimate, not proof of actual invoiced cost.
        """
        limits = self._attempt_limits()
        if type(max_output_tokens) is not int or max_output_tokens <= 0:
            raise CostGuardError("real attempt requires a positive output token limit")
        # Do not use the old 4-CJK-characters/token estimate for real reservations.
        input_tokens = 16 + sum(len(m.content.encode("utf-8")) + len(m.role.encode("utf-8")) + 32 for m in messages)
        tokens = input_tokens + max_output_tokens
        cost = tokens * limits["cost_per_million_tokens"] / 1_000_000
        if not math.isfinite(cost) or cost <= 0:
            raise CostGuardError("invalid attempt cost reservation")
        request_sha256 = hashlib.sha256(json.dumps(
            [{"role": m.role, "content": m.content} for m in messages],
            ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
        path = self.config.attempt_ledger_path or self.config.log_dir / "attempt_budget.json"
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path.with_name(path.name + ".lock"), "a+b") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise CostGuardError("attempt budget is in use by another invocation") from exc
            try:
                state = self._load_attempts(path, limits)
                self.call_count = state["call_count"]
                self.spent_tokens = state["spent_tokens"]
                self.spent_usd = state["spent_usd"]
                if state["aborted"]:
                    raise CostGuardError("durable budget aborted: " + state["abort_reason"])
                elapsed = time.time() - state["started_at_unix"]
                if elapsed < 0 or elapsed >= limits["max_duration_sec"]:
                    raise CostGuardError("attempt duration exhausted or clock moved backwards")
                remaining = limits["max_duration_sec"] - elapsed
                if limits["deadline_at_unix"] is not None:
                    remaining = min(remaining, limits["deadline_at_unix"] - time.time())
                    if remaining <= 0:
                        raise CostGuardError("absolute attempt deadline exhausted")
                previous = [a for a in state["attempts"] if a["request_sha256"] == request_sha256]
                # Only one extra same-input attempt after a classified transient
                # response. Unknown delivery, interruptions and success are not
                # evidence for replay. This survives a new router/Agent process.
                if previous and (len(previous) >= 2 or not previous[-1]["retry_eligible"]):
                    raise CostGuardError("same-input retry has no transient evidence or is exhausted")
                if self.call_count >= limits["max_calls_per_run"]:
                    raise CostGuardError("physical attempt count exhausted")
                if self.spent_tokens + tokens > limits["max_tokens_per_run"]:
                    raise CostGuardError("input plus output token reservation exceeds budget")
                if math.fsum([self.spent_usd, cost]) > limits["max_test_cost_usd"]:
                    raise CostGuardError("input plus output cost reservation exceeds budget")
                row = {"id": self.call_count + 1, "status": "reserved",
                       "reserved_tokens": tokens, "reserved_usd": cost,
                       "request_sha256": request_sha256, "retry_eligible": False,
                       "provider_id": provider_id, "model_name": model_name,
                       "max_output_tokens": max_output_tokens,
                       "timeout_sec": remaining}
                state["attempts"].append(row)
                state["call_count"] += 1
                state["spent_tokens"] += tokens
                state["spent_usd"] = math.fsum(a["reserved_usd"] for a in state["attempts"])
                self._save_attempts(path, state)
                self.call_count = state["call_count"]
                self.spent_tokens = state["spent_tokens"]
                self.spent_usd = state["spent_usd"]
                try:
                    yield row
                    observed = row.get("observed_usage", {})
                    if any(type(v) is not int or v < 0 for v in observed.values()):
                        raise CostGuardError("invalid provider usage")
                    total = max(observed.get("total_tokens", 0),
                                observed.get("prompt_tokens", 0) + observed.get("completion_tokens", 0))
                    if total > tokens or observed.get("completion_tokens", 0) > max_output_tokens:
                        row["reserved_tokens"] = max(tokens, total)
                        row["reserved_usd"] = row["reserved_tokens"] * limits["cost_per_million_tokens"] / 1_000_000
                        state["spent_tokens"] = sum(a["reserved_tokens"] for a in state["attempts"])
                        state["spent_usd"] = math.fsum(a["reserved_usd"] for a in state["attempts"])
                        self.spent_tokens, self.spent_usd = state["spent_tokens"], state["spent_usd"]
                        state["aborted"], state["abort_reason"] = True, "provider_usage_overrun"
                        raise CostGuardError("provider usage exceeded the reserved token allowance")
                except BaseException as exc:
                    row["status"] = "failed" if isinstance(exc, Exception) else "interrupted"
                    cause = exc
                    seen_causes = set()
                    while cause is not None and id(cause) not in seen_causes:
                        seen_causes.add(id(cause))
                        status = getattr(cause, "status_code", None)
                        if type(status) is int and (status == 429 or 500 <= status <= 599):
                            row["retry_eligible"] = True
                            break
                        cause = cause.__cause__
                    self._save_attempts(path, state)
                    raise
                else:
                    row["status"] = "succeeded"
                    self._save_attempts(path, state)
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

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
