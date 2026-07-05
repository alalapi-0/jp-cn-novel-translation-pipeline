from __future__ import annotations

import re
from typing import Any, Iterable

from .types import ReviewIssue, utc_now_iso

_ISSUE_SEQ = 0
_JP_SCRIPT_RE = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff]")
_PLACEHOLDER_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\{\{[^}]+\}\}"),
    re.compile(r"\[\[[^\]]+\]\]"),
    re.compile(r"\{PH_[A-Za-z0-9_]+\}"),
    re.compile(r"https?://[^\s\]}>]+"),
)
_JP_NEGATION_TRIGGER_RE = re.compile(
    r"(?:しなければ|しなかった|しない|行かない|行かなかった|行けない|来ない|来なかった|来られない|できない|出来ない|なければ)"
)
_JP_NEGATION_SOFT_EXEMPT_RE = re.compile(
    r"(?:しかない|かもしれない|のだろう|だろうか|じゃないか|のではない|のではないだろう|仕様|わけではない|なければならない)"
)
_CN_NEGATION_RE = re.compile(
    r"(?:没有|未|非|不|没|无|未能|未曾|不会|不是|没去|没有去|未能)"
)
_CN_AFFIRM_MOTION_RE = re.compile(r"(?:去了|来到|到达|抵达|会来|会来吧|来到了|去到|登上|前去|回去|跑到|会来呢)")
_AUTO_FIX_DENYLIST = {
    "狙击蚁",
    "秘遗物",
    "全队",
    "组队",
    "团队战",
    "派对会场",
    "复活点",
    "领导者",
    "队长",
    "老大",
    "领队",
    "首领",
    "头目",
    "领头",
    "女兵",
    "白袍",
    "斗篷",
    "黑斗篷",
    "阿玛莉",
    "马尔曼",
    "马尔曼（マーマン）",
    "马曼",
    "吸血鬼",
    "エルフ",
    "コトノハ",
    "グライテン",
    "ドラゴン",
    "邦布大人",
    "班布大人",
}


def _is_word_char(ch: str) -> bool:
    if not ch:
        return False
    return (
        ch.isalnum()
        or ("\u4e00" <= ch <= "\u9fff")
        or ("\u3040" <= ch <= "\u30ff")
        or ("ー" <= ch <= "々")
    )


_KATAKANA = set(chr(c) for c in range(0x30A0, 0x3100))


def _source_occurs(source: str, text: str) -> bool:
    if not source:
        return False
    source = source.strip("【】")
    if source not in text:
        return False
    if not all(ch in _KATAKANA for ch in source):
        return True
    idx = 0
    while True:
        pos = text.find(source, idx)
        if pos == -1:
            return False
        before = text[pos - 1] if pos > 0 else ""
        after = text[pos + len(source)] if pos + len(source) < len(text) else ""
        if before not in _KATAKANA and after not in _KATAKANA:
            return True
        idx = pos + len(source)


def _contains_standalone_variant(text: str, variant: str) -> bool:
    idx = text.find(variant)
    while idx != -1:
        before = text[idx - 1] if idx > 0 else ""
        after = text[idx + len(variant)] if idx + len(variant) < len(text) else ""
        if not _is_word_char(before) and not _is_word_char(after):
            return True
        idx = text.find(variant, idx + len(variant))
    return False


def _is_system_style_fragment(text: str) -> bool:
    compact = re.sub(r"\s+", "", text or "")
    if not compact:
        return False
    if compact in {
        "ありがとうございます",
        "Ｌ(・)Ｐ(・)が(・)減(・)って(・)い(・)た(・)。",
        "L(・)P(・)が(・)減(・)って(・)い(・)た(・)。",
    }:
        return True

    ascii_like_chars = sum(
        1
        for ch in compact
        if ch.isascii() or ch in "・()（）[]<>／＋－−=_—【】「」『』《》"
    )
    if len(compact) >= 16 and ascii_like_chars / len(compact) >= 0.45:
        return True
    return False


def _text_length_units(text: str, language_direction: str) -> int:
    """Length units for omission heuristic — CJK uses chars, Latin uses tokens."""
    stripped = (text or "").strip()
    if not stripped:
        return 0
    if language_direction == "JP_TO_CN" or _JP_SCRIPT_RE.search(stripped):
        return len(re.sub(r"\s+", "", stripped))
    return len(re.findall(r"\S+", stripped))


def _likely_omission(
    source_len: int,
    target_len: int,
    language_direction: str,
    *,
    source_text: str = "",
) -> bool:
    if source_len < 8 or target_len <= 0:
        return False
    if _is_system_style_fragment(source_text):
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
            source_text = seg.get("source_text", "") or ""
            human_edited = bool(seg.get("human_edited"))
            for term in terms:
                canonical = term.get("canonical_zh", "")
                if not canonical:
                    continue
                aliases = [a for a in term.get("aliases_zh", []) if a and a != canonical]
                if canonical in target or not aliases:
                    continue
                wrong_aliases = [a for a in aliases if _contains_standalone_variant(target, a)]
                if not wrong_aliases:
                    continue
                if not _source_occurs(term.get("source", ""), source_text):
                    continue
                normalized_wrong = [a for a in wrong_aliases if a not in _AUTO_FIX_DENYLIST]
                if not normalized_wrong:
                    continue
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
        if _likely_omission(src_len, tgt_len, direction, source_text=source):
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


def _collect_placeholders(text: str) -> list[str]:
    tokens: list[str] = []
    for pattern in _PLACEHOLDER_PATTERNS:
        tokens.extend(pattern.findall(text))
    seen: set[str] = set()
    ordered: list[str] = []
    for token in tokens:
        if token not in seen:
            seen.add(token)
            ordered.append(token)
    return ordered


def _negation_polarity_mismatch(source: str, target: str, language_direction: str) -> bool:
    """MVP: JP source negation vs CN target affirmative motion without negation."""
    if language_direction != "JP_TO_CN":
        return False
    if not source.strip() or not target.strip():
        return False
    if not _JP_NEGATION_TRIGGER_RE.search(source):
        return False
    if _JP_NEGATION_SOFT_EXEMPT_RE.search(source):
        return False
    if _CN_NEGATION_RE.search(target):
        return False
    return bool(_CN_AFFIRM_MOTION_RE.search(target))


def check_placeholder_lost(segments_doc: dict[str, Any]) -> list[ReviewIssue]:
    """Detect URL / brace / token placeholders present in source but missing in target."""
    issues: list[ReviewIssue] = []
    project_id = segments_doc["project_id"]
    direction = segments_doc["language_direction"]
    chapter_id = segments_doc.get("chapter_id", "ch-unknown")

    for para in segments_doc.get("paragraphs", []):
        paragraph_id = para.get("paragraph_id", "")
        for seg in para.get("segments", []):
            source = seg.get("source_text", "") or ""
            target = seg.get("target_text", "") or ""
            if not source:
                continue
            human_edited = bool(seg.get("human_edited"))
            for token in _collect_placeholders(source):
                if token in target:
                    continue
                issues.append(
                    _base_issue(
                        project_id=project_id,
                        language_direction=direction,
                        chapter_id=chapter_id,
                        paragraph_id=paragraph_id,
                        segment_id=seg.get("segment_id", ""),
                        issue_type="PLACEHOLDER_LOST",
                        severity="high",
                        description=f"译文中丢失占位符「{token}」",
                        suggested_fix="在译文中原样保留占位符或受保护标记",
                        source_text_ref=source[:80],
                        target_text_ref=target[:80],
                        created_by="checker.placeholder_lost",
                        evidence={"placeholder": token},
                        auto_fixable=not human_edited,
                        requires_human_review=human_edited,
                        human_edited_segment=human_edited,
                    )
                )
    return issues


def check_mistranslation(segments_doc: dict[str, Any]) -> list[ReviewIssue]:
    """Rule-layer semantic MVP: negation polarity mismatch (JP→CN)."""
    issues: list[ReviewIssue] = []
    project_id = segments_doc["project_id"]
    direction = segments_doc["language_direction"]
    chapter_id = segments_doc.get("chapter_id", "ch-unknown")

    for para in segments_doc.get("paragraphs", []):
        paragraph_id = para.get("paragraph_id", "")
        for seg in para.get("segments", []):
            source = seg.get("source_text", "") or ""
            target = seg.get("target_text", "") or ""
            if not _negation_polarity_mismatch(source, target, direction):
                continue
            human_edited = bool(seg.get("human_edited"))
            issues.append(
                _base_issue(
                    project_id=project_id,
                    language_direction=direction,
                    chapter_id=chapter_id,
                    paragraph_id=paragraph_id,
                    segment_id=seg.get("segment_id", ""),
                    issue_type="MISTRANSLATION",
                    severity="high",
                    description="原文含否定而译文呈肯定动作，疑似语义极性误译",
                    suggested_fix="对照原文否定范围，修正译文极性与动作方向",
                    source_text_ref=source[:80],
                    target_text_ref=target[:80],
                    created_by="checker.mistranslation",
                    evidence={
                        "rule": "jp_negation_vs_cn_affirm_motion",
                        "source_has_jp_negation": True,
                        "target_has_cn_negation": bool(_CN_NEGATION_RE.search(target)),
                    },
                    auto_fixable=False,
                    requires_human_review=True,
                    human_edited_segment=human_edited,
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
    issues.extend(check_placeholder_lost(segments_doc))
    issues.extend(check_mistranslation(segments_doc))
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
