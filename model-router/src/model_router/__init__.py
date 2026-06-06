"""Model Router package — unified LLM entrypoint."""

from __future__ import annotations

from .chat_types import ChatMessage, ChatOptions, ChatResult, UsageInfo
from .modelRouter import ModelRouter, chat, get_router, reset_router

__all__ = [
    "ChatMessage",
    "ChatOptions",
    "ChatResult",
    "ModelRouter",
    "UsageInfo",
    "chat",
    "get_router",
    "reset_router",
]
