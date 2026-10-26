"""Boundary regressions use a view with no live corpus or credentials mounted."""
import importlib.util
import json
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("isolated_checks_test", ROOT / "scripts/isolated_checks.py")
isolation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(isolation)


def test_real_roots_and_credentials_are_inaccessible(request):
    metadata = isolation.require_view(ROOT)
    original = Path(metadata["source_root"])
    assert not (original / "workspace/manifests/project_manifest.json").exists()
    assert not (original / ".env").exists()
    assert not (original.parent / "personal_style_hub").exists()
    # Other tests legitimately manufacture fake dotenv keys later in the suite.
    assert not request.config._ln_startup_secret_keys
    assert not (ROOT / ".env").exists()
    with pytest.raises(OSError):
        (original / "workspace/manifests/project_manifest.json").read_bytes()
    with pytest.raises(OSError):
        (original / "workspace/workbench_state.json").write_text("must not write")


def test_unmarked_root_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("LN_SYNTHETIC_CHECK_ROOT", str(tmp_path))
    with pytest.raises(OSError):
        isolation.require_view(tmp_path)


def test_symlinked_engineering_input_is_rejected(tmp_path):
    (tmp_path / "target").write_text("synthetic")
    (tmp_path / "link").symlink_to(tmp_path / "target")
    with pytest.raises(ValueError, match="ordinary"):
        isolation.safe_file(tmp_path, "link")


def test_symlinked_parent_is_rejected_even_inside_root(tmp_path):
    (tmp_path / "private").mkdir()
    (tmp_path / "private/source.py").write_text("synthetic")
    (tmp_path / "src").symlink_to(tmp_path / "private", target_is_directory=True)
    with pytest.raises(ValueError, match="ordinary"):
        isolation.safe_file(tmp_path, "src/source.py")


def test_fixture_registry_versions_match_copied_inputs():
    meta = isolation.require_view(ROOT)
    for path, record in meta["synthetic_fixture_registry"]["files"].items():
        assert meta["copied_sha256"][path] == record["sha256"]
    assert all(not p.startswith(("workspace/", "input_jp/", "output_cn/")) for p in meta["copied_sha256"])


def test_missing_bubblewrap_has_no_unsafe_fallback(monkeypatch, tmp_path):
    monkeypatch.setattr(isolation.shutil, "which", lambda _: None)
    with pytest.raises(RuntimeError, match="no unsafe fallback"):
        isolation.sandbox_command(ROOT, tmp_path, tmp_path, ["true"], venv=False)
