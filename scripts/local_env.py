"""Load unset environment variables from repo-root .env (never print values)."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from workbench.local_env import (  # noqa: E402
    applied_local_env_keys,
    apply_local_env,
    reset_local_env_cache,
)

__all__ = ["apply_local_env", "applied_local_env_keys", "reset_local_env_cache"]
