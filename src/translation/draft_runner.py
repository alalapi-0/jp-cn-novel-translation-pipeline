"""Run draft Stage A/B translation for bounded chapter sets."""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from providers.controlled_run import ControlledRunConfig, ControlledRunManager
from providers.cost_guard import CostGuard, CostGuardConfig, CostGuardError
from providers.registry import ProviderMode, get_provider
from providers.types import GenerateOptions
from translation.chapter_parser import ParsedChapter, Segment, list_chapter_files, parse_chapter_file
from translation.exporter import export_chapter_markdown, export_segments_doc
from translation.prompt_builder import build_batch_messages
from translation.response_extractor import extract_translations
from translation.validator import validate_draft_items

MAX_CHARS_PER_BATCH = 5_500
MAX_SEGMENTS_PER_BATCH = 8
MAX_API_RETRIES = 3
STAGE_A_MAX_CHAPTERS = 5
STAGE_B_MAX_CHAPTERS = 50


@dataclass(frozen=True)
class DraftStageSpec:
    stage_key: str
    scope: str
    limit_chapters: int
    run_id_prefix: str
    next_stage_label: str
    go_decision_filename: str


STAGE_A_SPEC = DraftStageSpec(
    stage_key="stage_a",
    scope="draft_stage_a_5ch",
    limit_chapters=STAGE_A_MAX_CHAPTERS,
    run_id_prefix="draft-a",
    next_stage_label="Stage B",
    go_decision_filename="go_decision.md",
)

STAGE_B_SPEC = DraftStageSpec(
    stage_key="stage_b",
    scope="draft_stage_b_50ch",
    limit_chapters=STAGE_B_MAX_CHAPTERS,
    run_id_prefix="run",
    next_stage_label="Stage C",
    go_decision_filename="stage_draft_b_50ch_go_decision.md",
)


@dataclass
class ChapterRunResult:
    chapter_id: str
    ok: bool
    message: str
    segments_translated: int = 0
    api_calls: int = 0


@dataclass
class DraftRunSummary:
    run_id: str
    chapters: list[ChapterRunResult] = field(default_factory=list)
    total_segments: int = 0
    translated_segments: int = 0
    api_calls: int = 0
    spent_usd: float = 0.0
    spent_tokens: int = 0
    provider_mode: str = "real"
    model_name: str = ""
    aborted: bool = False
    abort_reason: str = ""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _split_batches(chapter: ParsedChapter) -> list[list[Segment]]:
    batches: list[list[Segment]] = []
    current: list[Segment] = []
    char_count = 0
    for seg in chapter.segments:
        seg_len = len(seg.source_text)
        if current and (
            len(current) >= MAX_SEGMENTS_PER_BATCH
            or char_count + seg_len > MAX_CHARS_PER_BATCH
        ):
            batches.append(current)
            current = []
            char_count = 0
        current.append(seg)
        char_count += seg_len
    if current:
        batches.append(current)
    return batches


def _apply_items(chapter: ParsedChapter, batch: list[Segment], raw_output: str) -> tuple[bool, str]:
    expected = [s.segment_id for s in batch]
    source_lengths = {s.segment_id: len(s.source_text) for s in batch}
    extracted = extract_translations(raw_output, expected)
    if extracted.parse_status == "failed":
        return False, ";".join(extracted.parse_errors) or "extract_failed"

    validation = validate_draft_items(extracted.items, expected, source_lengths)
    if not validation.passed:
        codes = ",".join(i.code for i in validation.issues[:5])
        if extracted.parse_status != "ok":
            return False, f"validate:{codes}"
        # partial coverage still fails the batch for controlled run
        if any(i.code == "segment_id_coverage" for i in validation.issues):
            return False, f"validate:{codes}"

    by_id = {i.segment_id: i.translation for i in extracted.items}
    for seg in batch:
        if seg.segment_id in by_id:
            seg.draft_text = by_id[seg.segment_id]
            seg.status = "machine_translated"
    return True, "ok"


def run_draft_stage_a(
    *,
    repo_root: Path,
    input_dir: Path,
    limit_chapters: int,
    chapter_offset: int = 0,
    run_id: str | None = None,
    provider_factory: Callable[[CostGuard], Any] | None = None,
) -> tuple[DraftRunSummary, Path]:
    if limit_chapters > STAGE_A_MAX_CHAPTERS:
        raise ValueError(f"Stage A hard limit: max {STAGE_A_MAX_CHAPTERS} chapters")
    return run_draft_stage(
        spec=STAGE_A_SPEC,
        repo_root=repo_root,
        input_dir=input_dir,
        limit_chapters=limit_chapters,
        chapter_offset=chapter_offset,
        run_id=run_id,
        provider_factory=provider_factory,
    )


def run_draft_stage_b(
    *,
    repo_root: Path,
    input_dir: Path,
    limit_chapters: int = STAGE_B_MAX_CHAPTERS,
    chapter_offset: int = 0,
    run_id: str | None = None,
    provider_factory: Callable[[CostGuard], Any] | None = None,
) -> tuple[DraftRunSummary, Path]:
    if limit_chapters > STAGE_B_MAX_CHAPTERS:
        raise ValueError(f"Stage B hard limit: max {STAGE_B_MAX_CHAPTERS} chapters")
    return run_draft_stage(
        spec=STAGE_B_SPEC,
        repo_root=repo_root,
        input_dir=input_dir,
        limit_chapters=limit_chapters,
        chapter_offset=chapter_offset,
        run_id=run_id,
        provider_factory=provider_factory,
    )


def _hydrate_from_segments_json(run_root: Path, chapters: list[ParsedChapter]) -> None:
    path = run_root / "segments.json"
    if not path.is_file():
        return
    doc = json.loads(path.read_text(encoding="utf-8"))
    by_id: dict[str, dict[str, Any]] = {}
    for ch in doc.get("chapters", []):
        for seg in ch.get("segments", []):
            sid = seg.get("segment_id")
            if sid and (seg.get("draft_text") or "").strip():
                by_id[sid] = seg
    for chapter in chapters:
        for seg in chapter.segments:
            saved = by_id.get(seg.segment_id)
            if not saved:
                continue
            seg.draft_text = saved.get("draft_text", "")
            seg.status = saved.get("status") or "machine_translated"


_SEGMENT_ID_RE = re.compile(r"<!--\s*(\S+)\s*-->")


def _hydrate_from_draft_md(run_root: Path, chapters: list[ParsedChapter]) -> None:
    """Resume in-progress draft runs when segments.json is missing but chapter .md exists."""
    draft_dir = run_root / "draft"
    if not draft_dir.is_dir():
        return
    for chapter in chapters:
        md_path = draft_dir / f"{chapter.chapter_id}_draft_zh.md"
        if not md_path.is_file():
            continue
        by_id: dict[str, str] = {}
        current_id: str | None = None
        buf: list[str] = []
        for line in md_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("# "):
                continue
            match = _SEGMENT_ID_RE.match(line.strip())
            if match:
                if current_id and buf:
                    by_id[current_id] = "\n".join(buf).strip()
                current_id = match.group(1)
                buf = []
            elif current_id is not None:
                buf.append(line)
        if current_id and buf:
            by_id[current_id] = "\n".join(buf).strip()
        for seg in chapter.segments:
            if (seg.draft_text or "").strip():
                continue
            text = by_id.get(seg.segment_id, "")
            if text:
                seg.draft_text = text
                seg.status = "machine_translated"


def _count_translated_segments(chapters: list[ParsedChapter]) -> int:
    return sum(1 for ch in chapters for s in ch.segments if (s.draft_text or "").strip())


def _default_run_id(spec: DraftStageSpec) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    if spec.stage_key == "stage_b":
        return f"{spec.run_id_prefix}_{ts}_draft_stage_b_50ch"
    return f"{spec.run_id_prefix}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:8]}"


def run_draft_stage(
    *,
    spec: DraftStageSpec,
    repo_root: Path,
    input_dir: Path,
    limit_chapters: int,
    chapter_offset: int = 0,
    run_id: str | None = None,
    provider_factory: Callable[[CostGuard], Any] | None = None,
) -> tuple[DraftRunSummary, Path]:
    if limit_chapters > spec.limit_chapters:
        raise ValueError(f"{spec.scope} hard limit: max {spec.limit_chapters} chapters")
    run_id = run_id or _default_run_id(spec)
    run_root = repo_root / "workspace" / "runs" / run_id
    draft_dir = run_root / "draft"
    draft_dir.mkdir(parents=True, exist_ok=True)

    guard = CostGuard(CostGuardConfig.from_env())
    ctrl_cfg = ControlledRunConfig.from_env(checkpoint_dir=repo_root / "workspace" / "checkpoints")
    ctrl_cfg.run_id = run_id
    controlled = ControlledRunManager(ctrl_cfg)
    controlled.require_enabled()

    if provider_factory is not None:
        provider = provider_factory(guard)
        provider_mode = "custom"
        model_name = getattr(provider, "model_name", "unknown")
    else:
        mode = ProviderMode.FAKE if not guard.allow_real_network() else ProviderMode.REAL
        provider = get_provider(mode, cost_guard=guard)
        if mode == ProviderMode.FAKE:
            provider_mode = "fake"
            model_name = provider.model_name
        else:
            provider_mode = "real/model_router"
            model_name = provider.model_name or os.environ.get("DRAFT_MODEL", "")

    chapter_paths = list_chapter_files(input_dir, limit_chapters, offset=chapter_offset)
    if not chapter_paths:
        raise FileNotFoundError(
            f"no chapter files under {input_dir} (offset={chapter_offset}, limit={limit_chapters})"
        )

    parsed_chapters = [parse_chapter_file(p) for p in chapter_paths]
    _hydrate_from_segments_json(run_root, parsed_chapters)
    _hydrate_from_draft_md(run_root, parsed_chapters)
    total_expected = sum(len(ch.segments) for ch in parsed_chapters)
    translated_before = _count_translated_segments(parsed_chapters)
    if translated_before < total_expected and (
        controlled.checkpoint.status == "completed"
        or controlled.checkpoint.status.startswith("aborted")
    ):
        controlled.checkpoint.status = "in_progress"
        controlled.save()
    summary = DraftRunSummary(
        run_id=run_id,
        provider_mode=provider_mode,
        model_name=model_name,
    )

    for chapter in parsed_chapters:
        ch_result = ChapterRunResult(chapter_id=chapter.chapter_id, ok=True, message="ok")
        summary.total_segments += len(chapter.segments)

        for batch in _split_batches(chapter):
            pending = [s for s in batch if not (s.draft_text or "").strip()]
            if not pending:
                continue
            messages = build_batch_messages(pending, chapter_label=chapter.chapter_label)
            options = GenerateOptions(
                project_id="light-novel-jp-cn",
                language_direction="JP_TO_CN",
                pipeline_stage="draft_translation",
                input_reference=chapter.chapter_id,
            )
            result = None
            last_exc: Exception | None = None
            ok, msg = False, "no_attempt"
            for attempt in range(1, MAX_API_RETRIES + 1):
                try:
                    result = provider.generate(messages, options)
                    last_exc = None
                except (CostGuardError, RuntimeError, OSError) as exc:
                    last_exc = exc
                    result = None
                    if attempt >= MAX_API_RETRIES:
                        break
                    time.sleep(min(30, 5 * attempt))
                    continue
                ok, msg = _apply_items(chapter, pending, result.raw_output)
                if ok:
                    break
                result = None
                if attempt >= MAX_API_RETRIES:
                    break
                time.sleep(min(30, 5 * attempt))
            if last_exc is not None or result is None:
                exc = last_exc or RuntimeError(msg or "provider returned no result")
                summary.aborted = True
                summary.abort_reason = str(exc)
                controlled.abort(str(exc))
                ch_result.ok = False
                ch_result.message = str(exc)
                summary.chapters.append(ch_result)
                _write_run_artifacts(
                    repo_root,
                    run_root,
                    spec,
                    summary,
                    parsed_chapters,
                    chapter_paths,
                    input_dir,
                    chapter_offset=chapter_offset,
                )
                return summary, run_root

            summary.api_calls += 1
            ch_result.api_calls += 1
            if not ok:
                ch_result.ok = False
                ch_result.message = msg
                summary.aborted = True
                summary.abort_reason = f"{chapter.chapter_id}:{msg}"
                controlled.abort(summary.abort_reason)
                summary.chapters.append(ch_result)
                _write_run_artifacts(
                    repo_root,
                    run_root,
                    spec,
                    summary,
                    parsed_chapters,
                    chapter_paths,
                    input_dir,
                    chapter_offset=chapter_offset,
                )
                return summary, run_root

            for seg in pending:
                if seg.status == "machine_translated":
                    controlled.mark_segment_done(
                        seg.segment_id,
                        tokens=result.estimated_tokens // max(len(pending), 1),
                        cost_usd=result.cost_estimate_usd / max(len(pending), 1),
                    )
                    summary.translated_segments += 1
                    ch_result.segments_translated += 1

        export_chapter_markdown(chapter, draft_dir)
        summary.chapters.append(ch_result)

    summary.translated_segments = _count_translated_segments(parsed_chapters)
    if guard:
        summary.spent_usd = guard.spent_usd
        summary.spent_tokens = guard.spent_tokens
    elif controlled.checkpoint.spent_usd:
        summary.spent_usd = controlled.checkpoint.spent_usd
        summary.spent_tokens = controlled.checkpoint.spent_tokens

    controlled.complete()
    _write_run_artifacts(
        repo_root,
        run_root,
        spec,
        summary,
        parsed_chapters,
        chapter_paths,
        input_dir,
        chapter_offset=chapter_offset,
    )
    export_segments_doc(parsed_chapters, run_root / "segments.json")
    _write_quality_reports(run_root, spec, summary, parsed_chapters)
    return summary, run_root


def _write_run_artifacts(
    repo_root: Path,
    run_root: Path,
    spec: DraftStageSpec,
    summary: DraftRunSummary,
    chapters: list[ParsedChapter],
    chapter_paths: list[Path],
    input_dir: Path,
    *,
    chapter_offset: int = 0,
) -> None:
    export_segments_doc(chapters, run_root / "segments.json")
    meta = {
        "run_id": summary.run_id,
        "phase": "draft",
        "stage": spec.stage_key,
        "scope": spec.scope,
        "started_at": _utc_now(),
        "provider_mode": summary.provider_mode,
        "model_name": summary.model_name,
        "language_direction": "JP_TO_CN",
        "chapter_files": [str(p.relative_to(repo_root)) for p in chapter_paths],
        "input_dir": str(input_dir.relative_to(repo_root)),
        "limit_chapters": len(chapter_paths),
        "chapter_offset": chapter_offset,
        "real_api_called": summary.provider_mode.startswith("real"),
        "summary": {
            "total_segments": summary.total_segments,
            "translated_segments": summary.translated_segments,
            "api_calls": summary.api_calls,
            "spent_usd": summary.spent_usd,
            "spent_tokens": summary.spent_tokens,
            "aborted": summary.aborted,
            "abort_reason": summary.abort_reason,
        },
    }
    (run_root / "run_metadata.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_quality_reports(
    run_root: Path,
    spec: DraftStageSpec,
    summary: DraftRunSummary,
    chapters: list[ParsedChapter],
) -> None:
    total = summary.total_segments
    done = _count_translated_segments(chapters)
    summary.translated_segments = done
    coverage = done / total if total else 0.0
    chapter_ok = all(c.ok for c in summary.chapters)
    passed = (
        not summary.aborted
        and chapter_ok
        and coverage >= 0.98
        and done == total
    )
    next_eligible_key = (
        "stage_c_eligible" if spec.stage_key == "stage_b" else "stage_b_eligible"
    )
    report = {
        "run_id": summary.run_id,
        "phase": "draft",
        "stage": spec.stage_key,
        "scope": spec.scope,
        "coverage_ratio": round(coverage, 4),
        "segments_total": total,
        "segments_translated": done,
        "api_calls": summary.api_calls,
        "cost_usd": summary.spent_usd,
        "provider_mode": summary.provider_mode,
        "model_name": summary.model_name,
        "chapter_results": [
            {
                "chapter_id": c.chapter_id,
                "ok": c.ok,
                "message": c.message,
                "segments_translated": c.segments_translated,
            }
            for c in summary.chapters
        ],
        "passed": passed,
        next_eligible_key: passed,
        "generated_at": _utc_now(),
    }
    (run_root / "draft_quality_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    stage_title = "Stage A" if spec.stage_key == "stage_a" else "Stage B"
    chapter_cap = spec.limit_chapters
    md_lines = [
        f"# Draft {stage_title} 质量报告",
        "",
        f"- run_id: `{summary.run_id}`",
        f"- scope: `{spec.scope}`",
        f"- provider: `{summary.provider_mode}` / `{summary.model_name}`",
        f"- 段落覆盖: {done}/{total} ({coverage * 100:.1f}%)",
        f"- API 调用次数: {summary.api_calls}",
        f"- 估算成本 (USD): {summary.spent_usd:.6f}",
        f"- 门禁: **{'PASS' if passed else 'FAIL'}**",
        "",
        "## 章节",
        "",
    ]
    for ch in summary.chapters:
        md_lines.append(f"- {ch.chapter_id}: {'OK' if ch.ok else 'FAIL'} — {ch.message}")
    md_lines.extend(
        [
            "",
            f"## {spec.next_stage_label} 晋级",
            "",
            (
                f"可晋级 {spec.next_stage_label}（受控扩章）"
                if passed
                else "不可晋级：需修复流水线后重跑，禁止手改译文"
            ),
            "",
        ]
    )
    (run_root / "draft_quality_report.md").write_text("\n".join(md_lines), encoding="utf-8")
    go = "go" if passed else "no-go"
    stage_label = (
        f"Stage A draft ({chapter_cap} chapters)"
        if spec.stage_key == "stage_a"
        else f"Stage B draft ({chapter_cap} chapters, ch-001–ch-{chapter_cap:03d})"
    )
    (run_root / spec.go_decision_filename).write_text(
        "\n".join(
            [
                f"# Go decision: **{go}**",
                "",
                f"{stage_label}: {'PASS' if passed else 'FAIL'}.",
                "",
                "Refine phase is **blocked** until baseline draft exists and passes quality gate.",
                "",
            ]
        ),
        encoding="utf-8",
    )
