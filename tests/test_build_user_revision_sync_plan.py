from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
SCRIPT = ROOT / "scripts" / "build_user_revision_sync_plan.py"
FIXTURES = ROOT / "tests" / "fixtures" / "user_revision_sync"


def _isolated_cli(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "isolated_repo"
    (repo / "scripts").mkdir(parents=True)
    shutil.copy2(SCRIPT, repo / "scripts" / SCRIPT.name)
    shutil.copytree(ROOT / "src" / "revision_sync", repo / "src" / "revision_sync", ignore=shutil.ignore_patterns("__pycache__"))
    (repo / "src" / "translation").mkdir()
    for name in ("__init__.py", "chapter_parser.py"):
        shutil.copy2(ROOT / "src" / "translation" / name, repo / "src" / "translation" / name)
    (repo / "schemas").mkdir()
    shutil.copy2(ROOT / "schemas" / "user_revision_sync_plan.schema.json", repo / "schemas")
    return repo, repo / "scripts" / SCRIPT.name


def _run_structured(script: Path, cwd: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    return subprocess.run(
        [sys.executable, str(script), "--canonical", str(FIXTURES / "canonical.json"),
         "--revision", str(FIXTURES / "unchanged.json"),
         "--chapter-87-disposition", "awaiting_user_no_phase_a_change",
         "--policy-json", str(FIXTURES / "policy.json"), *extra],
        cwd=cwd, env=env, text=True, capture_output=True, check=False,
    )


def test_cli_emits_plan_to_stdout_and_creates_no_files(tmp_path: Path):
    repo, script = _isolated_cli(tmp_path)
    result = _run_structured(script, repo)
    assert result.returncode == 0, result.stderr
    plan = json.loads(result.stdout)
    assert plan["side_effects_applied"] is False
    assert plan["chapter_coverage"]["chapter_87_disposition"] == "awaiting_user_no_phase_a_change"
    assert plan["alignment"]["summary"]["complete_alignment"] is True
    assert not (repo / "artifacts").exists()


def test_cli_requires_explicit_chapter_87_disposition(tmp_path: Path):
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--canonical", str(FIXTURES / "canonical.json"),
         "--revision", str(FIXTURES / "unchanged.json")],
        cwd=tmp_path, text=True, capture_output=True, check=False,
    )
    assert result.returncode == 2
    assert "chapter-87-disposition" in result.stderr


def test_cli_valid_output_creates_fresh_fixed_root_and_only_requested_plan(tmp_path: Path):
    repo, script = _isolated_cli(tmp_path)
    output = repo / "artifacts" / "user_revision_sync" / "user_revision_sync_plan_pytest.json"
    assert not output.parent.exists()
    result = _run_structured(script, repo, "--output", str(output))
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    plan = json.loads(output.read_text(encoding="utf-8"))
    assert plan["status"] == "awaiting_confirmation"
    assert plan["side_effects_applied"] is False
    assert list(output.parent.iterdir()) == [output]


def test_cli_rejects_output_outside_approved_artifact_root(tmp_path: Path):
    repo, script = _isolated_cli(tmp_path)
    forbidden = tmp_path / "user_revision_sync_plan.json"
    result = _run_structured(script, repo, "--output", str(forbidden))
    assert result.returncode == 2
    assert "recognized JSON sync plan" in result.stderr
    assert not forbidden.exists()
    assert not (repo / "artifacts").exists()


def test_cli_invalid_input_with_valid_output_creates_no_artifact_root(tmp_path: Path):
    repo, script = _isolated_cli(tmp_path)
    malformed = tmp_path / "malformed.json"
    malformed.write_text("not JSON", encoding="utf-8")
    output = repo / "artifacts" / "user_revision_sync" / "user_revision_sync_plan_invalid.json"
    result = subprocess.run(
        [sys.executable, str(script), "--canonical", str(malformed),
         "--revision", str(FIXTURES / "unchanged.json"),
         "--chapter-87-disposition", "awaiting_user_no_phase_a_change", "--output", str(output)],
        cwd=repo, text=True, capture_output=True, check=False,
    )
    assert result.returncode != 0
    assert not (repo / "artifacts").exists()


def test_cli_rejects_revised_output_override_before_creating_artifact_root(tmp_path: Path):
    repo, script = _isolated_cli(tmp_path)
    policy = json.loads((FIXTURES / "policy.json").read_text(encoding="utf-8"))
    policy.setdefault("paths", {})["revised_output"] = "workspace/not-full-volume.md"
    policy_path = tmp_path / "invalid_policy.json"
    policy_path.write_text(json.dumps(policy), encoding="utf-8")
    output = repo / "artifacts" / "user_revision_sync" / "user_revision_sync_plan_invalid_target.json"
    result = subprocess.run(
        [sys.executable, str(script), "--canonical", str(FIXTURES / "canonical.json"),
         "--revision", str(FIXTURES / "unchanged.json"),
         "--chapter-87-disposition", "awaiting_user_no_phase_a_change",
         "--policy-json", str(policy_path), "--output", str(output)],
        cwd=repo, text=True, capture_output=True, check=False,
    )
    assert result.returncode == 2
    assert "revised_output must remain" in result.stderr
    assert not (repo / "artifacts").exists()


def test_cli_rejects_unrecognized_existing_file_in_approved_root(tmp_path: Path):
    repo, script = _isolated_cli(tmp_path)
    artifact_root = repo / "artifacts" / "user_revision_sync"
    artifact_root.mkdir(parents=True)
    forbidden = artifact_root / "user_revision_sync_plan_unrecognized.json"
    forbidden.write_text('{"owner":"not-a-plan"}\n', encoding="utf-8")
    result = _run_structured(script, repo, "--output", str(forbidden))
    assert result.returncode == 2
    assert json.loads(forbidden.read_text(encoding="utf-8")) == {"owner": "not-a-plan"}
    assert list(artifact_root.iterdir()) == [forbidden]


def test_cli_rejects_symlink_escape_from_approved_root(tmp_path: Path):
    repo, script = _isolated_cli(tmp_path)
    artifact_root = repo / "artifacts" / "user_revision_sync"
    artifact_root.mkdir(parents=True)
    outside = tmp_path / "outside.json"
    outside.write_text('{"untouched":true}\n', encoding="utf-8")
    link = artifact_root / "user_revision_sync_plan_symlink.json"
    link.symlink_to(outside)
    result = _run_structured(script, repo, "--output", str(link))
    assert result.returncode == 2
    assert json.loads(outside.read_text(encoding="utf-8")) == {"untouched": True}
    assert list(artifact_root.iterdir()) == [link]


def test_cli_rejects_symlink_alias_within_approved_root(tmp_path: Path):
    repo, script = _isolated_cli(tmp_path)
    artifact_root = repo / "artifacts" / "user_revision_sync"
    artifact_root.mkdir(parents=True)
    target = artifact_root / "user_revision_sync_plan_alias_target.json"
    link = artifact_root / "user_revision_sync_plan_alias.json"
    target.write_text('{"plan_type":"user_revision_sync_plan","schema_version":1}\n', encoding="utf-8")
    link.symlink_to(target)
    result = _run_structured(script, repo, "--output", str(link))
    assert result.returncode == 2
    assert "must not be a symlink" in result.stderr
    assert json.loads(target.read_text(encoding="utf-8"))["plan_type"] == "user_revision_sync_plan"
    assert set(artifact_root.iterdir()) == {link, target}


@pytest.mark.parametrize("symlink_component", ["artifacts", "user_revision_sync"])
def test_cli_rejects_parent_or_root_symlink_without_external_writes(tmp_path: Path, symlink_component: str):
    repo, script = _isolated_cli(tmp_path)
    outside = tmp_path / "outside_directory"
    outside.mkdir()
    if symlink_component == "artifacts":
        (repo / "artifacts").symlink_to(outside, target_is_directory=True)
    else:
        (repo / "artifacts").mkdir()
        (repo / "artifacts" / "user_revision_sync").symlink_to(outside, target_is_directory=True)
    output = repo / "artifacts" / "user_revision_sync" / "user_revision_sync_plan_symlink_root.json"
    result = _run_structured(script, repo, "--output", str(output))
    assert result.returncode == 2
    assert "real directory" in result.stderr
    assert list(outside.iterdir()) == []


@pytest.mark.parametrize("file_component", ["artifacts", "user_revision_sync"])
def test_cli_rejects_non_directory_component_without_partial_output(tmp_path: Path, file_component: str):
    repo, script = _isolated_cli(tmp_path)
    if file_component == "artifacts":
        component = repo / "artifacts"
    else:
        (repo / "artifacts").mkdir()
        component = repo / "artifacts" / "user_revision_sync"
    component.write_text("untouched\n", encoding="utf-8")
    output = repo / "artifacts" / "user_revision_sync" / "user_revision_sync_plan_non_directory.json"
    result = _run_structured(script, repo, "--output", str(output))
    assert result.returncode == 2
    assert component.read_text(encoding="utf-8") == "untouched\n"
    assert not any(repo.rglob("*.tmp"))


def test_cli_rejects_existing_output_directory_without_partial_output(tmp_path: Path):
    repo, script = _isolated_cli(tmp_path)
    output = repo / "artifacts" / "user_revision_sync" / "user_revision_sync_plan_directory.json"
    output.mkdir(parents=True)
    result = _run_structured(script, repo, "--output", str(output))
    assert result.returncode == 2
    assert "regular generated plan artifact" in result.stderr
    assert output.is_dir()
    assert list(output.parent.iterdir()) == [output]
    assert not any(repo.rglob("*.tmp"))


def test_cli_rejects_output_that_would_overwrite_input(tmp_path: Path):
    repo, script = _isolated_cli(tmp_path)
    artifact_root = repo / "artifacts" / "user_revision_sync"
    artifact_root.mkdir(parents=True)
    output = artifact_root / "user_revision_sync_plan_input.json"
    original = {
        "plan_type": "user_revision_sync_plan",
        "schema_version": 1,
        "segments": [],
    }
    output.write_text(json.dumps(original), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(script), "--canonical", str(output),
         "--revision", str(FIXTURES / "unchanged.json"),
         "--chapter-87-disposition", "awaiting_user_no_phase_a_change",
         "--policy-json", str(FIXTURES / "policy.json"),
         "--output", str(output)],
        cwd=repo, text=True, capture_output=True, check=False,
    )
    assert result.returncode == 2
    assert "overwrite an input" in result.stderr
    assert json.loads(output.read_text(encoding="utf-8")) == original
    assert list(artifact_root.iterdir()) == [output]


def test_cli_atomically_replaces_only_recognized_existing_plan(tmp_path: Path):
    repo, script = _isolated_cli(tmp_path)
    artifact_root = repo / "artifacts" / "user_revision_sync"
    artifact_root.mkdir(parents=True)
    output = artifact_root / "user_revision_sync_plan_existing.json"
    output.write_text('{"plan_type":"user_revision_sync_plan","schema_version":1}\n', encoding="utf-8")
    result = _run_structured(script, repo, "--output", str(output))
    assert result.returncode == 0, result.stderr
    assert json.loads(output.read_text(encoding="utf-8"))["status"] == "awaiting_confirmation"
    assert list(artifact_root.iterdir()) == [output]
    assert not any(repo.rglob("*.tmp"))


def test_repository_mode_is_read_only_and_missing_afterword_goes_manual(tmp_path: Path):
    fixture = FIXTURES / "repository"
    tracked = [fixture / "source" / "001-sample.md", fixture / "canonical.md",
               fixture / "revisions_missing_afterword" / "001_sample.md"]
    before = {str(path): path.read_bytes() for path in tracked}
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--source-dir", str(fixture / "source"),
         "--canonical-full-volume", str(fixture / "canonical.md"),
         "--revision-dir", str(fixture / "revisions_missing_afterword"),
         "--chapter-start", "1", "--chapter-end", "1",
         "--policy-json", str(FIXTURES / "policy.json")],
        cwd=tmp_path, env=env, text=True, capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    plan = json.loads(result.stdout)
    assert plan["alignment"]["summary"]["aligned_segment_count"] == 1
    assert plan["alignment"]["summary"]["manual_item_count"] == 1
    assert plan["alignment"]["manual_queue"][0]["canonical_segment_id"].endswith("seg-002")
    assert plan["needs_local_retranslation"] is True
    assert plan["affects_current_final_export"] is True
    assert plan["paths"]["source_dir"] == str(fixture / "source")
    assert plan["paths"]["revision_dir"] == str(fixture / "revisions_missing_afterword")
    assert plan["paths"]["canonical_full_volume"] == str(fixture / "canonical.md")
    assert plan["owner_decisions"][0]["id"] == "homunculus_exact_spelling"
    assert plan["owner_decisions"][0]["status"] == "awaiting_user"
    assert len(plan["owner_decisions"]) == 9
    assert plan["content_policies"]["metadata"] == "remove_transport_metadata_only"
    assert plan["chapter_coverage"]["chapter_87_disposition"].startswith("awaiting_user_no_phase_a_change")
    assert {str(path): path.read_bytes() for path in tracked} == before
    assert list(tmp_path.iterdir()) == []


def test_repository_mode_fails_closed_on_canonical_source_count_mismatch(tmp_path: Path):
    source = tmp_path / "source"
    revisions = tmp_path / "revisions"
    source.mkdir()
    revisions.mkdir()
    (source / "001-sample.md").write_text("# 第一章\n\n段一。\n\n段二。\n", encoding="utf-8")
    (revisions / "001_sample.md").write_text("标题\n\n译文。\n", encoding="utf-8")
    canonical = tmp_path / "canonical.md"
    canonical.write_text("# 第1章\n\n只有一段。\n", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--source-dir", str(source),
         "--canonical-full-volume", str(canonical), "--revision-dir", str(revisions),
         "--chapter-start", "1", "--chapter-end", "1",
         "--chapter-87-disposition", "awaiting_user_no_phase_a_change"],
        cwd=tmp_path, text=True, capture_output=True, check=False,
    )
    assert result.returncode == 2
    assert "canonical/source paragraph mismatch" in result.stderr
