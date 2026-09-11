#!/usr/bin/env python3
"""Export body-free project metrics with the shared Hub snapshot contract."""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable


REPO_ROOT = Path(__file__).resolve().parent.parent
PROJECT_ID = "light-novel"
EXPORTER_ID = "light-novel-metadata"
EXPORTER_VERSION = "1.0"


def _shared_hub_modules(hub_root: Path) -> tuple[Callable, Callable, type]:
    """Load the authoritative Hub writer and novel collector from one explicit root."""
    root = hub_root.expanduser().absolute()
    if not root.is_dir() or root.is_symlink():
        raise ValueError("hub root must be an existing ordinary directory")
    root = root.resolve(strict=True)
    source = root / "src"
    required = (
        source / "hub" / "metric_export.py",
        source / "hub" / "metric_novel.py",
        source / "hub" / "metric_snapshot.py",
        source / "hub" / "connection_sources.py",
    )
    if (
        not source.is_dir()
        or source.is_symlink()
        or any(not path.is_file() or path.is_symlink() for path in required)
    ):
        raise ValueError("hub root does not provide the shared metric snapshot contract")

    source_text = str(source.resolve(strict=True))
    sys.path.insert(0, source_text)
    try:
        importlib.invalidate_caches()
        metric_export = importlib.import_module("hub.metric_export")
        metric_novel = importlib.import_module("hub.metric_novel")
        connection_sources = importlib.import_module("hub.connection_sources")
    finally:
        try:
            sys.path.remove(source_text)
        except ValueError:
            pass

    for module in (metric_export, metric_novel, connection_sources):
        module_path = Path(module.__file__ or "").resolve(strict=True)
        if not module_path.is_relative_to(source):
            raise RuntimeError("loaded Hub metric module is outside the selected hub root")
    return (
        metric_export.export_metric_snapshot,
        metric_novel.collect_novel,
        connection_sources.SourceResolver,
    )


def export_snapshot(
    project_root: Path,
    hub_root: Path,
    *,
    clock: Callable[[], str] | None = None,
    registry_path: Path | None = None,
) -> dict:
    """Read declared metadata only and atomically replace ``.hub/status.json``."""
    export_metric_snapshot, collect_novel, source_resolver = _shared_hub_modules(
        hub_root
    )
    observed_at = (
        clock()
        if clock is not None
        else datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    )
    resolver = source_resolver(
        hub_root,
        registry_path=registry_path,
        clock=lambda: observed_at,
    )
    project = resolver.projects[PROJECT_ID]
    removed = (
        project.get("local_presence", {}).get("status") == "removed_local"
        or project.get("current_state_status") == "removed_local"
    )
    if (
        removed
        or project.get("connection_read_allowed", project.get("enabled")) is not True
        or project.get("access_profile") == "no_current_goal_access"
    ):
        raise ValueError("Hub registry does not authorize this project export")
    selected_root = project_root.expanduser().absolute()
    registered_root = Path(project["root_path"]).expanduser().absolute()
    if registered_root != selected_root:
        raise ValueError("project root does not match the selected Hub registry")
    if not selected_root.is_dir() or selected_root.is_symlink():
        raise ValueError("project root must be an existing ordinary directory")
    root = selected_root.resolve(strict=True)
    management = resolver.refresh(PROJECT_ID)
    if not management["success"]:
        raise ValueError("management source resolution failed; snapshot not exported")
    kwargs = {
        "exporter_id": EXPORTER_ID,
        "exporter_version": EXPORTER_VERSION,
        "management": management,
        "clock": lambda: observed_at,
    }
    return export_metric_snapshot(
        root,
        PROJECT_ID,
        {"business": collect_novel},
        **kwargs,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Export Light Novel metadata through the shared Hub snapshot writer"
    )
    parser.add_argument(
        "--hub-root",
        type=Path,
        required=True,
        help="explicit personal-control-hub checkout containing src/hub",
    )
    parser.add_argument("--project-root", type=Path, default=REPO_ROOT)
    args = parser.parse_args(argv)
    try:
        snapshot = export_snapshot(args.project_root, args.hub_root)
    except (ImportError, OSError, RuntimeError, TypeError, ValueError) as exc:
        print(f"hub metric export failed: {exc}", file=sys.stderr)
        return 2

    receipt = {
        "schema": "light_novel_hub_export_receipt_v1",
        "project_id": snapshot["project_id"],
        "snapshot_id": snapshot["snapshot_id"],
        "disposition": snapshot["disposition"],
        "metric_count": len(snapshot["metrics"]),
        "issue_count": len(snapshot["issues"]),
        "snapshot_path": ".hub/status.json",
    }
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
