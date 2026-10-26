#!/usr/bin/env python3
"""Run repository checks in a disposable, synthetic-only Linux mount namespace.

The host phase copies an explicit engineering allowlist, never runtime data or
dotenv files. Bubblewrap hides home/data/runtime mounts, clears credentials and
disables external networking. Missing isolation support fails closed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
MARKER = ".synthetic-check-view.json"
ENGINEERING_DIRS = {"src", "scripts", "tests", "schemas", "configs", "frontend",
                    "prompts", "directions", "model-router", ".github"}
ROOT_FILES = {"README.md", "AGENTS.md", "project.yaml", "agent_layer.yaml",
              "agent_tools.yaml", "hub.connection.yaml", "package.json",
              "package-lock.json", "requirements-dev.txt", "requirements.txt",
              ".gitignore", "conftest.py", "playwright.config.js", "playwright.config.ts"}
CONTENT_DOCS = {"docs/PROMPTS.md", "docs/TOOL_USAGE_POLICY.md", "docs/AGENT_RUNBOOK.md",
                "docs/SEARCH_POLICY.md", "docs/AGENT_ROADMAP.md", "docs/product_final_state_spec.md",
                "docs/optimization/EVALUATION_PROTOCOL.md",
                "docs/optimization/BASELINE_PROTOCOL.md",
                "docs/translation_production_protocol.md", "docs/translation_consistency_protocol.md"}
DEPLOYMENT_ENGINEERING_FILES = {"deploy/rr/light-novel-rr.service",
    "deploy/rr/adopt_user_service.py", "deploy/rr/refresh_user_service.py",
    "deploy/rr/test_adopt_user_service.py", "deploy/rr/test_refresh_user_service.py"}
PROVENANCE = "tests/fixtures/synthetic_sources.json"


def require_view(root: Path = ROOT) -> dict:
    if os.environ.get("LN_SYNTHETIC_CHECK_ROOT") != str(root):
        raise RuntimeError("use scripts/isolated_checks.py; live-workspace checks are forbidden")
    value = json.loads((root / MARKER).read_text())
    if value.get("schema") != "synthetic-check-view/1" or value.get("root") != str(root):
        raise RuntimeError("invalid synthetic check view")
    return value


def safe_file(root: Path, relative: str) -> Path:
    path = root / relative
    parents = path.relative_to(root).parents
    if (any((root / parent).is_symlink() for parent in parents)
            or path.is_symlink() or not path.is_file()
            or not path.resolve().is_relative_to(root.resolve())):
        raise ValueError(f"not an ordinary engineering file: {relative}")
    return path


def git_snapshot(root: Path) -> dict:
    commands = [["rev-parse", "--abbrev-ref", "HEAD"], ["status", "--porcelain"],
                ["ls-files", "--error-unmatch", ".env"], ["ls-files", ".env"]]
    commands += [["check-ignore", "-v", p] for p in
                 ("input_jp/sample.txt", "input_cn/sample.txt", "output_cn/translated/out.txt",
                  "output_jp/translated/out.txt")]
    result = {}
    for args in commands:
        p = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=False)
        result[json.dumps(args)] = {"returncode": p.returncode, "stdout": p.stdout, "stderr": p.stderr}
    return result


def build_view(root: Path, view: Path) -> dict:
    """Only registered synthetic fixtures may cross into the work view."""
    provenance = json.loads(safe_file(root, PROVENANCE).read_text())
    fixtures = provenance["files"]
    tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=root).decode().split("\0")
    # Include owned new engineering files; never sweep untracked work from another task.
    tracked += ["scripts/isolated_checks.py", "conftest.py", PROVENANCE,
                "tests/test_isolated_checks.py", "scripts/freeze_optimization_inventory.py",
                "tests/test_optimization_inventory.py", "src/translation/source_alignment.py",
                "tests/test_source_alignment.py", "scripts/build_optimization_alignment.py",
                "tests/test_optimization_alignment.py", "src/translation/evaluation_split.py",
                "scripts/build_optimization_split.py", "tests/test_evaluation_split.py",
                "tests/test_optimization_split.py", "tests/test_draft_validation_safety.py",
                "tests/test_review_coverage_safety.py", "tests/test_approval_provenance.py",
                "tests/test_consistency_execution_safety.py", "tests/test_provider_attempt_safety.py", "src/translation/draft_execution.py",
                "tests/test_draft_execution_safety.py", "src/providers/content_unit_budget.py",
                "tests/test_content_unit_budget.py", "src/translation/content_binding.py",
                "tests/test_content_binding.py", "tests/test_work_rule_isolation.py",
                "tests/test_actual_chapter_audit_isolation.py",
                "src/translation/context_policy.py", "tests/test_source_context.py",
                "src/translation/narrative_context.py", "tests/test_narrative_context.py",
                "src/translation/source_versions.py", "tests/test_source_versions.py",
                "src/translation/atomic_bundle.py", "src/translation/canonical_export.py", "tests/test_canonical_export.py",
                "scripts/run_isolated_ui.py", "tests/ui/optimization-flow.spec.ts", "tests/ui/trusted-native-fixture.ts",
                "src/workbench/canonical_service.py", "tests/test_canonical_service.py",
                "scripts/canonical_workbench.py", "tests/test_canonical_workbench_cli.py",
                "src/workbench/native_agent.py", "tests/test_native_agent.py", "tests/ui/native-agent-flow.spec.ts",
                "src/workbench/native_revision.py", "tests/test_native_revision.py",
                "src/workbench/native_process.py", "tests/test_native_process.py",
                "src/quality_review/calibration.py", "tests/test_quality_calibration.py",
                "tests/test_development_calibration.py", "tests/test_problem_driven_revision.py", "tests/test_revision_comparison.py", "src/translation/revision_comparison.py",
                "src/translation/baselines.py", "tests/test_translation_baselines.py",
                "docs/optimization/EVALUATION_PROTOCOL.md",
                "docs/optimization/BASELINE_PROTOCOL.md",
                "src/consistency/work_rules.py", "configs/work_rules.example.json",
                "src/assets/knowledge.py", "tests/test_knowledge_evidence.py",
                "scripts/audit_optimization_knowledge.py", "tests/test_optimization_knowledge_audit.py",
                "src/assets/source_knowledge.py", "tests/test_source_knowledge.py",
                "src/assets/legacy_translation.py", "tests/test_legacy_translation_review.py"]
    copied = {}; projected = []
    copied_bytes = 0
    for rel in sorted(set(tracked) - {""}):
        parts = Path(rel).parts
        if any(p in {".env", ".cursor", "__pycache__", "node_modules", ".venv"} or p.startswith(".env.") for p in parts):
            continue
        selected = parts[0] in ENGINEERING_DIRS or rel in ROOT_FILES or rel in CONTENT_DOCS
        selected |= rel in DEPLOYMENT_ENGINEERING_FILES
        selected |= rel in fixtures or rel == PROVENANCE or rel.startswith("data/schemas/")
        selected |= rel.startswith("governance/") and rel != "governance/round_state.yaml"
        if not (root / rel).is_file():
            continue
        target = view / rel
        if not selected:
            # Existence-only document checks do not need historical report contents.
            if rel.startswith("docs/") and not rel.startswith("docs/reports/"):
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("Existence projection only; document content not validated here.\n")
                projected.append(rel)
            continue
        source = safe_file(root, rel)
        copied_bytes += source.stat().st_size
        if source.stat().st_size > 8 * 1024 * 1024 or copied_bytes > 96 * 1024 * 1024:
            raise ValueError("engineering view exceeds bounded copy size")
        raw = source.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if rel in fixtures and fixtures[rel]["sha256"] != digest:
            raise ValueError(f"synthetic fixture version not registered: {rel}")
        if (rel.startswith("tests/fixtures/") or rel.startswith("data/examples/")) and rel not in fixtures and rel != PROVENANCE:
            raise ValueError(f"unregistered fixture: {rel}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        target.chmod(source.stat().st_mode & 0o777)
        copied[rel] = digest
    # Project only the current engineering state, never historical work-derived records.
    state = safe_file(root, "governance/round_state.yaml").read_text()
    current = state.split("\ncodex_governance:\n", 1)[1]
    (view / "governance/round_state.yaml").write_text(
        "latest_stats:\n  scheduler_paused: true\n  next_round_id: null\n"
        "codex_governance:\n" + current)
    (view / "reports").mkdir(exist_ok=True)
    (view / "reports/latest-agent-report.json").write_text(json.dumps({
        "round_id": "SYNTHETIC-CHECK", "timestamp": "2026-10-23T00:00:00Z",
        "agent": "synthetic fixture", "agent_surface": "codex", "mode": "test",
        "goal": "isolated engineering checks only", "tool_probe_status": "not_run",
        "gate_status": "not_run", "severity_summary": {"p0": 0, "p1": 0, "p2": 0, "p3": 0}}))
    for rel in ("workspace", "docs/reports", "docs/archive"):
        (view / rel).mkdir(parents=True, exist_ok=True)
    metadata = {"schema": "synthetic-check-view/1", "root": "/work",
                "source_root": str(root), "copied_sha256": copied,
                "copied_bytes": copied_bytes,
                "existence_only_documents": projected, "git": git_snapshot(root),
                "synthetic_fixture_registry": provenance,
                "excluded_checks": ["test_scan_repo_inventory.py", "test_tool_probe_build_report"],
                "exclusion_reason": "current owner prohibits Cursor/inventory probe execution"}
    (view / MARKER).write_text(json.dumps(metadata, indent=2))
    return metadata


def sandbox_command(root: Path, view: Path, scratch: Path, command: list[str], *, venv: bool, ui: bool = False) -> list[str]:
    bwrap = shutil.which("bwrap")
    if not bwrap:
        raise RuntimeError("bubblewrap unavailable; no unsafe fallback")
    # Empty root contains only mount points (no sizeable tmpfs outputs). Explicit
    # system-runtime mounts avoid exposing arbitrary host data outside /home.
    args = [bwrap, "--die-with-parent", "--unshare-all", "--tmpfs", "/"]
    for path in ("/usr", "/bin", "/sbin", "/lib", "/lib64"):
        if Path(path).exists():
            args += ["--ro-bind", path, path]
    for path in ("/home", "/root", "/data", "/Users", "/media", "/mnt", "/run", "/etc"):
        args += ["--dir", path]
    for path in ("/etc/ld.so.cache", "/etc/localtime", "/etc/passwd", "/etc/group", "/etc/nsswitch.conf"):
        if Path(path).exists():
            args += ["--ro-bind", path, path]
    args += ["--bind", str(view), "/work", "--bind", str(scratch), "/tmp",
             "--proc", "/proc", "--dev", "/dev", "--chdir", "/work", "--clearenv"]
    for key, value in {"PATH": "/venv/bin:/usr/local/bin:/usr/bin:/bin", "HOME": "/tmp/home",
                       "TMPDIR": "/tmp", "REAL_API_TESTS_ENABLED": "false", "MAX_TEST_COST_USD": "0",
                       "LN_SYNTHETIC_CHECK_ROOT": "/work", "PYTHONDONTWRITEBYTECODE": "1",
                       "LANG": "C.UTF-8"}.items():
        args += ["--setenv", key, value]
    if ui:
        node_binary = shutil.which("node")
        if not node_binary: raise RuntimeError("missing Node runtime")
        node_runtime = Path(node_binary).resolve().parent.parent
        args += ["--ro-bind", str(node_runtime), str(node_runtime)]
        chrome = Path(os.environ.get('LN_UI_CHROMIUM', '/opt/google/chrome/chrome'))
        modules = root / "node_modules"
        if not chrome.is_file() or not modules.is_dir():
            raise RuntimeError("missing installed Chrome/project Playwright; no install or live-profile fallback")
        args += ["--ro-bind", str(chrome.parent), str(chrome.parent),
                 "--ro-bind", str(modules.resolve()), "/work/node_modules",
                 "--setenv", "LN_UI_CHROMIUM", str(chrome),
                 "--setenv", "PATH", str(Path(node_binary).resolve().parent) + ":/venv/bin:/usr/local/bin:/usr/bin:/bin"]
        if Path('/etc/fonts').is_dir(): args += ["--ro-bind", "/etc/fonts", "/etc/fonts"]
    if venv:
        runtime = root / ".venv"
        if not (runtime / "bin/python").is_file():
            raise RuntimeError("missing .venv; install README development requirements after --probe")
        args += ["--ro-bind", str(runtime), "/venv"]
        (view / ".venv").symlink_to("/venv", target_is_directory=True)
    return args + command


def run(entry: str, arguments: list[str], *, root: Path = ROOT) -> int:
    # All sizeable temporary files stay on the repository's persistent disk.
    work = root / "workspace/tooling/isolated-checks"
    work.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="run-", dir=work) as run_dir:
        owned = Path(run_dir); view = owned / "view"; view.mkdir(); scratch = owned / "tmp"; scratch.mkdir()
        metadata = build_view(root, view)
        if entry == "probe":
            command = ["/usr/bin/python3", "scripts/isolated_checks.py", "--verify-boundary"]
        elif entry == "gate":
            command = ["/venv/bin/python", "scripts/agent_gate.py", *arguments]
        elif entry == "tooling":
            command = ["sh", "scripts/run_tooling_checks.sh", *arguments]
        elif entry == "pytest":
            command = ["/venv/bin/python", "-m", "pytest", *(arguments or ["tests/", "-q"])]
        elif entry == "ui":
            command = ["/venv/bin/python", "scripts/run_isolated_ui.py", *arguments]
        elif entry == "quality-review":
            command = ["/venv/bin/python", "scripts/run_quality_review.py", *arguments]
        else:
            raise ValueError(f"unknown check entry: {entry}")
        proc = subprocess.run(sandbox_command(root, view, scratch, command, venv=entry != "probe", ui=entry == "ui"), check=False)
        evidence = work / "latest"
        evidence.mkdir(exist_ok=True)
        for rel in ("reports/gate_result.json", "docs/reports/agent_gate_report.md", "docs/reports/protocol_compliance_report.md"):
            output = view / rel
            if output.is_file():
                shutil.copyfile(output, evidence / output.name)
        if entry == "ui" and (view / "artifacts").is_dir():
            ui_target = work / (owned.name + "-ui")
            shutil.copytree(view / "artifacts", ui_target)
        receipt = {"entry": entry, "arguments": arguments, "exit_code": proc.returncode,
                   "boundary": "mount namespace; live homes/data/runtime hidden; no external network; cleared environment",
                   "view": metadata}
    receipt["temporary_view_removed_on_exit"] = not owned.exists()
    raw = json.dumps(receipt, indent=2)
    (evidence / "receipt.json").write_text(raw)
    # Preserve attempts without keeping disposable workspaces or runtime data.
    (work / f"{owned.name}-receipt.json").write_text(raw)
    return proc.returncode


def verify_boundary() -> int:
    value = require_view()
    source = Path(value["source_root"])
    for path in (source / "workspace", source / ".env", source.parent / "personal_style_hub",
                 Path("/data"), Path("/Users")):
        # /data and /Users are empty mounts; all original contents are hidden.
        if path in (Path("/data"), Path("/Users")):
            assert not list(path.iterdir()), path
        else:
            assert not path.exists(), f"live path visible: {path}"
            try:
                with path.open("rb"):
                    pass
            except OSError:
                pass
            else:
                raise AssertionError(f"live path accessible: {path}")
    assert not any(k.endswith(("_API_KEY", "_TOKEN")) for k in os.environ)
    assert "LN_ISOLATION_PRIVATE_SENTINEL" not in os.environ
    assert not (ROOT / ".env").exists()
    assert not list((ROOT / "workspace").iterdir())
    with socket.socket() as network:
        network.settimeout(1)
        # The isolated network has no external route; no request reaches a provider.
        assert network.connect_ex(("192.0.2.1", 443)) != 0
    print("synthetic boundary: live workspace/dotenv/PSH inaccessible; empty runtime; credentials absent")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entry", choices=("probe", "gate", "tooling", "pytest", "quality-review", "ui"), default="probe")
    parser.add_argument("--verify-boundary", action="store_true")
    args, remaining = parser.parse_known_args(argv)
    if args.verify_boundary:
        return verify_boundary()
    if remaining[:1] == ["--"]:
        remaining = remaining[1:]
    return run(args.entry, remaining)


if __name__ == "__main__":
    raise SystemExit(main())
