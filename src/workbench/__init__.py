"""Workbench backend: multi-project manifests and active project selection."""

from workbench.project_registry import (
    ProjectManifest,
    get_active_project_id,
    list_project_manifests,
    resolve_active_manifest_path,
    seed_example_manifests,
    set_active_project_id,
)

__all__ = [
    "ProjectManifest",
    "get_active_project_id",
    "list_project_manifests",
    "resolve_active_manifest_path",
    "seed_example_manifests",
    "set_active_project_id",
]
