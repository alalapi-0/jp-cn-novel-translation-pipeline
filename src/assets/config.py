"""Load asset extraction settings from project.yaml."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class AssetExtractionConfig:
    enabled: bool = False
    default_mode: str = "rule-based"
    allow_real_api: bool = False
    max_chapters: int = 5
    max_segments: int = 50
    max_requests: int = 5
    write_to_public_asset_library: bool = False


def load_asset_extraction_config(repo_root: Path) -> AssetExtractionConfig:
    path = repo_root / "project.yaml"
    if not path.is_file():
        return AssetExtractionConfig()
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    section: dict[str, Any] = raw.get("asset_extraction") or {}
    return AssetExtractionConfig(
        enabled=bool(section.get("enabled", False)),
        default_mode=str(section.get("default_mode", "rule-based")),
        allow_real_api=bool(section.get("allow_real_api", False)),
        max_chapters=int(section.get("max_chapters", 5)),
        max_segments=int(section.get("max_segments", 50)),
        max_requests=int(section.get("max_requests", 5)),
        write_to_public_asset_library=bool(
            section.get("write_to_public_asset_library", False)
        ),
    )
