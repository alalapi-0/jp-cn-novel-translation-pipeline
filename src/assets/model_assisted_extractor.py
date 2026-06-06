"""Model-assisted asset extraction with strict cost and scope limits."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Callable

from .config import AssetExtractionConfig
from .loader import LoadedChapter
from .rule_based_extractor import extract_all_rule_based
from .types import BaseAsset

_PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "asset_extraction_prompt_v0.1.0.md"


def _api_key_available() -> bool:
    return bool(os.environ.get("OPENROUTER_API_KEY", "").strip())


def _allow_real_api(config: AssetExtractionConfig) -> bool:
    if not config.allow_real_api:
        return False
    if os.environ.get("REAL_API_TESTS_ENABLED", "").strip().lower() not in {
        "1",
        "true",
        "yes",
    }:
        return False
    return _api_key_available()


class ModelAssistedUnavailable(Exception):
    """Raised when model-assisted mode cannot run."""


def _load_prompt_template() -> str:
    if _PROMPT_PATH.is_file():
        return _PROMPT_PATH.read_text(encoding="utf-8")
    return (
        "Extract abstract narrative/game/naming/structure patterns only. "
        "Do not quote source text. Return JSON with assets array."
    )


def _parse_model_assets(raw: str) -> list[dict[str, Any]]:
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    doc = json.loads(text)
    items = doc.get("assets") or doc.get("items") or []
    if not isinstance(items, list):
        return []
    return [x for x in items if isinstance(x, dict)]


def _dict_to_base_asset(item: dict[str, Any]) -> BaseAsset:
    return BaseAsset(
        asset_id=str(item.get("asset_id", "ma-unknown")),
        asset_type=str(item.get("asset_type", "unknown")),
        abstraction_level=item.get("abstraction_level", "medium"),  # type: ignore[arg-type]
        copyright_safety_level=item.get("copyright_safety_level", "caution"),  # type: ignore[arg-type]
        reuse_guidance=str(item.get("reuse_guidance", "")),
        pattern_description=str(item.get("pattern_description", "")),
        generated_examples=[str(x) for x in (item.get("generated_examples") or [])],
        source_chapter_ids=[str(x) for x in (item.get("source_chapter_ids") or [])],
        tags=[str(x) for x in (item.get("tags") or ["model-assisted"])],
    )


def extract_model_assisted(
    chapters: list[LoadedChapter],
    *,
    config: AssetExtractionConfig,
    provider_factory: Callable[..., Any] | None = None,
) -> tuple[dict[str, list[BaseAsset]], int]:
    """Return extracted assets and network call count."""
    if not _allow_real_api(config):
        if not _api_key_available():
            raise ModelAssistedUnavailable(
                "model-assisted mode requires OPENROUTER_API_KEY and "
                "asset_extraction.allow_real_api=true with REAL_API_TESTS_ENABLED=true"
            )
        raise ModelAssistedUnavailable(
            "model-assisted mode blocked by config (allow_real_api=false or REAL_API_TESTS_ENABLED=false)"
        )

    # Bounded request plan: one batch prompt covering limited chapter summary.
    summaries: list[str] = []
    for ch in chapters:
        seg_preview = " | ".join(s.source_text[:40] for s in ch.segments[:3])
        summaries.append(f"{ch.chapter_id}: {seg_preview}")

    prompt = _load_prompt_template()
    user_content = (
        f"{prompt}\n\n"
        "Chapter previews (do NOT quote verbatim in output):\n"
        + "\n".join(summaries)
        + "\n\nReturn JSON: {\"assets\": [...]}"
    )

    network_calls = 0
    if provider_factory is None:
        from providers.cost_guard import CostGuard, CostGuardConfig
        from providers.registry import ProviderMode, get_provider

        guard = CostGuard(CostGuardConfig.from_env())
        provider = get_provider(ProviderMode.REAL, cost_guard=guard)
    else:
        from providers.cost_guard import CostGuard, CostGuardConfig

        provider = provider_factory(CostGuard(CostGuardConfig.from_env()))

    if config.max_requests <= 0:
        raise ModelAssistedUnavailable("max_requests limit reached (0)")

    result = provider.generate(
        [
            {"role": "system", "content": "You abstract reusable creative patterns only."},
            {"role": "user", "content": user_content},
        ],
        options={"max_tokens": 1200},
    )
    network_calls += 1

    raw = result.raw_output or json.dumps(result.parsed_output or {})
    parsed_items = _parse_model_assets(raw)

    buckets: dict[str, list[BaseAsset]] = {
        "narrative": [],
        "game_design": [],
        "naming_pattern": [],
        "chapter_structure": [],
    }
    for item in parsed_items:
        asset = _dict_to_base_asset(item)
        bucket = asset.asset_type if asset.asset_type in buckets else "narrative"
        buckets[bucket].append(asset)

    # Fallback enrich with rule-based if model returns nothing.
    if not any(buckets.values()):
        rb = extract_all_rule_based(chapters)
        for key, items in rb.items():
            buckets[key] = [x for x in items]  # type: ignore[misc]

    return buckets, network_calls
