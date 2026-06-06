"""Build reusable translation-memory assets from approved translation work."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal

from providers.cost_guard import CostGuard, CostGuardConfig
from providers.registry import ProviderMode, get_provider

AssetBuildMode = Literal["agent", "external_api"]
AssetStatusMode = Literal["approved", "translated"]

APPROVED_STATUSES = {"approved"}
TRANSLATED_STATUSES = {
    "approved",
    "machine_translated",
    "refined",
    "translated",
    "completed",
    "review_pending",
}
_KATAKANA_RE = re.compile(r"[ァ-ヴー]{3,}")
_BRACKET_RE = re.compile(r"【([^】]{1,32})】")
_CJK_TOKEN_RE = re.compile(r"[\u4e00-\u9fff]{2,8}")


class ExternalAssetExtractionUnavailable(RuntimeError):
    """Raised when external-api asset mode is not explicitly available."""


@dataclass(frozen=True)
class TranslationPair:
    segment_id: str
    source_text: str
    target_text: str
    status: str
    source_ref: str
    chapter_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "segment_id": self.segment_id,
            "source_text": self.source_text,
            "target_text": self.target_text,
            "status": self.status,
            "source_ref": self.source_ref,
            "chapter_id": self.chapter_id,
        }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_stem(value: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9_-]+", "_", value.strip())[:80].strip("_")
    return stem or "translation_assets"


def _status_allowed(status: str, status_mode: AssetStatusMode) -> bool:
    normalized = str(status or "").strip().lower()
    allowed = APPROVED_STATUSES if status_mode == "approved" else TRANSLATED_STATUSES
    return normalized in allowed


def _segment_text(seg: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = seg.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _collect_manifest_pairs(
    repo_root: Path,
    project_id: str,
    *,
    status_mode: AssetStatusMode,
) -> tuple[list[TranslationPair], str]:
    from workbench.project_registry import get_project_manifest
    from workbench.review_state import get_project_review_state

    manifest = get_project_manifest(repo_root, project_id)
    if manifest is None:
        raise KeyError(f"unknown project_id: {project_id}")
    review_state = get_project_review_state(repo_root, project_id)
    review_segments = review_state.get("segments") if isinstance(review_state, dict) else {}
    if not isinstance(review_segments, dict):
        review_segments = {}

    pairs: list[TranslationPair] = []
    for seg in manifest.segments:
        seg_id = _segment_text(seg, "id", "segment_id")
        state_entry = review_segments.get(seg_id, {}) if seg_id else {}
        status = str(
            (state_entry.get("status") if isinstance(state_entry, dict) else None)
            or seg.get("status")
            or "pending"
        ).strip().lower()
        if not _status_allowed(status, status_mode):
            continue
        source = _segment_text(seg, "source", "source_text")
        target = _segment_text(seg, "draft", "draft_text", "target_text", "translation")
        if source and target:
            pairs.append(
                TranslationPair(
                    segment_id=seg_id,
                    source_text=source,
                    target_text=target,
                    status=status,
                    source_ref=f"manifest:{project_id}",
                    chapter_id=str(seg.get("chapter") or ""),
                )
            )
    return pairs, manifest.language_direction


def _resolve_source_run_root(repo_root: Path, source_run: str) -> Path:
    from assets.loader import resolve_source_run_root

    return resolve_source_run_root(repo_root, source_run)


def _collect_run_pairs(
    repo_root: Path,
    source_run: str,
    *,
    status_mode: AssetStatusMode,
) -> tuple[list[TranslationPair], str]:
    run_root = _resolve_source_run_root(repo_root, source_run)
    path = run_root / "segments.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    pairs: list[TranslationPair] = []
    for ch in doc.get("chapters") or []:
        chapter_id = str(ch.get("chapter_id") or "")
        for seg in ch.get("segments") or []:
            if not isinstance(seg, dict):
                continue
            status = str(seg.get("status") or "").strip().lower()
            if not _status_allowed(status, status_mode):
                continue
            source = _segment_text(seg, "source_text", "source")
            target = _segment_text(seg, "refined_text", "draft_text", "target_text", "translation")
            seg_id = _segment_text(seg, "segment_id", "id")
            if source and target:
                pairs.append(
                    TranslationPair(
                        segment_id=seg_id,
                        source_text=source,
                        target_text=target,
                        status=status,
                        source_ref=f"run:{source_run}",
                        chapter_id=chapter_id,
                    )
                )
    return pairs, str(doc.get("language_direction") or "JP_TO_CN")


def _ordered_unique(items: list[dict[str, Any]], key: str, *, limit: int) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for item in items:
        value = str(item.get(key) or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(item)
        if len(out) >= limit:
            break
    return out


def _extract_terms(pairs: list[TranslationPair]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    terms: list[dict[str, Any]] = []
    proper_nouns: list[dict[str, Any]] = []
    for pair in pairs:
        for match in _BRACKET_RE.finditer(pair.source_text):
            source = match.group(0)
            target_match = _BRACKET_RE.search(pair.target_text)
            terms.append(
                {
                    "source": source,
                    "target": target_match.group(0) if target_match else "",
                    "kind": "bracket_label",
                    "evidence_segment_id": pair.segment_id,
                }
            )
        for source in _KATAKANA_RE.findall(pair.source_text):
            cjk_hits = _CJK_TOKEN_RE.findall(pair.target_text)
            proper_nouns.append(
                {
                    "source": source,
                    "target_hint": cjk_hits[0] if cjk_hits else "",
                    "kind": "katakana_candidate",
                    "evidence_segment_id": pair.segment_id,
                }
            )
    return (
        _ordered_unique(terms, "source", limit=80),
        _ordered_unique(proper_nouns, "source", limit=80),
    )


def _style_notes(pairs: list[TranslationPair]) -> list[str]:
    notes: list[str] = []
    if not pairs:
        return notes
    dialogue_count = sum(1 for p in pairs if "「" in p.source_text or "『" in p.source_text)
    bracket_count = sum(1 for p in pairs if "【" in p.source_text and "【" in p.target_text)
    avg_target_len = sum(len(p.target_text) for p in pairs) / max(len(pairs), 1)
    notes.append(f"已沉淀 {len(pairs)} 条翻译记忆；重启任务应优先保持译名与表达一致。")
    if dialogue_count:
        notes.append("对话段落保留中文引号风格，语气以自然简体中文为准。")
    if bracket_count:
        notes.append("方括号/系统提示类标记倾向保留全角括号结构。")
    notes.append(f"历史译文平均长度约 {avg_target_len:.0f} 字，可作为同章节节奏参考。")
    return notes


def _phrase_candidates(pairs: list[TranslationPair], *, limit: int = 20) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for pair in pairs:
        source = pair.source_text.strip()
        target = pair.target_text.strip()
        if 4 <= len(source) <= 80 and 2 <= len(target) <= 120:
            candidates.append(
                {
                    "source": source,
                    "target": target,
                    "segment_id": pair.segment_id,
                }
            )
        if len(candidates) >= limit:
            break
    return candidates


def _render_context_prompt(asset_doc: dict[str, Any], *, max_pairs: int = 12) -> str:
    lines = [
        "Translation memory context (reuse when relevant; do not force irrelevant terms):",
    ]
    for term in asset_doc.get("term_candidates", [])[:10]:
        target = term.get("target") or term.get("target_hint") or ""
        if target:
            lines.append(f"- Term: {term.get('source')} => {target}")
        else:
            lines.append(f"- Term candidate: {term.get('source')}")
    for term in asset_doc.get("proper_noun_candidates", [])[:10]:
        hint = term.get("target_hint") or ""
        lines.append(f"- Proper noun candidate: {term.get('source')}{' => ' + hint if hint else ''}")
    for pair in asset_doc.get("approved_pairs", [])[:max_pairs]:
        lines.append(
            f"- Pair {pair.get('segment_id')}: {pair.get('source_text')} => {pair.get('target_text')}"
        )
    for note in asset_doc.get("style_notes", [])[:6]:
        lines.append(f"- Style: {note}")
    return "\n".join(lines)


def _external_api_summary(
    pairs: list[TranslationPair],
    *,
    provider_factory: Callable[[CostGuard], Any] | None,
) -> tuple[dict[str, Any], int]:
    if provider_factory is None:
        enabled = os.environ.get("TRANSLATION_ASSET_EXTERNAL_API_ENABLED", "").strip().lower()
        if enabled not in {"1", "true", "yes"}:
            raise ExternalAssetExtractionUnavailable(
                "external_api mode is disabled; set TRANSLATION_ASSET_EXTERNAL_API_ENABLED=true"
            )
        if os.environ.get("REAL_API_TESTS_ENABLED", "").strip().lower() not in {"1", "true", "yes"}:
            raise ExternalAssetExtractionUnavailable(
                "external_api mode requires REAL_API_TESTS_ENABLED=true"
            )
        if not os.environ.get("OPENROUTER_API_KEY", "").strip():
            raise ExternalAssetExtractionUnavailable(
                "external_api mode requires OPENROUTER_API_KEY"
            )

    guard = CostGuard(CostGuardConfig.from_env())
    provider = provider_factory(guard) if provider_factory else get_provider(ProviderMode.REAL, cost_guard=guard)
    sample = [
        {
            "segment_id": p.segment_id,
            "source_preview": p.source_text[:120],
            "target_preview": p.target_text[:160],
        }
        for p in pairs[:20]
    ]
    result = provider.generate(
        [
            {
                "role": "system",
                "content": "Summarize reusable translation memory as compact JSON without quoting secrets.",
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "task": "Return JSON with style_notes and term_candidates arrays.",
                        "pairs": sample,
                    },
                    ensure_ascii=False,
                ),
            },
        ],
        options={"max_tokens": 800},
    )
    raw = result.raw_output or json.dumps(result.parsed_output or {})
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = {"style_notes": [raw[:500]], "term_candidates": []}
    if not isinstance(parsed, dict):
        parsed = {"style_notes": [], "term_candidates": []}
    return parsed, 1


def build_translation_memory_assets(
    *,
    repo_root: Path,
    project_id: str | None = None,
    source_run: str | None = None,
    output_path: Path | None = None,
    mode: AssetBuildMode = "agent",
    status_mode: AssetStatusMode = "approved",
    provider_factory: Callable[[CostGuard], Any] | None = None,
) -> dict[str, Any]:
    """Build a JSON asset file from reviewed manifests or completed run segments."""
    if mode not in {"agent", "external_api"}:
        raise ValueError("mode must be 'agent' or 'external_api'")
    if status_mode not in {"approved", "translated"}:
        raise ValueError("status_mode must be 'approved' or 'translated'")
    if bool(project_id) == bool(source_run):
        raise ValueError("provide exactly one of project_id or source_run")

    if project_id:
        pairs, language_direction = _collect_manifest_pairs(
            repo_root,
            project_id,
            status_mode=status_mode,
        )
        source_ref = f"manifest:{project_id}"
        stem = _safe_stem(project_id)
    else:
        assert source_run is not None
        pairs, language_direction = _collect_run_pairs(
            repo_root,
            source_run,
            status_mode=status_mode,
        )
        source_ref = f"run:{source_run}"
        stem = _safe_stem(source_run)

    if not pairs:
        raise ValueError(f"no {status_mode} translation pairs available for {source_ref}")

    terms, proper_nouns = _extract_terms(pairs)
    api_calls = 0
    external_summary: dict[str, Any] = {}
    if mode == "external_api":
        external_summary, api_calls = _external_api_summary(
            pairs,
            provider_factory=provider_factory,
        )
        for note in external_summary.get("style_notes") or []:
            if isinstance(note, str):
                pass
        for item in external_summary.get("term_candidates") or []:
            if isinstance(item, dict):
                terms.append(item)

    approved_pairs = [p.to_dict() for p in pairs]
    asset_doc: dict[str, Any] = {
        "schema_version": 1,
        "asset_kind": "translation_memory",
        "mode": mode,
        "status_mode": status_mode,
        "created_at": _utc_now(),
        "language_direction": language_direction,
        "source_refs": [source_ref],
        "approved_pairs": approved_pairs,
        "segment_map": {p.segment_id: p.target_text for p in pairs if p.segment_id},
        "term_candidates": _ordered_unique(terms, "source", limit=120),
        "proper_noun_candidates": proper_nouns,
        "phrase_candidates": _phrase_candidates(pairs),
        "style_notes": _style_notes(pairs),
        "external_api_summary": external_summary,
        "stats": {
            "pairs": len(pairs),
            "term_candidates": len(terms),
            "proper_noun_candidates": len(proper_nouns),
            "api_calls": api_calls,
        },
    }
    asset_doc["context_prompt"] = _render_context_prompt(asset_doc)

    out = output_path or (
        repo_root / "workspace" / "assets" / "translation_memory" / f"{stem}.json"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(asset_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    asset_doc["asset_path"] = str(out)
    try:
        asset_doc["asset_path_relative"] = str(out.relative_to(repo_root))
    except ValueError:
        asset_doc["asset_path_relative"] = str(out)
    return asset_doc


def load_translation_asset_context(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("asset_kind") != "translation_memory":
        raise ValueError(f"not a translation memory asset file: {path}")
    return data


def render_translation_asset_context(path: Path) -> str:
    data = load_translation_asset_context(path)
    prompt = str(data.get("context_prompt") or "").strip()
    return prompt or _render_context_prompt(data)
