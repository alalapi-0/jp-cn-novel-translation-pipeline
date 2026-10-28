"""Multi-project manifest registry under workspace/manifests/."""

from __future__ import annotations

import json
import yaml
from contextvars import ContextVar
import hashlib
import re
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from workbench.project_id import (
    InvalidProjectIdError,
    is_history_project_id,
    is_test_project_id,
    project_list_category,
    validate_project_id,
)

MANIFESTS_DIR_NAME = "manifests"
WORKBENCH_STATE_FILE = "workbench_state.json"
LEGACY_MANIFEST_NAME = "project_manifest.json"
EXAMPLE_GLOB = "workbench_project.*.example.json"
_REFRESH_LOCK = threading.Lock()
_project_locks_guard = threading.Lock()
_project_locks: dict[str, threading.Lock] = {}


class ManifestWriteInProgressError(RuntimeError):
    """Raised when another request is already writing the same manifest."""


class UnsafeManifestPathError(RuntimeError):
    """Raised when project manifest path is outside workspace/manifests."""


class TestProjectDeletionUnavailableError(Exception):
    """Cross-file test project deletion is unavailable until it can be coordinated."""

    def __init__(self) -> None:
        super().__init__("测试项目删除暂不可用，项目及审核记录会保留")


class DuplicateSegmentIdError(ValueError):
    """Raised when a manifest cannot identify one unique segment by ID."""


class ApprovalIdentityConflictError(RuntimeError):
    """Raised when a formal approval compare-and-set cannot be applied."""

    def __init__(
        self,
        message: str,
        *,
        error_code: str,
        project_id: str,
        segment_id: str,
        current_identity: str | None = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.project_id = project_id
        self.segment_id = segment_id
        self.current_identity = current_identity


def _project_write_lock(project_id: str) -> threading.Lock:
    with _project_locks_guard:
        lock = _project_locks.get(project_id)
        if lock is None:
            lock = threading.Lock()
            _project_locks[project_id] = lock
        return lock


@dataclass(frozen=True)
class ProjectManifest:
    project_id: str
    name: str
    language_direction: str
    status: str
    chapters: int
    segments: tuple[dict[str, Any], ...]
    path: Path | None = None
    source_inventory: dict[str, Any] | None = None

    def to_summary(self) -> dict[str, Any]:
        return {
            "id": self.project_id,
            "project_id": self.project_id,
            "name": self.name,
            "direction": self.language_direction,
            "language_direction": self.language_direction,
            "status": self.status,
            "chapters": self.chapters,
            "is_test": is_test_project_id(self.project_id),
            "category": project_list_category(self.project_id),
        }

    def to_workbench_payload(self) -> dict[str, Any]:
        from workbench.review_state import (
            approval_identity,
            segment_id,
            segment_text,
        )

        segments = []
        for segment in self.segments:
            enriched = dict(segment)
            enriched["id"] = segment_id(segment)
            enriched["source"] = segment_text(segment, "source", "source_text")
            enriched["draft"] = segment_text(
                segment,
                "draft",
                "draft_text",
                "target_text",
                "translation",
            )
            enriched["approval_identity"] = approval_identity(
                project_id=self.project_id,
                language_direction=self.language_direction,
                segment=segment,
            )
            segments.append(enriched)
        return {
            "project": self.to_summary(),
            "segments": segments,
        }


def manifests_dir(repo_root: Path) -> Path:
    return repo_root / "workspace" / MANIFESTS_DIR_NAME


def workbench_state_path(repo_root: Path) -> Path:
    return repo_root / "workspace" / WORKBENCH_STATE_FILE


def examples_dir(repo_root: Path) -> Path:
    return repo_root / "data" / "examples"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"manifest must be a JSON object: {path}")
    return data


def _path_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _safe_manifest_path(repo_root: Path, manifest: ProjectManifest) -> Path:
    root = manifests_dir(repo_root)
    candidate = (manifest.path or (root / f"{manifest.project_id}.json")).resolve()
    if not _path_within(candidate, root):
        raise UnsafeManifestPathError(f"unsafe manifest path for {manifest.project_id}: {candidate}")
    if candidate.suffix != ".json":
        raise UnsafeManifestPathError(f"refuse non-json manifest path: {candidate}")
    return candidate


def _source_context_digest(data: dict[str, Any]) -> str:
    """Ordered source scope, independent of target text or saved review labels."""
    from workbench.review_state import segment_id, segment_text
    from translation.source_versions import review_dependencies, value_sha
    rows = []
    for item in data.get('segments') or []:
        if not isinstance(item, dict): continue
        source = segment_text(item, 'source', 'source_text')
        binding = review_dependencies({k:v for k,v in item.items() if k=='source_binding'},source)
        rows.append({'id':segment_id(item),'source_sha256':hashlib.sha256(source.encode()).hexdigest(),
                     'source_binding':binding.get('source_binding_sha256')})
    return value_sha({'direction':data.get('language_direction') or data.get('direction') or 'JP_TO_CN',
                      'source_inventory':data.get('source_inventory'),'ordered_sources':rows})


def parse_project_manifest(data: dict[str, Any], *, path: Path | None = None) -> ProjectManifest:
    project_id = str(data.get("project_id") or "").strip()
    if not project_id:
        raise ValueError("manifest missing project_id")
    name = str(data.get("name") or project_id)
    direction = str(data.get("language_direction") or data.get("direction") or "JP_TO_CN")
    status = str(data.get("status") or "unknown")
    chapters_raw = data.get("chapters", 0)
    try:
        chapters = int(chapters_raw)
    except (TypeError, ValueError):
        chapters = 0
    segments_raw = data.get("segments") or []
    if not isinstance(segments_raw, list):
        raise ValueError(f"segments must be a list for {project_id}")
    segments: list[dict[str, Any]] = []
    segment_ids: set[str] = set()
    from workbench.review_state import segment_id
    context_revision = data.get('source_context_revision')
    if context_revision is not None and context_revision != _source_context_digest(data):
        raise ValueError('manifest source context revision changed')

    from translation.source_versions import dependency_versions
    dependency_catalog = data.get('dependency_versions')
    if dependency_catalog is not None:
        dependency_catalog = dependency_versions(dependency_catalog)
    for item in segments_raw:
        if isinstance(item, dict):
            item = dict(item)
            if 'dependency_keys' in item:
                keys=item['dependency_keys']
                if (not isinstance(keys,list) or len(keys)>256
                        or any(not isinstance(k,str) for k in keys)
                        or len(set(keys))!=len(keys) or dependency_catalog is None
                        or any(k not in dependency_catalog for k in keys)):
                    raise ValueError('missing or ambiguous selected dependency versions')
                item['dependency_versions']={k:dependency_catalog[k] for k in keys}
            elif 'dependency_versions' in item:
                item['dependency_versions']=dependency_versions(item['dependency_versions'])
            if context_revision is not None: item['source_context_revision'] = context_revision
            item_id = segment_id(item)
            if item_id and item_id in segment_ids:
                raise DuplicateSegmentIdError(
                    f"duplicate segment_id in project {project_id}: {item_id}"
                )
            if item_id:
                segment_ids.add(item_id)
            segments.append(item)
    return ProjectManifest(
        project_id=project_id,
        name=name,
        language_direction=direction,
        status=status,
        chapters=chapters,
        segments=tuple(segments),
        path=path,
        source_inventory=data.get("source_inventory") if isinstance(data.get("source_inventory"), dict) else None,
    )


def _source_inventory_digest(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode()).hexdigest()


def build_source_inventory(segments: list[dict[str, Any]], *, language_direction: str,
                           origin: str = "project_source_import") -> dict[str, Any]:
    """Capture the imported source scope, independent of generated target rows."""
    from workbench.review_state import segment_id, segment_text
    entries = []; seen = set(); modern = any(row.get("source_binding") is not None for row in segments if isinstance(row,dict))
    for row in segments:
        if not isinstance(row, dict):
            raise ValueError("source import contains a non-object segment")
        sid = segment_id(row); source = segment_text(row, "source", "source_text")
        if sid in seen:
            raise DuplicateSegmentIdError(f"duplicate source import ID: {sid}")
        if not sid or not source.strip():
            raise ValueError("source import requires unique IDs and non-empty source")
        seen.add(sid)
        entry={"segment_id":sid,"source_sha256":hashlib.sha256(source.encode()).hexdigest()}
        if modern:
            from translation.source_versions import validate_source_binding
            binding=validate_source_binding(row.get('source_binding'),source)
            entry.update(chapter_id=binding['chapter_id'],source_revision=binding['source_revision'],source_binding_sha256=binding['binding_sha256'])
        entries.append(entry)
    payload = {"schema": "workbench-source-inventory/2" if modern else "workbench-source-inventory/1", "language_direction": language_direction,
               "origin": origin, "entries": entries}
    value = {**payload, "inventory_sha256": _source_inventory_digest(payload)}
    validated_source_entries(value, language_direction=language_direction)
    return value


def validated_source_entries(value: Any, *, language_direction: str) -> list[dict[str, str]]:
    """Validate the frozen source descriptor; never reconstruct it from targets."""
    fields = {"schema", "language_direction", "origin", "entries", "inventory_sha256"}
    if (not isinstance(value, dict) or set(value) != fields
            or not isinstance(language_direction, str) or language_direction.upper() not in {"JP_TO_CN", "CN_TO_JP"}
            or value["schema"] not in {"workbench-source-inventory/1","workbench-source-inventory/2"}
            or value["language_direction"] != language_direction
            or not isinstance(value["origin"], str) or not value["origin"]
            or not isinstance(value["entries"], list)):
        raise ValueError("missing or invalid source inventory")
    seen = set()
    modern=value['schema']=='workbench-source-inventory/2'
    entry_fields={'segment_id','source_sha256'} | ({'chapter_id','source_revision','source_binding_sha256'} if modern else set())
    for row in value["entries"]:
        if (not isinstance(row, dict) or set(row) != entry_fields
                or not isinstance(row["segment_id"], str) or not row["segment_id"].strip()
                or row["segment_id"] in seen
                or not isinstance(row["source_sha256"], str)
                or not re.fullmatch(r"[0-9a-f]{64}", row["source_sha256"])):
            raise ValueError("invalid or duplicate source inventory entry")
        if modern and (not isinstance(row['chapter_id'],str) or not row['chapter_id'].strip()
                or any(not isinstance(row[k],str) or not re.fullmatch('[0-9a-f]{64}',row[k]) for k in ('source_revision','source_binding_sha256'))):
            raise ValueError('invalid versioned source inventory entry')
        seen.add(row["segment_id"])
    payload = {k: value[k] for k in fields if k != "inventory_sha256"}
    if _source_inventory_digest(payload) != value["inventory_sha256"]:
        raise ValueError("source inventory identity changed")
    return value["entries"]


_dependency_reads = ContextVar('manifest_dependency_reads', default=())


def _resolve_manifest_dependencies(repo_root, data):
    """Resolve only explicitly selected entries in the existing local stores.

    Pinned PSH bundle versions stay in the manifest; no sibling store is opened.
    Missing/withdrawn/cyclic dependencies change identity and withhold TM reuse.
    """
    from translation.source_versions import value_sha, dependency_versions
    raw_sources=data.get('dependency_sources',{})
    if raw_sources is None: raw_sources={}
    sources=raw_sources if isinstance(raw_sources,dict) and len(raw_sources)<=256 else {}
    raw_catalog=data.get('dependency_versions',{})
    raw_catalog=raw_catalog if isinstance(raw_catalog,dict) and len(raw_catalog)<=256 else {}
    catalog={};errors={};selected=set();projected=[]
    for key,value in raw_catalog.items():
        try: catalog.update(dependency_versions({key:value}))
        except ValueError: errors[key]='unavailable'
    for original in data.get('segments') or []:
        if not isinstance(original,dict):
            projected.append(original);continue
        row=dict(original);row.pop('dependency_resolution_errors',None)
        if 'dependency_keys' in row:
            keys=row['dependency_keys']
            try:
                if (not isinstance(keys,list) or len(keys)>256
                        or any(not isinstance(k,str) for k in keys) or len(set(keys))!=len(keys)):
                    raise ValueError('invalid selection')
                dependency_versions({key:'0'*64 for key in keys})
            except ValueError:
                row.pop('dependency_keys',None)
                row['dependency_versions']={'unavailable:selection':value_sha(keys)}
                row['dependency_resolution_errors']=['unavailable:selection']
            else:selected.update(keys)
        elif 'dependency_versions' in row:
            try: row['dependency_versions']=dependency_versions(row['dependency_versions'])
            except ValueError:
                row['dependency_versions']={'unavailable:direct':value_sha(row['dependency_versions'])}
                row['dependency_resolution_errors']=['unavailable:direct']
        projected.append(row)
    for key in selected:
        if key not in catalog or not isinstance(raw_sources,dict):
            catalog[key]=value_sha({'dependency':key,'unavailable':True})
            errors[key]='unavailable'
    # Invalid unused catalog keys cannot poison independent rows. Selected aliases
    # with typed live sources can recover through actual current-source validation.
    for key in list(errors):
        if key not in selected: errors.pop(key)
    for key in selected & sources.keys(): errors.pop(key,None)
    for key in sorted(selected & sources.keys()):
        descriptor=sources[key];identity=(str(repo_root.resolve()),key,value_sha(descriptor))
        stack=_dependency_reads.get();token=None
        try:
            if identity in stack: raise ValueError('cyclic dependency')
            token=_dependency_reads.set((*stack,identity))
            if not isinstance(descriptor,dict): raise ValueError('invalid dependency descriptor')
            kind=descriptor.get('kind')
            if kind in {'glossary','character'}:
                if set(descriptor)!={'kind','entry'} or not isinstance(descriptor['entry'],str):
                    raise ValueError('invalid config dependency descriptor')
                name='glossary.yaml' if kind=='glossary' else 'character_profile.yaml'
                from assets.translation_memory import _read_repo_file
                source_bytes=_read_repo_file(repo_root,Path('workspace/configs')/name)
                doc=yaml.safe_load(source_bytes);field='entries' if kind=='glossary' else 'characters'
                idfield='source_term' if kind=='glossary' else 'name'
                rows=[r for r in (doc.get(field) or []) if isinstance(r,dict) and r.get(idfield)==descriptor['entry']]
                if len(rows)!=1: raise ValueError('missing or ambiguous config dependency')
                row=rows[0]
                if row.get('deleted') or row.get('withdrawn'): raise ValueError('withdrawn config dependency')
                catalog[key]=value_sha(row)
            elif kind=='tm_pair':
                if set(descriptor)!={'kind','asset','pair_id'}: raise ValueError('invalid TM dependency descriptor')
                name=descriptor['asset'];pid=descriptor['pair_id']
                if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}\.json',name):
                    raise ValueError('invalid TM asset name')
                if not isinstance(pid,str) or not re.fullmatch(r'[0-9a-f]{64}',pid): raise ValueError('invalid TM pair ID')
                relative=Path('workspace/assets/translation_memory')/name
                path=repo_root/relative
                from assets.translation_memory import _current_asset_context, _read_repo_file
                source_bytes=_read_repo_file(repo_root,relative)
                doc=_current_asset_context(path,repo_root=repo_root,source_bytes=source_bytes)
                rows=[r for r in doc.get('translation_pairs',[]) if r['pair_id']==pid]
                if len(rows)!=1: raise ValueError('missing or stale TM dependency')
                catalog[key]=rows[0]['version_sha256']
            else: raise ValueError('unknown dependency source')
        except (OSError,ValueError,KeyError,TypeError,AttributeError,yaml.YAMLError):
            catalog[key]=value_sha({'dependency':key,'unavailable':True})
            errors[key]='unavailable'  # Never retain private exception bodies.
        finally:
            if token is not None: _dependency_reads.reset(token)
    result={**data,'dependency_versions':catalog,'segments':[]}
    for row in projected:
        if isinstance(row,dict):
            blocked=sorted(set(row.get('dependency_keys',[])) & errors.keys())
            blocked=sorted(set(blocked+row.get('dependency_resolution_errors',[])))
            if blocked: row['dependency_resolution_errors']=blocked
        result['segments'].append(row)
    return result


def load_project_manifest(path: Path, *, source_bytes: bytes | None = None) -> ProjectManifest:
    if source_bytes is None:
        data=_load_json(path)
    else:
        data=json.loads(source_bytes.decode('utf-8'))
        if not isinstance(data,dict):raise ValueError('manifest must be a JSON object')
    if path.parent.name=='manifests' and path.parent.parent.name=='workspace':
        data=_resolve_manifest_dependencies(path.parent.parent.parent,data)
    return parse_project_manifest(data, path=path)


def _manifest_project_id(path: Path) -> str | None:
    try:
        return parse_project_manifest(_load_json(path)).project_id
    except (OSError, json.JSONDecodeError, ValueError):
        return None


def list_project_manifest_paths(repo_root: Path) -> list[Path]:
    root = manifests_dir(repo_root)
    if not root.is_dir():
        return []
    paths = sorted(
        p for p in root.glob("*.json") if p.is_file() and p.name != LEGACY_MANIFEST_NAME
    )
    legacy = root / LEGACY_MANIFEST_NAME
    if legacy.is_file():
        legacy_id = _manifest_project_id(legacy)
        named_ids = {_manifest_project_id(p) for p in paths}
        named_ids.discard(None)
        if legacy_id is None or legacy_id not in named_ids:
            paths.append(legacy)
    return paths


def list_project_manifests(
    repo_root: Path,
    *,
    include_test: bool = True,
    include_history: bool = True,
) -> list[ProjectManifest]:
    manifests: list[ProjectManifest] = []
    seen: set[str] = set()
    for path in list_project_manifest_paths(repo_root):
        try:
            manifest = load_project_manifest(path)
        except DuplicateSegmentIdError:
            raise
        except (OSError, json.JSONDecodeError, ValueError):
            continue
        if manifest.project_id in seen:
            continue
        seen.add(manifest.project_id)
        if not include_test and is_test_project_id(manifest.project_id):
            continue
        if not include_history and is_history_project_id(manifest.project_id):
            continue
        manifests.append(manifest)
    manifests.sort(key=lambda m: m.project_id)
    return manifests


def _read_workbench_state(repo_root: Path) -> dict[str, Any]:
    path = workbench_state_path(repo_root)
    if not path.is_file():
        return {}
    try:
        data = _load_json(path)
    except (OSError, json.JSONDecodeError, ValueError):
        return {}
    return data


def get_active_project_id(repo_root: Path) -> str | None:
    state = _read_workbench_state(repo_root)
    active = str(state.get("active_project_id") or "").strip()
    if active:
        known = {m.project_id for m in list_project_manifests(repo_root)}
        if active in known:
            return active
    manifests = list_project_manifests(repo_root)
    if manifests:
        return manifests[0].project_id
    return None


def set_active_project_id(repo_root: Path, project_id: str) -> ProjectManifest:
    project_id = validate_project_id(project_id)
    match = next((m for m in list_project_manifests(repo_root) if m.project_id == project_id), None)
    if match is None:
        raise KeyError(f"unknown project_id: {project_id}")
    state_path = workbench_state_path(repo_root)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "active_project_id": project_id,
        "updated_at": utc_now(),
    }
    state_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return match


def get_project_manifest(repo_root: Path, project_id: str) -> ProjectManifest | None:
    try:
        project_id = validate_project_id(project_id)
    except InvalidProjectIdError:
        return None
    for manifest in list_project_manifests(repo_root):
        if manifest.project_id == project_id:
            return manifest
    return None


def resolve_active_manifest_path(repo_root: Path) -> Path | None:
    active_id = get_active_project_id(repo_root)
    if not active_id:
        legacy = manifests_dir(repo_root) / LEGACY_MANIFEST_NAME
        return legacy if legacy.is_file() else None
    for path in list_project_manifest_paths(repo_root):
        try:
            manifest = load_project_manifest(path)
        except (OSError, json.JSONDecodeError, ValueError):
            continue
        if manifest.project_id == active_id:
            return path
    legacy = manifests_dir(repo_root) / LEGACY_MANIFEST_NAME
    return legacy if legacy.is_file() else None


def refresh_example_manifests(repo_root: Path) -> list[Path]:
    """Copy committed example manifests into workspace/manifests (overwrite named files)."""
    with _REFRESH_LOCK:
        target_dir = manifests_dir(repo_root)
        target_dir.mkdir(parents=True, exist_ok=True)
        written: list[Path] = []
        for example in sorted(examples_dir(repo_root).glob(EXAMPLE_GLOB)):
            data = _load_json(example)
            data["source_inventory"] = build_source_inventory(data.get("segments", []),
                language_direction=data.get("language_direction", "JP_TO_CN"), origin="synthetic_example_import")
            manifest = save_project_manifest(repo_root, data)
            assert manifest.path is not None
            written.append(manifest.path)
        return written


def _save_project_manifest_unlocked(
    repo_root: Path,
    data: dict[str, Any],
) -> ProjectManifest:
    manifest = parse_project_manifest(data)
    target_dir = manifests_dir(repo_root)
    target_dir.mkdir(parents=True, exist_ok=True)
    dest = target_dir / f"{manifest.project_id}.json"
    if dest.exists():
        previous = _load_json(dest)
        current_source = _source_context_digest(data)
        if previous.get('source_context_revision') is not None or _source_context_digest(previous) != current_source:
            data = {**data,'source_context_revision':current_source}
            manifest = parse_project_manifest(data)
    tmp = dest.with_name(f"{dest.name}.{uuid.uuid4().hex}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(dest)
    return load_project_manifest(dest)


def save_project_manifest(repo_root: Path, data: dict[str, Any]) -> ProjectManifest:
    manifest = parse_project_manifest(data)
    lock = _project_write_lock(manifest.project_id)
    if not lock.acquire(blocking=False):
        raise ManifestWriteInProgressError(
            f"manifest write in progress: {manifest.project_id}"
        )
    try:
        return _save_project_manifest_unlocked(repo_root, data)
    finally:
        lock.release()


def create_project_manifest(
    repo_root: Path,
    *,
    project_id: str,
    name: str,
    language_direction: str,
    segments: list[dict[str, Any]] | None = None,
) -> ProjectManifest:
    project_id = validate_project_id(project_id)
    lock = _project_write_lock(project_id)
    if not lock.acquire(blocking=False):
        raise ManifestWriteInProgressError(f"manifest write in progress: {project_id}")
    try:
        if get_project_manifest(repo_root, project_id) is not None:
            raise ValueError(f"project already exists: {project_id}")
        payload = {
            "project_id": project_id,
            "name": name.strip() or project_id,
            "language_direction": language_direction.strip() or "JP_TO_CN",
            "status": "draft_pending",
            "chapters": 1,
            "segments": segments or [],
            "source_inventory": build_source_inventory(segments or [],
                language_direction=language_direction.strip() or "JP_TO_CN", origin="project_creation"),
        }
        return _save_project_manifest_unlocked(repo_root, payload)
    finally:
        lock.release()


def update_project_segments(
    repo_root: Path,
    project_id: str,
    segments: list[dict[str, Any]],
    *,
    status: str | None = None,
    source_segments: list[dict[str, Any]] | None = None,
) -> ProjectManifest:
    project_id = validate_project_id(project_id)
    lock = _project_write_lock(project_id)
    if not lock.acquire(blocking=False):
        raise ManifestWriteInProgressError(f"manifest write in progress: {project_id}")
    try:
        manifest = get_project_manifest(repo_root, project_id)
        if manifest is None:
            raise KeyError(f"unknown project_id: {project_id}")
        path = manifest.path or (manifests_dir(repo_root) / f"{project_id}.json")
        data = _load_json(path)
        data["segments"] = segments
        if source_segments is not None:
            data["source_inventory"] = build_source_inventory(source_segments,
                language_direction=manifest.language_direction)
        if status:
            data["status"] = status
        if data.get('source_context_revision') is not None:
            data['source_context_revision'] = _source_context_digest(data)
        data["chapters"] = max(int(data.get("chapters") or 1), 1)
        return _save_project_manifest_unlocked(repo_root, data)
    finally:
        lock.release()


def patch_project_review_state_cas(
    repo_root: Path,
    project_id: str,
    *,
    segments: dict[str, Any] | None = None,
    issues: dict[str, Any] | None = None,
    decision_actor: Any = None,
    _expected_review_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Atomically validate formal approvals against the locked current manifest."""
    from workbench.review_state import (
        approval_identity,
        has_approvable_content,
        patch_project_review_state,
        segment_id,
        decision_provenance,
        UNTRUSTED_APPROVAL_FIELDS,
    )

    project_id = validate_project_id(project_id)
    lock = _project_write_lock(project_id)
    if not lock.acquire(blocking=False):
        raise ManifestWriteInProgressError(f"manifest write in progress: {project_id}")
    try:
        manifest = get_project_manifest(repo_root, project_id)
        if manifest is None:
            raise KeyError(f"unknown project_id: {project_id}")

        current: dict[str, tuple[dict[str, Any], str]] = {}
        for segment in manifest.segments:
            current_segment_id = segment_id(segment)
            if not current_segment_id:
                continue
            current[current_segment_id] = (
                segment,
                approval_identity(
                    project_id=project_id,
                    language_direction=manifest.language_direction,
                    segment=segment,
                ),
            )

        sanitized_segments: dict[str, Any] = {}
        for raw_segment_id, raw_entry in (segments or {}).items():
            patch_segment_id = str(raw_segment_id).strip()
            if not isinstance(raw_entry, dict):
                continue
            current_item = current.get(patch_segment_id)
            if current_item is None:
                raise ApprovalIdentityConflictError(
                    f"segment is absent from the current manifest: {patch_segment_id}",
                    error_code="approval_identity_stale",
                    project_id=project_id,
                    segment_id=patch_segment_id,
                )
            current_segment, current_identity = current_item
            status = str(raw_entry.get("status") or "").strip().lower()
            sanitized = {
                key: value
                for key, value in raw_entry.items()
                if key not in UNTRUSTED_APPROVAL_FIELDS
            }
            if "status" in raw_entry:
                if status not in {"approved", "rejected", "pending"}:
                    raise ApprovalIdentityConflictError(
                        "unsupported segment decision; human/final issuance is unavailable",
                        error_code="approval_provenance_invalid", project_id=project_id,
                        segment_id=patch_segment_id,
                    )
                expected = raw_entry.get("expected_identity")
                if expected is None or expected == "":
                    raise ApprovalIdentityConflictError(
                        "status mutation requires expected_identity",
                        error_code="approval_identity_required",
                        project_id=project_id,
                        segment_id=patch_segment_id,
                        current_identity=current_identity,
                    )
                if not (
                    isinstance(expected, str)
                    and expected.startswith("sha256:")
                    and len(expected) == 71
                    and all(ch in "0123456789abcdef" for ch in expected[7:])
                ):
                    raise ApprovalIdentityConflictError(
                        "expected_identity must be a sha256 identity string",
                        error_code="approval_identity_invalid",
                        project_id=project_id,
                        segment_id=patch_segment_id,
                        current_identity=current_identity,
                    )
                if expected != current_identity:
                    raise ApprovalIdentityConflictError(
                        "expected_identity does not match the current segment content",
                        error_code="approval_identity_stale",
                        project_id=project_id,
                        segment_id=patch_segment_id,
                        current_identity=current_identity,
                    )
                if status == "approved" and not has_approvable_content(current_segment):
                    raise ApprovalIdentityConflictError(
                        "formal approval requires non-empty source and target content",
                        error_code="approval_identity_invalid",
                        project_id=project_id,
                        segment_id=patch_segment_id,
                        current_identity=current_identity,
                    )
                sanitized["approval_identity"] = current_identity
                sanitized["decision_provenance"] = decision_provenance(current_identity, status, decision_actor)
            sanitized_segments[patch_segment_id] = sanitized

        return patch_project_review_state(
            repo_root,
            project_id,
            segments=sanitized_segments or None,
            issues={key: {k: v for k, v in entry.items() if k not in UNTRUSTED_APPROVAL_FIELDS}
                    for key, entry in (issues or {}).items() if isinstance(entry, dict)} or None,
            _expected_review_state=_expected_review_state,
        )
    finally:
        lock.release()


def get_project_review_state_payload(repo_root: Path, project_id: str) -> dict[str, Any]:
    """Expose interpretation alongside unchanged raw legacy values."""
    from workbench.review_state import approval_identity, get_project_review_state, review_decision_summary, segment_id
    manifest = get_project_manifest(repo_root, project_id)
    if manifest is None:
        raise KeyError(project_id)
    state = get_project_review_state(repo_root, project_id)
    review_segments = state.get("segments")
    if not isinstance(review_segments, dict):
        review_segments = {}
    decisions = {}
    for segment in manifest.segments:
        sid = segment_id(segment)
        identity = approval_identity(project_id=project_id, language_direction=manifest.language_direction, segment=segment)
        decisions[sid] = review_decision_summary(review_segments.get(sid), identity, segment=segment)
    return {**state, "decision_summaries": decisions}


def update_project_status(
    repo_root: Path,
    project_id: str,
    *,
    status: str,
) -> ProjectManifest:
    project_id = validate_project_id(project_id)
    next_status = str(status or "").strip()
    if not next_status:
        raise ValueError("status is required")
    lock = _project_write_lock(project_id)
    if not lock.acquire(blocking=False):
        raise ManifestWriteInProgressError(f"manifest write in progress: {project_id}")
    try:
        manifest = get_project_manifest(repo_root, project_id)
        if manifest is None:
            raise KeyError(f"unknown project_id: {project_id}")
        path = _safe_manifest_path(repo_root, manifest)
        data = _load_json(path)
        data["status"] = next_status
        return _save_project_manifest_unlocked(repo_root, data)
    finally:
        lock.release()


def archive_project(repo_root: Path, project_id: str) -> ProjectManifest:
    return update_project_status(repo_root, project_id, status="archived")


def retry_project(repo_root: Path, project_id: str) -> ProjectManifest:
    from workbench.generation_jobs import clear_project_generation_job

    manifest = update_project_status(repo_root, project_id, status="draft_pending")
    clear_project_generation_job(repo_root, project_id)
    return manifest


def delete_test_project(repo_root: Path, project_id: str) -> dict[str, Any]:
    # Deleting the manifest and review state is not a coordinated transaction.
    # Keep both until a separately reviewed deletion mechanism is available.
    raise TestProjectDeletionUnavailableError()


def seed_example_manifests(repo_root: Path, *, force: bool = False) -> list[Path]:
    """Copy committed example manifests into workspace/manifests when empty."""
    target_dir = manifests_dir(repo_root)
    target_dir.mkdir(parents=True, exist_ok=True)
    existing = [p for p in target_dir.glob("*.json") if p.name != LEGACY_MANIFEST_NAME]
    if existing and not force:
        return existing
    example_paths = sorted(examples_dir(repo_root).glob(EXAMPLE_GLOB))
    written: list[Path] = []
    for example in example_paths:
        data = _load_json(example)
        data["source_inventory"] = build_source_inventory(data.get("segments", []),
            language_direction=data.get("language_direction", "JP_TO_CN"), origin="synthetic_example_import")
        project_id = str(data.get("project_id") or example.stem)
        dest = target_dir / f"{project_id}.json"
        if dest.is_file() and not force:
            written.append(dest)
            continue
        manifest = save_project_manifest(repo_root, data)
        assert manifest.path is not None
        written.append(manifest.path)
    active = get_active_project_id(repo_root)
    if not active and written:
        first = load_project_manifest(written[0])
        set_active_project_id(repo_root, first.project_id)
    return sorted(written)
