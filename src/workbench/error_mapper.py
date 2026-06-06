"""Public error mapping for Workbench API responses."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class PublicApiError:
    code: str
    message: str
    hint: str
    http_status: int


_SENSITIVE_PATTERNS = (
    (re.compile(r"(?i)(bearer)\s+[A-Za-z0-9._\-]+"), r"\1 <redacted>"),
    (re.compile(r"(?i)(api[_-]?key|token|cookie|password|secret)\s*[:=]\s*[^,\s]+"), r"\1=<redacted>"),
    (re.compile(r"sk-[A-Za-z0-9_\-]{12,}"), "sk-<redacted>"),
    (re.compile(r"AIza[0-9A-Za-z_\-]{20,}"), "AIza<redacted>"),
)


def _sanitize(message: str) -> str:
    text = str(message or "").strip()
    if not text:
        return "upstream provider error"
    for pattern, replacement in _SENSITIVE_PATTERNS:
        text = pattern.sub(replacement, text)
    if len(text) > 240:
        text = text[:240] + "..."
    return text


def map_provider_error(exc: Exception) -> PublicApiError:
    raw = _sanitize(str(exc) or exc.__class__.__name__)
    lower = raw.lower()
    if "401" in lower or "authentication" in lower or "api key env" in lower:
        return PublicApiError(
            code="auth_error",
            message="上游鉴权失败，无法访问真实 API。",
            hint="请检查本地 API Key 是否可用并确认服务端授权状态。",
            http_status=401,
        )
    if "402" in lower or "insufficient" in lower or "quota" in lower or "credit" in lower or "balance" in lower:
        return PublicApiError(
            code="quota_exceeded",
            message="上游额度不足或配额已用尽。",
            hint="请充值额度或切换到有可用配额的模型配置后重试。",
            http_status=402,
        )
    if "429" in lower or "rate limit" in lower:
        return PublicApiError(
            code="rate_limited",
            message="请求过于频繁，已被上游限流。",
            hint="请稍后重试，或降低并发和请求频率。",
            http_status=429,
        )
    if "timeout" in lower or "timed out" in lower:
        return PublicApiError(
            code="timeout",
            message="上游请求超时。",
            hint="请重试，必要时降低样本长度或切换更稳定模型。",
            http_status=504,
        )
    if "network" in lower or "connection" in lower or "urlerror" in lower or "incompleteread" in lower:
        return PublicApiError(
            code="network_error",
            message="网络连接异常，未能完成上游请求。",
            hint="请检查网络连通性后重试。",
            http_status=503,
        )
    if "400" in lower or "parameter" in lower or "invalid" in lower or "bad request" in lower:
        return PublicApiError(
            code="invalid_request",
            message="请求参数不符合上游接口要求。",
            hint="请检查输入文本、模型参数和请求体格式。",
            http_status=400,
        )
    return PublicApiError(
        code="provider_error",
        message="上游服务调用失败。",
        hint="可稍后重试；若持续失败请检查 provider 配置。",
        http_status=502,
    )
