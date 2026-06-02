#!/usr/bin/env python3
"""Deterministic repository gate for Agent autonomous advancement.

Does not call LLMs or external APIs. Does not read .env contents.
Exit codes: 0=PASS, 1=WARNING, 2=BLOCKED (see governance/repo_protocol_standard.yaml).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
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
        spec = importlib.util.spec_from_file_location(
            "light_novel_vector_db_inspect_gate",
            VECTOR_INSPECT_SCRIPT,
        )
        if not spec or not spec.loader:
            raise RuntimeError("cannot load vector_db_inspect module")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        manifest = REPO_ROOT / "workspace" / "manifests" / "project_manifest.json"
        report, _, _ = mod.run_inspection(DEFAULT_VECTOR_INDEX, manifest if manifest.is_file() else None)
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
                f"vector inspect skipped: {exc}",
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
    except Exception as exc:  # noqa: BLE001
        results.append(
            CheckResult(
                "round_50_e2e_trial",
                Severity.WARN,
                f"E2E trial skipped: {exc}",
            )
        )
    return results


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


def run_all_checks(strict: bool) -> list[CheckResult]:
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


def write_report(results: Sequence[CheckResult], exit_code: int, strict: bool) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines = [
        "# Agent Gate Report",
        "",
        f"- Generated: {now}",
        f"- Strict mode: {strict}",
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
    args = parser.parse_args(argv)

    results = run_all_checks(strict=args.strict)
    exit_code = aggregate_exit_code(results)
    write_report(results, exit_code, args.strict)

    payload = {
        "exit_code": exit_code,
        "strict": args.strict,
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
