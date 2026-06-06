"""Unified model router with profile selection and provider fallback."""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config_loader import ProfileConfig, ProviderConfig, RouterConfig, load_router_config
from .errors import ParameterError, ProviderError
from .providers.anthropic import AnthropicProvider
from .providers.base import BaseProvider
from .providers.gemini import GeminiProvider
from .providers.openaiCompatible import OpenAICompatibleProvider
from .chat_types import ChatMessage, ChatOptions, ChatResult

logger = logging.getLogger(__name__)

_router: "ModelRouter | None" = None


@dataclass
class RouteTarget:
    provider_id: str
    model: str
    temperature: float
    max_tokens: int | None
    timeout_sec: int
    max_retries: int


def _normalize_messages(messages: list[ChatMessage] | list[dict[str, str]]) -> list[ChatMessage]:
    out: list[ChatMessage] = []
    for msg in messages:
        if isinstance(msg, ChatMessage):
            out.append(msg)
        elif isinstance(msg, dict):
            out.append(ChatMessage(role=str(msg.get("role", "user")), content=str(msg.get("content", ""))))
        else:
            raise ParameterError("invalid message item", "router")
    return out


class ModelRouter:
    def __init__(self, config: RouterConfig) -> None:
        self.config = config
        self._provider_cache: dict[str, BaseProvider] = {}

    def _build_provider(self, cfg: ProviderConfig) -> BaseProvider:
        ptype = cfg.type.strip().lower()
        if ptype in {"openai_compatible", "openai-compatible", "openai"}:
            return OpenAICompatibleProvider(
                provider_id=cfg.provider_id,
                base_url=cfg.base_url,
                api_key_env=cfg.api_key_env,
                default_headers=cfg.default_headers,
            )
        if ptype == "anthropic":
            return AnthropicProvider(
                provider_id=cfg.provider_id,
                base_url=cfg.base_url or "https://api.anthropic.com/v1",
                api_key_env=cfg.api_key_env,
                api_version=cfg.api_version,
            )
        if ptype in {"gemini", "google"}:
            return GeminiProvider(
                provider_id=cfg.provider_id,
                base_url=cfg.base_url or "https://generativelanguage.googleapis.com/v1beta",
                api_key_env=cfg.api_key_env,
            )
        raise ParameterError(f"unknown provider type: {cfg.type}", cfg.provider_id)

    def _get_provider(self, provider_id: str) -> BaseProvider:
        if provider_id not in self._provider_cache:
            cfg = self.config.providers.get(provider_id)
            if cfg is None:
                raise ParameterError(f"unknown provider: {provider_id}", "router")
            self._provider_cache[provider_id] = self._build_provider(cfg)
        return self._provider_cache[provider_id]

    def _resolve_profile(self, profile_name: str | None) -> ProfileConfig:
        name = profile_name or self.config.default_profile
        profile = self.config.profiles.get(name)
        if profile is None:
            raise ParameterError(f"unknown profile: {name}", "router")
        return profile

    def _build_route_chain(self, profile: ProfileConfig, options: ChatOptions) -> list[RouteTarget]:
        chain: list[RouteTarget] = []

        def add_target(provider_id: str, model: str | None) -> None:
            cfg = self.config.providers.get(provider_id)
            if cfg is None:
                return
            resolved_model = model or profile.model
            timeout = options.timeout_sec or profile.timeout_sec or cfg.timeout_sec
            chain.append(
                RouteTarget(
                    provider_id=provider_id,
                    model=resolved_model,
                    temperature=options.temperature if options.temperature is not None else profile.temperature,
                    max_tokens=options.max_tokens if options.max_tokens is not None else profile.max_tokens,
                    timeout_sec=int(timeout),
                    max_retries=cfg.max_retries,
                )
            )

        primary_provider = options.provider or profile.provider
        primary_model = options.model or profile.model
        add_target(primary_provider, primary_model)

        for fb in profile.fallback:
            if not fb.provider:
                continue
            add_target(fb.provider, fb.model)

        if not chain:
            raise ParameterError("no usable provider in route chain", "router")
        return chain

    def chat(
        self,
        messages: list[ChatMessage] | list[dict[str, str]],
        options: ChatOptions | None = None,
    ) -> ChatResult:
        options = options or ChatOptions()
        normalized = _normalize_messages(messages)
        profile = self._resolve_profile(options.profile)
        chain = self._build_route_chain(profile, options)

        attempted: list[str] = []
        errors: list[str] = []
        last_error: Exception | None = None

        for target in chain:
            attempted.append(target.provider_id)
            provider = self._get_provider(target.provider_id)
            attempts = max(1, target.max_retries + 1)

            for attempt in range(1, attempts + 1):
                try:
                    result = provider.chat(
                        normalized,
                        model=target.model,
                        temperature=target.temperature,
                        max_tokens=target.max_tokens,
                        stream=options.stream,
                        timeout_sec=target.timeout_sec,
                    )
                    result.attempted_providers = list(attempted)
                    return result
                except ParameterError as exc:
                    logger.warning(
                        "model router parameter error provider=%s (no fallback)",
                        exc.provider,
                    )
                    raise RuntimeError(str(exc)) from exc
                except ProviderError as exc:
                    last_error = exc
                    errors.append(str(exc))
                    logger.warning(
                        "model router provider error provider=%s retryable=%s attempt=%s/%s",
                        exc.provider,
                        exc.retryable,
                        attempt,
                        attempts,
                    )
                    if not exc.retryable:
                        break
                    if attempt < attempts:
                        time.sleep(min(30, 2 ** attempt))
                        continue
                    break
                except Exception as exc:  # pragma: no cover - safety net
                    last_error = exc
                    errors.append(str(exc))
                    logger.warning("model router unexpected error provider=%s", target.provider_id)
                    break

        summary = "; ".join(errors[-3:]) if errors else "all providers failed"
        raise RuntimeError(f"model router exhausted fallback chain: {summary}") from last_error


def get_router(config_path: Path | None = None) -> ModelRouter:
    global _router
    if _router is None:
        path = config_path
        if path is None:
            env_path = os.environ.get("MODEL_ROUTER_CONFIG_PATH", "").strip()
            if env_path:
                path = Path(env_path)
        _router = ModelRouter(load_router_config(path))
    return _router


def reset_router() -> None:
    """Clear cached router (for tests)."""
    global _router
    _router = None


def chat(
    messages: list[ChatMessage] | list[dict[str, str]],
    options: ChatOptions | None = None,
    *,
    profile: str | None = None,
    model: str | None = None,
    provider: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    stream: bool = False,
    timeout_sec: int | None = None,
) -> ChatResult:
    """Module-level convenience wrapper around ``ModelRouter.chat``."""
    opts = options or ChatOptions()
    if profile is not None:
        opts.profile = profile
    if model is not None:
        opts.model = model
    if provider is not None:
        opts.provider = provider
    if temperature is not None:
        opts.temperature = temperature
    if max_tokens is not None:
        opts.max_tokens = max_tokens
    if stream:
        opts.stream = stream
    if timeout_sec is not None:
        opts.timeout_sec = timeout_sec
    return get_router().chat(messages, opts)
