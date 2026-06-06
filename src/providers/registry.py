"""Provider registry: resolve fake / dry-run / real by mode and env."""

from __future__ import annotations

from enum import Enum

from .cost_guard import CostGuard, CostGuardConfig
from .dry_run_provider import DryRunProvider
from .fake_provider import FakeProvider
from .router_provider import RouterProvider


class ProviderMode(str, Enum):
    FAKE = "fake"
    DRY_RUN = "dry_run"
    REAL = "real"


def get_provider(
    mode: ProviderMode,
    *,
    cost_guard: CostGuard | None = None,
    guard_config: CostGuardConfig | None = None,
) -> FakeProvider | DryRunProvider | RouterProvider:
    guard = cost_guard or CostGuard(guard_config or CostGuardConfig.from_env())

    if mode == ProviderMode.FAKE:
        return FakeProvider(cost_guard=guard)
    if mode == ProviderMode.DRY_RUN:
        return DryRunProvider(cost_guard=guard)
    if mode == ProviderMode.REAL:
        if not guard.allow_real_network():
            raise RuntimeError(
                "real provider blocked: REAL_API_TESTS_ENABLED is false (default). "
                "Enable only with explicit user authorization."
            )
        return RouterProvider(cost_guard=guard)
    raise ValueError(f"unknown provider mode: {mode}")
