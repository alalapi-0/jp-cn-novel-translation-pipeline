"""Real API sample segment generation for Workbench (low-cost, opt-in)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from workbench.api_status import resolve_api_mode
from workbench.dry_run_generate import _split_paragraphs

MAX_PARAGRAPHS = 3
MAX_CHARS_PER_PARA = 400


def real_api_available() -> bool:
    return resolve_api_mode() == "real_api"


def generate_segments_real_api(
    *,
    sample_text: str,
    language_direction: str = "JP_TO_CN",
    repo_root: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not real_api_available():
        raise ValueError(
            "real_api_unavailable: configure OPENROUTER_API_KEY and REAL_API_TESTS_ENABLED=true"
        )
    from providers.cost_guard import CostGuard, CostGuardConfig
    from providers.openrouter_provider import OpenRouterProvider
    from providers.types import GenerateOptions, Message

    paragraphs = _split_paragraphs(sample_text)[:MAX_PARAGRAPHS]
    if not paragraphs:
        raise ValueError("sample_text is required")
    for para in paragraphs:
        if len(para) > MAX_CHARS_PER_PARA:
            raise ValueError(
                f"paragraph too long (max {MAX_CHARS_PER_PARA} chars for real API sample)"
            )

    guard = CostGuard(
        CostGuardConfig(
            real_api_tests_enabled=True,
            max_test_cost_usd=float(os.environ.get("MAX_TEST_COST_USD", "0.05")),
            max_tokens_per_run=int(os.environ.get("MAX_TOKENS_PER_RUN", "2048")),
            log_dir=repo_root / ".agent_runtime" / "logs",
        )
    )
    provider = OpenRouterProvider(
        cost_guard=guard,
        max_tokens=512,
        temperature=0.3,
    )
    direction = language_direction.upper()
    target_lang = "Chinese" if direction.startswith("JP") else "Japanese"
    segments: list[dict[str, Any]] = []
    meta: dict[str, Any] = {
        "provider": provider.provider_id,
        "model": provider.model_name,
        "network_calls": 0,
    }

    for idx, para in enumerate(paragraphs, start=1):
        prompt = (
            f"Translate the following text to {target_lang}. "
            f"Return only the translation, no explanation.\n\n{para}"
        )
        result = provider.generate(
            [Message(role="user", content=prompt)],
            GenerateOptions(pipeline_stage="workbench_real_sample", input_reference=f"seg-{idx}"),
        )
        seg_id = f"seg-{idx:03d}"
        segments.append(
            {
                "id": seg_id,
                "segment_id": seg_id,
                "chapter": 1,
                "source": para,
                "draft": (result.raw_output or "").strip(),
                "status": "pending",
                "generated_by": "real_api",
            }
        )
    meta["network_calls"] = provider.network_calls
    return segments, meta
