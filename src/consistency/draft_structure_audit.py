"""Draft structure audit (FS-035, Level 2).

Integrates FS-032 segment index issues (missing segments, misalignment) with
source-language residual heuristics and format checks. Outputs deterministic
statistics and per-finding chapter / segment locations — never body text.

Severity (``phase_acceptance_criteria.md`` A5 / P0–P2 alignment)
-----------------------------------------------------------------
+-------------------+----------+-----------+----------------------------------+
| Kind              | Severity | Blocking  | Notes                            |
+===================+==========+===========+==================================+
| missing_segment   | blocking | yes       | Gap in segment id sequence       |
| missing_draft     | blocking | yes       | Segment row exists, draft empty  |
| misalignment      | blocking | yes       | Id/order/chapter mismatch        |
| source_residual   | warning  | no        | Kana-only heuristic (P1 fix)     |
| format_anomaly    | info     | no        | Excessive blank lines, etc.      |
+-------------------+----------+-----------+----------------------------------+
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from consistency.conflict_audit import chapters_from_segment_ids
from consistency.manifest import find_segments_files

SCHEMA_VERSION = 1

# Kana only — excludes CJK Han to avoid P1 false positives (Chinese-only drafts).
KANA_RE = re.compile(r"[\u3040-\u30ff]")
KANA_RUN_RE = re.compile(r"[\u3040-\u30ff]{2,}")

# Legacy heuristic that mis-flagged Chinese Han as source residual (regression guard).
LEGACY_RESIDUAL_RE = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff]")

BLOCKING_RULES: dict[str, str] = {
    "missing_segment": "blocking",
    "missing_draft": "blocking",
    "misalignment": "blocking",
    "source_residual": "non-blocking",
    "format_anomaly": "non-blocking",
}

SEVERITY_BY_KIND: dict[str, str] = {
    "missing_segment": "blocking",
    "missing_draft": "blocking",
    "misalignment": "blocking",
    "source_residual": "warning",
    "format_anomaly": "info",
}

BLOCKING_KINDS: frozenset[str] = frozenset(
    kind for kind, level in BLOCKING_RULES.items() if level == "blocking"
)

# Known false-positive drafts: pure Chinese / short CN must not trigger source_residual.
SOURCE_RESIDUAL_FALSE_POSITIVES: tuple[dict[str, str], ...] = (
    {"segment_id": "fp-ch-001-seg-001", "draft": "这是完全中文化的译文，没有任何日文残留。"},
    {"segment_id": "fp-ch-001-seg-002", "draft": "角色说道：「我们现在就去示例王国。」"},
    {"segment_id": "fp-ch-002-seg-001", "draft": "短句测试。"},
    {"segment_id": "fp-ch-003-seg-001", "draft": "王国、公会、技能、道具，全部使用中文术语。"},
    {"segment_id": "fp-ch-004-seg-001", "draft": "——他停顿了一下，然后继续讲述冒险经历。"},
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _finding_base(
    *,
    kind: str,
    severity: str,
    blocking: bool,
    chapters: list[str],
    segment_ids: list[str],
    **extra: Any,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "kind": kind,
        "severity": severity,
        "blocking": blocking,
        "chapters": chapters,
        "segment_ids": segment_ids,
    }
    row.update(extra)
    return row


def detect_source_residual(draft_text: str) -> dict[str, Any] | None:
    """Return residual hint metadata when kana is present (no draft body in output)."""
    draft = str(draft_text or "").strip()
    if not draft:
        return None
    if not KANA_RE.search(draft):
        return None
    runs = KANA_RUN_RE.findall(draft)
    if not runs:
        return None
    return {
        "hint": "japanese_kana_present",
        "kana_run_count": len(runs),
        "longest_kana_run": max(len(r) for r in runs),
    }


def detect_format_anomaly(draft_text: str) -> dict[str, Any] | None:
    """Detect non-blocking format issues (metadata hints only)."""
    raw = str(draft_text or "")
    draft = raw.strip()
    if not draft:
        return None
    hints: list[str] = []
    if re.search(r"\n{4,}", draft):
        hints.append("excessive_blank_lines")
    if raw != raw.strip():
        hints.append("edge_whitespace")
    if not hints:
        return None
    return {"hints": hints}


def legacy_would_flag_source_residual(draft_text: str) -> bool:
    """True if the pre-P1 heuristic (kana + Han) would have flagged this draft."""
    draft = str(draft_text or "").strip()
    if not draft:
        return False
    return bool(LEGACY_RESIDUAL_RE.search(draft) and len(draft) < 200)


def _misalignment_finding(issue: dict[str, Any]) -> dict[str, Any]:
    issue_type = str(issue.get("issue_type") or "misalignment")
    segment_id = str(issue.get("segment_id") or "")
    chapter_id = str(issue.get("chapter_id") or "")
    chapters = [chapter_id] if chapter_id else chapters_from_segment_ids([segment_id] if segment_id else [])
    segment_ids = [segment_id] if segment_id else []
    return _finding_base(
        kind="misalignment",
        severity=SEVERITY_BY_KIND["misalignment"],
        blocking=True,
        chapters=chapters,
        segment_ids=segment_ids,
        issue_subtype=issue_type,
        chapter_number=issue.get("chapter_number"),
        position_in_chapter=issue.get("position_in_chapter"),
        source_run_id=issue.get("source_run_id"),
        details={k: v for k, v in issue.items() if k not in {"issue_type", "chapter_id", "segment_id"}},
    )


def _missing_segment_finding(issue: dict[str, Any]) -> dict[str, Any]:
    chapter_id = str(issue.get("chapter_id") or "")
    expected_id = str(issue.get("expected_segment_id") or "")
    chapters = [chapter_id] if chapter_id else chapters_from_segment_ids([expected_id])
    segment_ids = [expected_id] if expected_id else []
    return _finding_base(
        kind="missing_segment",
        severity=SEVERITY_BY_KIND["missing_segment"],
        blocking=True,
        chapters=chapters,
        segment_ids=segment_ids,
        chapter_number=issue.get("chapter_number"),
        segment_index=issue.get("segment_index"),
        expected_segment_id=expected_id,
        source_run_id=issue.get("source_run_id"),
    )


def _findings_from_segment_index(segment_index: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    issues = segment_index.get("issues") or {}

    for issue in issues.get("missing_segments") or []:
        findings.append(_missing_segment_finding(dict(issue)))

    for issue in issues.get("misalignments") or []:
        findings.append(_misalignment_finding(dict(issue)))

    for segment_id, meta in sorted((segment_index.get("segments") or {}).items()):
        if meta.get("has_source") and not meta.get("has_draft"):
            findings.append(
                _finding_base(
                    kind="missing_draft",
                    severity=SEVERITY_BY_KIND["missing_draft"],
                    blocking=True,
                    chapters=chapters_from_segment_ids([segment_id]),
                    segment_ids=[segment_id],
                    chapter_id=meta.get("chapter_id"),
                    status=str(meta.get("status") or ""),
                )
            )

    return findings


def iter_segment_draft_scans(
    repo_root: Path,
    *,
    run_dirs: list[Path] | None = None,
) -> Iterator[tuple[str, str, str, str]]:
    """Yield (segment_id, chapter_id, run_id, draft_text) from completed draft runs."""
    for path in find_segments_files(repo_root, run_dirs):
        run_id = path.parent.name
        doc = json.loads(path.read_text(encoding="utf-8"))
        for chapter in doc.get("chapters") or []:
            chapter_id = str(chapter.get("chapter_id") or "")
            for segment in chapter.get("segments") or []:
                segment_id = str(segment.get("segment_id") or "")
                draft = str(segment.get("draft_text") or "")
                yield segment_id, chapter_id, run_id, draft


def _findings_from_draft_scan(repo_root: Path) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    seen_residual: set[str] = set()
    seen_format: set[str] = set()

    for segment_id, chapter_id, run_id, draft in iter_segment_draft_scans(repo_root):
        chapters = chapters_from_segment_ids([segment_id]) or ([chapter_id] if chapter_id else [])

        residual = detect_source_residual(draft)
        if residual and segment_id not in seen_residual:
            seen_residual.add(segment_id)
            findings.append(
                _finding_base(
                    kind="source_residual",
                    severity=SEVERITY_BY_KIND["source_residual"],
                    blocking=False,
                    chapters=chapters,
                    segment_ids=[segment_id],
                    source_run_id=run_id,
                    **residual,
                )
            )

        fmt = detect_format_anomaly(draft)
        if fmt and segment_id not in seen_format:
            seen_format.add(segment_id)
            findings.append(
                _finding_base(
                    kind="format_anomaly",
                    severity=SEVERITY_BY_KIND["format_anomaly"],
                    blocking=False,
                    chapters=chapters,
                    segment_ids=[segment_id],
                    source_run_id=run_id,
                    **fmt,
                )
            )

    return findings


def audit_draft_structure(
    segment_index: dict[str, Any],
    repo_root: Path,
    *,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build the draft structure audit report (deterministic for fixed inputs)."""
    findings: list[dict[str, Any]] = []
    findings.extend(_findings_from_segment_index(segment_index))
    findings.extend(_findings_from_draft_scan(repo_root))

    findings.sort(
        key=lambda row: (
            0 if row["blocking"] else 1,
            {"blocking": 0, "warning": 1, "info": 2}.get(str(row.get("severity")), 9),
            row["kind"],
            (row.get("segment_ids") or [""])[0],
        )
    )

    by_kind: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    blocking_count = 0
    for row in findings:
        kind = str(row["kind"])
        severity = str(row.get("severity") or "")
        by_kind[kind] = by_kind.get(kind, 0) + 1
        by_severity[severity] = by_severity.get(severity, 0) + 1
        if row["blocking"]:
            blocking_count += 1

    index_stats = segment_index.get("stats") or {}
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at or utc_now_iso(),
        "inputs": {
            "segment_index_generated_at": segment_index.get("generated_at"),
            "segment_index_schema_version": segment_index.get("schema_version"),
            "segments_indexed": index_stats.get("segments_indexed"),
            "chapters_covered": index_stats.get("chapters_covered"),
            "index_missing_segments_count": index_stats.get("missing_segments_count"),
            "index_misalignment_count": index_stats.get("misalignment_count"),
        },
        "blocking_rules": dict(BLOCKING_RULES),
        "severity_rules": dict(SEVERITY_BY_KIND),
        "false_positive_regression_count": len(SOURCE_RESIDUAL_FALSE_POSITIVES),
        "stats": {
            "findings_total": len(findings),
            "blocking_count": blocking_count,
            "non_blocking_count": len(findings) - blocking_count,
            "by_kind": dict(sorted(by_kind.items())),
            "by_severity": dict(sorted(by_severity.items())),
        },
        "findings": findings,
    }


def audit_summary(report: dict[str, Any]) -> dict[str, Any]:
    stats = report.get("stats") or {}
    blocking = int(stats.get("blocking_count") or 0)
    return {
        "status": "PASS" if blocking == 0 else "WARN",
        "findings_total": stats.get("findings_total"),
        "blocking_count": blocking,
        "non_blocking_count": stats.get("non_blocking_count"),
        "by_kind": stats.get("by_kind"),
        "by_severity": stats.get("by_severity"),
    }
