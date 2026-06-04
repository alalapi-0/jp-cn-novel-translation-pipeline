from __future__ import annotations

import re
from typing import Any, Iterable

from .types import ReviewIssue, utc_now_iso

_ISSUE_SEQ = 0
_JP_SCRIPT_RE = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff]")


def _text_length_units(text: str, language_direction: str) -> int:
    """Length units for omission heuristic — CJK uses chars, Latin uses tokens."""
    stripped = (text or "").strip()
    if not stripped:
        return 0
    if language_direction == "JP_TO_CN" or _JP_SCRIPT_RE.search(stripped):
        return len(re.sub(r"\s+", "", stripped))
    return len(re.findall(r"\S+", stripped))


def _likely_omission(source_len: int, target_len: int, language_direction: str) -> bool:
    if source_len < 8 or target_len <= 0:
        return False
    min_target = 2 if language_direction == "JP_TO_CN" else max(1, source_len // 3)
    return target_len <= max(min_target, source_len // 4)


def _next_issue_id(prefix: str) -> str:
    global _ISSUE_SEQ  # noqa: PLW0603
    _ISSUE_SEQ += 1
    return f"{prefix}-{_ISSUE_SEQ:04d}"


def reset_issue_counter() -> None:
    global _ISSUE_SEQ  # noqa: PLW0603
    _ISSUE_SEQ = 0


def _base_issue(
    *,
    project_id: str,
    language_direction: str,
    chapter_id: str,
    issue_type: str,
    severity: str,
    description: str,
    created_by: str,
    paragraph_id: str = "",
    segment_id: str = "",
    source_text_ref: str = "",
    target_text_ref: str = "",
    suggested_fix: str = "",
    evidence: dict[str, Any] | None = None,
    related_term_ids: list[str] | None = None,
    requires_human_review: bool = True,
    auto_fixable: bool = False,
    human_edited_segment: bool = False,
) -> ReviewIssue:
    return ReviewIssue(
        issue_id=_next_issue_id("ri"),
        project_id=project_id,
        language_direction=language_direction,
        chapter_id=chapter_id,
        paragraph_id=paragraph_id,
        segment_id=segment_id,
        issue_type=issue_type,
        severity=severity,
        source_text_ref=source_text_ref,
        target_text_ref=target_text_ref,
        description=description,
        suggested_fix=suggested_fix,
        evidence=evidence or {},
        related_term_ids=related_term_ids or [],
        status="open",
        created_by=created_by,
        created_at=utc_now_iso(),
        requires_human_review=requires_human_review,
        auto_fixable=auto_fixable,
        human_edited_segment=human_edited_segment,
    )


def check_term_consistency(
    segments_doc: dict[str, Any],
    glossary_doc: dict[str, Any],
) -> list[ReviewIssue]:
    """Deterministic locked-term and alias scan on synthetic segment targets."""
    issues: list[ReviewIssue] = []
    project_id = segments_doc["project_id"]
    direction = segments_doc["language_direction"]
    chapter_id = segments_doc.get("chapter_id", "ch-unknown")
    terms = glossary_doc.get("terms", [])

    for para in segments_doc.get("paragraphs", []):
        paragraph_id = para.get("paragraph_id", "")
        for seg in para.get("segments", []):
            target = seg.get("target_text", "") or ""
            human_edited = bool(seg.get("human_edited"))
            for term in terms:
                canonical = term.get("canonical_zh", "")
                if not canonical:
                    continue
                wrong_aliases = [
                    a for a in term.get("aliases_zh", []) if a and a in target and a != canonical
                ]
                uses_wrong = bool(wrong_aliases)
                if canonical not in target and any(a in target for a in term.get("aliases_zh", [])):
                    uses_wrong = True
                if not uses_wrong:
                    continue
                locked = bool(term.get("locked"))
                issue_type = "LOCKED_TERM_VIOLATION" if locked else "INCONSISTENT_TERM"
                severity = "high" if locked else "medium"
                wrong = wrong_aliases[0] if wrong_aliases else "non-canonical form"
                issues.append(
                    _base_issue(
                        project_id=project_id,
                        language_direction=direction,
                        chapter_id=chapter_id,
                        paragraph_id=paragraph_id,
                        segment_id=seg.get("segment_id", ""),
                        issue_type=issue_type,
                        severity=severity,
                        description=(
                            f"术语「{canonical}」在译文中出现非规范形式「{wrong}」"
                            + ("（locked）" if locked else "")
                        ),
                        suggested_fix=f"将译名统一为「{canonical}」",
                        source_text_ref=(seg.get("source_text", "") or "")[:80],
                        target_text_ref=target[:80],
                        created_by="checker.term_consistency",
                        related_term_ids=[term.get("term_id", "")],
                        evidence={
                            "canonical_zh": canonical,
                            "found": wrong,
                            "locked": locked,
                        },
                        auto_fixable=not locked and not human_edited,
                        requires_human_review=locked or human_edited,
                        human_edited_segment=human_edited,
                    )
                )
    return issues


def check_segment_alignment(segments_doc: dict[str, Any]) -> list[ReviewIssue]:
    """Compare expected segment ids vs present ids and orphan list."""
    issues: list[ReviewIssue] = []
    project_id = segments_doc["project_id"]
    direction = segments_doc["language_direction"]
    chapter_id = segments_doc.get("chapter_id", "ch-unknown")
    expected: set[str] = set(segments_doc.get("expected_segment_ids", []))
    present: set[str] = set()
    segment_by_id: dict[str, dict[str, Any]] = {}

    for para in segments_doc.get("paragraphs", []):
        paragraph_id = para.get("paragraph_id", "")
        for seg in para.get("segments", []):
            sid = seg.get("segment_id", "")
            if not sid:
                continue
            present.add(sid)
            segment_by_id[sid] = {**seg, "paragraph_id": paragraph_id}

    for missing in sorted(expected - present):
        issues.append(
            _base_issue(
                project_id=project_id,
                language_direction=direction,
                chapter_id=chapter_id,
                segment_id=missing,
                issue_type="SEGMENT_ALIGNMENT_ERROR",
                severity="high",
                description=f"期望 segment「{missing}」在译文中缺失",
                suggested_fix="补全对应 segment 译文或修正对齐表",
                created_by="checker.segment_alignment",
                evidence={"expected_segment_id": missing},
            )
        )

    for orphan in sorted(segments_doc.get("orphan_segment_ids", [])):
        if orphan in expected:
            continue
        issues.append(
            _base_issue(
                project_id=project_id,
                language_direction=direction,
                chapter_id=chapter_id,
                segment_id=orphan,
                issue_type="SEGMENT_ALIGNMENT_ERROR",
                severity="high",
                description=f"译文存在未在期望列表中的 segment「{orphan}」",
                suggested_fix="删除多余 segment 或更新 expected_segment_ids",
                created_by="checker.segment_alignment",
                evidence={"orphan_segment_id": orphan},
            )
        )

    for sid, seg in segment_by_id.items():
        source = seg.get("source_text", "") or ""
        target = seg.get("target_text", "") or ""
        if not source or not target:
            continue
        src_len = _text_length_units(source, direction)
        tgt_len = _text_length_units(target, direction)
        if _likely_omission(src_len, tgt_len, direction):
            human_edited = bool(seg.get("human_edited"))
            issues.append(
                _base_issue(
                    project_id=project_id,
                    language_direction=direction,
                    chapter_id=chapter_id,
                    paragraph_id=seg.get("paragraph_id", ""),
                    segment_id=sid,
                    issue_type="OMISSION",
                    severity="high",
                    description="译文词数明显少于原文，疑似漏译",
                    suggested_fix="对照原文补全缺失信息",
                    source_text_ref=source[:80],
                    target_text_ref=target[:80],
                    created_by="checker.segment_alignment",
                    evidence={
                        "source_length_units": src_len,
                        "target_length_units": tgt_len,
                        "length_heuristic": "cjk_chars" if direction == "JP_TO_CN" else "mixed",
                    },
                    human_edited_segment=human_edited,
                    requires_human_review=human_edited,
                )
            )

    return issues


def check_refinement_diff(segments_doc: dict[str, Any]) -> list[ReviewIssue]:
    """Flag draft vs refined divergence when refined changes locked-term surface forms."""
    issues: list[ReviewIssue] = []
    project_id = segments_doc["project_id"]
    direction = segments_doc["language_direction"]
    chapter_id = segments_doc.get("chapter_id", "ch-unknown")

    for para in segments_doc.get("paragraphs", []):
        paragraph_id = para.get("paragraph_id", "")
        for seg in para.get("segments", []):
            draft = (seg.get("draft_text") or "").strip()
            refined = (seg.get("refined_text") or "").strip()
            if not draft or not refined or draft == refined:
                continue
            if "魔法结晶" in refined and "魔法结晶" not in draft:
                issues.append(
                    _base_issue(
                        project_id=project_id,
                        language_direction=direction,
                        chapter_id=chapter_id,
                        paragraph_id=paragraph_id,
                        segment_id=seg.get("segment_id", ""),
                        issue_type="OVER_REFINEMENT",
                        severity="medium",
                        description="润色稿相对初译引入术语表面变化，需人工确认",
                        suggested_fix="对照术语表与初译，避免润色改写锁定译名",
                        source_text_ref=draft[:80],
                        target_text_ref=refined[:80],
                        created_by="checker.refinement_diff",
                        evidence={"draft_snippet": draft[:40], "refined_snippet": refined[:40]},
                        human_edited_segment=bool(seg.get("human_edited")),
                        requires_human_review=True,
                    )
                )
    return issues


def run_all_checkers(
    segments_doc: dict[str, Any],
    glossary_doc: dict[str, Any],
) -> list[ReviewIssue]:
    reset_issue_counter()
    issues: list[ReviewIssue] = []
    issues.extend(check_term_consistency(segments_doc, glossary_doc))
    issues.extend(check_segment_alignment(segments_doc))
    issues.extend(check_refinement_diff(segments_doc))
    return issues


def summarize_issues(issues: Iterable[ReviewIssue]) -> dict[str, Any]:
    issue_list = list(issues)
    by_type: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    for item in issue_list:
        by_type[item.issue_type] = by_type.get(item.issue_type, 0) + 1
        by_severity[item.severity] = by_severity.get(item.severity, 0) + 1
    return {
        "total": len(issue_list),
        "by_type": by_type,
        "by_severity": by_severity,
    }
