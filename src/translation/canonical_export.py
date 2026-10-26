"""Explicit, source-complete nonhuman accepted revision export.

This module captures existing current decisions; it never issues an acceptance.
Source inventory and source-document versions must have been frozen at import.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from translation.atomic_bundle import publish_bundle
from translation.source_versions import validate_source_binding, value_sha
from workbench.project_registry import parse_project_manifest, validated_source_entries
from workbench.review_state import approval_identity, review_decision_summary, segment_id, segment_text

TARGET_FIELDS = {'draft', 'draft_text', 'target_text', 'translation', 'refined_text'}


def selected_segment(row, field):
    if field not in TARGET_FIELDS or not isinstance(row.get(field), str) or not row[field].strip():
        raise ValueError('explicit non-empty target field required')
    result = {'id': segment_id(row), 'source': segment_text(row, 'source', 'source_text'), 'draft': row[field]}
    for name in ('source_binding', 'dependency_sha256', 'source_context_revision', 'dependency_versions', 'draft_recovery_revision'):
        if name in row: result[name] = row[name]
    return result


def _scope(data):
    manifest = parse_project_manifest(data)
    if any(row.get("dependency_resolution_errors") for row in manifest.segments):
        raise ValueError("unresolved dependency prevents accepted export")
    inventory = manifest.source_inventory
    entries = validated_source_entries(inventory, language_direction=manifest.language_direction)
    if inventory['schema'] != 'workbench-source-inventory/2' or not entries:
        raise ValueError('complete versioned source inventory required')
    ids = [segment_id(row) for row in manifest.segments]
    if ids != [entry['segment_id'] for entry in entries]:
        raise ValueError('missing, extra, duplicate or reordered source segments')
    chapters = {}; last = None; closed = set()
    for row, expected in zip(manifest.segments, entries):
        source = segment_text(row, 'source', 'source_text')
        binding = validate_source_binding(row.get('source_binding'), source)
        actual = {'segment_id': segment_id(row), 'source_sha256': hashlib.sha256(source.encode()).hexdigest(),
                  'chapter_id': binding['chapter_id'], 'source_revision': binding['source_revision'],
                  'source_binding_sha256': binding['binding_sha256']}
        if actual != expected: raise ValueError('source inventory version changed')
        chapter = binding['chapter_id']
        if chapter != last:
            if chapter in closed: raise ValueError('duplicate chapter group')
            if last is not None: closed.add(last)
            last = chapter
        if chapter in chapters and chapters[chapter] != binding['source_revision']:
            raise ValueError('multiple source versions in one chapter')
        chapters[chapter] = binding['source_revision']
    documents = data.get('source_documents')
    if not isinstance(documents, list) or len(documents) != len(chapters):
        raise ValueError('frozen expected source documents required')
    seen = set(); paths = set()
    for doc in documents:
        if not isinstance(doc, dict) or set(doc) != {'chapter_id', 'path', 'source_revision'}:
            raise ValueError('invalid source document descriptor')
        chapter = doc['chapter_id']; path = doc['path']
        if not isinstance(chapter, str) or chapter in seen or chapters.get(chapter) != doc['source_revision']:
            raise ValueError('missing, empty, duplicate or changed source chapter')
        if not isinstance(path, str) or path in paths: raise ValueError('unique source document path required')
        prefix = 'input_jp' if manifest.language_direction == 'JP_TO_CN' else 'input_cn'
        relative = Path(path)
        if relative.is_absolute() or '..' in relative.parts or len(relative.parts) < 2 or relative.parts[0] != prefix:
            raise ValueError('source document must remain in direction input directory')
        seen.add(chapter); paths.add(path)
    if manifest.chapters != len(chapters): raise ValueError('declared expected chapter count differs')
    return manifest, entries, documents


def build_accepted_revision(data, review_entries, target_fields):
    """Freeze an explicit choice already accepted by a current trusted caller."""
    manifest, entries, documents = _scope(data)
    if not isinstance(target_fields, dict) or set(target_fields) != {e['segment_id'] for e in entries}:
        raise ValueError('explicit target selection must cover the complete source inventory')
    rows = []
    for row, expected in zip(manifest.segments, entries):
        sid = expected['segment_id']; field = target_fields[sid]
        selected = selected_segment(row, field)
        identity = approval_identity(project_id=manifest.project_id, language_direction=manifest.language_direction, segment=selected)
        entry = review_entries.get(sid)
        if not review_decision_summary(entry, identity, segment=selected)['candidate_accepted']:
            raise ValueError('missing or stale accepted review: ' + sid)
        rows.append({**expected, 'target_field': field, 'target_sha256': hashlib.sha256(selected['draft'].encode()).hexdigest(),
                     'approval_identity': identity, 'review_entry_sha256': value_sha(entry)})
    payload = {'schema': 'accepted-revision/1', 'project_id': manifest.project_id,
               'language_direction': manifest.language_direction, 'source_inventory_sha256': manifest.source_inventory['inventory_sha256'],
               'source_documents': documents, 'segments': rows, 'approval_scope': 'nonhuman_candidate', 'human_approved_final': False}
    return {**payload, 'revision_sha256': value_sha(payload)}


def validate_accepted_revision(data, review_entries):
    accepted = data.get('accepted_revision')
    if not isinstance(accepted, dict) or not isinstance(accepted.get('segments'), list):
        raise ValueError('explicit accepted revision required')
    choices = {}
    for row in accepted['segments']:
        if not isinstance(row, dict) or row.get('segment_id') in choices: raise ValueError('duplicate accepted segment')
        choices[row.get('segment_id')] = row.get('target_field')
    actual = build_accepted_revision(data, review_entries, choices)
    if actual != accepted: raise ValueError('accepted revision or dependencies changed')
    return actual


def _check_documents(root, documents, segments):
    from translation.chapter_parser import parse_chapter_file
    for doc in documents:
        path = root / doc['path']
        if (path.is_symlink() or any(p.is_symlink() for p in path.parents)
                or not path.is_file() or not path.resolve().is_relative_to(root.resolve())):
            raise ValueError('source document missing or unmanaged')
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != doc['source_revision']:
            raise ValueError('source document version changed')
        parsed = parse_chapter_file(path, source_bytes=raw)
        expected = [row for row in segments if row['source_binding']['chapter_id'] == doc['chapter_id']]
        if parsed.chapter_id != doc['chapter_id'] or not parsed.segments or len(parsed.segments) != len(expected):
            raise ValueError('source chapter parser coverage differs from frozen scope')
        for actual, frozen in zip(parsed.segments, expected):
            if actual.segment_id != segment_id(frozen) or actual.source_binding != frozen['source_binding']:
                raise ValueError('source chapter parser version or complete scope changed')


def export_accepted_revision(repo_root, data, review_entries, *, output_root=None, before_commit=None):
    root = Path(repo_root)
    from workbench.project_registry import _resolve_manifest_dependencies
    raw_data=data
    data=_resolve_manifest_dependencies(root,raw_data)
    accepted = validate_accepted_revision(data, review_entries)
    manifest, entries, documents = _scope(data)
    _check_documents(root, documents, manifest.segments)
    suffix = 'cn' if manifest.language_direction == 'JP_TO_CN' else 'jp'
    expected_root = root / ('output_' + suffix)
    output = Path(output_root) if output_root is not None else expected_root
    if output.absolute() != expected_root.absolute(): raise ValueError('canonical output direction/root mismatch')
    volume_rel = 'translated/full_volume_' + suffix + '.md'
    def check_output_scope():
        for directory in (output, output / 'translated', output / 'bilingual'):
            if directory.is_symlink() or any(parent.is_symlink() for parent in directory.parents):
                raise ValueError('unmanaged canonical output directory preserved')
        translated = output / 'translated'
        if translated.exists() and any(path.name not in {Path(volume_rel).name, '.gitkeep'} for path in translated.iterdir()):
            raise ValueError('unmanaged extra canonical outputs preserved; resolve explicitly')
        bilingual = output / 'bilingual'
        if bilingual.exists() and any(bilingual.glob('*.md')):
            raise ValueError('legacy bilingual final copies preserved; resolve explicitly')
    check_output_scope()
    text = []; previous = None
    for row, selected in zip(manifest.segments, accepted['segments']):
        if selected['chapter_id'] != previous:
            text.extend(['# ' + selected['chapter_id'], '']); previous = selected['chapter_id']
        text.extend([row[selected['target_field']], ''])
    volume = ('\n'.join(text).rstrip() + '\n').encode()
    result = {'schema_version': 3, 'accepted_revision': accepted, 'project_id': manifest.project_id,
              'language_direction': manifest.language_direction, 'source_inventory_sha256': manifest.source_inventory['inventory_sha256'],
              'canonical_final_translation': str(Path('output_' + suffix) / volume_rel),
              'canonical_final_translation_count': 1, 'final_translation_policy': 'explicit_accepted_revision',
              'volume_sha256': hashlib.sha256(volume).hexdigest(), 'chapters_exported': len(documents),
              'segments_exported': len(entries), 'approval_scope': 'nonhuman_candidate', 'human_approved_final': False}
    def recheck():
        if before_commit is not None: before_commit()
        if validate_accepted_revision(_resolve_manifest_dependencies(root,raw_data), review_entries) != accepted:
            raise RuntimeError('accepted selection changed during export')
        _check_documents(root, documents, manifest.segments)
        check_output_scope()
    bundle = publish_bundle(output, {'volume.md': volume, 'manifest.json': (json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2)+'\n').encode()},
                            {volume_rel: 'volume.md', 'final_export_manifest.json': 'manifest.json'}, before_commit=recheck)
    return {**result, **bundle}
