"""Safety validator for abstracted translation-derived assets."""

from __future__ import annotations

import re
from typing import Any

from .types import BaseAsset, CopyrightSafetyLevel, SafetyCheckResult

MAX_PATTERN_DESCRIPTION_LEN = 500
MAX_EXAMPLE_LEN = 200
MAX_TOTAL_EXAMPLES_LEN = 600
MAX_SOURCE_SPECIFIC_NAMES = 3
SOURCE_OVERLAP_MIN_CHARS = 12
SOURCE_OVERLAP_RATIO = 0.55

_REQUIRED_FIELDS = ("abstraction_level", "copyright_safety_level", "reuse_guidance")

_KATAKANA_NAME_RE = re.compile(r"[ァ-ヴー]{3,}")
_LATIN_BRAND_RE = re.compile(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b")
_CJK_LONG_PHRASE_RE = re.compile(r"[\u4e00-\u9fff\u3040-\u30ff]{8,}")

_NARRATIVE_RETELLING_MARKERS = (
    "然后",
    "接着",
    "随后",
    "与此同时",
    "その後",
    "そして",
    "chapter summary",
    "章节内容",
    "故事讲述了",
)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", "", (text or "").strip())


def _longest_common_substring_ratio(a: str, b: str) -> float:
    na, nb = _normalize(a), _normalize(b)
    if not na or not nb:
        return 0.0
    shorter, longer = (na, nb) if len(na) <= len(nb) else (nb, na)
    best = 0
    for i in range(len(shorter)):
        for j in range(i + 1, len(shorter) + 1):
            frag = shorter[i:j]
            if len(frag) < SOURCE_OVERLAP_MIN_CHARS:
                continue
            if frag in longer:
                best = max(best, len(frag))
    return best / max(len(shorter), 1)


def _count_source_specific_names(text: str) -> int:
    names = set()
    for m in _KATAKANA_NAME_RE.finditer(text):
        names.add(m.group(0))
    for m in _LATIN_BRAND_RE.finditer(text):
        names.add(m.group(0))
    return len(names)


def _looks_like_retelling(description: str, examples: list[str]) -> bool:
    blob = f"{description} {' '.join(examples)}".lower()
    hits = sum(1 for marker in _NARRATIVE_RETELLING_MARKERS if marker in blob)
    if hits >= 2:
        return True
    long_phrases = _CJK_LONG_PHRASE_RE.findall(description)
    return len(long_phrases) >= 4 and len(description) > 280


def validate_asset(
    asset: BaseAsset | dict[str, Any],
    *,
    source_corpus: str = "",
) -> SafetyCheckResult:
    if isinstance(asset, BaseAsset):
        data = asset.to_dict()
        asset_id = asset.asset_id
        asset_type = asset.asset_type
    else:
        data = asset
        asset_id = str(data.get("asset_id", "unknown"))
        asset_type = str(data.get("asset_type", "unknown"))

    violations: list[str] = []
    safety_level: CopyrightSafetyLevel = data.get("copyright_safety_level", "unsafe")  # type: ignore[assignment]

    for field in _REQUIRED_FIELDS:
        value = data.get(field)
        if not value or not str(value).strip():
            violations.append(f"missing_required_field:{field}")

    description = str(data.get("pattern_description", ""))
    examples = [str(x) for x in (data.get("generated_examples") or [])]

    if len(description) > MAX_PATTERN_DESCRIPTION_LEN:
        violations.append("long_text:pattern_description")

    if _looks_like_retelling(description, examples) and asset_type == "narrative":
        violations.append("narrative_retelling_not_pattern")

    total_example_len = 0
    for idx, example in enumerate(examples):
        if len(example) > MAX_EXAMPLE_LEN:
            violations.append(f"long_text:generated_examples[{idx}]")
        total_example_len += len(example)
        if source_corpus and example.strip():
            ratio = _longest_common_substring_ratio(example, source_corpus)
            if ratio >= SOURCE_OVERLAP_RATIO:
                violations.append(f"example_from_source:generated_examples[{idx}]")
    if total_example_len > MAX_TOTAL_EXAMPLES_LEN:
        violations.append("long_text:generated_examples_total")

    name_blob = " ".join(
        [
            description,
            " ".join(examples),
            str(data.get("pattern_kind", "")),
            str(data.get("structural_pattern", "")),
        ]
    )
    if _count_source_specific_names(name_blob) > MAX_SOURCE_SPECIFIC_NAMES:
        violations.append("too_many_source_specific_names")

    if safety_level == "unsafe":
        violations.append("copyright_safety_level:unsafe")

    passed = len(violations) == 0 and safety_level in ("safe", "caution")
    return SafetyCheckResult(
        asset_id=asset_id,
        asset_type=asset_type,
        passed=passed,
        violations=violations,
        copyright_safety_level=safety_level,
    )


def validate_assets(
    assets: list[BaseAsset | dict[str, Any]],
    *,
    source_corpus: str = "",
) -> list[SafetyCheckResult]:
    return [validate_asset(a, source_corpus=source_corpus) for a in assets]


def partition_by_safety(
    assets: list[BaseAsset],
    results: list[SafetyCheckResult],
) -> tuple[list[BaseAsset], list[BaseAsset]]:
    by_id = {r.asset_id: r for r in results}
    safe: list[BaseAsset] = []
    blocked: list[BaseAsset] = []
    for asset in assets:
        result = by_id.get(asset.asset_id)
        if result and result.passed and result.copyright_safety_level != "unsafe":
            safe.append(asset)
        else:
            blocked.append(asset)
    return safe, blocked
