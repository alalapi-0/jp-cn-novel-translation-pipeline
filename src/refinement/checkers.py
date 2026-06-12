"""Phase D refinement quality checkers (FS-043).

Three deterministic checkers run after each R-MR round:
  1. over_refinement — diff_ratio / length expansion vs FS-042 change_log stats
  2. terminology_preservation — locked glossary target terms not altered in refined
  3. character_voice — character_profile voice markers preserved in refined

Blocking criteria (round-level gate):
  over_refinement:
    - Any refined segment with diff_ratio >= max_segment_diff_ratio (default 0.35), OR
      modification_type == length_expansion, OR length_ratio >= max_segment_length_ratio (1.20)
    - BLOCK when over_refined_count / refined_segments > max_over_refined_fraction (0.05)
  terminology_preservation:
    - BLOCK on first locked term present in draft but missing or replaced in refined
  character_voice:
    - BLOCK when a character voice marker (first_person / speech_tic) present in draft
      is absent from refined for the same segment
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

from refinement.diff_builder import (
    MODIFICATION_LENGTH_EXPANSION,
    MODIFICATION_PENDING,
    MODIFICATION_SKIPPED_HUMAN,
    build_refine_diff,
    iter_segment_records,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_WORKSPACE_GLOSSARY = _REPO_ROOT / "workspace" / "configs" / "glossary.yaml"
DEFAULT_WORKSPACE_CHARACTER = _REPO_ROOT / "workspace" / "configs" / "character_profile.yaml"
DEFAULT_TEMPLATE_GLOSSARY = _REPO_ROOT / "configs" / "glossary.yaml"
DEFAULT_TEMPLATE_CHARACTER = _REPO_ROOT / "configs" / "character_profile.yaml"

CHECKER_OVER_REFINEMENT = "over_refinement"
CHECKER_TERMINOLOGY = "terminology_preservation"
CHECKER_CHARACTER_VOICE = "character_voice"

BLOCKING_CRITERIA: dict[str, str] = {
    CHECKER_OVER_REFINEMENT: (
        "Flag segments with diff_ratio >= max_segment_diff_ratio, "
        "modification_type=length_expansion, or length_ratio >= max_segment_length_ratio. "
        "BLOCK when flagged_count / refined_segments > max_over_refined_fraction."
    ),
    CHECKER_TERMINOLOGY: (
        "For each glossary entry with locked=true and non-empty target_term: "
        "if draft contains the target_term in a refined segment, refined must still contain it. "
        "BLOCK on first violation."
    ),
    CHECKER_CHARACTER_VOICE: (
        "For each character_profile entry, voice markers = first_person + speech_tics. "
        "When draft in a matched segment contains a marker, refined must retain it. "
        "BLOCK on first lost marker."
    ),
}

DEFAULT_THRESHOLDS: dict[str, float] = {
    "max_segment_diff_ratio": 0.35,
    "max_segment_length_ratio": 1.20,
    "max_over_refined_fraction": 0.05,
}


@dataclass
class RefinementCheckIssue:
    checker: str
    severity: str
    segment_id: str
    chapter_id: str
    rule: str
    description: str
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CheckerSummary:
    checker: str
    status: str
    blocking_count: int
    warning_count: int
    segments_checked: int
    blocking_rule: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RefinementQualityReport:
    run_id: str
    status: str
    blocking_count: int
    warning_count: int
    checkers: list[CheckerSummary]
    issues: list[RefinementCheckIssue]
    thresholds: dict[str, float]
    stats: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "status": self.status,
            "blocking_count": self.blocking_count,
            "warning_count": self.warning_count,
            "blocking_criteria": BLOCKING_CRITERIA,
            "thresholds": self.thresholds,
            "stats": self.stats,
            "checkers": [c.to_dict() for c in self.checkers],
            "issues": [i.to_dict() for i in self.issues],
        }


def _resolve_config_path(workspace_path: Path, template_path: Path) -> Path:
    if workspace_path.is_file():
        return workspace_path
    return template_path


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    return doc if isinstance(doc, dict) else {}


def _locked_glossary_entries(glossary_doc: dict[str, Any]) -> list[dict[str, Any]]:
    entries = glossary_doc.get("entries") or []
    out: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("deleted"):
            continue
        if not entry.get("locked"):
            continue
        target = str(entry.get("target_term") or "").strip()
        if not target:
            continue
        out.append(entry)
    return out


def _character_profiles(character_doc: dict[str, Any]) -> list[dict[str, Any]]:
    chars = character_doc.get("characters") or []
    return [c for c in chars if isinstance(c, dict)]


def _segment_iter(doc: dict[str, Any]) -> list[dict[str, Any]]:
    segments: list[dict[str, Any]] = []
    for chapter in doc.get("chapters") or []:
        if not isinstance(chapter, dict):
            continue
        chapter_id = str(chapter.get("chapter_id") or "")
        for seg in chapter.get("segments") or []:
            if not isinstance(seg, dict):
                continue
            segments.append(
                {
                    "chapter_id": chapter_id,
                    "segment_id": str(seg.get("segment_id") or ""),
                    "source_text": str(seg.get("source_text") or ""),
                    "draft_text": str(seg.get("draft_text") or "").strip(),
                    "refined_text": str(seg.get("refined_text") or "").strip(),
                    "human_edited": bool(seg.get("human_edited")),
                }
            )
    return segments


def _character_hit(char: dict[str, Any], haystack: str) -> bool:
    name = str(char.get("name") or "")
    if name and name in haystack:
        return True
    target = str(char.get("target_name") or "")
    if target and target in haystack:
        return True
    return any(a and str(a) in haystack for a in char.get("aliases") or [])


def _voice_markers(char: dict[str, Any]) -> list[str]:
    markers: list[str] = []
    first = str(char.get("first_person") or "").strip()
    if first:
        markers.append(first)
    for tic in char.get("speech_tics") or []:
        t = str(tic or "").strip()
        if t:
            markers.append(t)
    return markers


def _is_over_refined(rec: dict[str, Any], thresholds: dict[str, float]) -> bool:
    if rec["modification_type"] in {MODIFICATION_PENDING, MODIFICATION_SKIPPED_HUMAN}:
        return False
    refined_chars = int(rec.get("refined_char_count") or 0)
    if refined_chars <= 0 and not rec.get("refined_text"):
        return False
    if rec["modification_type"] == MODIFICATION_LENGTH_EXPANSION:
        return True
    if float(rec.get("diff_ratio") or 0) >= thresholds["max_segment_diff_ratio"]:
        return True
    length_ratio = rec.get("length_ratio")
    if length_ratio is not None and float(length_ratio) >= thresholds["max_segment_length_ratio"]:
        return True
    return False


def check_over_refinement(
    change_log_segments: list[dict[str, Any]],
    *,
    thresholds: dict[str, float] | None = None,
) -> tuple[list[RefinementCheckIssue], CheckerSummary]:
    thresholds = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    issues: list[RefinementCheckIssue] = []
    refined_records = [
        r
        for r in change_log_segments
        if r.get("modification_type")
        not in {MODIFICATION_PENDING, MODIFICATION_SKIPPED_HUMAN}
        and (r.get("refined_text") or r.get("draft_char_count", 0) > 0)
    ]
    eligible = [r for r in refined_records if r.get("refined_text") or r.get("changed")]
    flagged = [r for r in change_log_segments if _is_over_refined(r, thresholds)]

    for rec in flagged:
        issues.append(
            RefinementCheckIssue(
                checker=CHECKER_OVER_REFINEMENT,
                severity="blocking",
                segment_id=str(rec.get("segment_id") or ""),
                chapter_id=str(rec.get("chapter_id") or ""),
                rule="segment_over_refined",
                description="段落润色改动幅度或长度膨胀超过阈值",
                evidence={
                    "diff_ratio": rec.get("diff_ratio"),
                    "length_ratio": rec.get("length_ratio"),
                    "modification_type": rec.get("modification_type"),
                },
            )
        )

    refined_count = len(
        [
            r
            for r in change_log_segments
            if r.get("modification_type")
            not in {MODIFICATION_PENDING, MODIFICATION_SKIPPED_HUMAN}
            and int(r.get("refined_char_count") or 0) > 0
        ]
    )
    if refined_count == 0:
        return [], CheckerSummary(
            checker=CHECKER_OVER_REFINEMENT,
            status="pass",
            blocking_count=0,
            warning_count=0,
            segments_checked=0,
            blocking_rule=BLOCKING_CRITERIA[CHECKER_OVER_REFINEMENT],
        )

    fraction = len(flagged) / refined_count
    round_blocking = fraction > thresholds["max_over_refined_fraction"]

    summary = CheckerSummary(
        checker=CHECKER_OVER_REFINEMENT,
        status="blocking" if round_blocking else ("warning" if flagged else "pass"),
        blocking_count=len(flagged) if round_blocking else 0,
        warning_count=0 if round_blocking else len(flagged),
        segments_checked=len(eligible),
        blocking_rule=BLOCKING_CRITERIA[CHECKER_OVER_REFINEMENT],
    )
    if round_blocking and flagged:
        issues.append(
            RefinementCheckIssue(
                checker=CHECKER_OVER_REFINEMENT,
                severity="blocking",
                segment_id="",
                chapter_id="",
                rule="round_over_refined_fraction",
                description="超阈值润色段落比例超过 round 上限",
                evidence={
                    "flagged_segments": len(flagged),
                    "refined_segments": refined_count,
                    "fraction": round(fraction, 6),
                    "max_over_refined_fraction": thresholds["max_over_refined_fraction"],
                },
            )
        )
    elif not round_blocking:
        issues = [i for i in issues if i.rule != "round_over_refined_fraction"]
        if flagged:
            for issue in issues:
                issue.severity = "warning"

    return issues, summary


def check_terminology_preservation(
    segments: list[dict[str, Any]],
    glossary_doc: dict[str, Any],
) -> tuple[list[RefinementCheckIssue], CheckerSummary]:
    issues: list[RefinementCheckIssue] = []
    locked = _locked_glossary_entries(glossary_doc)
    checked = 0

    for seg in segments:
        draft = seg["draft_text"]
        refined = seg["refined_text"]
        if not draft or not refined or draft == refined:
            continue
        checked += 1
        for entry in locked:
            term = str(entry.get("target_term") or "")
            if term not in draft:
                continue
            if term in refined:
                continue
            issues.append(
                RefinementCheckIssue(
                    checker=CHECKER_TERMINOLOGY,
                    severity="blocking",
                    segment_id=seg["segment_id"],
                    chapter_id=seg["chapter_id"],
                    rule="locked_term_altered",
                    description="locked 术语在润色稿中被改写或丢失",
                    evidence={
                        "source_term": entry.get("source_term"),
                        "target_term": term,
                        "locked": True,
                    },
                )
            )
            break

    summary = CheckerSummary(
        checker=CHECKER_TERMINOLOGY,
        status="blocking" if issues else "pass",
        blocking_count=len(issues),
        warning_count=0,
        segments_checked=checked,
        blocking_rule=BLOCKING_CRITERIA[CHECKER_TERMINOLOGY],
    )
    return issues, summary


def check_character_voice(
    segments: list[dict[str, Any]],
    character_doc: dict[str, Any],
) -> tuple[list[RefinementCheckIssue], CheckerSummary]:
    issues: list[RefinementCheckIssue] = []
    characters = _character_profiles(character_doc)
    checked = 0

    for seg in segments:
        draft = seg["draft_text"]
        refined = seg["refined_text"]
        if not draft or not refined or draft == refined:
            continue
        haystack = f"{seg['source_text']}\n{draft}"
        matched = [c for c in characters if _character_hit(c, haystack)]
        if not matched:
            continue
        checked += 1
        for char in matched:
            for marker in _voice_markers(char):
                if marker not in draft:
                    continue
                if marker in refined:
                    continue
                issues.append(
                    RefinementCheckIssue(
                        checker=CHECKER_CHARACTER_VOICE,
                        severity="blocking",
                        segment_id=seg["segment_id"],
                        chapter_id=seg["chapter_id"],
                        rule="voice_marker_lost",
                        description="角色语气关键标记在润色稿中丢失或被统一化",
                        evidence={
                            "character": char.get("name"),
                            "target_name": char.get("target_name"),
                            "marker": marker,
                            "marker_kind": "first_person"
                            if marker == str(char.get("first_person") or "")
                            else "speech_tic",
                        },
                    )
                )
                break
            if issues and issues[-1].segment_id == seg["segment_id"]:
                break

    summary = CheckerSummary(
        checker=CHECKER_CHARACTER_VOICE,
        status="blocking" if issues else "pass",
        blocking_count=len(issues),
        warning_count=0,
        segments_checked=checked,
        blocking_rule=BLOCKING_CRITERIA[CHECKER_CHARACTER_VOICE],
    )
    return issues, summary


def run_refinement_checks(
    segments_doc: dict[str, Any],
    *,
    run_id: str = "",
    glossary_path: Path | None = None,
    character_path: Path | None = None,
    change_log: dict[str, Any] | None = None,
    thresholds: dict[str, float] | None = None,
) -> RefinementQualityReport:
    """Run all three refinement checkers on a segments document."""
    resolved_run_id = run_id or str(segments_doc.get("run_id") or "")
    merged_thresholds = {**DEFAULT_THRESHOLDS, **(thresholds or {})}

    glossary_p = glossary_path or _resolve_config_path(
        DEFAULT_WORKSPACE_GLOSSARY, DEFAULT_TEMPLATE_GLOSSARY
    )
    character_p = character_path or _resolve_config_path(
        DEFAULT_WORKSPACE_CHARACTER, DEFAULT_TEMPLATE_CHARACTER
    )
    glossary_doc = _load_yaml(glossary_p)
    character_doc = _load_yaml(character_p)

    if change_log is None:
        _, change_log = build_refine_diff(segments_doc, run_id=resolved_run_id)

    records = iter_segment_records(segments_doc)
    change_segments = change_log.get("segments") or []
    change_by_id = {str(s.get("segment_id") or ""): s for s in change_segments}
    enriched_change: list[dict[str, Any]] = []
    for rec in records:
        seg_id = rec["segment_id"]
        base = dict(change_by_id.get(seg_id, {}))
        base.setdefault("segment_id", seg_id)
        base.setdefault("chapter_id", rec["chapter_id"])
        base["refined_text"] = rec["refined_text"]
        base["baseline_text"] = rec["baseline_text"]
        enriched_change.append(base)

    segments = _segment_iter(segments_doc)
    all_issues: list[RefinementCheckIssue] = []
    summaries: list[CheckerSummary] = []

    over_issues, over_summary = check_over_refinement(enriched_change, thresholds=merged_thresholds)
    term_issues, term_summary = check_terminology_preservation(segments, glossary_doc)
    voice_issues, voice_summary = check_character_voice(segments, character_doc)

    all_issues.extend(over_issues + term_issues + voice_issues)
    summaries.extend([over_summary, term_summary, voice_summary])

    blocking = [i for i in all_issues if i.severity == "blocking"]
    warnings = [i for i in all_issues if i.severity == "warning"]
    if blocking:
        status = "blocking"
    elif warnings:
        status = "warning"
    else:
        status = "pass"

    stats = change_log.get("summary") or {}
    return RefinementQualityReport(
        run_id=resolved_run_id,
        status=status,
        blocking_count=len(blocking),
        warning_count=len(warnings),
        checkers=summaries,
        issues=all_issues,
        thresholds=merged_thresholds,
        stats={
            "total_segments": stats.get("total_segments", len(records)),
            "refined_segments": stats.get("refined_segments"),
            "avg_diff_ratio": stats.get("avg_diff_ratio"),
            "glossary_path": str(glossary_p),
            "character_profile_path": str(character_p),
        },
    )


def run_refinement_checks_for_run(
    run_root: Path,
    *,
    repo_root: Path | None = None,
    glossary_path: Path | None = None,
    character_path: Path | None = None,
    thresholds: dict[str, float] | None = None,
) -> RefinementQualityReport:
    """Load segments.json from a run directory and execute checkers."""
    run_root = run_root.resolve()
    repo_root = (repo_root or _REPO_ROOT).resolve()
    seg_path = run_root / "segments.json"
    if not seg_path.is_file():
        raise FileNotFoundError(f"segments.json not found: {seg_path}")

    segments_doc = json.loads(seg_path.read_text(encoding="utf-8"))
    meta_path = run_root / "run_metadata.json"
    run_id = run_root.name
    if meta_path.is_file():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        run_id = str(meta.get("run_id") or run_id)

    change_log_path = run_root / "change_log.json"
    change_log = None
    if change_log_path.is_file():
        change_log = json.loads(change_log_path.read_text(encoding="utf-8"))

    rel_glossary = glossary_path
    if rel_glossary is None:
        ws_glossary = repo_root / "workspace" / "configs" / "glossary.yaml"
        rel_glossary = _resolve_config_path(ws_glossary, repo_root / "configs" / "glossary.yaml")
    rel_character = character_path
    if rel_character is None:
        ws_char = repo_root / "workspace" / "configs" / "character_profile.yaml"
        rel_character = _resolve_config_path(ws_char, repo_root / "configs" / "character_profile.yaml")

    return run_refinement_checks(
        segments_doc,
        run_id=run_id,
        glossary_path=rel_glossary,
        character_path=rel_character,
        change_log=change_log,
        thresholds=thresholds,
    )


def write_refinement_quality_report(run_root: Path, report: RefinementQualityReport) -> Path:
    run_root.mkdir(parents=True, exist_ok=True)
    out_path = run_root / "refinement_quality_report.json"
    out_path.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return out_path


def aggregate_exit_code(report: RefinementQualityReport) -> int:
    if report.blocking_count > 0:
        return 2
    return 0
