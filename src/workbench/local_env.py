"""Load unset environment variables from repo-root .env (never print values)."""

from __future__ import annotations

import os
from pathlib import Path

_APPLIED_KEYS: list[str] | None = None


def _effective_env(key: str) -> str | None:
    """Return trimmed env value, or None when unset/blank."""
    val = os.environ.get(key)
    if val is None:
        return None
    stripped = str(val).strip()
    return stripped if stripped else None


def reset_local_env_cache() -> None:
    """Clear apply cache (tests only)."""
    global _APPLIED_KEYS
    _APPLIED_KEYS = None


def apply_local_env(repo_root: Path, *, force: bool = False) -> list[str]:
    """Set unset env vars from ``repo_root/.env``. Returns applied key names only."""
    global _APPLIED_KEYS
    if not force and _APPLIED_KEYS is not None:
        return list(_APPLIED_KEYS)
    env_path = repo_root / ".env"
    if not env_path.is_file():
        _APPLIED_KEYS = []
        return []
    applied: list[str] = []
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        value = value.strip()
        if not value:
            continue
        if _effective_env(key) is not None:
            continue
        os.environ[key] = value
        applied.append(key)
    _APPLIED_KEYS = applied
    return list(applied)


def applied_local_env_keys() -> list[str]:
    """Return keys applied from the last ``apply_local_env`` call in this process."""
    return list(_APPLIED_KEYS or [])
