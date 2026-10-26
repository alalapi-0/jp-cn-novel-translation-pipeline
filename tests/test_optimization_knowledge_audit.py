"""Synthetic provenance, no-release and complete-census regressions."""
from pathlib import Path
from datetime import datetime, timezone, timedelta
import hashlib
import json
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'src'), str(Path(__file__).parent)]
import audit_optimization_knowledge as audit
import build_optimization_alignment as alignment
from test_optimization_split import freeze


@pytest.mark.parametrize('characters, expected', [
    ([{'personality_summary': 'FICTIONAL_SUMMARY'}], 'str'),
    ({'OPAQUE_KEY': {'personality_summary': 'FICTIONAL_SUMMARY'}}, 'str'),
    ([{'personality_summary': None}], 'NoneType'),
])
def test_schema_character_summary_visible_as_structural_scalar(characters, expected):
    rows = list(audit.inline_nodes({'characters': characters}, 'character', guard=lambda: None))
    summaries = [r for r in rows if r['category_hint'] == 'summary']
    assert len(summaries) == 1 and summaries[0]['shape'] == expected
    assert 'FICTIONAL_SUMMARY' not in json.dumps(rows)
    assert 'OPAQUE_KEY' not in json.dumps(rows)


@pytest.mark.parametrize('value, kind', [
    ({'personality_summary': object()}, 'character'),
    ({'characters': [{'nested': {'personality_summary': object()}}]}, 'character'),
    ({'characters': [{'personality_summary': object()}]}, 'glossary'),
    ({'characters': [{'personality_summary': object()}]}, 'tm'),
    ({'characters': [{'personal_summary': object(), 'personal_notes': object(),
                      'style_notes': object(), 'api_token': object()}]}, 'character'),
])
def test_schema_summary_exception_keeps_other_private_paths_pruned(value, kind):
    rows = list(audit.inline_nodes(value, kind, guard=lambda: None))
    assert any(r['shape'] == 'pruned' for r in rows)
    assert all('value' not in r for r in rows)
    assert audit.protected_field('personality_summary') == 'style'


@pytest.mark.parametrize('value', [[], {}, 1, 1.5, True])
def test_schema_character_summary_malformed_type_refuses_descent(value):
    with pytest.raises(ValueError, match='summary type'):
        list(audit.inline_nodes({'characters': [{'personality_summary': value}]},
                               'character', guard=lambda: None))


def summary_case(characters=None):
    doc = {'characters': characters if characters is not None else [{
        'personality_summary': 'FICTIONAL_SUMMARY', 'manual_notes': 'PRIVATE_NOTES',
        'target_name': 'PRIVATE_TARGET'}]}
    raw = json.dumps(doc).encode(); revision = hashlib.sha256(raw).hexdigest()
    descriptor = {'path': 'workspace/configs/character_profile.yaml', 'sha256': revision}
    records = doc['characters']
    prior = []
    for i, row in enumerate(records if type(records) is list else records.values()):
        pointer = f'$.characters[{i}]' if type(records) is list else f'$.characters[ordinal:{i}]'
        prior.append({'artifact_path': descriptor['path'], 'artifact_revision': revision,
                      'record_pointer': pointer, 'record_id': audit.digest([descriptor['path'], revision, pointer]),
                      'record_sha256': audit.digest(row), 'category': 'character'})
    return raw, descriptor, prior


@pytest.mark.parametrize('characters', [None, {'PRIVATE_KEY': {'personality_summary': None}}])
def test_summary_envelopes_bind_original_identity_without_projecting_content(characters):
    raw, descriptor, prior = summary_case(characters)
    rows = audit.character_summary_envelopes(raw, descriptor, prior, guard=lambda: None)
    assert len(rows) == 1 and rows[0]['record_id'] == prior[0]['record_id']
    assert rows[0]['record_sha256'] == prior[0]['record_sha256']
    assert rows[0]['present'] and rows[0]['scalar_type'] in {'str', 'NoneType'}
    assert rows[0]['schema_path'] == prior[0]['record_pointer'] + '.personality_summary'
    assert not any(rows[0][k] for k in ['semantic_verified', 'provenance_verified', 'consumer',
                                     'human_approved', 'adoption'])
    assert not any(v in json.dumps(rows) for v in ['FICTIONAL_SUMMARY', 'PRIVATE_',
                                                  'scalar_length', 'scalar_sha256', 'empty'])


@pytest.mark.parametrize('change', ['raw', 'family', 'pointer', 'row_hash', 'missing', 'duplicate'])
def test_summary_envelope_drift_and_missing_identity_refuse(change):
    raw, descriptor, prior = summary_case()
    if change == 'raw': raw += b' '
    elif change == 'family': descriptor['path'] = 'workspace/configs/glossary.yaml'
    elif change == 'pointer': prior[0]['record_pointer'] = '$.characters[99]'
    elif change == 'row_hash': prior[0]['record_sha256'] = 'invalid'
    elif change == 'missing': prior.clear()
    else: prior.append(dict(prior[0]))
    with pytest.raises(ValueError):
        audit.character_summary_envelopes(raw, descriptor, prior, guard=lambda: None)


def test_summary_view_excludes_unrelated_fields_before_traversal(monkeypatch):
    raw, descriptor, prior = summary_case()
    monkeypatch.setattr(audit, 'decode', lambda *_: {'characters': [{
        'personality_summary': 'FICTIONAL_SUMMARY', 'target_name': object(),
        'manual_notes': object(), 'personal_notes': object(), 'cached_prompt': object()}]})
    assert len(audit.character_summary_envelopes(raw, descriptor, prior, guard=lambda: None)) == 1
    left = {'characters': [{'personality_summary': 'FIRST'}]}
    right = {'characters': [{'personality_summary': ''}]}
    assert list(audit.inline_nodes(left, 'character', guard=lambda: None)) == list(
        audit.inline_nodes(right, 'character', guard=lambda: None))


def case(tmp_path, entries=None):
    private, manifest, _ = freeze(tmp_path)
    split = json.loads(manifest.read_text())
    version = tmp_path / split['inputs'][0]['path']
    inventory = json.loads(version.read_text())
    sources = split['chapters']
    dev = next(r for r in sources if r['partition'] == 'development')
    held = next(r for r in sources if r['partition'] == 'holdout')
    original = next(x for x in inventory['entries'] if x['path'] == dev['path'])
    text = (version.parent / original['snapshot']).read_text()
    proof = {k: dev[k] for k in ('language_direction', 'chapter_id', 'source_revision')}
    proof.update(start_char=0, end_char=4, quote=text[:4])
    payloads = entries or {
        'workspace/configs/glossary.yaml': {
            'entries': [{'source_term': 'PRIVATE_TERM', 'target_term': 'PRIVATE_TARGET',
                         'locked': True, 'approved_by_user': True, 'source_evidence': [proof]}]},
        'workspace/configs/character_profile.yaml': {'characters': [{
            'name': 'PRIVATE_CHARACTER', 'relationships': ['PRIVATE_RELATION'],
            'address_map': {'PRIVATE_KEY': 'PRIVATE_ADDRESS'}, 'personality_summary': 'PRIVATE_SUMMARY'}]},
        'workspace/configs/world_bible.yaml': {'entries': [{'name': 'PRIVATE_WORLD'}]},
        'workspace/assets/translation_memory/synthetic.json': {
            'approved_pairs': [{'source_text': 'PRIVATE_PAIR_SOURCE', 'target_text': 'PRIVATE_PAIR_TARGET'}],
            'term_candidates': {'PRIVATE_HINT': 12}, 'style_notes': ['PRIVATE_STYLE'],
            'cached_prompt': 'PRIVATE_PROMPT'}}
    for path, value in payloads.items():
        raw = json.dumps(value, ensure_ascii=False).encode()
        sha = hashlib.sha256(raw).hexdigest()
        (version.parent / 'blobs' / sha).write_bytes(raw)
        inventory['entries'].append({'path': path, 'category': 'structured_knowledge_or_tm',
            'bytes': len(raw), 'sha256': sha, 'snapshot': f'blobs/{sha}',
            'freeze_status': 'read_only_recoverable_version'})
    inventory['registered_denominator'] = len(inventory['entries'])
    version.write_text(json.dumps(inventory))
    split['inputs'][0]['sha256'] = hashlib.sha256(version.read_bytes()).hexdigest()
    split['inputs'][0]['registered_denominator'] = len(inventory['entries'])
    split['registered_file_denominator'] = len(inventory['entries'])
    manifest = private / 'extended-split.json'
    manifest.write_text(json.dumps(split))
    reader = audit.KnowledgeAudit(tmp_path, manifest, hashlib.sha256(manifest.read_bytes()).hexdigest())
    return private, reader, dev, held, proof


def permit(private, reader, **changes):
    output = private / 'sealed-census'
    value = {'decision': 'APPROVE', 'candidate_sha256': '1' * 64,
             'plan_sha256': audit.digest(reader.plan()), 'runtime_authorized': True,
             'effects': 'sealed_deterministic_parse_only', 'model_operations': 0,
             'body_projection': False, 'output': str(output.relative_to(reader.root)),
             'effect_cutoff': (datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat()}
    value.update(changes)
    path = private / 'runtime-approval.json'; path.write_text(json.dumps(value))
    return dict(approval_path=path, approval_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                candidate_sha256='1' * 64, output=output)


def observe(monkeypatch):
    seen = []; original = alignment.FrozenReader.read
    def record(self, row):
        seen.append(row['category'])
        return original(self, row)
    monkeypatch.setattr(alignment.FrozenReader, 'read', record)
    return seen


def inline_case(tmp_path, entries=None):
    private, reader, *_ = case(tmp_path, entries)
    prior_args = permit(private, reader)
    prior = reader.audit(**prior_args)
    records = prior_args['output'] / 'records.jsonl'
    inputs = dict(prior_records=records, prior_sha256=prior['records_sha256'],
                  prior_count=prior['record_denominator'])
    plan = reader.inline_plan(**inputs)
    output = private / 'inline-structure'
    value = {'decision': 'APPROVE', 'runtime_authorized': True,
             'candidate_sha256': '3' * 64, 'plan_sha256': audit.digest(plan),
             'effects': 'sealed_inline_structure_only', 'model_operations': 0,
             'body_projection': False, 'output': str(output.relative_to(reader.root)),
             'effect_cutoff': (datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat()}
    path = private / 'inline-approval.json'; path.write_text(json.dumps(value))
    args = {**inputs, 'approval_path': path,
            'approval_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'candidate_sha256': '3' * 64, 'output': output}
    return reader, args


def test_inline_metadata_reuses_original_scope_without_blob_reads(tmp_path, monkeypatch):
    reader, args = inline_case(tmp_path)
    seen = observe(monkeypatch)
    plan = reader.inline_plan(**{k: args[k] for k in ['prior_records', 'prior_sha256', 'prior_count']})
    assert not seen and plan['effects'] == 'sealed_inline_structure_only'
    assert plan['prior_records']['count'] == 8 and len(plan['files']) == 4


def test_inline_nested_categories_are_structural_not_semantic_and_keep_original_links(tmp_path, monkeypatch):
    entries = {'workspace/configs/character_profile.yaml': {'characters': [{
        'name': 'PRIVATE_CHARACTER', 'extra': {'relationships': [{'PRIVATE_PERSON': 'PRIVATE_RELATION'}],
        'address_map': {'PRIVATE_ADDRESS': 'PRIVATE_FORM'}, 'world': {'PRIVATE_WORLD': True},
        'summary': 'PRIVATE_SUMMARY'}, 'cached_prompt': {'relationships': ['PRIVATE_PROMPT']}}]}}
    reader, args = inline_case(tmp_path, entries)
    seen = observe(monkeypatch); summary = reader.audit_inline(**args)
    assert seen == ['structured_knowledge_or_tm'] and summary['source_snapshot_reads'] == 0
    assert summary['original_record_denominator'] == summary['known_records_linked'] == 1
    for category in ['relationship', 'address', 'world', 'summary']:
        assert summary['category_hints'][category] == 1
    assert summary['opaque_structural_envelopes'] > 0
    assert summary['protected_fields_unexamined']['prompt'] == 1
    assert not any(summary[k] for k in ['P3_R01_T02_complete', 'consumer_eligible', 'human_approved_final', 'production_adoption'])
    output = (args['output'] / 'structure.jsonl').read_text()
    assert 'PRIVATE_' not in output + json.dumps(summary)
    rows = [json.loads(v) for v in output.splitlines()]
    assert len({r['pointer'] for r in rows}) == len(rows)
    assert sum(bool(r['known_record']) for r in rows) == 1
    assert all(r['disposition'] == 'withheld_unverified' and not r['consumer_eligible'] for r in rows)


def test_inline_prunes_before_descending_or_hashing_protected_values():
    # Unsupported sentinels would fail traversal or hashing if visited.
    secret = object()
    value = {'style_notes': secret, 'cached_prompt': secret, 'source_text': secret,
             'api_token': secret, 'visible': {'relationships': []}}
    rows = list(audit.inline_nodes(value, 'character', guard=lambda: None))
    assert sum(r['shape'] == 'pruned' for r in rows) == 4
    assert len(rows) == 7 and all('value' not in r for r in rows)
    assert len([r for r in rows if r['category_hint'] == 'relationship']) == 1


@pytest.mark.parametrize('change', [
    {'effects': 'sealed_deterministic_parse_only'}, {'body_projection': True},
    {'model_operations': 1}, {'plan_sha256': '0' * 64}, {'runtime_authorized': False},
    {'effect_cutoff': '2000-01-01T00:00:00+00:00'}])
def test_inline_wrong_approval_opens_no_blob(tmp_path, monkeypatch, change):
    reader, args = inline_case(tmp_path)
    path = args['approval_path']; value = json.loads(path.read_text()); value.update(change)
    path.write_text(json.dumps(value)); args['approval_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    seen = observe(monkeypatch)
    with pytest.raises(PermissionError): reader.audit_inline(**args)
    assert not seen and not args['output'].exists()


def test_inline_existing_output_and_original_census_drift_refuse_before_blob(tmp_path, monkeypatch):
    reader, args = inline_case(tmp_path)
    args['output'].mkdir(); seen = observe(monkeypatch)
    with pytest.raises(FileExistsError): reader.audit_inline(**args)
    assert not seen
    args['output'].rmdir(); args['prior_records'].write_text('{}\n')
    with pytest.raises(PermissionError, match='census drifted'): reader.audit_inline(**args)
    assert not seen and not (args['output'] / 'summary.json').exists()


@pytest.mark.parametrize('limits', [
    {'nodes': 2, 'depth': 64, 'output_bytes': 9999, 'seconds': 120},
    {'nodes': 1000000, 'depth': 1, 'output_bytes': 9999, 'seconds': 120}])
def test_inline_total_and_depth_limits_fail_closed(limits):
    with pytest.raises(ValueError, match='bound exceeded'):
        list(audit.inline_nodes({'one': [{'two': 'PRIVATE'}]}, 'character',
                                guard=lambda: None, limits=limits))


def test_inline_output_limit_retains_failure_without_complete_summary(tmp_path, monkeypatch):
    reader, args = inline_case(tmp_path)
    monkeypatch.setitem(audit.INLINE_LIMITS, 'output_bytes', 100)
    # The changed bound is an input identity, so obtain the matching synthetic permit.
    plan = reader.inline_plan(**{k: args[k] for k in ['prior_records', 'prior_sha256', 'prior_count']})
    path = args['approval_path']; value = json.loads(path.read_text()); value['plan_sha256'] = audit.digest(plan)
    path.write_text(json.dumps(value)); args['approval_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match='output bound exceeded'): reader.audit_inline(**args)
    assert (args['output'] / 'structure.jsonl').is_file()
    assert not (args['output'] / 'summary.json').exists()


def test_inline_deterministic_paths_and_hashes_do_not_depend_on_values():
    left = {'PRIVATE_ENTITY': {'summary': 'PRIVATE_ONE', 'text': object()}}
    right = {'PRIVATE_ENTITY': {'summary': 'PRIVATE_TWO', 'text': object()}}
    rows = lambda v: list(audit.inline_nodes(v, 'character', guard=lambda: None))
    assert rows(left) == rows(right)
    assert 'PRIVATE_' not in json.dumps(rows(left))


def test_inline_original_container_routes_are_not_new_opaque_envelopes(tmp_path):
    reader, args = inline_case(tmp_path, {'workspace/configs/character_profile.yaml': {
        'characters': [{'name': 'PRIVATE_CHARACTER', 'extra': {'world': {'unused': True}}}]}})
    summary = reader.audit_inline(**args)
    rows = [json.loads(v) for v in (args['output'] / 'structure.jsonl').read_text().splitlines()]
    known = [r for r in rows if r['known_structural_route']]
    assert len(known) == 3  # root, original collection, original record
    assert not any(r['opaque_structural_envelope'] for r in known)
    assert summary['known_route_category_hints']['character'] == 1
    assert summary['new_field_category_hints']['character'] == 0
    assert summary['new_field_category_hints']['world'] == 1
    assert all(summary['category_hints'][k] == summary['known_route_category_hints'][k] +
               summary['new_field_category_hints'][k] for k in audit.CATEGORIES)


def test_inline_original_pointer_prefixes_reject_arbitrary_or_ambiguous_keys():
    assert audit.wire_prefixes('$.entries[ordinal:2].summary') == {
        '$', '$.entries', '$.entries[ordinal:2]', '$.entries[ordinal:2].summary'}
    for value in ['$.PRIVATE_CHARACTER', '$.entries[2]trailing', '$[NaN]', 'entries[0]']:
        with pytest.raises(ValueError): audit.wire_prefixes(value)


def test_metadata_complete_census_opens_no_body(tmp_path, monkeypatch):
    private, reader, *_ = case(tmp_path)
    seen = observe(monkeypatch); p = reader.plan()
    assert not seen
    assert (p['registered_paths'], p['frozen_records'], p['source_files']) == (30, 30, 24)
    assert p['partitions'] == {'development': 16, 'holdout': 8}
    assert len(p['files']) == 4 and not p['body_projection']
    assert p == reader.plan()


@pytest.mark.parametrize('change', [
    {'decision': 'REJECT'}, {'candidate_sha256': '2' * 64}, {'plan_sha256': '0' * 64},
    {'runtime_authorized': False}, {'effects': 'allow_everything'}, {'model_operations': 1},
    {'body_projection': True}, {'output': 'workspace/tooling/optimization/elsewhere'},
    {'effect_cutoff': '2000-01-01T00:00:00+00:00'}])
def test_wrong_approval_denied_before_any_snapshot(tmp_path, monkeypatch, change):
    private, reader, *_ = case(tmp_path)
    args = permit(private, reader, **change); seen = observe(monkeypatch)
    with pytest.raises(PermissionError):
        reader.audit(**args)
    assert not seen and not args['output'].exists()


def test_actual_adapter_locates_source_but_never_promotes_or_projects(tmp_path, monkeypatch):
    private, reader, *_ = case(tmp_path)
    args = permit(private, reader); seen = observe(monkeypatch)
    summary = reader.audit(**args)
    assert seen.count('structured_knowledge_or_tm') == 4
    assert summary['source_snapshot_reads'] == seen.count('source_original') == 1
    assert summary['file_denominator'] == 4 and summary['record_denominator'] == 8
    assert summary['categories']['relationship'] == summary['categories']['address'] == 1
    assert summary['categories']['summary'] == summary['categories']['world'] == 1
    assert summary['provenance_statuses']['located_development_evidence_semantics_unverified'] == 1
    rows = [json.loads(line) for line in (args['output'] / 'records.jsonl').read_text().splitlines()]
    assert len({r['record_id'] for r in rows}) == len(rows)
    assert all(not r['consumer_eligible'] and r['disposition'] == 'withheld_unverified' for r in rows)
    assert all(r['semantic_truth'] == 'not_verified' and not r['human_approved_final'] for r in rows)
    assert 'PRIVATE_' not in json.dumps(summary) + (args['output'] / 'records.jsonl').read_text()
    assert not summary['P3_R01_T02_complete'] and summary['model_body_releases'] == 0


def test_holdout_anywhere_in_proof_list_denied_before_source_read(tmp_path, monkeypatch):
    private, first, dev, held, proof = case(tmp_path)
    # Update the synthetic registered container and re-pin its inventory/split.
    held_proof = {**proof, **{k: held[k] for k in ('language_direction', 'chapter_id', 'source_revision')}}
    other = tmp_path / 'other'; other.mkdir()
    private, reader, *_ = case(other, {'workspace/configs/glossary.yaml': {
        'entries': [{'source_term': 'PRIVATE', 'source_evidence': [proof, held_proof]}]}})
    seen = observe(monkeypatch); summary = reader.audit(**permit(private, reader))
    assert 'source_original' not in seen
    assert summary['provenance_statuses'] == {'holdout_dependency': 1}


@pytest.mark.parametrize('patch,status', [
    ({'chapter_id': 'ch-999'}, 'unknown_source_identity'),
    ({'source_revision': '0' * 64}, 'unknown_source_identity'),
    ({'language_direction': 'CN_TO_JP'}, 'unknown_source_identity'),
    ({'quote': 'FAIL'}, 'stale_or_inexact_source_span'),
    ({'start_char': True}, 'invalid_source_proof'),
    ({'end_char': 0}, 'invalid_source_proof')])
def test_spoofed_or_stale_source_evidence_is_withheld(tmp_path, patch, status):
    _, first, _, _, proof = case(tmp_path)
    other = tmp_path / 'other'; other.mkdir()
    private, reader, *_ = case(other, {'workspace/configs/glossary.yaml': {
        'entries': [{'source_term': 'PRIVATE', 'source_evidence': [{**proof, **patch}]}]}})
    summary = reader.audit(**permit(private, reader))
    assert summary['provenance_statuses'] == {status: 1}


def test_bare_chapter_and_legacy_labels_never_establish_provenance(tmp_path):
    private, reader, *_ = case(tmp_path, {'workspace/configs/glossary.yaml': {
        'entries': [{'source_term': 'PRIVATE', 'first_seen_chapter': 1,
                     'locked': True, 'approved_by_user': True, 'human_approved_final': True}]}})
    summary = reader.audit(**permit(private, reader))
    assert summary['provenance_statuses'] == {'missing_source_proof': 1}
    assert summary['source_snapshot_reads'] == 0


def test_existing_output_prevents_replay_before_body_access(tmp_path, monkeypatch):
    private, reader, *_ = case(tmp_path)
    args = permit(private, reader); args['output'].mkdir(); seen = observe(monkeypatch)
    with pytest.raises(FileExistsError):
        reader.audit(**args)
    assert not seen


@pytest.mark.parametrize('where', ['split_disk', 'inventory_disk', 'memory'])
def test_metadata_drift_fails_before_body_access(tmp_path, monkeypatch, where):
    private, reader, *_ = case(tmp_path)
    args = permit(private, reader); seen = observe(monkeypatch)
    if where == 'memory':
        next(iter(reader.reader.entries.values()))['bytes'] += 1
    else:
        p = reader.manifest if where == 'split_disk' else reader.root / reader.reader.split['inputs'][0]['path']
        p.write_bytes(p.read_bytes() + b' ')
    with pytest.raises(PermissionError, match='changed|mutated'):
        reader.audit(**args)
    assert not seen


def test_unknown_registered_family_denied_before_any_body(tmp_path, monkeypatch):
    private, reader, *_ = case(tmp_path, {'workspace/configs/unknown.yaml': {'entries': []}})
    seen = observe(monkeypatch)
    assert reader.plan()['files'][0]['family'] == 'unknown'
    with pytest.raises(PermissionError, match='unsupported'):
        reader.audit(**permit(private, reader))
    assert not seen


def test_changed_or_symlinked_snapshot_refused(tmp_path):
    private, reader, *_ = case(tmp_path)
    args = permit(private, reader)
    row = reader.reader.entries[reader.plan()['files'][0]['path']]
    owner = reader.reader.owners[row['path']]; blob = owner.path.parent / row['snapshot']
    raw = blob.read_bytes(); blob.write_bytes(raw + b' ')
    with pytest.raises(ValueError, match='content identity'):
        reader.audit(**args)


@pytest.mark.parametrize('raw,suffix', [
    (b'{"entries": [], "entries": ["PRIVATE_SECRET"]}', '.json'),
    (b'entries: []\nentries: PRIVATE_SECRET\n', '.yaml'),
    (b'entries: &a [*a]\n', '.yaml'),
    (b'entries: !!python/object:PRIVATE_SECRET {}\n', '.yaml'),
    (b'{"PRIVATE_SECRET":', '.json')])
def test_ambiguous_or_unsafe_parser_errors_redact_private_bodies(raw, suffix):
    with pytest.raises(ValueError) as e:
        audit.decode(raw, suffix)
    assert 'PRIVATE_SECRET' not in str(e.value)


def test_yaml_dates_remain_serializable_and_mapping_keys_do_not_leak():
    value = audit.decode(b'created_at: 2020-01-01\nentries: []\n', '.yaml')
    assert value['created_at'] == '2020-01-01' and audit.digest(value)
    assert audit.items({'PRIVATE_KEY': 'private'}, '$.relationships')[0][1] == '$.relationships[ordinal:0]'


def test_symlinked_snapshot_is_denied_before_read(tmp_path, monkeypatch):
    private, reader, *_ = case(tmp_path)
    args = permit(private, reader)
    row = reader.reader.entries[reader.plan()['files'][0]['path']]
    blob = reader.reader.owners[row['path']].path.parent / row['snapshot']
    other = blob.with_name('unregistered-copy'); other.write_bytes(blob.read_bytes())
    blob.unlink(); blob.symlink_to(other)
    seen = observe(monkeypatch)
    with pytest.raises(ValueError, match='ordinary private'):
        reader.audit(**args)
    assert not seen


def test_nonregular_blob_and_approval_refused_without_open(tmp_path, monkeypatch):
    import os
    private, reader, *_ = case(tmp_path)
    args = permit(private, reader)
    row = reader.reader.entries[reader.plan()['files'][0]['path']]
    blob = reader.reader.owners[row['path']].path.parent / row['snapshot']
    blob.unlink(); os.mkfifo(blob)
    seen = observe(monkeypatch)
    with pytest.raises(ValueError, match='ordinary audit'):
        reader.audit(**args)
    assert not seen


def test_aggregate_quote_limit_checked_before_any_source(tmp_path, monkeypatch):
    _, first, _, _, proof = case(tmp_path)
    other = tmp_path / 'other'; other.mkdir()
    e = {**proof, 'start_char': 0, 'end_char': 1201, 'quote': 'x' * 1201}
    private, reader, *_ = case(other, {'workspace/configs/glossary.yaml': {
        'entries': [{'source_term': 'PRIVATE', 'source_evidence': [e, e]}]}})
    seen = observe(monkeypatch)
    summary = reader.audit(**permit(private, reader))
    assert summary['provenance_statuses'] == {'invalid_source_proof': 1}
    assert 'source_original' not in seen


def test_output_bound_preserves_partial_failure_without_summary(tmp_path, monkeypatch):
    private, reader, *_ = case(tmp_path)
    monkeypatch.setitem(audit.LIMITS, 'output_bytes', 1)
    args = permit(private, reader)
    with pytest.raises(ValueError, match='output bound'):
        reader.audit(**args)
    assert not (args['output'] / 'summary.json').exists()
