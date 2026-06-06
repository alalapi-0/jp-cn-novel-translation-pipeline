"""Orchestrate translation-derived asset extraction runs."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .asset_safety_validator import partition_by_safety, validate_assets
from .config import AssetExtractionConfig, load_asset_extraction_config
from .loader import (
    apply_segment_limit,
    collect_source_corpus,
    load_segments_doc,
    resolve_source_run_root,
    select_chapters,
)
from .model_assisted_extractor import ModelAssistedUnavailable, extract_model_assisted
from .rule_based_extractor import extract_all_rule_based
from .types import AssetExtractionRun, BaseAsset


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_jsonl(path: Path, items: list[BaseAsset]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for item in items:
            handle.write(json.dumps(item.to_dict(), ensure_ascii=False) + "\n")


def _render_safety_report(
    results: list,
    *,
    safe_count: int,
    blocked_count: int,
    write_public: bool,
) -> str:
    lines = [
        "# Abstraction Safety Report",
        "",
        f"- Safe assets: {safe_count}",
        f"- Blocked assets: {blocked_count}",
        f"- Public library write: {'yes' if write_public else 'no (default)'}",
        "",
        "## Violations",
    ]
    for r in results:
        if r.violations:
            lines.append(f"- `{r.asset_id}` ({r.asset_type}): {', '.join(r.violations)}")
    if safe_count and not any(r.violations for r in results):
        lines.append("- (none)")
    return "\n".join(lines) + "\n"


def _render_quality_report(stats: dict[str, Any], mode: str) -> str:
    return "\n".join(
        [
            "# Extraction Quality Report",
            "",
            f"- Mode: {mode}",
            f"- Chapters processed: {stats.get('chapters_processed', 0)}",
            f"- Segments processed: {stats.get('segments_processed', 0)}",
            f"- Assets extracted: {stats.get('assets_total', 0)}",
            f"- Assets passed safety: {stats.get('assets_safe', 0)}",
            f"- API calls: {stats.get('api_calls', 0)}",
            "",
            "## By category",
            f"- narrative: {stats.get('narrative', 0)}",
            f"- game_design: {stats.get('game_design', 0)}",
            f"- naming_pattern: {stats.get('naming_pattern', 0)}",
            f"- chapter_structure: {stats.get('chapter_structure', 0)}",
            "",
        ]
    )


def run_asset_extraction(
    *,
    repo_root: Path,
    source_run: str,
    output_dir: Path | None = None,
    mode: str = "rule-based",
    chapters_spec: str | None = "1-5",
    config: AssetExtractionConfig | None = None,
    run_id: str | None = None,
    provider_factory: Callable[..., Any] | None = None,
    dry_run_model: bool = False,
) -> dict[str, Any]:
    cfg = config or load_asset_extraction_config(repo_root)
    if mode not in {"rule-based", "model-assisted"}:
        raise ValueError(f"unsupported mode: {mode}")

    source_root = resolve_source_run_root(repo_root, source_run)
    doc = load_segments_doc(source_root)
    chapters = select_chapters(
        doc,
        chapters_spec=chapters_spec,
        max_chapters=cfg.max_chapters,
    )
    chapters = apply_segment_limit(chapters, cfg.max_segments)
    if not chapters:
        raise ValueError("no chapters matched selection")

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    extraction_run_id = run_id or f"asset_extract_{ts}_{source_run[:24]}"
    out_root = output_dir or (
        repo_root / "workspace" / "asset_extraction_runs" / extraction_run_id
    )
    out_root.mkdir(parents=True, exist_ok=True)

    api_calls = 0
    if mode == "rule-based":
        buckets = extract_all_rule_based(chapters)
    else:
        if dry_run_model:
            raise ModelAssistedUnavailable("dry_run_model=true — skipping API")
        buckets, api_calls = extract_model_assisted(
            chapters,
            config=cfg,
            provider_factory=provider_factory,
        )

    all_assets: list[BaseAsset] = []
    for key in ("narrative", "game_design", "naming_pattern", "chapter_structure"):
        all_assets.extend(buckets.get(key, []))

    source_corpus = collect_source_corpus(chapters)
    safety_results = validate_assets(all_assets, source_corpus=source_corpus)
    safe_assets, blocked_assets = partition_by_safety(all_assets, safety_results)

    segments_processed = sum(len(c.segments) for c in chapters)
    stats = {
        "chapters_processed": len(chapters),
        "segments_processed": segments_processed,
        "assets_total": len(all_assets),
        "assets_safe": len(safe_assets),
        "assets_blocked": len(blocked_assets),
        "api_calls": api_calls,
        "narrative": len(buckets.get("narrative", [])),
        "game_design": len(buckets.get("game_design", [])),
        "naming_pattern": len(buckets.get("naming_pattern", [])),
        "chapter_structure": len(buckets.get("chapter_structure", [])),
    }

    metadata = AssetExtractionRun(
        run_id=extraction_run_id,
        source_run_id=source_run,
        mode=mode,  # type: ignore[arg-type]
        chapters_processed=[c.chapter_id for c in chapters],
        created_at=_utc_now(),
        config_snapshot=asdict(cfg),
        stats=stats,
    )
    (out_root / "extraction_metadata.json").write_text(
        json.dumps(metadata.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    _write_jsonl(out_root / "narrative_assets.jsonl", buckets.get("narrative", []))
    _write_jsonl(out_root / "game_design_assets.jsonl", buckets.get("game_design", []))
    _write_jsonl(
        out_root / "naming_pattern_assets.jsonl", buckets.get("naming_pattern", [])
    )
    _write_jsonl(
        out_root / "chapter_structure_assets.jsonl",
        buckets.get("chapter_structure", []),
    )

    write_public = cfg.write_to_public_asset_library and bool(safe_assets)
    (out_root / "abstraction_safety_report.md").write_text(
        _render_safety_report(
            safety_results,
            safe_count=len(safe_assets),
            blocked_count=len(blocked_assets),
            write_public=write_public,
        ),
        encoding="utf-8",
    )
    (out_root / "extraction_quality_report.md").write_text(
        _render_quality_report(stats, mode),
        encoding="utf-8",
    )

    if write_public:
        pub = repo_root / "assets_extracted"
        pub.mkdir(parents=True, exist_ok=True)
        for name in (
            "narrative_assets.jsonl",
            "game_design_assets.jsonl",
            "naming_pattern_assets.jsonl",
            "chapter_structure_assets.jsonl",
        ):
            src = out_root / name
            if src.is_file():
                (pub / f"{extraction_run_id}_{name}").write_text(
                    src.read_text(encoding="utf-8"), encoding="utf-8"
                )

    return {
        "run_id": extraction_run_id,
        "output_dir": str(out_root),
        "stats": stats,
        "safe_assets": len(safe_assets),
        "blocked_assets": len(blocked_assets),
        "public_library_written": write_public,
    }
