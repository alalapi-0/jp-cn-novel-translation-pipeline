"""Refuse collection on live data; keep all permitted checks in the synthetic view."""
import importlib.util
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
collect_ignore = ["tests/test_scan_repo_inventory.py"]


def pytest_configure(config):
    config._ln_startup_secret_keys = [key for key in os.environ if key.endswith(("_API_KEY", "_TOKEN"))]
    spec = importlib.util.spec_from_file_location("isolated_test_boundary", ROOT / "scripts/isolated_checks.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    try:
        module.require_view(ROOT)
    except (OSError, ValueError, RuntimeError) as exc:
        raise pytest.UsageError("Use npm run test:py -- tests/ -q (synthetic-only isolation required)") from exc


def pytest_collection_modifyitems(config, items):
    excluded = [item for item in items if item.name == "test_tool_probe_build_report"]
    if excluded:
        config.hook.pytest_deselected(items=excluded)
        items[:] = [item for item in items if item not in excluded]
