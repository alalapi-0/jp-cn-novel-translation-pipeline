"""Load models.yaml and apply environment overrides."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover - stdlib fallback for minimal installs
    yaml = None  # type: ignore[assignment]


@dataclass
class ProviderConfig:
    provider_id: str
    type: str
    base_url: str = ""
    api_key_env: str = ""
    timeout_sec: int = 600
    max_retries: int = 0
    default_headers: dict[str, str] = field(default_factory=dict)
    api_version: str = "2023-06-01"


@dataclass
class ProfileFallback:
    provider: str
    model: str | None = None


@dataclass
class ProfileConfig:
    name: str
    provider: str
    model: str
    temperature: float = 0.3
    max_tokens: int | None = None
    timeout_sec: int | None = None
    fallback: list[ProfileFallback] = field(default_factory=list)


@dataclass
class RouterConfig:
    default_profile: str
    profiles: dict[str, ProfileConfig]
    providers: dict[str, ProviderConfig]
    config_path: Path


def default_config_path() -> Path:
    env_path = os.environ.get("MODEL_ROUTER_CONFIG_PATH", "").strip()
    if env_path:
        return Path(env_path).expanduser().resolve()
    return Path(__file__).resolve().parent.parent.parent / "config" / "models.yaml"


def _parse_yaml_text(text: str) -> dict[str, Any]:
    if yaml is not None:
        loaded = yaml.safe_load(text)
        return loaded if isinstance(loaded, dict) else {}
    return _parse_minimal_yaml(text)


def _parse_minimal_yaml(text: str) -> dict[str, Any]:
    """Very small YAML subset parser for environments without PyYAML."""
    # Prefer PyYAML in production; this keeps router usable with zero extra deps.
    import json

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    raise RuntimeError(
        "PyYAML is required to parse models.yaml. Install with: pip install pyyaml"
    )


def load_router_config(config_path: Path | None = None) -> RouterConfig:
    path = (config_path or default_config_path()).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"model router config not found: {path}")

    raw = _parse_yaml_text(path.read_text(encoding="utf-8"))
    default_profile = os.environ.get("MODEL_ROUTER_DEFAULT_PROFILE") or raw.get(
        "default_profile", "coding"
    )

    providers: dict[str, ProviderConfig] = {}
    for pid, pdata in (raw.get("providers") or {}).items():
        if not isinstance(pdata, dict):
            continue
        providers[str(pid)] = ProviderConfig(
            provider_id=str(pid),
            type=str(pdata.get("type") or "openai_compatible"),
            base_url=str(pdata.get("base_url") or ""),
            api_key_env=str(pdata.get("api_key_env") or ""),
            timeout_sec=int(pdata.get("timeout_sec") or 600),
            max_retries=int(pdata.get("max_retries") or 0),
            default_headers=dict(pdata.get("default_headers") or {}),
            api_version=str(pdata.get("api_version") or "2023-06-01"),
        )

    profiles: dict[str, ProfileConfig] = {}
    for name, pdata in (raw.get("profiles") or {}).items():
        if not isinstance(pdata, dict):
            continue
        fallback_raw = pdata.get("fallback") or []
        fallback: list[ProfileFallback] = []
        for item in fallback_raw:
            if isinstance(item, dict):
                fallback.append(
                    ProfileFallback(
                        provider=str(item.get("provider") or ""),
                        model=item.get("model"),
                    )
                )
        profiles[str(name)] = ProfileConfig(
            name=str(name),
            provider=str(pdata.get("provider") or ""),
            model=str(pdata.get("model") or ""),
            temperature=float(pdata.get("temperature", 0.3)),
            max_tokens=pdata.get("max_tokens"),
            timeout_sec=pdata.get("timeout_sec"),
            fallback=fallback,
        )

    return RouterConfig(
        default_profile=str(default_profile),
        profiles=profiles,
        providers=providers,
        config_path=path,
    )
