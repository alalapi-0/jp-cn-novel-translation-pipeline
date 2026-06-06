"""Provider error classification for fallback decisions."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ProviderError(Exception):
    """Base provider error."""

    message: str
    provider: str
    status_code: int | None = None
    retryable: bool = True

    def __str__(self) -> str:
        code = f" HTTP {self.status_code}" if self.status_code else ""
        return f"[{self.provider}]{code}: {self.message}"


class ParameterError(ProviderError):
    """Invalid request parameters — do not fallback."""

    retryable: bool = False


class AuthenticationError(ProviderError):
    """Invalid or missing credentials — may fallback to another provider."""


class InsufficientCreditsError(ProviderError):
    """Account balance / quota exhausted."""


class RegionBlockedError(ProviderError):
    """Region or policy restriction."""


class RateLimitError(ProviderError):
    """Rate limit exceeded."""


class ServerError(ProviderError):
    """Upstream 5xx server error."""


class TimeoutError(ProviderError):
    """Request timed out."""


class NetworkError(ProviderError):
    """Transport-level failure."""


def classify_http_error(provider: str, status_code: int, message: str) -> ProviderError:
    """Map HTTP status to a typed provider error."""
    safe_msg = _sanitize_message(message)
    if status_code == 400:
        return ParameterError(safe_msg, provider, status_code)
    if status_code == 401:
        return AuthenticationError(safe_msg, provider, status_code)
    if status_code == 402:
        return InsufficientCreditsError(safe_msg, provider, status_code)
    if status_code == 403:
        return RegionBlockedError(safe_msg, provider, status_code)
    if status_code == 429:
        return RateLimitError(safe_msg, provider, status_code)
    if 500 <= status_code <= 599:
        return ServerError(safe_msg, provider, status_code)
    if status_code >= 400:
        return ProviderError(safe_msg, provider, status_code, retryable=False)
    return ProviderError(safe_msg, provider, status_code)


def _sanitize_message(message: str) -> str:
    """Strip potentially sensitive fragments from error text."""
    text = (message or "").strip()
    if len(text) > 500:
        text = text[:500] + "…"
    return text
