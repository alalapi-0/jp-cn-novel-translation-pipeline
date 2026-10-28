"""Run draft Stage A/B translation for bounded chapter sets."""

from __future__ import annotations

import json
import hashlib
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

from providers.controlled_run import ControlledRunConfig, ControlledRunManager, checkpoint_lock
from translation.draft_execution import DraftExecution
from providers.content_unit_budget import ContentUnitBudget
from providers.cost_guard import CostGuard, CostGuardConfig, CostGuardError
from providers.registry import ProviderMode, get_provider
from providers.types import GenerateOptions
from translation.chapter_parser import ParsedChapter, Segment, list_chapter_files, parse_chapter_file, chapter_id_from_path
from translation.exporter import export_chapter_markdown, export_segments_doc
from translation.pipeline_events import classify_error, emit_event
from translation.prompt_builder import build_batch_messages
from translation.context_policy import SourceContextCatalog, SourceContextPolicy
from translation.narrative_context import NarrativeContextCatalog
from translation.response_extractor import extract_translations
from translation.run_progress import init_run_metadata, write_run_progress
from translation.stop_control import StopRequested, check_stop_or_raise
from translation.validator import validate_draft_items

MAX_CHARS_PER_BATCH = 5_500
MAX_SEGMENTS_PER_BATCH = 8
MAX_API_RETRIES = 2
STAGE_A_MAX_CHAPTERS = 5
STAGE_B_MAX_CHAPTERS = 50
DEFAULT_BATCH_TOKEN_BUDGET = 12_000
DEFAULT_MAX_SEGMENTS_PER_CALL = 30
DEFAULT_PROVIDER_TIMEOUT_SECONDS = 120
# draft_translation currently routes through OpenRouter (3 attempts) and one
# fallback provider (2 attempts). Reserve wall time for the whole route chain.
MAX_ROUTER_ATTEMPTS_PER_GENERATE = 5
WALL_TIME_START_SAFETY_SECONDS = 5.0


@dataclass
class RunBudget:
    max_api_calls: int | None = None
    max_segments: int = 0
    max_wall_seconds: float = 0.0
    progress_interval_seconds: float = 30.0
    api_calls_used: int = 0
    segments_used: int = 0
    started_at: float = field(default_factory=time.monotonic)
    last_progress_at: float = 0.0

    def exhausted(self) -> bool:
        if self.max_api_calls is not None and self.api_calls_used >= self.max_api_calls:
            return True
        if self.max_segments > 0 and self.segments_used >= self.max_segments:
            return True
        if self.max_wall_seconds > 0 and (time.monotonic() - self.started_at) >= self.max_wall_seconds:
            return True
        return False

    def remaining_wall_seconds(self) -> float | None:
        if self.max_wall_seconds <= 0:
            return None
        elapsed = time.monotonic() - self.started_at
        return max(0.0, self.max_wall_seconds - elapsed)

    def should_write_progress(self) -> bool:
        if self.progress_interval_seconds <= 0:
            return False
        now = time.monotonic()
        if now - self.last_progress_at >= self.progress_interval_seconds:
            self.last_progress_at = now
            return True
        return False


def _bound_provider_timeout(
    provider: Any,
    run_budget: RunBudget | None,
    *,
    outer_attempts_remaining: int,
) -> int | None:
    """Keep a routed provider call inside the remaining run wall budget."""
    if run_budget is None or not hasattr(provider, "timeout_sec"):
        return None
    remaining = run_budget.remaining_wall_seconds()
    if remaining is None:
        return None

    retry_slots = max(1, outer_attempts_remaining) * MAX_ROUTER_ATTEMPTS_PER_GENERATE
    usable = max(1.0, remaining - WALL_TIME_START_SAFETY_SECONDS)
    budget_timeout = max(1, int(usable / retry_slots))
    current = getattr(provider, "timeout_sec", None)
    caps = [DEFAULT_PROVIDER_TIMEOUT_SECONDS, budget_timeout]
    if isinstance(current, (int, float)) and current > 0:
        caps.append(int(current))
    timeout = max(1, min(caps))
    provider.timeout_sec = timeout
    return timeout


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
    validation_warnings: list[dict[str, Any]] = field(default_factory=list)


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
    simulated: bool = False
    simulated_segments: int = 0
    provider_attempts: int = 0


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


def _apply_items(chapter: ParsedChapter, batch: list[Segment], raw_output: str,
                 *, warnings: list[dict[str, Any]] | None = None) -> tuple[bool, str]:
    expected = [s.segment_id for s in batch]
    if any(not isinstance(sid, str) or not sid.strip() for sid in expected):
        return False, "validate:invalid_expected_id"
    source_lengths = {s.segment_id: len(s.source_text) for s in batch}
    extracted = extract_translations(raw_output, expected)
    if extracted.parse_status != "ok":
        return False, ";".join(extracted.parse_errors) or "extract_failed"

    validation = validate_draft_items(extracted.items, expected, source_lengths)
    if not validation.passed:
        codes = ",".join(i.code for i in validation.issues[:5])
        return False, f"validate:{codes}"

    if warnings is not None:
        warnings.extend(validation.to_dict()["issues"])

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
    source_context_policy: SourceContextPolicy | None = None,
    narrative_catalog: NarrativeContextCatalog | None = None,
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
        source_context_policy=source_context_policy,
        narrative_catalog=narrative_catalog,
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
    source_context_policy: SourceContextPolicy | None = None,
    narrative_catalog: NarrativeContextCatalog | None = None,
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
        source_context_policy=source_context_policy,
        narrative_catalog=narrative_catalog,
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


def _segment_needs_translation(seg: Segment) -> bool:
    """Skip segments with draft_text; re-translate checkpoint-done segments missing draft."""
    return not (seg.draft_text or "").strip()


def run_draft_stage(*, spec, repo_root, input_dir, **kwargs):
    if kwargs.get('asset_context_path') is not None or kwargs.get('asset_context_path_resolved') is not None:
        raise ValueError('unscoped asset context is disabled; provide source-bound narrative_catalog')
    selected=list_chapter_files(input_dir,kwargs['limit_chapters'],offset=kwargs.get('chapter_offset',0))
    ids=[chapter_id_from_path(path) for path in selected]
    if len(set(ids))!=len(ids):
        raise ValueError('duplicate draft chapter identity; source binding is ambiguous')
    run_id=kwargs.pop("run_id", None) or _default_run_id(spec)
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", run_id) or run_id in {".", ".."}:
        raise ValueError("invalid draft run identity")
    guard=CostGuard(CostGuardConfig.from_env())
    factory=kwargs.get("provider_factory")
    mode=ProviderMode.FAKE if not guard.allow_real_network() else ProviderMode.REAL
    provider=factory(guard) if factory else get_provider(mode,cost_guard=guard)
    simulated=getattr(provider,"provider_id","") in {"fake","dry_run","fake_provider","dry_run_provider"}
    base=repo_root/"workspace"/("simulations" if simulated else "")
    run_root=base/"runs"/run_id
    with checkpoint_lock(run_root/"draft_execution"):
        return _run_draft_stage_owned(spec=spec,repo_root=repo_root,input_dir=input_dir,run_id=run_id,
            _prepared=(guard,provider,simulated,base),**kwargs)


def _run_draft_stage_owned(
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
    source_context_policy: SourceContextPolicy | None = None,
    narrative_catalog: NarrativeContextCatalog | None = None,
    _prepared: tuple | None = None,
) -> tuple[DraftRunSummary, Path]:
    if limit_chapters > spec.limit_chapters:
        raise ValueError(f"{spec.scope} hard limit: max {spec.limit_chapters} chapters")
    run_id = run_id or _default_run_id(spec)
    guard, provider, simulated, base = _prepared
    run_root = base / "runs" / run_id
    draft_dir = run_root / "draft"
    ctrl_cfg = ControlledRunConfig.from_env(checkpoint_dir=base / "checkpoints")
    ctrl_cfg.run_id = run_id
    controlled = ControlledRunManager(ctrl_cfg)
    controlled.require_enabled()
    provider_mode = "fake" if simulated else ("custom" if provider_factory else "real/model_router")
    model_name = getattr(provider, "model_name", "unknown")

    chapter_paths = list_chapter_files(input_dir, limit_chapters, offset=chapter_offset)
    if not chapter_paths:
        raise FileNotFoundError(
            f"no chapter files under {input_dir} (offset={chapter_offset}, limit={limit_chapters})"
        )

    source_bytes={str(p):p.read_bytes() for p in chapter_paths}
    source_hashes={key:hashlib.sha256(raw).hexdigest() for key,raw in source_bytes.items()}
    parsed_chapters = [parse_chapter_file(p,source_bytes=source_bytes[str(p)]) for p in chapter_paths]
    chapter_ids = [ch.chapter_id for ch in parsed_chapters]
    segment_ids = [s.segment_id for ch in parsed_chapters for s in ch.segments]
    if len(set(chapter_ids)) != len(chapter_ids) or len(set(segment_ids)) != len(segment_ids):
        raise ValueError('duplicate draft chapter or segment identity; source binding is ambiguous')
    if any(hashlib.sha256(p.read_bytes()).hexdigest()!=source_hashes[str(p)] for p in chapter_paths):
        raise RuntimeError("source changed while parsing draft inputs")
    source_context_policy=SourceContextPolicy() if source_context_policy is None else source_context_policy
    if not isinstance(source_context_policy,SourceContextPolicy):raise ValueError("invalid source context policy")
    source_catalog=SourceContextCatalog(parsed_chapters)
    narrative_catalog=NarrativeContextCatalog(source_catalog) if narrative_catalog is None else narrative_catalog
    if not isinstance(narrative_catalog,NarrativeContextCatalog) or narrative_catalog.source.sha256!=source_catalog.sha256:
        raise ValueError("narrative context differs from selected source catalog")
    asset_context, asset_context_ref = "", ""
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
    if run_budget is None:
        run_budget = RunBudget()
    identity = {"run_id":run_id,"mode":provider_mode,"stage":spec.stage_key,
        "sources":[{"path":str(p.resolve()),"sha256":source_hashes[str(p)]} for p in chapter_paths],
        "asset_context_sha256":hashlib.sha256(asset_context.encode()).hexdigest() if isinstance(asset_context,str) else hashlib.sha256(json.dumps(asset_context,sort_keys=True,ensure_ascii=False).encode()).hexdigest(),
        "provider":getattr(provider,"provider_id","unknown"),"model":model_name,
        "planner":[batch_token_budget,max_segments_per_call,compact_context],
        "source_context":source_catalog.identity(source_context_policy),
        "narrative_context":narrative_catalog.identity(),
        "source_bindings":[{'chapter_id':ch.chapter_id,'source_revision':ch.source_revision,
                            'parser_version':ch.parser_version,
                            'bindings':[seg.source_binding for seg in ch.segments]} for ch in parsed_chapters]}
    execution = DraftExecution(controlled,run_budget,guard,run_root,identity)
    execution.content_units = {ch.chapter_id: ContentUnitBudget(base / 'checkpoints',
        source_bytes[str(path)].decode('utf-8')) for ch, path in zip(parsed_chapters, chapter_paths)}
    controlled.draft_execution = execution
    draft_dir.mkdir(parents=True,exist_ok=True)
    init_run_metadata(run_root,run_id=run_id,phase="draft",stage=spec.stage_key,scope=spec.scope,chapter_offset=chapter_offset)
    _hydrate_from_segments_json(run_root, parsed_chapters)
    execution.reconcile_done(parsed_chapters,simulated)
    controlled.draft_execution.save_segments(parsed_chapters)
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
        execution.set_status("in_progress")
    summary = DraftRunSummary(
        run_id=run_id,
        provider_mode=provider_mode,
        model_name=model_name,
        asset_context_path=asset_context_ref,
        api_calls=0 if simulated else run_budget.api_calls_used,
        simulated=simulated,
        total_segments=total_expected,
        provider_attempts=execution.state.get("provider_attempts",0),
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
            run_budget=run_budget,
            execution=execution,
            source_catalog=source_catalog,source_context_policy=source_context_policy,
            narrative_catalog=narrative_catalog,
        )
    except DraftRunTickExit as tick_exit:
        tick_exit.summary.tick_paused = True
        tick_exit.summary.translated_segments = _count_translated_segments(parsed_chapters)
        if tick_exit.summary.simulated:
            tick_exit.summary.simulated_segments=tick_exit.summary.translated_segments
            tick_exit.summary.translated_segments=0
        if guard:
            tick_exit.summary.spent_usd = guard.spent_usd
            tick_exit.summary.spent_tokens = guard.spent_tokens
        execution.set_status("in_progress")
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
        controlled.draft_execution.save_segments(parsed_chapters)
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
        controlled.draft_execution.save_segments(parsed_chapters)
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
    summary.spent_usd=max(guard.spent_usd,controlled.checkpoint.spent_usd)
    summary.spent_tokens=max(guard.spent_tokens,controlled.checkpoint.spent_tokens)

    if simulated:
        execution.set_status("simulated")
        summary.simulated_segments=summary.translated_segments
        summary.translated_segments=0
    else:
        controlled.complete()
    final_status = "simulated" if simulated else ("failed" if summary.aborted else "completed")
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
    controlled.draft_execution.save_segments(parsed_chapters)
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
    run_budget: RunBudget | None = None,
    execution: DraftExecution | None = None,
    source_catalog: SourceContextCatalog | None = None,
    source_context_policy: SourceContextPolicy | None = None,
    narrative_catalog: NarrativeContextCatalog | None = None,
) -> None:
    source_catalog=source_catalog or SourceContextCatalog(parsed_chapters)
    source_context_policy=SourceContextPolicy() if source_context_policy is None else source_context_policy
    tick_start = time.monotonic()
    segments_this_tick = 0
    tick_limited = tick_max_segments > 0 or tick_max_wall_seconds > 0
    use_planner = batch_token_budget > 0 or max_segments_per_call > 0
    round_id = os.environ.get("TRANSLATION_ROUND_ID", "")

    if run_budget and run_budget.last_progress_at <= 0:
        run_budget.last_progress_at = time.monotonic()

    for chapter in parsed_chapters:
        ch_result = ChapterRunResult(chapter_id=chapter.chapter_id, ok=True, message="ok")

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
            pending = [s for s in batch if _segment_needs_translation(s)]
            if not pending:
                continue
            if tick_limited and _tick_budget_exhausted(
                tick_start=tick_start,
                segments_this_tick=segments_this_tick,
                tick_max_segments=tick_max_segments,
                tick_max_wall_seconds=tick_max_wall_seconds,
            ):
                raise DraftRunTickExit(summary, run_root)
            if run_budget and run_budget.exhausted():
                controlled.draft_execution.save_segments(parsed_chapters)
                controlled.save()
                raise DraftRunTickExit(summary, run_root)

            check_stop_or_raise(worker_id=worker_id, run_id=run_id, repo_root=repo_root)
            if run_budget and run_budget.max_segments > 0:
                remaining_segments=max(0,run_budget.max_segments-run_budget.segments_used)
                pending=pending[:remaining_segments]
                if not pending:raise DraftRunTickExit(summary,run_root)
            if heartbeat_cb:
                heartbeat_cb()
            check_stop_or_raise(worker_id=worker_id, run_id=run_id, repo_root=repo_root)

            source_context=source_catalog.before(pending,source_context_policy)
            narrative_context=narrative_catalog.for_batch(pending) if narrative_catalog is not None else None
            messages = build_batch_messages(
                pending,
                chapter_label=chapter.chapter_label,
                asset_context=asset_context if not compact_context else None,
                compact_context=compact_context,
                source_context=source_context,
                narrative_context=narrative_context,
                source_catalog_sha256=source_catalog.sha256,
            )
            options = GenerateOptions(
                project_id="light-novel-jp-cn",
                language_direction="JP_TO_CN",
                pipeline_stage="draft_translation",
                input_reference=chapter.chapter_id,
                metadata={'source_context_sha256':source_context.to_dict()['sha256'],
                          'narrative_context_sha256':narrative_context.to_dict()['sha256'] if narrative_context else None},
            )
            result = None
            last_exc: Exception | None = None
            ok, msg = False, "no_attempt"
            for attempt in range(1, MAX_API_RETRIES + 1):
                remaining = run_budget.remaining_wall_seconds() if run_budget else None
                if run_budget and (
                    run_budget.exhausted()
                    or (
                        remaining is not None
                        and remaining <= WALL_TIME_START_SAFETY_SECONDS
                    )
                ):
                    controlled.draft_execution.save_segments(parsed_chapters)
                    controlled.save()
                    raise DraftRunTickExit(summary, run_root)
                _bound_provider_timeout(
                    provider,
                    run_budget,
                    outer_attempts_remaining=MAX_API_RETRIES - attempt + 1,
                )
                if heartbeat_cb:
                    heartbeat_cb()
                check_stop_or_raise(worker_id=worker_id, run_id=run_id, repo_root=repo_root)
                reserved=False
                try:
                    execution.reserve(messages,[s.segment_id for s in pending])
                    reserved=True
                    if not summary.simulated:
                        summary.api_calls=run_budget.api_calls_used
                    ch_result.api_calls+=1
                    try:
                        unit = execution.content_units[chapter.chapter_id]
                        with unit.operation(messages, role='generation', revision=0, run_id=run_id) as lease:
                            old_lease = execution.guard.content_unit_lease
                            execution.guard.content_unit_lease = lease
                            try:
                                result = provider.generate(messages, options)
                            finally:
                                execution.guard.content_unit_lease = old_lease
                    except BaseException as call_error:
                        execution.finish(call_error)
                        raise
                    finally:
                        summary.provider_attempts=max(summary.provider_attempts,execution.guard.call_count)
                    if result.dry_run and not summary.simulated:
                        raise RuntimeError("simulation result cannot complete real draft work")
                    execution.finish()
                    last_exc = None
                except Exception as exc:
                    last_exc = exc
                    result = None
                    if isinstance(exc,CostGuardError) or not reserved or attempt >= MAX_API_RETRIES or not execution.state["attempts"] or not execution.state["attempts"][-1]["retry_eligible"]:
                        break
                    time.sleep(min(30, 5 * attempt))
                    continue
                execution.verify_sources()
                ok, msg = _apply_items(chapter, pending, result.raw_output,
                                       warnings=ch_result.validation_warnings)
                if ok:
                    break
                execution.finish(RuntimeError(msg))
                result = None
                break

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

            # Persist the complete candidate before committing any done IDs.
            controlled.draft_execution.save_segments(parsed_chapters)

            segments_flush_interval = max(
                1, int(os.environ.get("SEGMENTS_FLUSH_INTERVAL", "10"))
            )
            segments_since_flush = 0
            for seg in pending:
                if seg.status == "machine_translated":
                    if not summary.simulated and not controlled.is_segment_done(seg.segment_id):
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
                        controlled.draft_execution.save_segments(parsed_chapters)
                        controlled.save()
                        raise DraftRunTickExit(summary, run_root)
                    if run_budget and run_budget.exhausted() and _count_translated_segments(parsed_chapters) < total_expected:
                        controlled.draft_execution.save_segments(parsed_chapters)
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
                        controlled.draft_execution.save_segments(parsed_chapters)
                        segments_since_flush = 0
            controlled.draft_execution.save_segments(parsed_chapters)
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

        controlled.draft_execution.save_chapter(chapter, draft_dir)
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
    # The caller already persists the bound segments before writing derived metadata.
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
        "real_api_called": False if not summary.provider_mode.startswith("real") or summary.provider_attempts==0 else None,
        "provider_method_attempts": summary.provider_attempts,
        "real_network_observation": "unknown" if summary.provider_mode.startswith("real") and summary.provider_attempts else "no_registered_provider_dispatch",
        "simulated": summary.simulated,
        "execution_mode": "mock" if summary.simulated else ("api_translation" if summary.provider_mode.startswith("real") else "unknown"),
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
    done = 0 if summary.simulated else _count_translated_segments(chapters)
    summary.translated_segments = done
    coverage = done / total if total else 0.0
    chapter_ok = all(c.ok for c in summary.chapters)
    passed = (
        not summary.aborted
        and not summary.simulated
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
        "quality_scope": "structural_draft_completeness_only; semantic_review_pending",
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
                "validation_warnings": c.validation_warnings,
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
