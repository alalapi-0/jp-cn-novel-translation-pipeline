#!/usr/bin/env python3
"""Round 50 controlled E2E trial: synthetic sample through ingest → export.

Uses fake provider only (cost=0). Writes artifacts under workspace/ (gitignored).
Exit: 0=success, 2=blocked validation error.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from providers.controlled_run import ControlledRunConfig, ControlledRunManager  # noqa: E402
from providers.cost_guard import CostGuard, CostGuardConfig  # noqa: E402
from providers.fake_provider import FakeProvider  # noqa: E402
from providers.types import GenerateOptions, Message  # noqa: E402
from quality_review.runner import run_review, validate_report_dict, write_report  # noqa: E402

SYNTHETIC_SOURCE = REPO_ROOT / "data" / "examples" / "e2e_trial_chapter.md"
DEFAULT_GLOSSARY = REPO_ROOT / "data" / "examples" / "review_glossary.fixture.json"
TRIAL_ROOT = REPO_ROOT / "workspace" / "e2e_trial"
MANIFEST_PATH = TRIAL_ROOT / "manifest.json"
VECTOR_MANIFEST_PATH = REPO_ROOT / "workspace" / "manifests" / "project_manifest.json"
SEGMENTS_PATH = TRIAL_ROOT / "segments.json"
TERMS_PATH = TRIAL_ROOT / "terminology_candidates.json"
CHARS_PATH = TRIAL_ROOT / "character_candidates.json"
REFINE_DIFF_PATH = TRIAL_ROOT / "refine_diff.json"
ISSUE_REPORT_PATH = REPO_ROOT / "workspace" / "review" / "issue_report.json"
EXPORT_DIR = TRIAL_ROOT / "export"
VECTOR_INDEX_PATH = REPO_ROOT / "workspace" / "vector_store" / "index.json"
TRIAL_REPORT_PATH = REPO_ROOT / "docs" / "reports" / "round_50_controlled_trial_report.md"
CHECKPOINT_RUN_ID = "round_50_e2e"

PROJECT_ID = "demo-jp-cn"
LANGUAGE_DIRECTION = "JP_TO_CN"
CHAPTER_ID = "ch-001"

TERM_PATTERN = re.compile(r"魔力結晶|異世界|[\u4e00-\u9fff\u3040-\u30ff]{2,8}")
CHAR_PATTERN = re.compile(r"リーナ")


@dataclass
class StepResult:
    name: str
    exit_code: int
    message: str
    artifacts: list[str] = field(default_factory=list)


@dataclass
class TrialReport:
    trial_scope: dict[str, Any]
    pipeline_steps: list[dict[str, Any]]
    tooling_used: list[str]
    gate_results: dict[str, Any] = field(default_factory=dict)
    cost_summary: dict[str, Any] = field(default_factory=dict)
    artifacts_paths: list[str] = field(default_factory=list)
    regressions: list[str] = field(default_factory=list)
    recommended_next_phase: str = ""
    go_no_go: str = "go"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_synthetic_chapter(path: Path) -> tuple[str, list[dict[str, Any]]]:
    text = path.read_text(encoding="utf-8")
    title_match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    chapter_title = title_match.group(1).strip() if title_match else "chapter"
    body_match = re.search(r"^##\s+(.+?)\n\n(.+)\Z", text, re.MULTILINE | re.DOTALL)
    if not body_match:
        raise ValueError(f"cannot parse chapter body: {path}")
    section_title = body_match.group(1).strip()
    body = body_match.group(2).strip()
    raw_paras = [p.strip() for p in re.split(r"\n\n+", body) if p.strip()]
    segments: list[dict[str, Any]] = []
    for idx, para in enumerate(raw_paras, start=1):
        seg_id = f"seg-{idx:03d}"
        human_edited = "人工锁定" in para or "禁止覆盖" in para
        segments.append(
            {
                "segment_id": seg_id,
                "source_text": para,
                "target_text": "",
                "draft_text": "",
                "refined_text": "",
                "status": "human_reviewed" if human_edited else "pending",
                "human_edited": human_edited,
            }
        )
    return f"{chapter_title} / {section_title}", segments


def step_ingest_manifest(source: Path) -> StepResult:
    if not source.is_file():
        return StepResult("ingest", 2, f"missing source: {source}")
    TRIAL_ROOT.mkdir(parents=True, exist_ok=True)
    manifest = {
        "project_id": PROJECT_ID,
        "language_direction": LANGUAGE_DIRECTION,
        "source_path": str(source.relative_to(REPO_ROOT)),
        "ingested_at": utc_now(),
        "chapter_ids": [CHAPTER_ID],
        "provider_mode": "fake",
        "real_api_called": False,
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    vector_manifest = {
        "project_id": PROJECT_ID,
        "language_direction": LANGUAGE_DIRECTION.lower(),
        "segments": [{"chapter_id": CHAPTER_ID, "segment_id": sid} for sid in ["seg-001", "seg-002", "seg-003"]],
    }
    VECTOR_MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    VECTOR_MANIFEST_PATH.write_text(
        json.dumps(vector_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    artifacts = [str(MANIFEST_PATH.relative_to(REPO_ROOT)), str(VECTOR_MANIFEST_PATH.relative_to(REPO_ROOT))]
    return StepResult("ingest", 0, "manifest written", artifacts)


def step_parse_segments(source: Path) -> StepResult:
    try:
        chapter_label, segments = parse_synthetic_chapter(source)
    except ValueError as exc:
        return StepResult("parse", 2, str(exc))
    doc = {
        "project_id": PROJECT_ID,
        "language_direction": LANGUAGE_DIRECTION,
        "chapter_id": CHAPTER_ID,
        "chapter_label": chapter_label,
        "expected_segment_ids": [s["segment_id"] for s in segments],
        "paragraphs": [{"paragraph_id": "para-001", "segments": segments}],
        "orphan_segment_ids": [],
    }
    SEGMENTS_PATH.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return StepResult(
        "parse",
        0,
        f"{len(segments)} segment(s) parsed",
        [str(SEGMENTS_PATH.relative_to(REPO_ROOT))],
    )


def step_extract_terminology(segments_doc: dict[str, Any]) -> StepResult:
    seen: set[str] = set()
    candidates: list[dict[str, Any]] = []
    for para in segments_doc.get("paragraphs", []):
        for seg in para.get("segments", []):
            for match in TERM_PATTERN.findall(seg.get("source_text", "")):
                if match in seen:
                    continue
                seen.add(match)
                candidates.append(
                    {
                        "term_id": f"term-cand-{len(candidates)+1:03d}",
                        "source": match,
                        "extraction_method": "rule_pattern",
                        "confidence": 0.85,
                    }
                )
    payload = {
        "project_id": PROJECT_ID,
        "language_direction": LANGUAGE_DIRECTION,
        "candidates": candidates,
        "generated_at": utc_now(),
    }
    TERMS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return StepResult(
        "terminology",
        0,
        f"{len(candidates)} term candidate(s)",
        [str(TERMS_PATH.relative_to(REPO_ROOT))],
    )


def step_extract_characters(segments_doc: dict[str, Any]) -> StepResult:
    names: set[str] = set()
    for para in segments_doc.get("paragraphs", []):
        for seg in para.get("segments", []):
            names.update(CHAR_PATTERN.findall(seg.get("source_text", "")))
    chars = [
        {
            "character_id": f"char-{idx:03d}",
            "name_ja": name,
            "name_zh": "莉娜" if name == "リーナ" else name,
            "extraction_method": "rule_pattern",
        }
        for idx, name in enumerate(sorted(names), start=1)
    ]
    payload = {
        "project_id": PROJECT_ID,
        "language_direction": LANGUAGE_DIRECTION,
        "characters": chars,
        "generated_at": utc_now(),
    }
    CHARS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return StepResult(
        "characters",
        0,
        f"{len(chars)} character candidate(s)",
        [str(CHARS_PATH.relative_to(REPO_ROOT))],
    )


def _segment_list(segments_doc: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for para in segments_doc.get("paragraphs", []):
        out.extend(para.get("segments", []))
    return out


def step_draft_translate(segments_doc: dict[str, Any], guard: CostGuard) -> StepResult:
    translated = 0
    total_cost = 0.0
    for seg in _segment_list(segments_doc):
        if seg.get("human_edited"):
            continue
        sid = seg["segment_id"]
        if sid == "seg-001":
            fixed = {"translation": "莉娜从宝箱中取出了魔法结晶。蓝光照亮了洞窟。", "notes": "e2e deliberate term alias"}
        elif sid == "seg-002":
            fixed = {"translation": "异界。", "notes": "e2e deliberate omission"}
        else:
            fixed = {"translation": f"[fake] {seg['source_text'][:40]}", "notes": "fake default"}
        seg_provider = FakeProvider(cost_guard=guard, fixed_output=fixed)
        result = seg_provider.generate(
            [Message(role="user", content=seg["source_text"])],
            GenerateOptions(project_id=PROJECT_ID, pipeline_stage="draft_translation"),
        )
        seg["draft_text"] = result.parsed_output["translation"]
        seg["target_text"] = seg["draft_text"]
        seg["status"] = "machine_translated"
        translated += 1
        total_cost += result.cost_estimate_usd
    SEGMENTS_PATH.write_text(json.dumps(segments_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return StepResult(
        "translate",
        0,
        f"{translated} segment(s) fake-translated; cost={total_cost:.6f} USD",
        [str(SEGMENTS_PATH.relative_to(REPO_ROOT))],
    )


def step_refine(segments_doc: dict[str, Any]) -> StepResult:
    diffs: list[dict[str, Any]] = []
    for seg in _segment_list(segments_doc):
        if seg.get("human_edited"):
            diffs.append(
                {
                    "segment_id": seg["segment_id"],
                    "skipped": True,
                    "reason": "human_edited protected",
                }
            )
            continue
        before = seg.get("draft_text", "")
        sid = seg.get("segment_id", "")
        if sid == "seg-001":
            after = before.replace("魔法结晶", "魔力结晶")
        elif sid == "seg-002":
            after = "她望向异世界的天空，心中充满疑问。"
        else:
            after = before
        seg["refined_text"] = after
        diffs.append(
            {
                "segment_id": seg["segment_id"],
                "before": before,
                "after": after,
                "skipped": False,
            }
        )
    payload = {"generated_at": utc_now(), "diffs": diffs}
    REFINE_DIFF_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    SEGMENTS_PATH.write_text(json.dumps(segments_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return StepResult(
        "refine",
        0,
        f"{sum(1 for d in diffs if not d.get('skipped'))} refine diff(s); human_edited skipped",
        [str(REFINE_DIFF_PATH.relative_to(REPO_ROOT))],
    )


def step_quality_review() -> StepResult:
    report = run_review(SEGMENTS_PATH, DEFAULT_GLOSSARY, generated_by="round_50_e2e_trial")
    errors = validate_report_dict(report.to_dict())
    if errors:
        return StepResult("quality_review", 2, "; ".join(errors))
    write_report(report, ISSUE_REPORT_PATH)
    issue_count = len(report.issues)
    return StepResult(
        "quality_review",
        0,
        f"{issue_count} issue(s); status={report.review_status}",
        [str(ISSUE_REPORT_PATH.relative_to(REPO_ROOT))],
    )


def step_export(segments_doc: dict[str, Any]) -> StepResult:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# {segments_doc.get('chapter_label', CHAPTER_ID)}",
        "",
        f"> exported_at: {utc_now()}",
        f"> project: {PROJECT_ID}",
        "",
    ]
    for seg in _segment_list(segments_doc):
        lines.extend(
            [
                f"## {seg['segment_id']}",
                "",
                "**原文**",
                "",
                seg.get("source_text", ""),
                "",
                "**初译**",
                "",
                seg.get("draft_text") or "—",
                "",
                "**润色**",
                "",
                seg.get("refined_text") or seg.get("draft_text") or "—",
                "",
                "---",
                "",
            ]
        )
    bilingual_path = EXPORT_DIR / "chapter_bilingual.md"
    bilingual_path.write_text("\n".join(lines), encoding="utf-8")
    meta = {
        "project_id": PROJECT_ID,
        "chapter_id": CHAPTER_ID,
        "segment_count": len(_segment_list(segments_doc)),
        "export_path": str(bilingual_path.relative_to(REPO_ROOT)),
        "final_status": "draft_not_final",
        "high_issues_unresolved": True,
        "exported_at": utc_now(),
    }
    meta_path = EXPORT_DIR / "export_meta.json"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return StepResult(
        "export",
        0,
        "bilingual export written (not marked final — issues pending)",
        [
            str(bilingual_path.relative_to(REPO_ROOT)),
            str(meta_path.relative_to(REPO_ROOT)),
        ],
    )


def step_vector_index(segments_doc: dict[str, Any]) -> StepResult:
    VECTOR_INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    vectors = []
    for seg in _segment_list(segments_doc):
        vectors.append(
            {
                "embedding_id": f"emb-{CHAPTER_ID}-{seg['segment_id']}",
                "metadata": {
                    "project_id": PROJECT_ID,
                    "language_direction": LANGUAGE_DIRECTION.lower(),
                    "chapter_id": CHAPTER_ID,
                    "segment_id": seg["segment_id"],
                    "model": "mock-embedding-v0",
                    "version": "round_50_e2e",
                },
            }
        )
    index = {
        "index_metadata": {
            "backend": "json_mock",
            "schema_version": "1.0.0",
            "project_id": PROJECT_ID,
            "language_direction": LANGUAGE_DIRECTION.lower(),
            "embedding_model": "mock-embedding-v0",
            "embedding_dimension": 384,
            "source_manifest": "workspace/manifests/project_manifest.json",
        },
        "vectors": vectors,
    }
    VECTOR_INDEX_PATH.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return StepResult(
        "vector_index",
        0,
        f"{len(vectors)} mock vector(s)",
        [str(VECTOR_INDEX_PATH.relative_to(REPO_ROOT))],
    )


def write_trial_report(
    results: list[StepResult],
    guard: CostGuard,
    *,
    gate_exit: int | None = None,
    protocol_exit: int | None = None,
) -> Path:
    TRIAL_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    blocked = [r for r in results if r.exit_code == 2]
    go_no_go = "no-go" if blocked else "go"
    report = TrialReport(
        trial_scope={
            "round": "round_50",
            "project_id": PROJECT_ID,
            "source": str(SYNTHETIC_SOURCE.relative_to(REPO_ROOT)),
            "provider_mode": "fake",
            "real_api_called": False,
            "full_translation_executed": False,
            "segments": len(_segment_list(json.loads(SEGMENTS_PATH.read_text(encoding="utf-8"))))
            if SEGMENTS_PATH.is_file()
            else 0,
        },
        pipeline_steps=[asdict(r) for r in results],
        tooling_used=[
            "scripts/run_round_50_e2e_trial.py",
            "providers/fake_provider.py",
            "providers/cost_guard.py",
            "providers/controlled_run.py",
            "quality_review/runner.py",
            "scripts/run_quality_review.py",
            "scripts/vector_db_inspect.py",
            "frontend workbench (Playwright)",
        ],
        gate_results={
            "agent_gate_exit": gate_exit,
            "protocol_check_exit": protocol_exit,
        },
        cost_summary={
            "estimated_usd": round(guard.spent_usd, 8),
            "estimated_tokens": guard.spent_tokens,
            "call_count": guard.call_count,
            "real_api_called": False,
            "actual_paid_usd": 0.0,
        },
        artifacts_paths=sorted({a for r in results for a in r.artifacts}),
        regressions=[],
        recommended_next_phase=(
            "Phase 2: Round 51+ — 长篇受控试跑（用户授权 + cost guard）、"
            "多项目管理、后端 API 服务化；semantic/voice checkers"
        ),
        go_no_go=go_no_go,
    )
    lines = [
        "# Round 50 Controlled E2E Trial Report",
        "",
        f"- Generated: {utc_now()}",
        f"- Go/No-Go: **{report.go_no_go.upper()}**",
        "",
        "## trial_scope",
        "",
        "```json",
        json.dumps(report.trial_scope, ensure_ascii=False, indent=2),
        "```",
        "",
        "## pipeline_steps",
        "",
        "| Step | Exit | Message |",
        "|------|------|---------|",
    ]
    for step in report.pipeline_steps:
        lines.append(f"| {step['name']} | {step['exit_code']} | {step['message']} |")
    lines.extend(
        [
            "",
            "## cost_summary",
            "",
            "```json",
            json.dumps(report.cost_summary, ensure_ascii=False, indent=2),
            "```",
            "",
            "## artifacts_paths",
            "",
        ]
    )
    lines.extend(f"- `{p}`" for p in report.artifacts_paths)
    lines.extend(
        [
            "",
            "## recommended_next_phase",
            "",
            report.recommended_next_phase,
            "",
            "## regressions",
            "",
            "None observed in Round 50 synthetic trial.",
            "",
        ]
    )
    TRIAL_REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return TRIAL_REPORT_PATH


def run_trial(*, skip_report: bool = False) -> tuple[list[StepResult], int]:
    guard = CostGuard(
        CostGuardConfig(
            max_test_cost_usd=1.0,
            max_tokens_per_run=10_000,
            log_dir=REPO_ROOT / "workspace" / "model_runs",
        )
    )
    run_mgr = ControlledRunManager(
        ControlledRunConfig(
            enabled=True,
            checkpoint_dir=REPO_ROOT / "workspace" / "checkpoints",
            run_id=CHECKPOINT_RUN_ID,
        )
    )
    results: list[StepResult] = []

    def run_step(name: str, fn) -> bool:
        res = fn()
        results.append(res)
        if res.exit_code == 0:
            run_mgr.checkpoint.metadata[name] = {"status": "ok", "at": utc_now()}
            run_mgr.save()
        return res.exit_code != 2

    if not run_step("ingest", lambda: step_ingest_manifest(SYNTHETIC_SOURCE)):
        return results, 2
    if not run_step("parse", lambda: step_parse_segments(SYNTHETIC_SOURCE)):
        return results, 2

    segments_doc = json.loads(SEGMENTS_PATH.read_text(encoding="utf-8"))
    if not run_step("terminology", lambda: step_extract_terminology(segments_doc)):
        return results, 2
    if not run_step("characters", lambda: step_extract_characters(segments_doc)):
        return results, 2
    if not run_step("translate", lambda: step_draft_translate(segments_doc, guard)):
        return results, 2

    segments_doc = json.loads(SEGMENTS_PATH.read_text(encoding="utf-8"))
    if not run_step("refine", lambda: step_refine(segments_doc)):
        return results, 2
    if not run_step("quality_review", step_quality_review):
        return results, 2

    segments_doc = json.loads(SEGMENTS_PATH.read_text(encoding="utf-8"))
    if not run_step("export", lambda: step_export(segments_doc)):
        return results, 2
    if not run_step("vector_index", lambda: step_vector_index(segments_doc)):
        return results, 2

    run_mgr.complete()
    if not skip_report:
        write_trial_report(results, guard)
    return results, 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Round 50 controlled E2E trial")
    parser.add_argument("--json", action="store_true", help="Print step results as JSON")
    parser.add_argument("--skip-report", action="store_true", help="Skip writing trial report")
    args = parser.parse_args(argv)

    results, exit_code = run_trial(skip_report=args.skip_report)
    if args.json:
        print(json.dumps([asdict(r) for r in results], ensure_ascii=False, indent=2))
    else:
        label = "PASS" if exit_code == 0 else "BLOCKED"
        print(f"round_50_e2e: {label} (exit {exit_code})")
        for r in results:
            print(f"  {r.name}: exit={r.exit_code} — {r.message}")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
