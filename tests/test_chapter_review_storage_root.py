from __future__ import annotations

import shlex
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE_SCRIPT = REPO_ROOT / "scripts" / "chapter_review_storage_root.sh"
ZSH = shutil.which("zsh")

pytestmark = pytest.mark.skipif(ZSH is None, reason="zsh is unavailable")


def _script_fixture(tmp_path: Path, root: Path, volume: Path) -> Path:
    guard = tmp_path / "guard.sh"
    guard.write_text(
        "#!/bin/sh\n"
        f"printf '%s\\n' {shlex.quote(str(root))}\n",
        encoding="utf-8",
    )
    guard.chmod(0o755)
    script = tmp_path / "chapter-review-storage.sh"
    text = SOURCE_SCRIPT.read_text(encoding="utf-8")
    text = text.replace(
        "readonly guard=/Users/alalapi/.config/storage-governance/guard.sh",
        f"readonly guard={shlex.quote(str(guard))}",
    )
    text = text.replace(
        "readonly expected_root=/Volumes/AI_WORK_SSD/ProjectData/light_novel/chapter_review",
        f"readonly expected_root={shlex.quote(str(root))}",
    )
    text = text.replace(
        "readonly expected_volume=/Volumes/AI_WORK_SSD",
        f"readonly expected_volume={shlex.quote(str(volume))}",
    )
    script.write_text(text, encoding="utf-8")
    script.chmod(0o755)
    return script


def test_real_external_root_passes(tmp_path: Path) -> None:
    volume = tmp_path / "volume"
    root = volume / "ProjectData" / "light_novel" / "chapter_review"
    root.mkdir(parents=True)
    script = _script_fixture(tmp_path, root, volume)
    proc = subprocess.run([ZSH, str(script), "--check"], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


def test_symlink_root_is_rejected(tmp_path: Path) -> None:
    volume = tmp_path / "volume"
    real_root = tmp_path / "real-root"
    real_root.mkdir()
    root = volume / "ProjectData" / "light_novel" / "chapter_review"
    root.parent.mkdir(parents=True)
    root.symlink_to(real_root, target_is_directory=True)
    script = _script_fixture(tmp_path, root, volume)
    proc = subprocess.run([ZSH, str(script), "--check"], capture_output=True, text=True)
    assert proc.returncode == 78
    assert "redirected" in proc.stderr


def test_symlink_path_component_is_rejected(tmp_path: Path) -> None:
    volume = tmp_path / "volume"
    root = volume / "ProjectData" / "light_novel" / "chapter_review"
    root.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "escape").symlink_to(outside, target_is_directory=True)
    script = _script_fixture(tmp_path, root, volume)
    proc = subprocess.run(
        [ZSH, str(script), "--path", "escape/report.json"],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 78
    assert "contains a symlink" in proc.stderr
