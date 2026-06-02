"""Lightweight token estimation (no external tokenizer dependency)."""

from __future__ import annotations

from .types import Message


def estimate_tokens(messages: list[Message]) -> int:
    """Rough token count: ~4 chars per token for mixed CJK/Latin text."""
    total_chars = sum(len(m.content) for m in messages)
    return max(1, (total_chars + 3) // 4)


def estimate_cost_usd(tokens: int, cost_per_million_tokens: float = 0.5) -> float:
    return round(tokens * cost_per_million_tokens / 1_000_000, 8)
