"""Provider adapters: lazy exports to avoid import cycles and speed gate/smoke checks."""

from __future__ import annotations

from typing import TYPE_CHECKING

__all__ = [
    "ControlledRunConfig",
    "ControlledRunManager",
    "CostGuard",
    "CostGuardConfig",
    "CostGuardError",
    "DryRunProvider",
    "FakeProvider",
    "RouterProvider",
    "GenerateOptions",
    "Message",
    "ModelResult",
    "ProviderMode",
    "get_provider",
]

_LAZY = {
    "ControlledRunConfig": (".controlled_run", "ControlledRunConfig"),
    "ControlledRunManager": (".controlled_run", "ControlledRunManager"),
    "CostGuard": (".cost_guard", "CostGuard"),
    "CostGuardConfig": (".cost_guard", "CostGuardConfig"),
    "CostGuardError": (".cost_guard", "CostGuardError"),
    "DryRunProvider": (".dry_run_provider", "DryRunProvider"),
    "FakeProvider": (".fake_provider", "FakeProvider"),
    "RouterProvider": (".router_provider", "RouterProvider"),
    "OpenRouterProvider": (".openrouter_provider", "OpenRouterProvider"),
    "GenerateOptions": (".types", "GenerateOptions"),
    "Message": (".types", "Message"),
    "ModelResult": (".types", "ModelResult"),
    "ProviderMode": (".registry", "ProviderMode"),
    "get_provider": (".registry", "get_provider"),
}


def __getattr__(name: str):
    if name not in _LAZY:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr = _LAZY[name]
    import importlib

    mod = importlib.import_module(module_name, __name__)
    value = getattr(mod, attr)
    globals()[name] = value
    return value


if TYPE_CHECKING:
    from .controlled_run import ControlledRunConfig, ControlledRunManager
    from .cost_guard import CostGuard, CostGuardConfig, CostGuardError
    from .dry_run_provider import DryRunProvider
    from .fake_provider import FakeProvider
    from .openrouter_provider import OpenRouterProvider
    from .router_provider import RouterProvider
    from .registry import ProviderMode, get_provider
    from .types import GenerateOptions, Message, ModelResult
