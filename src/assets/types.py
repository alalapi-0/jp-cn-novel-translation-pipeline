"""Schema types for translation-derived asset extraction."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

AbstractionLevel = Literal["high", "medium", "low"]
CopyrightSafetyLevel = Literal["safe", "caution", "unsafe"]
ExtractionMode = Literal["rule-based", "model-assisted"]


@dataclass(kw_only=True)
class BaseAsset:
    asset_id: str
    asset_type: str
    abstraction_level: AbstractionLevel
    copyright_safety_level: CopyrightSafetyLevel
    reuse_guidance: str
    pattern_description: str
    generated_examples: list[str] = field(default_factory=list)
    source_chapter_ids: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    safety_notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(kw_only=True)
class NarrativeAsset(BaseAsset):
    asset_type: str = "narrative"
    narrative_role: str = ""
    structural_pattern: str = ""


@dataclass(kw_only=True)
class GameDesignAsset(BaseAsset):
    asset_type: str = "game_design"
    mechanism_category: str = ""
    abstraction_scope: str = ""


@dataclass(kw_only=True)
class NamingPatternAsset(BaseAsset):
    asset_type: str = "naming_pattern"
    pattern_kind: str = ""
    linguistic_markers: list[str] = field(default_factory=list)


@dataclass(kw_only=True)
class ChapterStructureAsset(BaseAsset):
    asset_type: str = "chapter_structure"
    chapter_function: str = ""
    hook_type: str = ""
    pacing_notes: str = ""


@dataclass
class AssetExtractionRun:
    run_id: str
    source_run_id: str
    mode: ExtractionMode
    chapters_processed: list[str]
    created_at: str
    config_snapshot: dict[str, Any]
    stats: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SafetyCheckResult:
    asset_id: str
    asset_type: str
    passed: bool
    violations: list[str] = field(default_factory=list)
    copyright_safety_level: CopyrightSafetyLevel = "safe"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
