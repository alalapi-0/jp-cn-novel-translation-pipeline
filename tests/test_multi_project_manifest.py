"""Tests for multi-project workbench manifest registry."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from workbench import project_registry as reg  # noqa: E402


@pytest.fixture()
def tmp_repo(tmp_path: Path) -> Path:
    examples = REPO_ROOT / "data" / "examples"
    for example in examples.glob("workbench_project.*.example.json"):
        target = tmp_path / "data" / "examples" / example.name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
    return tmp_path


def test_seed_example_manifests_creates_two_projects(tmp_repo: Path) -> None:
    paths = reg.seed_example_manifests(tmp_repo)
    assert len(paths) >= 2
    manifests = reg.list_project_manifests(tmp_repo)
    ids = {m.project_id for m in manifests}
    assert "demo-jp-cn" in ids
    assert "demo-cn-jp" in ids


def test_set_active_project_persists_state(tmp_repo: Path) -> None:
    reg.seed_example_manifests(tmp_repo)
    reg.set_active_project_id(tmp_repo, "demo-cn-jp")
    assert reg.get_active_project_id(tmp_repo) == "demo-cn-jp"
    state = json.loads(reg.workbench_state_path(tmp_repo).read_text(encoding="utf-8"))
    assert state["active_project_id"] == "demo-cn-jp"


def test_unknown_project_raises_key_error(tmp_repo: Path) -> None:
    reg.seed_example_manifests(tmp_repo)
    with pytest.raises(KeyError):
        reg.set_active_project_id(tmp_repo, "missing-project")


def test_workbench_payload_includes_segments(tmp_repo: Path) -> None:
    reg.seed_example_manifests(tmp_repo)
    manifest = reg.get_project_manifest(tmp_repo, "demo-jp-cn")
    assert manifest is not None
    payload = manifest.to_workbench_payload()
    assert payload["project"]["id"] == "demo-jp-cn"
    assert len(payload["segments"]) == 5


def test_resolve_active_manifest_path(tmp_repo: Path) -> None:
    reg.seed_example_manifests(tmp_repo)
    reg.set_active_project_id(tmp_repo, "demo-cn-jp")
    path = reg.resolve_active_manifest_path(tmp_repo)
    assert path is not None
    assert path.name == "demo-cn-jp.json"


def test_legacy_manifest_hidden_when_named_manifest_exists(tmp_repo: Path) -> None:
    reg.seed_example_manifests(tmp_repo)
    manifests_dir = reg.manifests_dir(tmp_repo)
    legacy = manifests_dir / reg.LEGACY_MANIFEST_NAME
    legacy.write_text(
        json.dumps(
            {
                "project_id": "demo-jp-cn",
                "name": "legacy duplicate",
                "language_direction": "JP_TO_CN",
                "status": "unknown",
                "chapters": 0,
                "segments": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    manifests = reg.list_project_manifests(tmp_repo)
    ids = [m.project_id for m in manifests]
    assert ids.count("demo-jp-cn") == 1
    jp_cn = next(m for m in manifests if m.project_id == "demo-jp-cn")
    assert jp_cn.name == "示例项目（日译中）"
