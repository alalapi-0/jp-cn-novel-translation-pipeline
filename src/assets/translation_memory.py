"""Build reusable translation-memory assets from approved translation work."""

from __future__ import annotations

import json
import os
import re
import stat
import sys
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal

from providers.cost_guard import CostGuard, CostGuardConfig
from providers.registry import ProviderMode, get_provider

AssetBuildMode = Literal["agent", "external_api"]
AssetStatusMode = Literal["approved", "translated"]

APPROVED_STATUSES = {"approved"}
TRANSLATED_STATUSES = {
    "approved",
    "machine_translated",
    "refined",
    "translated",
    "completed",
    "review_pending",
}
_KATAKANA_RE = re.compile(r"[ァ-ヴー]{3,}")
_BRACKET_RE = re.compile(r"【([^】]{1,32})】")
_CJK_TOKEN_RE = re.compile(r"[\u4e00-\u9fff]{2,8}")


class ExternalAssetExtractionUnavailable(RuntimeError):
    """Raised when external-api asset mode is not explicitly available."""


@dataclass(frozen=True)
class TranslationPair:
    segment_id: str
    source_text: str
    target_text: str
    status: str
    source_ref: str
    chapter_id: str = ""
    acceptance_provenance: dict[str, Any] | None = None
    dependencies: dict[str, Any] = field(default_factory=dict)
    qualification: str = "unreviewed_translation"

    def to_dict(self) -> dict[str, Any]:
        from translation.source_versions import text_sha, value_sha
        row = {
            "segment_id": self.segment_id,
            "source_text": self.source_text,
            "target_text": self.target_text,
            "status": self.status,
            "source_ref": self.source_ref,
            "chapter_id": self.chapter_id,
            "acceptance_provenance": self.acceptance_provenance,
            "qualification": self.qualification,
            "dependencies": self.dependencies,
            "source_sha256": text_sha(self.source_text),
            "target_sha256": text_sha(self.target_text),
        }
        row["pair_id"] = value_sha({k:row[k] for k in ("source_ref","chapter_id","segment_id")})
        row["version_sha256"] = value_sha(row)
        return row


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_stem(value: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9_-]+", "_", value.strip())[:80].strip("_")
    return stem or "translation_assets"


def _status_allowed(status: str, status_mode: AssetStatusMode) -> bool:
    normalized = str(status or "").strip().lower()
    allowed = APPROVED_STATUSES if status_mode == "approved" else TRANSLATED_STATUSES
    return normalized in allowed


def _segment_text(seg: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = seg.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _open_at2(root_fd: int, relative: Path, *, resolve: int) -> int:
    """Use Linux's atomic path resolution; unsupported hosts fail closed."""
    import ctypes
    import errno
    import platform
    if sys.platform != "linux" or platform.machine() != "x86_64":
        raise ValueError("secure direct source reads are unavailable on this host")

    class OpenHow(ctypes.Structure):
        _fields_ = [("flags", ctypes.c_uint64), ("mode", ctypes.c_uint64), ("resolve", ctypes.c_uint64)]

    # Linux UAPI: __NR_openat2=437 on x86_64.
    how = OpenHow(os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK, 0, resolve)
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        syscall = libc.syscall
    except (OSError, AttributeError):
        raise ValueError("secure direct source reads are unavailable on this host") from None
    syscall.restype = ctypes.c_long
    result = syscall(ctypes.c_long(437), ctypes.c_int(root_fd), ctypes.c_char_p(os.fsencode(relative)),
                     ctypes.byref(how), ctypes.c_size_t(ctypes.sizeof(how)))
    if result < 0:
        if ctypes.get_errno() == errno.ENOENT:
            raise FileNotFoundError("direct source is unavailable")
        raise ValueError("direct source path is unsafe or unavailable")
    return int(result)


def _open_beneath(root_fd: int, relative: Path) -> int:
    # BENEATH, NO_SYMLINKS, NO_MAGICLINKS and NO_XDEV.
    return _open_at2(root_fd, relative, resolve=0x0F)


def _read_repo_file(repo_root: Path, relative: Path) -> bytes:
    """Open one direct repository path atomically beneath the trusted root.

    This protects the direct file read only; dependency resolution has its own
    separate boundary and is not certified by this check.
    """
    if (relative.is_absolute() or not relative.parts
            or any(part in {"", ".", ".."} for part in relative.parts)):
        raise ValueError("invalid repository-relative source path")
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise ValueError("secure repository reads are unavailable")
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    root_fd = None
    file_fd = None
    try:
        root_fd = os.open(Path(repo_root).resolve(strict=True), directory_flags)
        file_fd = _open_beneath(root_fd, relative)
        before = os.fstat(file_fd)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise ValueError("direct source is not a uniquely linked regular file")
        chunks = []
        while True:
            chunk = os.read(file_fd, 65536)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(file_fd)
        identity = lambda value: (value.st_dev, value.st_ino, value.st_mode, value.st_nlink, value.st_size,
                                  value.st_mtime_ns, value.st_ctime_ns)
        if identity(before) != identity(after):
            raise ValueError("direct source changed during read")
        content = b"".join(chunks)
        if len(content) != before.st_size:
            raise ValueError("direct source changed during read")
        return content
    except FileNotFoundError:
        raise
    except OSError:
        raise ValueError("direct source path is unavailable or linked") from None
    finally:
        pending = sys.exc_info()[1]
        failures = []
        for fd in (file_fd, root_fd):
            if fd is not None:
                try:
                    os.close(fd)
                except OSError as error:
                    failures.append(error)
        if failures:
            if pending is not None:
                raise BaseExceptionGroup("direct source read and cleanup failed", [pending, *failures]) from None
            if len(failures) == 1:
                raise failures[0]
            raise ExceptionGroup("direct source cleanup failed", failures)


def _collect_manifest_pairs(
    repo_root: Path,
    project_id: str,
    *,
    status_mode: AssetStatusMode,
) -> tuple[list[TranslationPair], str]:
    from workbench.project_registry import load_project_manifest
    from workbench.project_id import validate_project_id
    from workbench.review_state import (
        approval_identity,
        get_project_review_state,
        is_formally_approved,
        segment_id,
        segment_text,
    )

    from translation.source_versions import review_dependencies
    project_id=validate_project_id(project_id)
    root=repo_root/'workspace/manifests';path=root/f'{project_id}.json'
    try:
        source_bytes=_read_repo_file(repo_root,Path('workspace/manifests')/f'{project_id}.json')
    except FileNotFoundError:
        raise KeyError(f"unknown project_id: {project_id}") from None
    manifest=load_project_manifest(path,source_bytes=source_bytes)
    if manifest.project_id!=project_id:
        raise ValueError('translation memory manifest identity differs')
    review_state = get_project_review_state(repo_root, project_id)
    review_segments = review_state.get("segments") if isinstance(review_state, dict) else {}
    if not isinstance(review_segments, dict):
        review_segments = {}

    pairs: list[TranslationPair] = []
    for seg in manifest.segments:
        if seg.get("dependency_resolution_errors"):
            continue
        seg_id = segment_id(seg)
        state_entry = review_segments.get(seg_id, {}) if seg_id else {}
        status = str(
            (state_entry.get("status") if isinstance(state_entry, dict) else None)
            or seg.get("status")
            or "pending"
        ).strip().lower()
        current_identity = approval_identity(
            project_id=manifest.project_id,
            language_direction=manifest.language_direction,
            segment=seg,
        )
        if status_mode == "approved":
            if not is_formally_approved(
                state_entry,
                current_identity,
                segment=seg,
            ):
                continue
            status = "approved"
        elif not _status_allowed(status, status_mode):
            continue
        source = segment_text(seg, "source", "source_text")
        target = segment_text(seg, "draft", "draft_text", "target_text", "translation")
        if source and target:
            pairs.append(
                TranslationPair(
                    segment_id=seg_id,
                    source_text=source,
                    target_text=target,
                    status=status,
                    source_ref=f"manifest:{project_id}",
                    chapter_id=str(seg.get("chapter") or ""),
                    acceptance_provenance=state_entry.get("decision_provenance") if status_mode == "approved" else None,
                    dependencies=review_dependencies(seg, source),
                    qualification="nonhuman_candidate" if status_mode == "approved" else "unreviewed_translation",
                )
            )
    return pairs, manifest.language_direction


def _read_source_run(repo_root: Path, source_run: str) -> tuple[Path, bytes]:
    if type(source_run) is not str or not source_run or '\x00' in source_run:
        raise ValueError('invalid translation memory source-run reference')
    relative=Path(source_run)
    if relative.is_absolute():
        try:
            relative=relative.relative_to(Path(os.path.abspath(repo_root)))
        except ValueError:
            raise ValueError('translation memory source run outside direct roots') from None
    if not relative.parts or any(part in {'.','..'} for part in relative.parts):
        raise ValueError('invalid translation memory source-run reference')
    runs=Path('workspace/runs');diagnostics=Path('workspace/diagnostics/real_api_runs')
    if len(relative.parts)==1:
        candidates=[runs/relative,diagnostics/relative/'workspace/runs'/relative]
    elif relative.parts[:len(runs.parts)]==runs.parts or relative.parts[:len(diagnostics.parts)]==diagnostics.parts:
        candidates=[relative]
    else:
        raise ValueError('translation memory source run outside direct roots')
    for candidate in candidates:
        try:
            return repo_root/candidate,_read_repo_file(repo_root,candidate/'segments.json')
        except FileNotFoundError:
            continue
    raise FileNotFoundError('translation memory source run unavailable')


def _chapter_key(value):
    text=str(value)
    match=re.fullmatch(r'(?:ch-)?0*(\d+)',text,re.IGNORECASE)
    return str(int(match.group(1))) if match else text


def _collect_run_pairs(
    repo_root: Path,
    source_run: str,
    *,
    status_mode: AssetStatusMode,
) -> tuple[list[TranslationPair], str]:
    run_root,source_bytes = _read_source_run(repo_root, source_run)
    doc = json.loads(source_bytes.decode('utf-8'))
    pairs: list[TranslationPair] = []
    from translation.source_versions import review_dependencies
    # Both entry routes require the same current Workbench/CAS evidence. A run's
    # approved label alone remains readable data, never an acceptance authority.
    accepted = []
    if status_mode == "approved":
        project_id = doc.get('project_id')
        if not isinstance(project_id, str) or not project_id:
            return pairs, str(doc.get("language_direction") or "JP_TO_CN")
        accepted, direction = _collect_manifest_pairs(repo_root, project_id, status_mode='approved')
        if direction != str(doc.get('language_direction') or 'JP_TO_CN'):
            return [], direction
    from workbench.project_registry import _resolve_manifest_dependencies
    from translation.source_versions import dependency_versions
    flattened=[row for ch in doc.get('chapters') or [] for row in ch.get('segments') or [] if isinstance(row,dict)]
    resolved=_resolve_manifest_dependencies(repo_root,{**doc,'segments':flattened})
    rows=iter(resolved['segments'])
    catalog=dependency_versions(resolved.get('dependency_versions',{}))
    for ch in doc.get("chapters") or []:
        chapter_id = str(ch.get("chapter_id") or "")
        for seg in ch.get("segments") or []:
            if not isinstance(seg, dict):
                continue
            seg=dict(next(rows))
            if seg.get('dependency_resolution_errors'): continue
            if 'dependency_keys' in seg:
                keys=seg['dependency_keys']
                if (not isinstance(keys,list) or any(not isinstance(k,str) for k in keys)
                        or len(set(keys))!=len(keys) or any(k not in catalog for k in keys)):
                    raise ValueError('missing or ambiguous run dependency versions')
                seg['dependency_versions']={k:catalog[k] for k in keys}
            status = str(seg.get("status") or "").strip().lower()
            if not _status_allowed(status, "translated"):
                continue
            source = _segment_text(seg, "source_text", "source")
            target = _segment_text(seg, "draft", "draft_text", "target_text", "translation")
            seg_id = _segment_text(seg, "segment_id", "id")
            if source and target:
                deps=review_dependencies(seg, source)
                if status_mode == 'approved':
                    matches=[p for p in accepted if p.segment_id==seg_id and p.source_text==source
                             and p.target_text==target and p.dependencies==deps
                             and _chapter_key(p.chapter_id)==_chapter_key(chapter_id)]
                    if len(matches)==1:
                        pairs.append(replace(matches[0], source_ref=f'run:{source_run}', chapter_id=chapter_id))
                    continue
                pairs.append(
                    TranslationPair(
                        segment_id=seg_id,
                        source_text=source,
                        target_text=target,
                        status=status,
                        source_ref=f"run:{source_run}",
                        chapter_id=chapter_id,
                        dependencies=deps,
                    )
                )
    return pairs, str(doc.get("language_direction") or "JP_TO_CN")


def _ordered_unique(items: list[dict[str, Any]], key: str, *, limit: int) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for item in items:
        value = str(item.get(key) or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(item)
        if len(out) >= limit:
            break
    return out


def _extract_terms(pairs: list[TranslationPair]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    terms: list[dict[str, Any]] = []
    proper_nouns: list[dict[str, Any]] = []
    for pair in pairs:
        for match in _BRACKET_RE.finditer(pair.source_text):
            source = match.group(0)
            target_match = _BRACKET_RE.search(pair.target_text)
            terms.append(
                {
                    "source": source,
                    "target": target_match.group(0) if target_match else "",
                    "kind": "bracket_label",
                    "evidence_segment_id": pair.segment_id,
                }
            )
        for source in _KATAKANA_RE.findall(pair.source_text):
            cjk_hits = _CJK_TOKEN_RE.findall(pair.target_text)
            proper_nouns.append(
                {
                    "source": source,
                    "target_hint": cjk_hits[0] if cjk_hits else "",
                    "kind": "katakana_candidate",
                    "evidence_segment_id": pair.segment_id,
                }
            )
    return (
        _ordered_unique(terms, "source", limit=80),
        _ordered_unique(proper_nouns, "source", limit=80),
    )


def _style_notes(pairs: list[TranslationPair]) -> list[str]:
    notes: list[str] = []
    if not pairs:
        return notes
    dialogue_count = sum(1 for p in pairs if "「" in p.source_text or "『" in p.source_text)
    bracket_count = sum(1 for p in pairs if "【" in p.source_text and "【" in p.target_text)
    avg_target_len = sum(len(p.target_text) for p in pairs) / max(len(pairs), 1)
    notes.append(f"已沉淀 {len(pairs)} 条翻译记忆；重启任务应优先保持译名与表达一致。")
    if dialogue_count:
        notes.append("对话段落保留中文引号风格，语气以自然简体中文为准。")
    if bracket_count:
        notes.append("方括号/系统提示类标记倾向保留全角括号结构。")
    notes.append(f"历史译文平均长度约 {avg_target_len:.0f} 字，可作为同章节节奏参考。")
    return notes


def _phrase_candidates(pairs: list[TranslationPair], *, limit: int = 20) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for pair in pairs:
        source = pair.source_text.strip()
        target = pair.target_text.strip()
        if 4 <= len(source) <= 80 and 2 <= len(target) <= 120:
            candidates.append(
                {
                    "source": source,
                    "target": target,
                    "segment_id": pair.segment_id,
                }
            )
        if len(candidates) >= limit:
            break
    return candidates


def _render_context_prompt(asset_doc: dict[str, Any], *, max_pairs: int = 12) -> str:
    lines = [
        "Translation memory context (reuse when relevant; do not force irrelevant terms):",
    ]
    for term in asset_doc.get("term_candidates", [])[:10]:
        target = term.get("target") or term.get("target_hint") or ""
        if target:
            lines.append(f"- Term: {term.get('source')} => {target}")
        else:
            lines.append(f"- Term candidate: {term.get('source')}")
    for term in asset_doc.get("proper_noun_candidates", [])[:10]:
        hint = term.get("target_hint") or ""
        lines.append(f"- Proper noun candidate: {term.get('source')}{' => ' + hint if hint else ''}")
    for pair in asset_doc.get("translation_pairs", asset_doc.get("approved_pairs", []))[:max_pairs]:
        lines.append(
            f"- Pair {pair.get('segment_id')}: {pair.get('source_text')} => {pair.get('target_text')}"
        )
    for note in asset_doc.get("style_notes", [])[:6]:
        lines.append(f"- Style: {note}")
    return "\n".join(lines)


def _external_api_summary(
    pairs: list[TranslationPair],
    *,
    provider_factory: Callable[[CostGuard], Any] | None,
) -> tuple[dict[str, Any], int]:
    if provider_factory is None:
        enabled = os.environ.get("TRANSLATION_ASSET_EXTERNAL_API_ENABLED", "").strip().lower()
        if enabled not in {"1", "true", "yes"}:
            raise ExternalAssetExtractionUnavailable(
                "external_api mode is disabled; set TRANSLATION_ASSET_EXTERNAL_API_ENABLED=true"
            )
        if os.environ.get("REAL_API_TESTS_ENABLED", "").strip().lower() not in {"1", "true", "yes"}:
            raise ExternalAssetExtractionUnavailable(
                "external_api mode requires REAL_API_TESTS_ENABLED=true"
            )
        if not os.environ.get("OPENROUTER_API_KEY", "").strip():
            raise ExternalAssetExtractionUnavailable(
                "external_api mode requires OPENROUTER_API_KEY"
            )

    guard = CostGuard(CostGuardConfig.from_env())
    provider = provider_factory(guard) if provider_factory else get_provider(ProviderMode.REAL, cost_guard=guard)
    sample = [
        {
            "segment_id": p.segment_id,
            "source_preview": p.source_text[:120],
            "target_preview": p.target_text[:160],
        }
        for p in pairs[:20]
    ]
    result = provider.generate(
        [
            {
                "role": "system",
                "content": "Summarize reusable translation memory as compact JSON without quoting secrets.",
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "task": "Return JSON with style_notes and term_candidates arrays.",
                        "pairs": sample,
                    },
                    ensure_ascii=False,
                ),
            },
        ],
        options={"max_tokens": 800},
    )
    raw = result.raw_output or json.dumps(result.parsed_output or {})
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = {"style_notes": [raw[:500]], "term_candidates": []}
    if not isinstance(parsed, dict):
        parsed = {"style_notes": [], "term_candidates": []}
    return parsed, 1


def build_translation_memory_assets(
    *,
    repo_root: Path,
    project_id: str | None = None,
    source_run: str | None = None,
    output_path: Path | None = None,
    mode: AssetBuildMode = "agent",
    status_mode: AssetStatusMode = "approved",
    provider_factory: Callable[[CostGuard], Any] | None = None,
) -> dict[str, Any]:
    """Build a JSON asset file from reviewed manifests or completed run segments."""
    if mode not in {"agent", "external_api"}:
        raise ValueError("mode must be 'agent' or 'external_api'")
    if status_mode not in {"approved", "translated"}:
        raise ValueError("status_mode must be 'approved' or 'translated'")
    if bool(project_id) == bool(source_run):
        raise ValueError("provide exactly one of project_id or source_run")

    if project_id:
        pairs, language_direction = _collect_manifest_pairs(
            repo_root,
            project_id,
            status_mode=status_mode,
        )
        source_ref = f"manifest:{project_id}"
        stem = _safe_stem(project_id)
    else:
        assert source_run is not None
        pairs, language_direction = _collect_run_pairs(
            repo_root,
            source_run,
            status_mode=status_mode,
        )
        source_ref = f"run:{source_run}"
        stem = _safe_stem(source_run)

    if not pairs:
        raise ValueError(f"no {status_mode} translation pairs available for {source_ref}")

    terms, proper_nouns = _extract_terms(pairs)
    api_calls = 0
    external_summary: dict[str, Any] = {}
    if mode == "external_api":
        external_summary, api_calls = _external_api_summary(
            pairs,
            provider_factory=provider_factory,
        )
        for note in external_summary.get("style_notes") or []:
            if isinstance(note, str):
                pass
        for item in external_summary.get("term_candidates") or []:
            if isinstance(item, dict):
                terms.append(item)

    translation_pairs = [p.to_dict() for p in pairs]
    ids=[p["pair_id"] for p in translation_pairs]
    if len(set(ids))!=len(ids):
        raise ValueError("ambiguous duplicate translation memory pair identity")
    asset_doc: dict[str, Any] = {
        "schema_version": 2,
        "asset_kind": "translation_memory",
        "mode": mode,
        "status_mode": status_mode,
        "approval_scope": "nonhuman_candidate" if status_mode == "approved" else "unreviewed_translation",
        "human_approved_final": False,
        "is_canonical": False,
        "created_at": _utc_now(),
        "language_direction": language_direction,
        "source_refs": [source_ref],
        "translation_pairs": translation_pairs,
        "approved_pairs": translation_pairs if status_mode == "approved" else [],
        "machine_pairs": translation_pairs if status_mode == "translated" else [],
        "withdrawn_pair_ids": [],
        "segment_map": {p.segment_id: p.target_text for p in pairs if p.segment_id},
        "term_candidates": _ordered_unique(terms, "source", limit=120),
        "proper_noun_candidates": proper_nouns,
        "phrase_candidates": _phrase_candidates(pairs),
        "style_notes": _style_notes(pairs),
        "external_api_summary": external_summary,
        "stats": {
            "pairs": len(pairs),
            "term_candidates": len(terms),
            "proper_noun_candidates": len(proper_nouns),
            "api_calls": api_calls,
        },
    }
    asset_doc["context_prompt"] = _render_context_prompt(asset_doc)

    out = output_path or (
        repo_root / "workspace" / "assets" / "translation_memory" / f"{stem}.json"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(asset_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    asset_doc["asset_path"] = str(out)
    try:
        asset_doc["asset_path_relative"] = str(out.relative_to(repo_root))
    except ValueError:
        asset_doc["asset_path_relative"] = str(out)
    return asset_doc


def load_translation_asset_context(path: Path, *, source_bytes: bytes | None = None) -> dict[str, Any]:
    content = path.read_text(encoding="utf-8") if source_bytes is None else source_bytes.decode("utf-8")
    data = json.loads(content)
    if not isinstance(data, dict) or data.get("asset_kind") != "translation_memory":
        raise ValueError(f"not a translation memory asset file: {path}")
    return data


def _current_asset_context(
    path: Path, *, repo_root: Path | None = None, source_bytes: bytes | None = None
) -> dict[str, Any]:
    """Read-through validation; never updates or deletes the saved audit snapshot."""
    data = load_translation_asset_context(path, source_bytes=source_bytes)
    if data.get('schema_version') != 2 or data.get('withdrawn') is True:
        return {}
    if repo_root is None:
        resolved=path.resolve()
        if resolved.parent.parts[-3:] != ('workspace','assets','translation_memory'):
            return {}
        repo_root=resolved.parents[3]
    refs=data.get('source_refs')
    if not isinstance(refs,list) or len(refs)!=1 or not isinstance(refs[0],str):
        return {}
    origin, _, name=refs[0].partition(':')
    mode=data.get('status_mode')
    if mode not in {'approved','translated'}: return {}
    try:
        if origin=='manifest':
            pairs,direction=_collect_manifest_pairs(repo_root,name,status_mode=mode)
        elif origin=='run':
            pairs,direction=_collect_run_pairs(repo_root,name,status_mode=mode)
        else: return {}
    except (OSError, ValueError, KeyError, TypeError):
        return {}  # Missing/ambiguous/stale dependency is withheld, not repaired.
    if direction!=data.get('language_direction'): return {}
    current={};duplicates=set()
    for pair in pairs:
        row=pair.to_dict();pid=row['pair_id']
        if pid in current: duplicates.add(pid)
        current[pid]=row
    saved=data.get('translation_pairs')
    withdrawn=data.get('withdrawn_pair_ids',[])
    if not isinstance(saved,list) or not isinstance(withdrawn,list): return {}
    counts={}
    for row in saved:
        if isinstance(row,dict) and isinstance(row.get('pair_id'),str):
            counts[row['pair_id']]=counts.get(row['pair_id'],0)+1
    valid=[]
    for row in saved:
        if not isinstance(row,dict): continue
        pid=row.get('pair_id')
        if not isinstance(pid,str): continue
        now=current.get(pid)
        if counts.get(pid)!=1 or pid in duplicates or pid in withdrawn or now is None: continue
        # Full semantic row equality also rejects modified pair payloads or forged digests.
        if row!=now: continue
        valid.append(now)
    if not valid: return {}
    # Derived terms/style cannot outlive any parent; recompute only from fresh pairs.
    objects=[TranslationPair(segment_id=r['segment_id'],source_text=r['source_text'],
        target_text=r['target_text'],status=r['status'],source_ref=r['source_ref'],
        chapter_id=r['chapter_id']) for r in valid]
    terms,nouns=_extract_terms(objects)
    return {**data,'translation_pairs':valid,'approved_pairs':valid if mode=='approved' else [],
            'machine_pairs':valid if mode=='translated' else [],'term_candidates':terms,
            'proper_noun_candidates':nouns,'phrase_candidates':_phrase_candidates(objects),
            'style_notes':_style_notes(objects)}


def render_translation_asset_context(path: Path, *, repo_root: Path | None = None) -> str:
    data = _current_asset_context(path, repo_root=repo_root)
    return _render_context_prompt(data) if data else ''


def select_batch_context_hits(
    path: Path,
    batch_source_texts: list[str],
    *,
    max_terms: int = 8,
    max_pairs: int = 6,
    max_character_notes: int = 4,
    repo_root: Path | None = None,
) -> str:
    """Return compact glossary/character hits for one batch (no full asset dump)."""
    limits = (max_terms, max_pairs, max_character_notes)
    if any(type(limit) is not int or limit < 0 for limit in limits):
        raise ValueError("context limits must be nonnegative integers")
    if not batch_source_texts or not any(limits):
        return ""
    data = _current_asset_context(path, repo_root=repo_root)
    haystack = "\n".join(batch_source_texts)

    lines: list[str] = []

    term_hits = 0
    for term in data.get("term_candidates", []):
        if term_hits >= max_terms:
            break
        source = str(term.get("source") or "").strip()
        if not source or source not in haystack:
            continue
        target = term.get("target") or term.get("target_hint") or ""
        if target:
            lines.append(f"- Term: {source} => {target}")
        else:
            lines.append(f"- Term: {source}")
        term_hits += 1

    name_hits = 0
    for term in data.get("proper_noun_candidates", []):
        if name_hits >= max_character_notes:
            break
        source = str(term.get("source") or "").strip()
        if not source or source not in haystack:
            continue
        hint = term.get("target_hint") or ""
        lines.append(
            f"- Name: {source}{' => ' + hint if hint else ''}"
        )
        name_hits += 1

    pair_hits = 0
    for pair in data.get("translation_pairs", []):
        if pair_hits >= max_pairs:
            break
        source = str(pair.get("source_text") or "").strip()
        if not source or len(source) < 4 or source not in haystack:
            continue
        target = str(pair.get("target_text") or "").strip()
        if target:
            lines.append(f"- Phrase: {source[:40]} => {target[:60]}")
            pair_hits += 1

    if not lines:
        return ""
    return "Relevant translation memory (use only when applicable):\n" + "\n".join(lines)
