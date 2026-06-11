"""Run draft Stage A/B translation for bounded chapter sets."""

from __future__ import annotations

import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

REPO_SCRIPTS = Path(__file__).resolve().parent.parent.parent / "scripts"
if str(REPO_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(REPO_SCRIPTS))

from plan_translation_batches import plan_batches, split_failed_batch  # noqa: E402

from providers.controlled_run import ControlledRunConfig, ControlledRunManager
from providers.cost_guard import CostGuard, CostGuardConfig, CostGuardError
from providers.registry import ProviderMode, get_provider
from providers.types import GenerateOptions
from translation.chapter_parser import ParsedChapter, Segment, list_chapter_files, parse_chapter_file
from translation.exporter import export_chapter_markdown, export_segments_doc
from translation.pipeline_events import classify_error, emit_event
from translation.prompt_builder import build_batch_messages
from translation.response_extractor import extract_translations
from translation.run_progress import init_run_metadata, write_run_progress
from translation.stop_control import StopRequested, check_stop_or_raise
from translation.validator import validate_draft_items

MAX_CHARS_PER_BATCH = 5_500
MAX_SEGMENTS_PER_BATCH = 8
MAX_API_RETRIES = 3
STAGE_A_MAX_CHAPTERS = 5
STAGE_B_MAX_CHAPTERS = 50
DEFAULT_BATCH_TOKEN_BUDGET = 12_000
DEFAULT_MAX_SEGMENTS_PER_CALL = 30


@dataclass
class RunBudget:
    max_api_calls: int = 0
    max_segments: int = 0
    max_wall_seconds: float = 0.0
    progress_interval_seconds: float = 30.0
    api_calls_used: int = 0
    segments_used: int = 0
    started_at: float = field(default_factory=time.monotonic)
    last_progress_at: float = 0.0

    def exhausted(self) -> bool:
        if self.max_api_calls > 0 and self.api_calls_used >= self.max_api_calls:
            return True
        if self.max_segments > 0 and self.segments_used >= self.max_segments:
            return True
        if self.max_wall_seconds > 0 and (time.monotonic() - self.started_at) >= self.max_wall_seconds:
            return True
        return False

    def should_write_progress(self) -> bool:
        if self.progress_interval_seconds <= 0:
            return False
        now = time.monotonic()
        if now - self.last_progress_at >= self.progress_interval_seconds:
            self.last_progress_at = now
            return True
        return False


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
    asset_context_path: str = ""
    aborted: bool = False
    abort_reason: str = ""
    tick_paused: bool = False


class DraftRunEarlyExit(Exception):
    """Internal control flow when draft run ends early (failure path)."""

    def __init__(self, summary: DraftRunSummary, run_root: Path) -> None:
        self.summary = summary
        self.run_root = run_root
        super().__init__("draft_run_early_exit")


class DraftRunTickExit(Exception):
    """Supervised tick budget exhausted; checkpoint saved, resume on next tick."""

    def __init__(self, summary: DraftRunSummary, run_root: Path) -> None:
        self.summary = summary
        self.run_root = run_root
        super().__init__("draft_run_tick_exit")


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


def _split_batches_planned(
    chapter: ParsedChapter,
    *,
    batch_token_budget: int,
    max_segments_per_call: int,
) -> list[list[Segment]]:
    plan = plan_batches(
        chapter.segments,
        token_budget=batch_token_budget,
        max_segments_per_call=max_segments_per_call,
    )
    by_id = {s.segment_id: s for s in chapter.segments}
    batches: list[list[Segment]] = []
    for planned in plan.batches:
        batch = [by_id[sid] for sid in planned.segment_ids if sid in by_id]
        if batch:
            batches.append(batch)
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
    asset_context_path: Path | None = None,
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
        asset_context_path=asset_context_path,
    )


def run_draft_stage_b(
    *,
    repo_root: Path,
    input_dir: Path,
    limit_chapters: int = STAGE_B_MAX_CHAPTERS,
    chapter_offset: int = 0,
    run_id: str | None = None,
    provider_factory: Callable[[CostGuard], Any] | None = None,
    asset_context_path: Path | None = None,
    heartbeat_cb: Callable[[], None] | None = None,
    worker_id: str = "",
    tick_max_segments: int = 0,
    tick_max_wall_seconds: float = 0,
    batch_token_budget: int = 0,
    max_segments_per_call: int = 0,
    compact_context: bool = False,
    asset_context_path_resolved: Path | None = None,
    run_budget: RunBudget | None = None,
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
        asset_context_path=asset_context_path,
        heartbeat_cb=heartbeat_cb,
        worker_id=worker_id,
        tick_max_segments=tick_max_segments,
        tick_max_wall_seconds=tick_max_wall_seconds,
        batch_token_budget=batch_token_budget,
        max_segments_per_call=max_segments_per_call,
        compact_context=compact_context,
        asset_context_path_resolved=asset_context_path_resolved,
        run_budget=run_budget,
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


def _load_asset_context(repo_root: Path, path: Path | None) -> tuple[str, str]:
    if path is None:
        return "", ""
    resolved = path if path.is_absolute() else repo_root / path
    if not resolved.is_file():
        raise FileNotFoundError(f"asset context not found: {resolved}")
    from assets.translation_memory import render_translation_asset_context

    rendered = render_translation_asset_context(resolved)
    try:
        rel = str(resolved.relative_to(repo_root))
    except ValueError:
        rel = str(resolved)
    return rendered, rel


def _segment_needs_translation(seg: Segment) -> bool:
    """Skip segments with draft_text; re-translate checkpoint-done segments missing draft."""
    return not (seg.draft_text or "").strip()


def run_draft_stage(
    *,
    spec: DraftStageSpec,
    repo_root: Path,
    input_dir: Path,
    limit_chapters: int,
    chapter_offset: int = 0,
    run_id: str | None = None,
    provider_factory: Callable[[CostGuard], Any] | None = None,
    asset_context_path: Path | None = None,
    heartbeat_cb: Callable[[], None] | None = None,
    worker_id: str = "",
    tick_max_segments: int = 0,
    tick_max_wall_seconds: float = 0,
    batch_token_budget: int = 0,
    max_segments_per_call: int = 0,
    compact_context: bool = False,
    asset_context_path_resolved: Path | None = None,
    run_budget: RunBudget | None = None,
) -> tuple[DraftRunSummary, Path]:
    if limit_chapters > spec.limit_chapters:
        raise ValueError(f"{spec.scope} hard limit: max {spec.limit_chapters} chapters")
    run_id = run_id or _default_run_id(spec)
    run_root = repo_root / "workspace" / "runs" / run_id
    draft_dir = run_root / "draft"
    draft_dir.mkdir(parents=True, exist_ok=True)

    init_run_metadata(
        run_root,
        run_id=run_id,
        phase="draft",
        stage=spec.stage_key,
        scope=spec.scope,
        chapter_offset=chapter_offset,
    )

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
    asset_context, asset_context_ref = _load_asset_context(repo_root, asset_context_path)
    asset_resolved = asset_context_path
    if asset_resolved is not None and not asset_resolved.is_absolute():
        asset_resolved = repo_root / asset_resolved
    use_planner = batch_token_budget > 0 or max_segments_per_call > 0
    if use_planner and batch_token_budget <= 0:
        batch_token_budget = DEFAULT_BATCH_TOKEN_BUDGET
    if use_planner and max_segments_per_call <= 0:
        max_segments_per_call = DEFAULT_MAX_SEGMENTS_PER_CALL
    if run_budget is None and (
        os.environ.get("MICRO_ROUND_MAX_API_CALLS")
        or os.environ.get("MICRO_ROUND_MAX_SEGMENTS")
    ):
        run_budget = RunBudget(
            max_api_calls=int(os.environ.get("MICRO_ROUND_MAX_API_CALLS", "0") or 0),
            max_segments=int(os.environ.get("MICRO_ROUND_MAX_SEGMENTS", "0") or 0),
            max_wall_seconds=float(os.environ.get("MICRO_ROUND_MAX_WALL_SECONDS", "0") or 0),
            progress_interval_seconds=float(
                os.environ.get("MICRO_ROUND_PROGRESS_INTERVAL", "30") or 30
            ),
        )
    _hydrate_from_segments_json(run_root, parsed_chapters)
    _hydrate_from_draft_md(run_root, parsed_chapters)
    total_expected = sum(len(ch.segments) for ch in parsed_chapters)
    translated_before = _count_translated_segments(parsed_chapters)

    write_run_progress(
        run_root,
        run_id=run_id,
        phase="draft",
        stage=spec.scope,
        chapter_offset=chapter_offset,
        status="in_progress",
        total_segments=total_expected,
        completed_segments=translated_before,
    )
    emit_event("draft_start", run_id=run_id, phase="draft", stage=spec.scope)
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
        asset_context_path=asset_context_ref,
    )

    try:
        _run_chapter_batches(
            parsed_chapters=parsed_chapters,
            summary=summary,
            controlled=controlled,
            provider=provider,
            asset_context=asset_context,
            run_root=run_root,
            run_id=run_id,
            spec=spec,
            chapter_offset=chapter_offset,
            total_expected=total_expected,
            draft_dir=draft_dir,
            heartbeat_cb=heartbeat_cb,
            worker_id=worker_id,
            repo_root=repo_root,
            chapter_paths=chapter_paths,
            input_dir=input_dir,
            tick_max_segments=tick_max_segments,
            tick_max_wall_seconds=tick_max_wall_seconds,
            batch_token_budget=batch_token_budget if use_planner else 0,
            max_segments_per_call=max_segments_per_call if use_planner else 0,
            compact_context=compact_context or use_planner,
            asset_resolved=asset_resolved,
            run_budget=run_budget,
        )
    except DraftRunTickExit as tick_exit:
        tick_exit.summary.tick_paused = True
        tick_exit.summary.translated_segments = _count_translated_segments(parsed_chapters)
        if guard:
            tick_exit.summary.spent_usd = guard.spent_usd
            tick_exit.summary.spent_tokens = guard.spent_tokens
        controlled.checkpoint.status = "in_progress"
        controlled.save()
        write_run_progress(
            run_root,
            run_id=run_id,
            phase="draft",
            stage=spec.scope,
            chapter_offset=chapter_offset,
            status="in_progress",
            total_segments=total_expected,
            completed_segments=tick_exit.summary.translated_segments,
        )
        export_segments_doc(parsed_chapters, run_root / "segments.json")
        _write_run_artifacts(
            repo_root,
            run_root,
            spec,
            tick_exit.summary,
            parsed_chapters,
            chapter_paths,
            input_dir,
            chapter_offset=chapter_offset,
        )
        return tick_exit.summary, tick_exit.run_root
    except DraftRunEarlyExit as early:
        return early.summary, early.run_root
    except StopRequested:
        summary.aborted = True
        summary.abort_reason = "stopped_by_controller"
        summary.translated_segments = _count_translated_segments(parsed_chapters)
        controlled.abort("stopped_by_controller")
        write_run_progress(
            run_root,
            run_id=run_id,
            phase="draft",
            stage=spec.scope,
            chapter_offset=chapter_offset,
            status="stopped_by_controller",
            total_segments=total_expected,
            completed_segments=summary.translated_segments,
            last_error_type="stopped_by_controller",
        )
        export_segments_doc(parsed_chapters, run_root / "segments.json")
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
        raise

    summary.translated_segments = _count_translated_segments(parsed_chapters)
    if guard:
        summary.spent_usd = guard.spent_usd
        summary.spent_tokens = guard.spent_tokens
    elif controlled.checkpoint.spent_usd:
        summary.spent_usd = controlled.checkpoint.spent_usd
        summary.spent_tokens = controlled.checkpoint.spent_tokens

    controlled.complete()
    final_status = "failed" if summary.aborted else "completed"
    write_run_progress(
        run_root,
        run_id=run_id,
        phase="draft",
        stage=spec.scope,
        chapter_offset=chapter_offset,
        status=final_status,
        total_segments=total_expected,
        completed_segments=summary.translated_segments,
        last_error_type=classify_error(summary.abort_reason) if summary.aborted else "",
    )
    emit_event("draft_complete", run_id=run_id, phase="draft", stage=spec.scope, status=final_status)
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


def _tick_budget_exhausted(
    *,
    tick_start: float,
    segments_this_tick: int,
    tick_max_segments: int,
    tick_max_wall_seconds: float,
) -> bool:
    if tick_max_segments > 0 and segments_this_tick >= tick_max_segments:
        return True
    if tick_max_wall_seconds > 0 and (time.monotonic() - tick_start) >= tick_max_wall_seconds:
        return True
    return False


def _write_compact_progress(
    run_root: Path,
    *,
    run_id: str,
    round_id: str,
    summary: DraftRunSummary,
    chapter_offset: int,
    total_expected: int,
    completed: int,
    run_budget: RunBudget | None,
    status: str = "in_progress",
) -> None:
    payload = {
        "schema_version": 1,
        "run_id": run_id,
        "round_id": round_id,
        "status": status,
        "progress": f"{completed}/{total_expected}",
        "api_calls": summary.api_calls,
        "cost_usd": round(summary.spent_usd, 6),
        "segments_per_call": round(summary.api_calls and (completed / summary.api_calls) or 0, 2),
        "updated_at": _utc_now(),
    }
    if run_budget:
        payload["budget"] = {
            "max_api_calls": run_budget.max_api_calls,
            "max_segments": run_budget.max_segments,
            "api_calls_used": run_budget.api_calls_used,
            "segments_used": run_budget.segments_used,
        }
    path = run_root / "micro_round_progress.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _run_chapter_batches(
    *,
    parsed_chapters: list[ParsedChapter],
    summary: DraftRunSummary,
    controlled: Any,
    provider: Any,
    asset_context: str,
    run_root: Path,
    run_id: str,
    spec: DraftStageSpec,
    chapter_offset: int,
    total_expected: int,
    draft_dir: Path,
    heartbeat_cb: Callable[[], None] | None,
    worker_id: str,
    repo_root: Path,
    chapter_paths: list[Path],
    input_dir: Path,
    tick_max_segments: int = 0,
    tick_max_wall_seconds: float = 0,
    batch_token_budget: int = 0,
    max_segments_per_call: int = 0,
    compact_context: bool = False,
    asset_resolved: Path | None = None,
    run_budget: RunBudget | None = None,
) -> None:
    tick_start = time.monotonic()
    segments_this_tick = 0
    tick_limited = tick_max_segments > 0 or tick_max_wall_seconds > 0
    use_planner = batch_token_budget > 0 or max_segments_per_call > 0
    round_id = os.environ.get("TRANSLATION_ROUND_ID", "")

    if run_budget and run_budget.last_progress_at <= 0:
        run_budget.last_progress_at = time.monotonic()

    for chapter in parsed_chapters:
        ch_result = ChapterRunResult(chapter_id=chapter.chapter_id, ok=True, message="ok")
        summary.total_segments += len(chapter.segments)

        if use_planner:
            batch_list = _split_batches_planned(
                chapter,
                batch_token_budget=batch_token_budget,
                max_segments_per_call=max_segments_per_call,
            )
        else:
            batch_list = _split_batches(chapter)

        batch_queue: list[list[Segment]] = list(batch_list)

        while batch_queue:
            batch = batch_queue.pop(0)
            if tick_limited and _tick_budget_exhausted(
                tick_start=tick_start,
                segments_this_tick=segments_this_tick,
                tick_max_segments=tick_max_segments,
                tick_max_wall_seconds=tick_max_wall_seconds,
            ):
                raise DraftRunTickExit(summary, run_root)
            if run_budget and run_budget.exhausted():
                export_segments_doc(parsed_chapters, run_root / "segments.json")
                controlled.save()
                raise DraftRunTickExit(summary, run_root)

            check_stop_or_raise(worker_id=worker_id, run_id=run_id, repo_root=repo_root)
            pending = [s for s in batch if _segment_needs_translation(s)]
            if not pending:
                continue
            if heartbeat_cb:
                heartbeat_cb()
            check_stop_or_raise(worker_id=worker_id, run_id=run_id, repo_root=repo_root)

            glossary_hits = ""
            if compact_context:
                hit_blocks: list[str] = []
                if asset_resolved and asset_resolved.is_file():
                    from assets.translation_memory import select_batch_context_hits

                    tm_hits = select_batch_context_hits(
                        asset_resolved,
                        [s.source_text for s in pending],
                    )
                    if tm_hits:
                        hit_blocks.append(tm_hits)
                # FS-016: configs asset layer (batch-hit subset only, spec §22)
                from translation.configs_asset_context import build_configs_asset_context

                configs_ctx = build_configs_asset_context(
                    [s.source_text for s in pending]
                )
                if not configs_ctx.empty:
                    hit_blocks.append(configs_ctx.text)
                glossary_hits = "\n".join(hit_blocks)

            messages = build_batch_messages(
                pending,
                chapter_label=chapter.chapter_label,
                asset_context=asset_context if not compact_context else None,
                compact_context=compact_context,
                glossary_hits=glossary_hits,
            )
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
                if heartbeat_cb:
                    heartbeat_cb()
                check_stop_or_raise(worker_id=worker_id, run_id=run_id, repo_root=repo_root)
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
                write_run_progress(
                    run_root,
                    run_id=run_id,
                    phase="draft",
                    stage=spec.scope,
                    chapter_offset=chapter_offset,
                    status="failed",
                    total_segments=total_expected,
                    completed_segments=_count_translated_segments(parsed_chapters),
                    last_error_type=classify_error(str(exc)),
                )
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
                raise DraftRunEarlyExit(summary, run_root)

            if not ok:
                if len(pending) > 1 and use_planner:
                    for part in reversed(split_failed_batch(pending)):
                        batch_queue.insert(0, part)
                    continue
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
                raise DraftRunEarlyExit(summary, run_root)

            summary.api_calls += 1
            ch_result.api_calls += 1
            if run_budget:
                run_budget.api_calls_used += 1

            segments_flush_interval = max(
                1, int(os.environ.get("SEGMENTS_FLUSH_INTERVAL", "10"))
            )
            segments_since_flush = 0
            for seg in pending:
                if seg.status == "machine_translated":
                    if not controlled.is_segment_done(seg.segment_id):
                        controlled.mark_segment_done(
                            seg.segment_id,
                            tokens=result.estimated_tokens // max(len(pending), 1),
                            cost_usd=result.cost_estimate_usd / max(len(pending), 1),
                        )
                    summary.translated_segments += 1
                    ch_result.segments_translated += 1
                    segments_since_flush += 1
                    segments_this_tick += 1
                    if run_budget:
                        run_budget.segments_used += 1
                    if tick_limited and _tick_budget_exhausted(
                        tick_start=tick_start,
                        segments_this_tick=segments_this_tick,
                        tick_max_segments=tick_max_segments,
                        tick_max_wall_seconds=tick_max_wall_seconds,
                    ):
                        export_segments_doc(parsed_chapters, run_root / "segments.json")
                        controlled.save()
                        raise DraftRunTickExit(summary, run_root)
                    if run_budget and run_budget.exhausted():
                        export_segments_doc(parsed_chapters, run_root / "segments.json")
                        controlled.save()
                        raise DraftRunTickExit(summary, run_root)
                    write_run_progress(
                        run_root,
                        run_id=run_id,
                        phase="draft",
                        stage=spec.scope,
                        chapter_offset=chapter_offset,
                        status="in_progress",
                        total_segments=total_expected,
                        completed_segments=_count_translated_segments(parsed_chapters),
                        last_completed_segment_id=seg.segment_id,
                    )
                    if segments_since_flush >= segments_flush_interval:
                        export_segments_doc(parsed_chapters, run_root / "segments.json")
                        segments_since_flush = 0
            export_segments_doc(parsed_chapters, run_root / "segments.json")
            controlled.save()
            if run_budget and run_budget.should_write_progress():
                completed = _count_translated_segments(parsed_chapters)
                _write_compact_progress(
                    run_root,
                    run_id=run_id,
                    round_id=round_id,
                    summary=summary,
                    chapter_offset=chapter_offset,
                    total_expected=total_expected,
                    completed=completed,
                    run_budget=run_budget,
                )
            if heartbeat_cb:
                heartbeat_cb()

        export_chapter_markdown(chapter, draft_dir)
        summary.chapters.append(ch_result)


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
    existing_meta = {}
    meta_path = run_root / "run_metadata.json"
    if meta_path.is_file():
        try:
            existing_meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            existing_meta = {}
    meta = {
        "run_id": summary.run_id,
        "phase": "draft",
        "stage": spec.stage_key,
        "scope": spec.scope,
        "started_at": existing_meta.get("started_at") or _utc_now(),
        "provider_mode": summary.provider_mode,
        "model_name": summary.model_name,
        "asset_context_path": summary.asset_context_path,
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
