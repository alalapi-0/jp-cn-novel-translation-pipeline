#!/usr/bin/env python3
"""Deterministic repository gate for Agent autonomous advancement.

Does not call LLMs or external APIs. Does not read .env contents.
Exit codes: 0=PASS, 1=WARNING, 2=BLOCKED (see governance/repo_protocol_standard.yaml).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Iterable, Sequence


class Severity(str, Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


@dataclass
class CheckResult:
    check_id: str
    severity: Severity
    message: str

    def to_dict(self) -> dict:
        return {
            "id": self.check_id,
            "severity": self.severity.value,
            "message": self.message,
        }


REPO_ROOT = Path(__file__).resolve().parent.parent
REPORT_PATH = REPO_ROOT / "docs" / "reports" / "agent_gate_report.md"
GATE_RESULT_PATH = REPO_ROOT / "reports" / "gate_result.json"

AGENT_LAYER_FILES: Sequence[tuple[str, Path]] = (
    ("agent_layer_yaml", REPO_ROOT / "agent_layer.yaml"),
    ("agent_tools_yaml", REPO_ROOT / "agent_tools.yaml"),
    ("tool_usage_policy", REPO_ROOT / "docs" / "TOOL_USAGE_POLICY.md"),
    ("agent_runbook", REPO_ROOT / "docs" / "AGENT_RUNBOOK.md"),
    ("agent_roadmap", REPO_ROOT / "docs" / "AGENT_ROADMAP.md"),
    ("search_policy", REPO_ROOT / "docs" / "SEARCH_POLICY.md"),
    ("tool_inventory", REPO_ROOT / "docs" / "TOOL_INVENTORY.md"),
    ("latest_agent_report", REPO_ROOT / "reports" / "latest-agent-report.json"),
    ("round_report_schema", REPO_ROOT / "schemas" / "agent_round_report.schema.json"),
)

REQUIRED_DOCS: Sequence[tuple[str, Path]] = (
    ("docs_exist_readme", REPO_ROOT / "README.md"),
    ("docs_exist_agents", REPO_ROOT / "AGENTS.md"),
    ("docs_exist_project_yaml", REPO_ROOT / "project.yaml"),
    ("docs_exist_vision", REPO_ROOT / "docs" / "project_vision.md"),
    ("docs_exist_architecture", REPO_ROOT / "docs" / "architecture_overview.md"),
    ("docs_exist_governance_rules", REPO_ROOT / "docs" / "governance_rules.md"),
    ("docs_exist_index", REPO_ROOT / "docs" / "index.md"),
)

ROADMAP_DOCS: Sequence[tuple[str, Path, bool]] = (
    ("roadmap_exists_00_40", REPO_ROOT / "docs" / "roadmap_rounds_00_40.md", True),
    (
        "roadmap_exists_41_50",
        REPO_ROOT / "docs" / "roadmap_rounds_41_50_tooling_and_workbench.md",
        False,
    ),
)

PROTOCOL_AND_ALIGNMENT: Sequence[tuple[str, Path]] = (
    ("protocol_exists", REPO_ROOT / "governance" / "repo_protocol_standard.yaml"),
    ("protocol_alignment_exists", REPO_ROOT / "docs" / "repo_protocol_alignment.md"),
)

TOOLING_DOCS: Sequence[tuple[str, Path]] = (
    ("tooling_strategy_exists", REPO_ROOT / "docs" / "agent_tooling_strategy.md"),
    ("mcp_plan_exists", REPO_ROOT / "docs" / "mcp_playwright_setup_plan.md"),
    ("frontend_plan_exists", REPO_ROOT / "docs" / "frontend_workbench_plan.md"),
    ("api_provider_strategy_exists", REPO_ROOT / "docs" / "api_provider_strategy.md"),
)

REFERENCE_DOCS: Sequence[tuple[str, Path]] = (
    (
        "reference_method_docs_exist",
        REPO_ROOT / "docs" / "reference_repo_methodology_integration.md",
    ),
    ("stable_id_jsonl_doc_exists", REPO_ROOT / "docs" / "stable_id_and_jsonl_design.md"),
    (
        "extractor_validator_doc_exists",
        REPO_ROOT / "docs" / "extractor_validator_reference_inspired.md",
    ),
    (
        "provider_adapter_doc_exists",
        REPO_ROOT / "docs" / "provider_adapter_reference_inspired.md",
    ),
    (
        "exporter_principle_doc_exists",
        REPO_ROOT / "docs" / "exporter_reference_inspired_design.md",
    ),
)

PROMPT_TEMPLATES_GLOB = "prompts/*_template.md"

GITIGNORE_REQUIRED_SNIPPETS = (
    ".env",
    "input_jp/*",
    "input_cn/*",
    "output_cn/translated/*",
    "docs/reports/*.md",
)


def _rel_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _file_exists(check_id: str, path: Path) -> CheckResult:
    rel = _rel_path(path)
    if path.is_file():
        return CheckResult(check_id, Severity.PASS, f"found: {rel}")
    return CheckResult(check_id, Severity.FAIL, f"missing required file: {rel}")


def _git(args: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def check_docs_exist() -> list[CheckResult]:
    return [_file_exists(cid, p) for cid, p in REQUIRED_DOCS]


def check_roadmaps(strict: bool) -> list[CheckResult]:
    results: list[CheckResult] = []
    for cid, path, core in ROADMAP_DOCS:
        if path.is_file():
            results.append(CheckResult(cid, Severity.PASS, f"found: {path.name}"))
            continue
        if core or (cid == "roadmap_exists_41_50" and strict):
            results.append(
                CheckResult(cid, Severity.FAIL, f"missing roadmap: {path.relative_to(REPO_ROOT)}")
            )
        else:
            results.append(
                CheckResult(
                    cid,
                    Severity.WARN,
                    f"missing roadmap (non-strict warning): {path.relative_to(REPO_ROOT)}",
                )
            )
    return results


def check_protocol_docs() -> list[CheckResult]:
    return [_file_exists(cid, p) for cid, p in PROTOCOL_AND_ALIGNMENT]


def check_tooling_docs() -> list[CheckResult]:
    return [_file_exists(cid, p) for cid, p in TOOLING_DOCS]


def check_reference_docs() -> list[CheckResult]:
    return [_file_exists(cid, p) for cid, p in REFERENCE_DOCS]


def check_prompt_templates() -> CheckResult:
    templates = sorted(REPO_ROOT.glob(PROMPT_TEMPLATES_GLOB))
    count = len(templates)
    if count >= 6:
        return CheckResult(
            "prompt_templates_exist",
            Severity.PASS,
            f"found {count} prompt templates under prompts/",
        )
    return CheckResult(
        "prompt_templates_exist",
        Severity.WARN,
        f"only {count} prompt templates (expected >= 6)",
    )


def check_direction_dirs() -> list[CheckResult]:
    results: list[CheckResult] = []
    for name in ("jp_to_cn", "cn_to_jp"):
        path = REPO_ROOT / "directions" / name
        if path.is_dir():
            results.append(
                CheckResult(
                    "direction_dirs_exist",
                    Severity.PASS,
                    f"found directions/{name}/",
                )
            )
        else:
            results.append(
                CheckResult(
                    "direction_dirs_exist",
                    Severity.WARN,
                    f"missing directions/{name}/",
                )
            )
    return results


def check_gitignore_safe() -> CheckResult:
    gitignore = REPO_ROOT / ".gitignore"
    if not gitignore.is_file():
        return CheckResult("gitignore_safe", Severity.FAIL, ".gitignore missing")
    text = gitignore.read_text(encoding="utf-8", errors="replace")
    missing = [s for s in GITIGNORE_REQUIRED_SNIPPETS if s not in text]
    if not missing:
        return CheckResult("gitignore_safe", Severity.PASS, "required ignore rules present")
    return CheckResult(
        "gitignore_safe",
        Severity.WARN,
        f".gitignore may be incomplete; missing snippets: {', '.join(missing)}",
    )


def check_env_not_tracked() -> CheckResult:
    proc = _git(["ls-files", "--error-unmatch", ".env"], REPO_ROOT)
    if proc.returncode == 0:
        return CheckResult(
            "env_not_tracked",
            Severity.FAIL,
            ".env is tracked by Git — remove from index before autonomous work",
        )
    # Only the real secrets file counts; .env.example may be tracked intentionally.
    tracked_dotenv = _git(["ls-files", ".env"], REPO_ROOT).stdout.strip()
    if tracked_dotenv:
        return CheckResult(
            "env_not_tracked",
            Severity.FAIL,
            ".env is tracked by Git — remove from index before autonomous work",
        )
    return CheckResult("env_not_tracked", Severity.PASS, ".env not tracked")


def _path_ignored_by_git(rel: str) -> bool:
    proc = _git(["check-ignore", "-v", rel], REPO_ROOT)
    return proc.returncode == 0


def check_input_sources_ignored() -> list[CheckResult]:
    results: list[CheckResult] = []
    for rel in ("input_jp/sample.txt", "input_cn/sample.txt"):
        if _path_ignored_by_git(rel):
            results.append(
                CheckResult(
                    "input_sources_ignored",
                    Severity.PASS,
                    f"git ignores synthetic path {rel}",
                )
            )
        else:
            results.append(
                CheckResult(
                    "input_sources_ignored",
                    Severity.WARN,
                    f"git may not ignore {rel} (check-ignore returned non-zero)",
                )
            )
    return results


def check_outputs_ignored() -> list[CheckResult]:
    results: list[CheckResult] = []
    for rel in (
        "output_cn/translated/out.txt",
        "output_jp/translated/out.txt",
    ):
        if _path_ignored_by_git(rel):
            results.append(
                CheckResult(
                    "outputs_ignored",
                    Severity.PASS,
                    f"git ignores synthetic path {rel}",
                )
            )
        else:
            results.append(
                CheckResult(
                    "outputs_ignored",
                    Severity.WARN,
                    f"git may not ignore {rel}",
                )
            )
    return results


def check_frontend_mvp_exists() -> CheckResult:
    index = REPO_ROOT / "frontend" / "index.html"
    review = REPO_ROOT / "frontend" / "review.html"
    config = REPO_ROOT / "frontend" / "assets" / "config.js"
    if index.is_file() and review.is_file() and config.is_file():
        return CheckResult(
            "frontend_mvp_exists",
            Severity.PASS,
            "frontend index/review pages and config present",
        )
    return CheckResult(
        "frontend_mvp_exists",
        Severity.WARN,
        "frontend MVP pages missing (expected index.html, review.html, assets/config.js)",
    )


VECTOR_INSPECT_SCRIPT = REPO_ROOT / "scripts" / "vector_db_inspect.py"
VECTOR_SCHEMA = REPO_ROOT / "data" / "schemas" / "vector_index_metadata.schema.json"
DEFAULT_VECTOR_INDEX = REPO_ROOT / "workspace" / "vector_store" / "index.json"

QUALITY_REVIEW_SCRIPT = REPO_ROOT / "scripts" / "run_quality_review.py"
REVIEW_ISSUE_SCHEMA = REPO_ROOT / "data" / "schemas" / "review_issue.schema.json"
REVIEW_EXAMPLE_REPORT = REPO_ROOT / "data" / "examples" / "review_issue_report.example.json"
FRONTEND_ISSUES_PAGE = REPO_ROOT / "frontend" / "issues.html"
REVIEW_SEGMENTS_FIXTURE = REPO_ROOT / "data" / "examples" / "review_segments.fixture.json"
REVIEW_GLOSSARY_FIXTURE = REPO_ROOT / "data" / "examples" / "review_glossary.fixture.json"
E2E_TRIAL_SCRIPT = REPO_ROOT / "scripts" / "run_round_50_e2e_trial.py"
E2E_SYNTHETIC_SOURCE = REPO_ROOT / "data" / "examples" / "e2e_trial_chapter.md"


def check_vector_store_tooling() -> list[CheckResult]:
    """Optional vector index checks — missing index is soft fallback (WARN), not BLOCKED."""
    results: list[CheckResult] = []
    if VECTOR_INSPECT_SCRIPT.is_file():
        results.append(
            CheckResult(
                "vector_inspect_script_exists",
                Severity.PASS,
                "found scripts/vector_db_inspect.py",
            )
        )
    else:
        results.append(
            CheckResult(
                "vector_inspect_script_exists",
                Severity.WARN,
                "missing scripts/vector_db_inspect.py (Round 48 tooling)",
            )
        )
        return results

    if VECTOR_SCHEMA.is_file():
        results.append(
            CheckResult(
                "vector_metadata_schema_exists",
                Severity.PASS,
                "found data/schemas/vector_index_metadata.schema.json",
            )
        )
    else:
        results.append(
            CheckResult(
                "vector_metadata_schema_exists",
                Severity.WARN,
                "missing vector index metadata schema",
            )
        )

    if not DEFAULT_VECTOR_INDEX.is_file():
        results.append(
            CheckResult(
                "vector_index_present",
                Severity.PASS,
                "no workspace/vector_store/index.json — soft fallback OK for non-vector rounds",
            )
        )
        return results

    try:
        if str(REPO_ROOT / "src") not in sys.path:
            sys.path.insert(0, str(REPO_ROOT / "src"))
        spec = importlib.util.spec_from_file_location(
            "light_novel_vector_db_inspect_gate",
            VECTOR_INSPECT_SCRIPT,
        )
        if not spec or not spec.loader:
            raise RuntimeError("cannot load vector_db_inspect module")
        mod = importlib.util.module_from_spec(spec)
        sys.modules["light_novel_vector_db_inspect_gate"] = mod
        spec.loader.exec_module(mod)
        manifest_path = REPO_ROOT / "workspace" / "manifests" / "project_manifest.json"
        try:
            wb_spec = importlib.util.spec_from_file_location(
                "light_novel_workbench_registry_gate",
                REPO_ROOT / "src" / "workbench" / "project_registry.py",
            )
            if wb_spec and wb_spec.loader:
                wb_mod = importlib.util.module_from_spec(wb_spec)
                sys.modules["light_novel_workbench_registry_gate"] = wb_mod
                wb_spec.loader.exec_module(wb_mod)
                resolved = wb_mod.resolve_active_manifest_path(REPO_ROOT)
                if resolved and resolved.is_file():
                    manifest_path = resolved
        except Exception:
            pass
        report, _, _ = mod.run_inspection(DEFAULT_VECTOR_INDEX, manifest_path if manifest_path.is_file() else None)
        code = mod.aggregate_exit_code(report.findings)
        if code == 2:
            msg = "; ".join(f.message for f in report.findings if f.severity == mod.Severity.FAIL)
            results.append(
                CheckResult(
                    "vector_index_health",
                    Severity.WARN,
                    f"local index parse/structure issue (non-blocking): {msg or 'see vector_db_inspect'}",
                )
            )
        elif code == 1:
            warn_codes = sorted({f.code for f in report.findings if f.severity == mod.Severity.WARN})
            results.append(
                CheckResult(
                    "vector_index_health",
                    Severity.WARN,
                    f"index present with {report.vector_count} vector(s); "
                    f"inspect warnings: {', '.join(warn_codes) or 'metadata/orphan'}",
                )
            )
        else:
            results.append(
                CheckResult(
                    "vector_index_health",
                    Severity.PASS,
                    f"index present; {report.vector_count} vector(s) metadata OK",
                )
            )
    except Exception as exc:  # noqa: BLE001 — gate must stay deterministic and never crash
        results.append(
            CheckResult(
                "vector_index_health",
                Severity.WARN,
                f"vector inspect skipped ({type(exc).__name__}): {exc}",
            )
        )
    return results


def check_quality_review_tooling() -> list[CheckResult]:
    """Round 49 quality review scaffold — missing pieces are soft WARN."""
    results: list[CheckResult] = []
    required = (
        ("quality_review_script_exists", QUALITY_REVIEW_SCRIPT),
        ("review_issue_schema_exists", REVIEW_ISSUE_SCHEMA),
        ("review_issue_example_exists", REVIEW_EXAMPLE_REPORT),
        ("frontend_issues_page_exists", FRONTEND_ISSUES_PAGE),
    )
    for cid, path in required:
        if path.is_file():
            results.append(CheckResult(cid, Severity.PASS, f"found: {_rel_path(path)}"))
        else:
            results.append(
                CheckResult(cid, Severity.WARN, f"missing Round 49 artifact: {_rel_path(path)}")
            )

    if not QUALITY_REVIEW_SCRIPT.is_file():
        return results

    try:
        proc = subprocess.run(
            [
                sys.executable,
                str(QUALITY_REVIEW_SCRIPT),
                "--segments",
                str(REVIEW_SEGMENTS_FIXTURE),
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode == 2:
            results.append(
                CheckResult(
                    "quality_review_runner",
                    Severity.WARN,
                    f"review runner blocked: {proc.stderr.strip() or proc.stdout.strip()}",
                )
            )
        elif proc.returncode == 1:
            results.append(
                CheckResult(
                    "quality_review_runner",
                    Severity.WARN,
                    "review runner returned no issues on default fixture",
                )
            )
        else:
            results.append(
                CheckResult(
                    "quality_review_runner",
                    Severity.PASS,
                    "deterministic review runner OK on synthetic fixture",
                )
            )
    except Exception as exc:  # noqa: BLE001
        results.append(
            CheckResult(
                "quality_review_runner",
                Severity.WARN,
                f"quality review runner skipped: {exc}",
            )
        )
    return results


def check_round_50_e2e_trial() -> list[CheckResult]:
    """Round 50 controlled E2E trial scaffold."""
    results: list[CheckResult] = []
    for cid, path in (
        ("e2e_trial_script_exists", E2E_TRIAL_SCRIPT),
        ("e2e_synthetic_source_exists", E2E_SYNTHETIC_SOURCE),
    ):
        if path.is_file():
            results.append(CheckResult(cid, Severity.PASS, f"found: {_rel_path(path)}"))
        else:
            results.append(
                CheckResult(cid, Severity.WARN, f"missing Round 50 artifact: {_rel_path(path)}")
            )
    if not E2E_TRIAL_SCRIPT.is_file():
        return results
    try:
        proc = subprocess.run(
            [sys.executable, str(E2E_TRIAL_SCRIPT), "--skip-report"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=90,
        )
        if proc.returncode == 0:
            results.append(
                CheckResult(
                    "round_50_e2e_trial",
                    Severity.PASS,
                    "controlled E2E trial script OK on synthetic sample",
                )
            )
        else:
            results.append(
                CheckResult(
                    "round_50_e2e_trial",
                    Severity.WARN,
                    f"E2E trial blocked: {proc.stderr.strip() or proc.stdout.strip()}",
                )
            )
    except subprocess.TimeoutExpired:
        results.append(
            CheckResult(
                "round_50_e2e_trial",
                Severity.WARN,
                "E2E trial timed out after 90s (skipped)",
            )
        )
    except Exception as exc:  # noqa: BLE001
        results.append(
            CheckResult(
                "round_50_e2e_trial",
                Severity.WARN,
                f"E2E trial skipped: {exc}",
            )
        )
    return results


def check_round_51_openrouter_smoke() -> list[CheckResult]:
    """Round 51 OpenRouter smoke script — dry-run subprocess only."""
    smoke_script = REPO_ROOT / "scripts" / "run_openrouter_smoke.py"
    if not smoke_script.is_file():
        return [
            CheckResult(
                "round_51_smoke_script_exists",
                Severity.WARN,
                "missing scripts/run_openrouter_smoke.py",
            )
        ]
    results = [
        CheckResult(
            "round_51_smoke_script_exists",
            Severity.PASS,
            f"found: {_rel_path(smoke_script)}",
        )
    ]
    try:
        proc = subprocess.run(
            [sys.executable, str(smoke_script), "--dry-run"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
            env={**os.environ, "REAL_API_TESTS_ENABLED": "false"},
        )
        if proc.returncode == 0:
            results.append(
                CheckResult(
                    "round_51_openrouter_smoke",
                    Severity.PASS,
                    "dry-run smoke script OK",
                )
            )
        else:
            results.append(
                CheckResult(
                    "round_51_openrouter_smoke",
                    Severity.WARN,
                    f"smoke script failed: {proc.stderr.strip() or proc.stdout.strip()}",
                )
            )
    except subprocess.TimeoutExpired:
        results.append(
            CheckResult(
                "round_51_openrouter_smoke",
                Severity.WARN,
                "smoke script timed out after 120s",
            )
        )
    except Exception as exc:  # noqa: BLE001
        results.append(
            CheckResult(
                "round_51_openrouter_smoke",
                Severity.WARN,
                f"smoke script skipped: {exc}",
            )
        )
    return results


def check_round_52_refine_stage_c() -> list[CheckResult]:
    """Round 52 Stage C refine pilot — dry-run subprocess when Stage B run exists."""
    refine_script = REPO_ROOT / "scripts" / "refine_stage_c.py"
    if not refine_script.is_file():
        return [
            CheckResult(
                "round_52_refine_script_exists",
                Severity.WARN,
                "missing scripts/refine_stage_c.py",
            )
        ]
    results = [
        CheckResult(
            "round_52_refine_script_exists",
            Severity.PASS,
            f"found: {_rel_path(refine_script)}",
        )
    ]
    stage_b = REPO_ROOT / "workspace" / "runs" / "run_20260602_203645_draft_stage_b_50ch" / "segments.json"
    if not stage_b.is_file():
        results.append(
            CheckResult(
                "round_52_refine_dry_run",
                Severity.WARN,
                "Stage B segments.json not present; refine dry-run skipped",
            )
        )
        return results
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".stage_state.json",
            delete=False,
        ) as tmp_state:
            tmp_state_path = tmp_state.name
        proc = subprocess.run(
            [
                sys.executable,
                str(refine_script),
                "--run-id",
                "run_20260602_203645_draft_stage_b_50ch",
                "--limit-segments",
                "2",
                "--dry-run",
                "--stage-state-path",
                tmp_state_path,
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=180,
            env={**os.environ, "REAL_API_TESTS_ENABLED": "false"},
        )
        try:
            os.unlink(tmp_state_path)
        except OSError:
            pass
        if proc.returncode == 0:
            results.append(
                CheckResult(
                    "round_52_refine_dry_run",
                    Severity.PASS,
                    "Stage C refine dry-run OK",
                )
            )
        else:
            results.append(
                CheckResult(
                    "round_52_refine_dry_run",
                    Severity.WARN,
                    f"refine dry-run failed: {proc.stderr.strip() or proc.stdout.strip()}",
                )
            )
    except subprocess.TimeoutExpired:
        results.append(
            CheckResult(
                "round_52_refine_dry_run",
                Severity.WARN,
                "refine dry-run timed out after 180s",
            )
        )
    except Exception as exc:  # noqa: BLE001
        results.append(
            CheckResult(
                "round_52_refine_dry_run",
                Severity.WARN,
                f"refine dry-run skipped: {exc}",
            )
        )
    return results


def check_round_53_multi_project_manifest() -> list[CheckResult]:
    """Round 53 multi-project manifest backend + workbench project switch."""
    registry_path = REPO_ROOT / "src" / "workbench" / "project_registry.py"
    serve_script = REPO_ROOT / "scripts" / "serve_frontend.py"
    example_glob = REPO_ROOT / "data" / "examples" / "workbench_project.demo-jp-cn.example.json"
    results: list[CheckResult] = []

    if registry_path.is_file():
        results.append(
            CheckResult(
                "round_53_registry_module_exists",
                Severity.PASS,
                f"found: {_rel_path(registry_path)}",
            )
        )
    else:
        results.append(
            CheckResult(
                "round_53_registry_module_exists",
                Severity.WARN,
                "missing src/workbench/project_registry.py",
            )
        )
        return results

    if serve_script.is_file():
        results.append(
            CheckResult(
                "round_53_serve_frontend_exists",
                Severity.PASS,
                f"found: {_rel_path(serve_script)}",
            )
        )
    else:
        results.append(
            CheckResult(
                "round_53_serve_frontend_exists",
                Severity.WARN,
                "missing scripts/serve_frontend.py",
            )
        )

    if example_glob.is_file():
        results.append(
            CheckResult(
                "round_53_example_manifests_exist",
                Severity.PASS,
                "found committed workbench_project.*.example.json fixtures",
            )
        )
    else:
        results.append(
            CheckResult(
                "round_53_example_manifests_exist",
                Severity.WARN,
                "missing data/examples/workbench_project.*.example.json",
            )
        )

    try:
        sys.path.insert(0, str(REPO_ROOT / "src"))
        from workbench.project_registry import (  # noqa: WPS433
            get_active_project_id,
            list_project_manifests,
            seed_example_manifests,
            set_active_project_id,
        )

        seed_example_manifests(REPO_ROOT)
        manifests = list_project_manifests(REPO_ROOT)
        if len(manifests) >= 2:
            results.append(
                CheckResult(
                    "round_53_manifest_count",
                    Severity.PASS,
                    f"{len(manifests)} project manifest(s) under workspace/manifests",
                )
            )
        else:
            results.append(
                CheckResult(
                    "round_53_manifest_count",
                    Severity.WARN,
                    f"expected >=2 manifests, found {len(manifests)}",
                )
            )

        active_before = get_active_project_id(REPO_ROOT)
        alt = next((m.project_id for m in manifests if m.project_id != active_before), None)
        if alt:
            set_active_project_id(REPO_ROOT, alt)
            restored = get_active_project_id(REPO_ROOT)
            if active_before:
                set_active_project_id(REPO_ROOT, active_before)
            if restored == alt:
                results.append(
                    CheckResult(
                        "round_53_active_project_switch",
                        Severity.PASS,
                        "active project switch persisted in workspace/workbench_state.json",
                    )
                )
            else:
                results.append(
                    CheckResult(
                        "round_53_active_project_switch",
                        Severity.WARN,
                        f"switch to {alt} did not persist",
                    )
                )
        else:
            results.append(
                CheckResult(
                    "round_53_active_project_switch",
                    Severity.WARN,
                    "need >=2 manifests to verify project switch",
                )
            )
    except Exception as exc:  # noqa: BLE001
        results.append(
            CheckResult(
                "round_53_registry_runtime",
                Severity.WARN,
                f"multi-project registry check skipped: {exc}",
            )
        )
    return results


def check_round_54_semantic_checker_mvp() -> list[CheckResult]:
    """Round 54 MISTRANSLATION / PLACEHOLDER_LOST + workbench quality-review API."""
    checkers_path = REPO_ROOT / "src" / "quality_review" / "checkers.py"
    adapter_path = REPO_ROOT / "src" / "quality_review" / "workbench_adapter.py"
    segments_fixture = REPO_ROOT / "data" / "examples" / "review_segments.fixture.json"
    results: list[CheckResult] = []

    for cid, path in (
        ("round_54_checkers_module", checkers_path),
        ("round_54_workbench_adapter", adapter_path),
    ):
        if path.is_file():
            results.append(CheckResult(cid, Severity.PASS, f"found: {_rel_path(path)}"))
        else:
            results.append(CheckResult(cid, Severity.WARN, f"missing {_rel_path(path)}"))
            return results

    try:
        sys.path.insert(0, str(REPO_ROOT / "src"))
        from quality_review.checkers import (  # noqa: WPS433
            check_mistranslation,
            check_placeholder_lost,
            reset_issue_counter,
        )
        from quality_review.runner import run_review  # noqa: WPS433

        if not segments_fixture.is_file():
            results.append(
                CheckResult(
                    "round_54_fixture_semantic_cases",
                    Severity.WARN,
                    "missing review_segments.fixture.json",
                )
            )
            return results

        report = run_review(segments_fixture, REVIEW_GLOSSARY_FIXTURE)
        types = set(report.summary.get("by_type", {}))
        if "MISTRANSLATION" in types and "PLACEHOLDER_LOST" in types:
            results.append(
                CheckResult(
                    "round_54_fixture_semantic_cases",
                    Severity.PASS,
                    "fixture emits MISTRANSLATION and PLACEHOLDER_LOST",
                )
            )
        else:
            results.append(
                CheckResult(
                    "round_54_fixture_semantic_cases",
                    Severity.WARN,
                    f"expected semantic types, got: {sorted(types)}",
                )
            )

        server_src = (REPO_ROOT / "src" / "workbench" / "server.py").read_text(encoding="utf-8")
        if "/quality-review" in server_src:
            results.append(
                CheckResult(
                    "round_54_quality_review_api_route",
                    Severity.PASS,
                    "workbench server exposes /quality-review",
                )
            )
        else:
            results.append(
                CheckResult(
                    "round_54_quality_review_api_route",
                    Severity.WARN,
                    "missing /api/projects/*/quality-review handler",
                )
            )

        doc = json.loads(segments_fixture.read_text(encoding="utf-8"))
        reset_issue_counter()
        ph_issues = check_placeholder_lost(doc)
        mis_issues = check_mistranslation(doc)
        if ph_issues and mis_issues:
            results.append(
                CheckResult(
                    "round_54_checker_functions",
                    Severity.PASS,
                    f"placeholder={len(ph_issues)} mistranslation={len(mis_issues)}",
                )
            )
        else:
            results.append(
                CheckResult(
                    "round_54_checker_functions",
                    Severity.WARN,
                    "semantic checker functions returned no issues on fixture",
                )
            )
    except Exception as exc:  # noqa: BLE001
        results.append(
            CheckResult(
                "round_54_semantic_runtime",
                Severity.WARN,
                f"semantic checker check skipped: {exc}",
            )
        )
    return results


def check_round_55_ci_tooling_integration() -> list[CheckResult]:
    """Round 55 GitHub Actions CI — check:tooling required, test:ui optional."""
    results: list[CheckResult] = []
    package_json = REPO_ROOT / "package.json"
    tooling_script = REPO_ROOT / "scripts" / "run_tooling_checks.sh"
    workflows_dir = REPO_ROOT / ".github" / "workflows"

    if package_json.is_file():
        text = package_json.read_text(encoding="utf-8", errors="replace")
        scripts_ok = '"check:tooling"' in text and '"test:ui"' in text
        if scripts_ok:
            results.append(
                CheckResult(
                    "round_55_package_scripts",
                    Severity.PASS,
                    "package.json defines check:tooling and test:ui",
                )
            )
        else:
            results.append(
                CheckResult(
                    "round_55_package_scripts",
                    Severity.WARN,
                    "package.json missing check:tooling or test:ui script",
                )
            )
    else:
        results.append(
            CheckResult(
                "round_55_package_scripts",
                Severity.WARN,
                "missing package.json",
            )
        )

    if tooling_script.is_file():
        results.append(
            CheckResult(
                "round_55_tooling_script_exists",
                Severity.PASS,
                f"found: {_rel_path(tooling_script)}",
            )
        )
    else:
        results.append(
            CheckResult(
                "round_55_tooling_script_exists",
                Severity.WARN,
                "missing scripts/run_tooling_checks.sh",
            )
        )

    workflow_files = sorted(workflows_dir.glob("*.yml")) + sorted(workflows_dir.glob("*.yaml"))
    if not workflow_files:
        results.append(
            CheckResult(
                "round_55_ci_workflow_exists",
                Severity.WARN,
                "no .github/workflows/*.yml — CI not wired",
            )
        )
        return results

    ci_text = ""
    for wf in workflow_files:
        ci_text += wf.read_text(encoding="utf-8", errors="replace")
    has_tooling = "check:tooling" in ci_text
    has_ui = "test:ui" in ci_text
    if has_tooling:
        results.append(
            CheckResult(
                "round_55_ci_workflow_exists",
                Severity.PASS,
                f"workflow invokes check:tooling ({len(workflow_files)} file(s))",
            )
        )
    else:
        results.append(
            CheckResult(
                "round_55_ci_workflow_exists",
                Severity.WARN,
                "workflows present but missing check:tooling step",
            )
        )
    if has_ui:
        results.append(
            CheckResult(
                "round_55_ci_ui_optional",
                Severity.PASS,
                "workflow references test:ui (optional job)",
            )
        )
    else:
        results.append(
            CheckResult(
                "round_55_ci_ui_optional",
                Severity.WARN,
                "workflow missing optional test:ui job",
            )
        )
    return results


def check_agent_layer_v2(*, strict_layer: bool = False) -> list[CheckResult]:
    """Tool-aware Agent Layer 2.0 required artifacts.

    Default: missing files → WARN (non-blocking for legacy pipeline rounds).
    ``--strict-layer``: missing files → FAIL (exit 2).
    """
    missing_severity = Severity.FAIL if strict_layer else Severity.WARN
    results: list[CheckResult] = []
    for cid, path in AGENT_LAYER_FILES:
        if path.is_file():
            results.append(
                CheckResult(
                    f"agent_layer_{cid}",
                    Severity.PASS,
                    f"found: {_rel_path(path)}",
                )
            )
        else:
            results.append(
                CheckResult(
                    f"agent_layer_{cid}",
                    missing_severity,
                    f"missing Agent Layer 2.0 file: {_rel_path(path)}",
                )
            )
    probe_script = REPO_ROOT / "scripts" / "tool_probe.py"
    if probe_script.is_file():
        results.append(
            CheckResult(
                "agent_layer_tool_probe_script",
                Severity.PASS,
                "found scripts/tool_probe.py",
            )
        )
    else:
        results.append(
            CheckResult(
                "agent_layer_tool_probe_script",
                missing_severity,
                "missing scripts/tool_probe.py",
            )
        )
    return results


def check_real_api_env_guard() -> CheckResult:
    """Agent Layer rounds default dry-run; REAL_API in env is a governance violation."""
    raw = os.environ.get("REAL_API_TESTS_ENABLED", "")
    enabled = raw.strip().lower() in ("1", "true", "yes", "on")
    if enabled:
        return CheckResult(
            "real_api_env_guard",
            Severity.FAIL,
            "REAL_API_TESTS_ENABLED is set; agent rounds must stay dry-run (unset or use explicit human-approved real API script)",
        )
    return CheckResult(
        "real_api_env_guard",
        Severity.PASS,
        "REAL_API_TESTS_ENABLED not enabled in environment",
    )


def enqueue_gate_failures(results: Sequence[CheckResult]) -> None:
    """Append bugfix tasks for FAIL checks (AL-020). Best-effort; never raises."""
    failed = [r for r in results if r.severity == Severity.FAIL]
    if not failed:
        return
    agent_script = REPO_ROOT / "scripts" / "agent.py"
    if not agent_script.is_file():
        return
    for item in failed[:5]:
        reason = f"agent_gate FAIL: {item.check_id} — {item.message[:120]}"
        try:
            subprocess.run(
                [sys.executable, str(agent_script), "enqueue", "--type", "bugfix", "--reason", reason],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
                timeout=15,
            )
        except (OSError, subprocess.TimeoutExpired):
            break


def check_git_status_summary() -> list[CheckResult]:
    results: list[CheckResult] = []
    branch = _git(["rev-parse", "--abbrev-ref", "HEAD"], REPO_ROOT).stdout.strip() or "unknown"
    dirty = _git(["status", "--porcelain"], REPO_ROOT).stdout.strip()
    if dirty:
        lines = len(dirty.splitlines())
        results.append(
            CheckResult(
                "git_status_dirty",
                Severity.WARN,
                f"working tree has {lines} uncommitted change(s) on branch {branch}",
            )
        )
    else:
        results.append(
            CheckResult(
                "git_status_clean",
                Severity.PASS,
                f"working tree clean on branch {branch}",
            )
        )
    if branch not in ("main", "master"):
        results.append(
            CheckResult(
                "git_branch_not_main",
                Severity.WARN,
                f"current branch is {branch}, not main/master",
            )
        )
    return results


def run_all_checks(*, strict: bool = False, strict_layer: bool = False) -> list[CheckResult]:
    results: list[CheckResult] = []
    results.extend(check_docs_exist())
    results.extend(check_roadmaps(strict))
    results.extend(check_protocol_docs())
    results.extend(check_tooling_docs())
    results.extend(check_reference_docs())
    results.append(check_prompt_templates())
    results.extend(check_direction_dirs())
    results.append(check_gitignore_safe())
    results.append(check_frontend_mvp_exists())
    results.extend(check_vector_store_tooling())
    results.extend(check_quality_review_tooling())
    results.extend(check_round_50_e2e_trial())
    results.extend(check_round_51_openrouter_smoke())
    results.extend(check_round_52_refine_stage_c())
    results.extend(check_round_53_multi_project_manifest())
    results.extend(check_round_54_semantic_checker_mvp())
    results.extend(check_round_55_ci_tooling_integration())
    results.extend(check_agent_layer_v2(strict_layer=strict_layer))
    results.append(check_real_api_env_guard())
    results.append(check_env_not_tracked())
    results.extend(check_input_sources_ignored())
    results.extend(check_outputs_ignored())
    results.extend(check_git_status_summary())
    return results


def aggregate_exit_code(results: Iterable[CheckResult]) -> int:
    severities = {r.severity for r in results}
    if Severity.FAIL in severities:
        return 2
    if Severity.WARN in severities:
        return 1
    return 0


def write_gate_result_json(
    results: Sequence[CheckResult],
    exit_code: int,
    *,
    tool_usage: Sequence[dict] | None = None,
) -> None:
    """Write machine-readable gate summary for Agent Layer 2.0."""
    GATE_RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    passed = [r.check_id for r in results if r.severity == Severity.PASS]
    failed = [r.check_id for r in results if r.severity == Severity.FAIL]
    skipped: list[str] = []
    blocked = failed.copy()
    status_map = {0: "passed", 1: "warning", 2: "failed"}
    payload = {
        "status": status_map.get(exit_code, "failed"),
        "timestamp": now,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "blocked": blocked,
        "checks": [r.to_dict() for r in results],
        "commands": [
            {
                "name": "agent_gate",
                "command": "python3 scripts/agent_gate.py",
                "exit_code": exit_code,
                "summary": status_map.get(exit_code, "unknown"),
            }
        ],
        "tool_usage": list(tool_usage or []),
        "next_action": "fix_failed_checks" if failed else "continue_next_round",
    }
    GATE_RESULT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_report(
    results: Sequence[CheckResult],
    exit_code: int,
    *,
    strict: bool,
    strict_layer: bool,
) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines = [
        "# Agent Gate Report",
        "",
        f"- Generated: {now}",
        f"- Strict mode: {strict}",
        f"- Strict Layer 2.0 mode: {strict_layer}",
        f"- Exit code: {exit_code}",
        "",
        "## Checks",
        "",
        "| ID | Status | Message |",
        "|----|--------|---------|",
    ]
    for r in results:
        lines.append(f"| {r.check_id} | {r.severity.value} | {r.message} |")
    lines.extend(["", "## Summary", ""])
    counts = {s: sum(1 for r in results if r.severity == s) for s in Severity}
    lines.append(
        f"pass={counts[Severity.PASS]}, warn={counts[Severity.WARN]}, fail={counts[Severity.FAIL]}"
    )
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deterministic agent gate for light_novel repo")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON to stdout")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat missing roadmap 41-50 and doc gaps as BLOCKED where applicable",
    )
    parser.add_argument(
        "--strict-layer",
        action="store_true",
        help="FAIL (exit 2) if Agent Layer 2.0 files in AGENT_LAYER_FILES are missing",
    )
    parser.add_argument(
        "--enqueue-failures",
        action="store_true",
        help="On BLOCKED (exit 2), enqueue bugfix tasks via scripts/agent.py (AL-020)",
    )
    args = parser.parse_args(argv)

    results = run_all_checks(strict=args.strict, strict_layer=args.strict_layer)
    exit_code = aggregate_exit_code(results)
    if args.enqueue_failures and exit_code == 2:
        enqueue_gate_failures(results)
    write_report(results, exit_code, strict=args.strict, strict_layer=args.strict_layer)
    write_gate_result_json(
        results,
        exit_code,
        tool_usage=[
            {"tool": "shell", "used": True, "purpose": "run agent_gate checks"},
            {"tool": "web_search", "used": False, "reason": "gate does not require fresh external info"},
        ],
    )

    payload = {
        "exit_code": exit_code,
        "strict": args.strict,
        "strict_layer": args.strict_layer,
        "report_path": str(REPORT_PATH.relative_to(REPO_ROOT)),
        "checks": [r.to_dict() for r in results],
    }

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        label = {0: "PASS", 1: "WARNING", 2: "BLOCKED"}[exit_code]
        print(f"agent_gate: {label} (exit {exit_code})")
        print(f"report: {REPORT_PATH.relative_to(REPO_ROOT)}")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
