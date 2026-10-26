#!/usr/bin/env python3
"""Pinned, body-redacted census of registered legacy knowledge.

Metadata preparation opens no snapshots. A separately approved sealed census
can inspect the fixed containers, but never releases a proposition, target,
style note or source quote. Located evidence is not semantic verification.
This is a private audit adapter, not a production knowledge consumer.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import stat
import sys
import time

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'scripts'))
from build_optimization_split import DevelopmentReader, private_path

CATEGORIES = ('glossary', 'character', 'relationship', 'address', 'world', 'summary',
              'tm_pair', 'derived_hint', 'creative_pattern', 'metadata', 'unknown')
STRUCTURED = {'structured_knowledge', 'structured_knowledge_or_tm'}
LIMITS = {'file_bytes': 16 * 1024 * 1024, 'total_bytes': 32 * 1024 * 1024,
          'records': 100000, 'evidence_per_record': 8, 'quote_codepoints': 2400,
          'source_proof_reads': 1024, 'source_proof_bytes': 32 * 1024 * 1024,
          'output_bytes': 64 * 1024 * 1024}
INLINE_LIMITS = {'nodes': 1000000, 'depth': 64, 'output_bytes': 64 * 1024 * 1024,
                 'seconds': 120}
INLINE_FIELDS = {
    'glossary': 'glossary', 'terms': 'glossary', 'terminology': 'glossary', '术语': 'glossary',
    'character': 'character', 'characters': 'character', '角色': 'character', '人物': 'character',
    'relationship': 'relationship', 'relationships': 'relationship', 'relations': 'relationship',
    '关系': 'relationship', '人际关系': 'relationship',
    'address': 'address', 'address_map': 'address', 'forms_of_address': 'address', '称谓': 'address', '称呼': 'address',
    'world': 'world', 'world_bible': 'world', 'world_setting': 'world', '世界观': 'world', '设定': 'world',
    'summary': 'summary', 'summaries': 'summary', 'chapter_summary': 'summary',
    'personality_summary': 'summary', '摘要': 'summary', '梗概': 'summary'}
COLLECTION_FIELDS = {'entries', 'characters', 'relationships', 'address_map', 'summaries',
                     'approved_pairs', 'machine_pairs', 'term_candidates', 'proper_noun_candidates',
                     'phrase_candidates', 'knowledge_claims'}
WIRE_FIELDS = COLLECTION_FIELDS | {'summary', 'personality_summary', 'chapter_summary'}


def protected_field(key):
    """Classify the key before looking up its child. Never inspect that value."""
    key = key.casefold().replace('-', '_')
    for group, tokens in [
            ('credential', ('secret', 'password', 'credential', 'token', 'api_key', 'cookie')),
            ('prompt', ('prompt',)), ('style', ('style', 'preference', 'personal')),
            ('cache', ('cache',)),
            ('raw_text', ('text', 'quote', 'content', 'notes', 'description', 'excerpt', 'raw', '正文'))]:
        if any(token in key for token in tokens):
            return group
    return None


def wire_prefixes(pointer):
    """Known census routes, including their containers, are not new envelopes."""
    parts = re.findall(r'\$|\.[a-z_]+|\[(?:ordinal:)?[0-9]+\]', pointer)
    if (not parts or parts[0] != '$' or ''.join(parts) != pointer
            or any(p.startswith('.') and p[1:] not in WIRE_FIELDS for p in parts)):
        raise ValueError('unsupported original record pointer')
    return {''.join(parts[:i]) for i in range(1, len(parts) + 1)}


def inline_nodes(value, kind, *, guard, limits=None):
    """Ordinal tree coverage; no scalar value or protected subtree is hashed.

    Wire pointers exist only for matching the older fixed-field census. Public
    structural pointers contain member/list ordinals, never arbitrary keys.
    """
    limits = INLINE_LIMITS if limits is None else limits
    stack = [(value, '$', '$', 0, None)]
    total = 0
    while stack:
        node, pointer, wire, depth, edge = stack.pop()
        guard(); total += 1
        if total > limits['nodes'] or depth > limits['depth']:
            raise ValueError('inline structural traversal bound exceeded')
        typ = type(node)
        if typ not in {dict, list, str, int, float, bool, type(None)}:
            raise ValueError('unsupported inline structural node')
        row = {'pointer': pointer, 'wire_pointer': wire, 'depth': depth,
               'shape': typ.__name__, 'category_hint': 'unknown', 'field_sha256': None}
        if edge is not None:
            row.update(edge)
        if typ in {dict, list}:
            row['children'] = len(node)
            if total + len(stack) + len(node) > limits['nodes']:
                raise ValueError('inline structural traversal bound exceeded')
        yield row
        if typ is list:
            stack.extend((node[i], f'{pointer}/l{i}', f'{wire}[{i}]', depth + 1, None)
                         for i in range(len(node) - 1, -1, -1))
        elif typ is dict:
            collection = wire.rsplit('.', 1)[-1] in COLLECTION_FIELDS or (wire == '$' and kind == 'creative_pattern')
            children = []
            # Iterating keys instead of items makes pruning precede child access.
            for i, key in enumerate(node):
                if type(key) is not str:
                    raise ValueError('unsupported inline structural mapping key')
                child_wire = f'{wire}.{key}' if not collection and key in WIRE_FIELDS else f'{wire}[ordinal:{i}]'
                child_pointer = f'{pointer}/m{i}'
                normalized = key.casefold().replace('-', '_')
                edge = {'category_hint': INLINE_FIELDS.get(normalized, 'unknown'),
                        'field_sha256': hashlib.sha256(key.encode()).hexdigest()}
                group = protected_field(key)
                character_summary = (kind == 'character' and key == 'personality_summary'
                                     and re.fullmatch(r'\$\.characters\[(?:ordinal:)?[0-9]+\]', wire))
                if character_summary:
                    summary = node[key]
                    if type(summary) not in {str, type(None)}:
                        raise ValueError('invalid schema character summary type')
                    group = None
                if group is not None:
                    total += 1
                    if total > limits['nodes'] or depth + 1 > limits['depth']:
                        raise ValueError('inline structural traversal bound exceeded')
                    yield {'pointer': child_pointer, 'wire_pointer': child_wire, 'depth': depth + 1,
                           'shape': 'pruned', 'protected_group': group, **edge}
                    continue
                children.append((summary if character_summary else node[key],
                                 child_pointer, child_wire, depth + 1, edge))
            stack.extend(reversed(children))


def character_summary_envelopes(raw, descriptor, prior_records, *, guard, limits=None):
    """Structural fiction-summary coverage, never a proposition or scalar digest.

    The frozen artifact digest binds the original row pointers and census hashes.
    Only the characters collection and its exact schema summary field are looked
    up; other character fields are not accessed or rehashed.
    """
    guard()
    path = descriptor['path']; revision = descriptor['sha256']
    if (family(path) != 'character' or type(raw) is not bytes
            or len(raw) > LIMITS['file_bytes']
            or hashlib.sha256(raw).hexdigest() != revision):
        raise ValueError('character summary frozen artifact differs')
    document = decode(raw, Path(path).suffix)
    characters = document.get('characters') if type(document) is dict else None
    if type(characters) not in {list, dict}:
        raise ValueError('invalid schema character collection')
    known = {}
    for old in prior_records:
        if old['artifact_path'] != path or old['category'] != 'character':
            continue
        pointer = old['record_pointer']
        if (pointer in known or old['artifact_revision'] != revision
                or old['record_id'] != digest([path, revision, pointer])
                or not re.fullmatch('[0-9a-f]{64}', old['record_sha256'])):
            raise ValueError('original character census identity differs')
        known[pointer] = old
    filtered = []; links = []
    for index, record in enumerate(characters if type(characters) is list else characters.values()):
        guard()
        pointer = (f'$.characters[{index}]' if type(characters) is list
                   else f'$.characters[ordinal:{index}]')
        if type(record) is not dict or 'personality_summary' not in record or pointer not in known:
            raise ValueError('missing schema character summary or original identity')
        value = record['personality_summary']
        if type(value) not in {str, type(None)}:
            raise ValueError('invalid schema character summary type')
        filtered.append({'personality_summary': value}); links.append((pointer, known[pointer]))
    if len(known) != len(links):
        raise ValueError('original character census coverage differs')
    # The narrow view excludes every other field before any traversal.
    nodes = list(inline_nodes({'characters': filtered}, 'character', guard=guard, limits=limits))
    summaries = [r for r in nodes if r['category_hint'] == 'summary']
    if len(summaries) != len(links) or any(r['shape'] not in {'str', 'NoneType'} for r in summaries):
        raise ValueError('schema character summary structural coverage differs')
    return [{'record_id': old['record_id'], 'record_sha256': old['record_sha256'],
             'artifact_revision': revision, 'schema_path': pointer + '.personality_summary',
             'field_id': digest([old['record_id'], 'personality_summary']),
             'category': 'summary', 'present': True, 'scalar_type': row['shape'],
             'semantic_verified': False, 'provenance_verified': False,
             'consumer': False, 'human_approved': False, 'adoption': False}
            for (pointer, old), row in zip(links, summaries)]


def unique_pairs(pairs):
    result = {}
    for k, v in pairs:
        if type(k) is not str or k in result:
            raise ValueError('ambiguous knowledge mapping')
        result[k] = v
    return result


class AuditLoader(yaml.SafeLoader):
    yaml_implicit_resolvers = {
        k: [(tag, pattern) for tag, pattern in values if tag != 'tag:yaml.org,2002:timestamp']
        for k, values in yaml.SafeLoader.yaml_implicit_resolvers.items()}

    def construct_mapping(self, node, deep=False):
        return unique_pairs((self.construct_object(k, deep=deep), self.construct_object(v, deep=deep))
                            for k, v in node.value)


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def ordinary(path, max_bytes):
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_size > max_bytes:
        raise ValueError('bounded ordinary audit file required')
    return path


def family(path):
    """Route registered paths, never entity names or a body's self-declared type."""
    p = Path(path)
    if p.parent == Path('workspace/configs'):
        return {'glossary.yaml': 'glossary', 'character_profile.yaml': 'character',
                'world_bible.yaml': 'world', 'chapter_summaries.yaml': 'summary',
                'chapter_summaries.json': 'summary'}.get(p.name, 'unknown')
    if p.parent == Path('workspace/assets/translation_memory') and p.suffix == '.json':
        return 'tm'
    if p.parts[:2] == ('workspace', 'asset_extraction_runs'):
        if p.name in {'narrative_assets.jsonl', 'game_design_assets.jsonl',
                      'naming_pattern_assets.jsonl', 'chapter_structure_assets.jsonl'}:
            return 'creative_pattern'
        if p.name == 'extraction_metadata.json':
            return 'metadata'
    return 'unknown'


def decode(raw, suffix):
    """Bounded safe syntax only; parser diagnostics may contain private excerpts."""
    try:
        text = raw.decode('utf-8')
        if suffix == '.jsonl':
            return [json.loads(line, object_pairs_hook=unique_pairs)
                    for line in text.splitlines() if line.strip()]
        if suffix in {'.yaml', '.yml'}:
            # Aliases can hide cycles or amplify traversals; legacy audits do not
            # need YAML object sharing. Reject before constructing any document.
            if any(isinstance(t, (yaml.tokens.AliasToken, yaml.tokens.AnchorToken))
                   for t in yaml.scan(text)):
                raise ValueError('YAML references are not supported')
            return yaml.load(text, Loader=AuditLoader)
        return json.loads(text, object_pairs_hook=unique_pairs)
    except (ValueError, UnicodeError, yaml.YAMLError, RecursionError):
        raise ValueError('registered knowledge container cannot be safely decoded') from None


def items(value, pointer, *, nullable=False):
    if value is None and nullable:
        return []
    if type(value) is list:
        return [(v, f'{pointer}[{i}]') for i, v in enumerate(value)]
    if type(value) is dict:
        # Do not expose arbitrary mapping keys (which can themselves be names).
        return [(v, f'{pointer}[ordinal:{i}]') for i, v in enumerate(value.values())]
    raise ValueError('unsupported registered collection shape')


def records(value, kind):
    """Enumerate known wire fields. Opaque fields remain explicitly unexamined."""
    if kind == 'creative_pattern':
        for v, ptr in items(value, '$'):
            yield 'creative_pattern', v, ptr
        return
    if type(value) is not dict:
        raise ValueError('registered knowledge object required')
    if kind == 'metadata':
        yield 'metadata', value, '$'
        return
    if kind == 'tm':
        for key in ('approved_pairs', 'machine_pairs'):
            for v, ptr in items(value.get(key), f'$.{key}', nullable=True):
                yield 'tm_pair', v, ptr
        for key in ('term_candidates', 'proper_noun_candidates', 'phrase_candidates'):
            for v, ptr in items(value.get(key), f'$.{key}', nullable=True):
                yield 'derived_hint', v, ptr
        # Cached prompt/style/source-ref values are never enumerated or released.
        return
    key = {'glossary': 'entries', 'character': 'characters', 'world': 'entries',
           'summary': 'summaries'}[kind]
    for v, ptr in items(value.get(key), f'$.{key}'):
        yield kind, v, ptr
        if type(v) is not dict:
            continue
        if kind == 'character':
            for name, category in [('relationships', 'relationship'), ('address_map', 'address')]:
                for child, childptr in items(v.get(name), f'{ptr}.{name}', nullable=True):
                    yield category, child, childptr
        # An inline summary is a candidate fragment, not a chapter synopsis.
        for name in ('summary', 'personality_summary', 'chapter_summary'):
            if name in v and v[name] not in (None, ''):
                yield 'summary', v[name], f'{ptr}.{name}'
        claims = v.get('knowledge_claims', [])
        if type(claims) is not list:
            raise ValueError('invalid knowledge claim collection')
        for i, claim in enumerate(claims):
            category = claim.get('category') if type(claim) is dict else 'unknown'
            yield category if category in CATEGORIES else 'unknown', claim, f'{ptr}.knowledge_claims[{i}]'


class KnowledgeAudit:
    def __init__(self, root, manifest, expected_sha256):
        self.root = Path(root).resolve()
        self.manifest = Path(manifest).absolute()
        self.expected = expected_sha256
        self.reader = DevelopmentReader(self.root, self.manifest, self.expected)
        self._memory = digest({'split': self.reader.split, 'entries': self.reader.entries})

    def _check(self):
        if digest({'split': self.reader.split, 'entries': self.reader.entries}) != self._memory:
            raise PermissionError('frozen audit metadata mutated')
        for spec in [*self.reader.split['inputs'], {'path': str(self.manifest.relative_to(self.root)),
                                                   'sha256': self.expected}]:
            p = private_path(self.root, self.root / spec['path'])
            if hashlib.sha256(ordinary(p, 64 * 1024 * 1024).read_bytes()).hexdigest() != spec['sha256']:
                raise PermissionError('frozen audit input changed')

    def plan(self):
        self._check()
        files = []
        for row in sorted(self.reader.entries.values(), key=lambda r: r['path']):
            if row['category'] not in STRUCTURED:
                continue
            files.append({'path': row['path'], 'sha256': row.get('sha256'),
                          'bytes': row['bytes'], 'family': family(row['path']),
                          'frozen': row.get('freeze_status') == 'read_only_recoverable_version'})
        return {'schema': 'knowledge-audit-plan/1', 'split_sha256': self.expected,
                'version_inputs': deepcopy(self.reader.split['inputs']),
                'registered_paths': len(self.reader.entries),
                'frozen_records': sum(r.get('freeze_status') == 'read_only_recoverable_version'
                                      for r in self.reader.entries.values()),
                'source_files': self.reader.split['source_denominator'],
                'partitions': deepcopy(self.reader.split['partition_counts']),
                'categories': list(CATEGORIES), 'files': files, 'limits': dict(LIMITS),
                'body_projection': False, 'semantic_verification': False,
                'source_policy': 'development evidence only; holdout/unknown denied before source read',
                'opaque_fields': 'not semantically examined; no completeness claim for inline facts',
                'tm_policy': 'sealed pair/hint census only; all derived values withheld',
                'effects': 'sealed_deterministic_parse_only'}

    def inline_plan(self, *, prior_records, prior_sha256, prior_count):
        """Pin a new structural pass using metadata only, without blob access."""
        path = private_path(self.root, Path(prior_records))
        if (not re.fullmatch('[0-9a-f]{64}', prior_sha256)
                or type(prior_count) is not int or not 0 < prior_count <= LIMITS['records']):
            raise ValueError('bounded original record identity required')
        plan = self.plan()
        plan.update(schema='knowledge-inline-plan/1', effects='sealed_inline_structure_only',
                    prior_records={'path': str(path.relative_to(self.root)),
                                   'sha256': prior_sha256, 'count': prior_count},
                    inline_limits=dict(INLINE_LIMITS), source_policy='no source snapshot reads',
                    opaque_fields='structural only; all meaning remains unexamined',
                    protected_policy='prune by field label before child access; no value hashes')
        return plan

    def audit_inline(self, *, prior_records, prior_sha256, prior_count, approval_path,
                     approval_sha256, candidate_sha256, output):
        """One separately approved sealed structural pass; no source accessor."""
        plan = self.inline_plan(prior_records=prior_records, prior_sha256=prior_sha256,
                                prior_count=prior_count)
        approval = ordinary(private_path(self.root, Path(approval_path)), 16384).read_bytes()
        if hashlib.sha256(approval).hexdigest() != approval_sha256:
            raise PermissionError('exact inline approval required')
        permit = json.loads(approval, object_pairs_hook=unique_pairs)
        out = private_path(self.root, Path(output))
        if (not re.fullmatch('[0-9a-f]{64}', candidate_sha256)
                or permit.get('decision') != 'APPROVE' or permit.get('runtime_authorized') is not True
                or permit.get('candidate_sha256') != candidate_sha256
                or permit.get('plan_sha256') != digest(plan)
                or permit.get('effects') != 'sealed_inline_structure_only'
                or permit.get('output') != str(out.relative_to(self.root))
                or permit.get('model_operations') != 0 or permit.get('body_projection') is not False):
            raise PermissionError('inline approval differs from exact scope')
        deadline = datetime.fromisoformat(permit['effect_cutoff']); started = time.monotonic()
        def guard(*, recheck=False):
            if (deadline.tzinfo is None or datetime.now(timezone.utc) >= deadline
                    or time.monotonic() - started >= INLINE_LIMITS['seconds']):
                raise PermissionError('inline audit window closed')
            if recheck:
                self._check()
        guard(recheck=True)
        files = plan['files']
        if (sum(r['bytes'] for r in files) > LIMITS['total_bytes']
                or any(r['bytes'] > LIMITS['file_bytes'] or not r['frozen']
                       or r['family'] == 'unknown' for r in files)):
            raise PermissionError('unsupported inline container scope')
        # Output preexistence refuses the entire pass before prior data or blobs.
        out.mkdir(mode=0o700)
        prior = ordinary(private_path(self.root, Path(prior_records)), LIMITS['output_bytes']).read_bytes()
        if hashlib.sha256(prior).hexdigest() != prior_sha256:
            raise PermissionError('original census drifted')
        by_file = {}; known_routes = {}; identities = set(); pointers = set()
        fixed = {f['path']: f for f in files}
        for line in prior.decode('utf-8').splitlines():
            guard()
            row = json.loads(line, object_pairs_hook=unique_pairs)
            path, pointer = row['artifact_path'], row['record_pointer']
            if (path not in fixed or row['artifact_revision'] != fixed[path]['sha256']
                    or row['record_id'] != digest([path, fixed[path]['sha256'], pointer])
                    or not re.fullmatch('[0-9a-f]{64}', row['record_sha256'])
                    or row['category'] not in CATEGORIES or row['consumer_eligible'] is not False
                    or row['semantic_truth'] != 'not_verified' or row['human_approved_final'] is not False
                    or row['disposition'] != 'withheld_unverified'
                    or row['record_id'] in identities or (path, pointer) in pointers):
                raise ValueError('unexpected or duplicate original record link')
            identities.add(row['record_id']); pointers.add((path, pointer))
            known_routes.setdefault(path, set()).update(wire_prefixes(pointer))
            by_file.setdefault(path, {})[pointer] = {k: row[k] for k in
                ('record_id', 'record_sha256', 'record_pointer', 'category')}
        if len(identities) != prior_count:
            raise ValueError('original record denominator differs')
        del prior
        totals = Counter(); hints = Counter(); new_hints = Counter(); known_hints = Counter()
        protected = Counter(); file_results = []
        linked = set(); emitted = 0; coverage = hashlib.sha256()
        with (out / 'structure.jsonl').open('x', encoding='utf-8') as handle:
            def emit(row):
                nonlocal emitted
                guard()
                line = json.dumps(row, sort_keys=True, ensure_ascii=False) + '\n'
                emitted += len(line.encode())
                if emitted > INLINE_LIMITS['output_bytes']:
                    raise ValueError('inline output bound exceeded')
                handle.write(line)
            for spec in files:
                guard(recheck=True)
                entry = self.reader.entries[spec['path']]; owner = self.reader.owners[entry['path']]
                ordinary(private_path(self.root, owner.path.parent / entry['snapshot']), LIMITS['file_bytes'])
                raw = owner.read(entry)
                value = decode(raw, Path(entry['path']).suffix)
                local = Counter(); seen_paths = set(); original = by_file.get(spec['path'], {})
                remaining = {**INLINE_LIMITS, 'nodes': INLINE_LIMITS['nodes'] - totals['nodes']}
                for node in inline_nodes(value, spec['family'], guard=guard, limits=remaining):
                    totals['nodes'] += 1; local['nodes'] += 1
                    if totals['nodes'] > INLINE_LIMITS['nodes'] or node['pointer'] in seen_paths:
                        raise ValueError('duplicate path or total inline node bound exceeded')
                    seen_paths.add(node['pointer'])
                    wire = node.pop('wire_pointer')
                    known_route = wire in known_routes.get(spec['path'], set())
                    link = original.get(wire)
                    if link:
                        if link['record_id'] in linked:
                            raise ValueError('duplicate visited original record')
                        linked.add(link['record_id']); local['known_records'] += 1
                    coverage.update(json.dumps([spec['sha256'], node], sort_keys=True).encode())
                    if node['shape'] == 'pruned':
                        protected[node['protected_group']] += 1; local['protected_fields'] += 1
                    if node['category_hint'] != 'unknown':
                        hints[node['category_hint']] += 1; local['category_hints'] += 1
                        (known_hints if known_route else new_hints)[node['category_hint']] += 1
                    elif node['shape'] not in {'dict', 'list', 'pruned'}:
                        local['unexamined_scalars'] += 1
                    if node['shape'] in {'dict', 'list'} or node['shape'] == 'pruned' or link or node['category_hint'] != 'unknown':
                        opaque = not known_route and node['shape'] in {'dict', 'list'} and node['category_hint'] == 'unknown'
                        totals['opaque_structural_envelopes'] += int(opaque)
                        emit({'container_sha256': spec['sha256'], **node, 'known_record': link,
                              'known_structural_route': known_route,
                              'opaque_structural_envelope': opaque,
                              'disposition': 'withheld_unverified', 'semantic_truth': 'not_verified',
                              'consumer_eligible': False, 'human_approved_final': False})
                        totals['emitted_envelopes'] += 1
                if any(r['record_id'] not in linked for r in original.values()):
                    raise ValueError('original record link not structurally visited')
                file_results.append({'path': spec['path'], 'sha256': spec['sha256'], **dict(local)})
                del raw, value
        guard(recheck=True)
        if linked != identities:
            raise ValueError('original record coverage differs')
        summary = {'schema': 'knowledge-inline-summary/1', 'plan_sha256': digest(plan),
                   'candidate_sha256': candidate_sha256, 'files': file_results,
                   'file_denominator': len(files), 'input_bytes': sum(r['bytes'] for r in files),
                   'original_record_denominator': prior_count, 'known_records_linked': len(linked),
                   'original_records_sha256': prior_sha256, **dict(totals),
                   'category_hints': {k: hints[k] for k in CATEGORIES},
                   'known_route_category_hints': {k: known_hints[k] for k in CATEGORIES},
                   'new_field_category_hints': {k: new_hints[k] for k in CATEGORIES},
                   'protected_fields_unexamined': dict(protected),
                   'structural_coverage_sha256': coverage.hexdigest(), 'output_bytes': emitted,
                   'structure_sha256': hashlib.sha256((out / 'structure.jsonl').read_bytes()).hexdigest(),
                   'elapsed_seconds': time.monotonic() - started, 'knowledge_snapshot_reads': len(files),
                   'source_snapshot_reads': 0, 'model_operations': 0, 'body_projection': False,
                   'semantic_truth': 'not_verified', 'P3_R01_T02_complete': False,
                   'consumer_eligible': False, 'human_approved_final': False, 'production_adoption': False,
                   'unexamined': 'all scalar meanings and protected subtrees; key hints do not establish facts or absence'}
        # Keep the complete output, including its finite summary, within one cap.
        summary_bytes = (json.dumps(summary, ensure_ascii=False, indent=2) + '\n').encode()
        if emitted + len(summary_bytes) > INLINE_LIMITS['output_bytes']:
            raise ValueError('inline combined output bound exceeded')
        (out / 'summary.json').write_bytes(summary_bytes)
        guard(recheck=True)
        return summary

    def _evidence(self, record, guard):
        if type(record) is not dict:
            return 'missing_source_proof', []
        evidence = record.get('source_evidence')
        if type(evidence) is not list or not evidence:
            return ('unsupported_catalog_or_missing_document_proof'
                    if record.get('evidence') else 'missing_source_proof'), []
        if len(evidence) > LIMITS['evidence_per_record']:
            return 'invalid_source_proof', []
        source_rows = self.reader.split['chapters']; chosen = []; quote_chars = 0
        for e in evidence:
            if type(e) is not dict:
                return 'invalid_source_proof', []
            matches = [r for r in source_rows if all(r[k] == e.get(k) for k in
                       ('language_direction', 'chapter_id', 'source_revision'))]
            if len(matches) != 1:
                return 'unknown_source_identity', []
            if matches[0]['partition'] != 'development':
                return 'holdout_dependency', []
            a, b, quote = e.get('start_char'), e.get('end_char'), e.get('quote')
            if (type(a) is not int or type(b) is not int or not 0 <= a < b
                    or type(quote) is not str or not quote or len(quote) != b - a):
                return 'invalid_source_proof', []
            quote_chars += len(quote)
            if quote_chars > LIMITS['quote_codepoints']:
                return 'invalid_source_proof', []
            chosen.append((matches[0], a, b, quote))
        # Validate the complete dependency list before reading any source body.
        located = []
        for row, a, b, quote in chosen:
            guard(recheck=True)
            source_bytes = self.reader.entries[row['path']]['bytes']
            if (self.source_reads >= LIMITS['source_proof_reads']
                    or self.source_bytes + source_bytes > LIMITS['source_proof_bytes']):
                raise ValueError('sealed source proof read bound exceeded')
            source_entry = self.reader.entries[row['path']]
            owner = self.reader.owners[row['path']]
            ordinary(private_path(self.root, owner.path.parent / source_entry['snapshot']), LIMITS['file_bytes'])
            text = self.reader.source_context((row['language_direction'], row['chapter_id'], row['source_revision']))
            self.source_reads += 1
            self.source_bytes += source_bytes
            if not b <= len(text) or text[a:b] != quote:
                return 'stale_or_inexact_source_span', []
            located.append({'chapter_id': row['chapter_id'], 'language_direction': row['language_direction'],
                            'source_revision': row['source_revision'], 'start_char': a, 'end_char': b,
                            'quote_sha256': hashlib.sha256(quote.encode()).hexdigest()})
        return 'located_development_evidence_semantics_unverified', located

    def audit(self, *, approval_path, approval_sha256, candidate_sha256, output):
        """One sealed census; caller must obtain fresh exact independent approval.

        This validates the recorded decision's identity, not an OS sandbox or a
        cryptographic Governor identity. It exposes no knowledge-value accessor.
        """
        plan = self.plan(); plan_hash = digest(plan)
        p = private_path(self.root, Path(approval_path))
        raw = ordinary(p, 16384).read_bytes()
        if len(raw) > 16384 or hashlib.sha256(raw).hexdigest() != approval_sha256:
            raise PermissionError('exact bounded approval receipt required')
        permit = json.loads(raw)
        if (not re.fullmatch('[0-9a-f]{64}', candidate_sha256)
                or permit.get('candidate_sha256') != candidate_sha256
                or permit.get('plan_sha256') != plan_hash or permit.get('decision') != 'APPROVE'
                or permit.get('runtime_authorized') is not True
                or permit.get('effects') != 'sealed_deterministic_parse_only'
                or permit.get('model_operations') != 0
                or permit.get('body_projection') is not False):
            raise PermissionError('sealed audit approval does not match')
        out = private_path(self.root, Path(output))
        if permit.get('output') != str(out.relative_to(self.root)):
            raise PermissionError('sealed audit output differs from approval')
        deadline = datetime.fromisoformat(permit['effect_cutoff'])
        def guard(*, recheck=False):
            if recheck:
                self._check()
            if deadline.tzinfo is None or datetime.now(timezone.utc) >= deadline:
                raise PermissionError('sealed audit window closed')
        guard(recheck=True)
        files = plan['files']
        if (sum(r['bytes'] for r in files) > LIMITS['total_bytes']
                or any(r['bytes'] > LIMITS['file_bytes'] or not r['frozen']
                       or r['family'] == 'unknown' for r in files)):
            raise PermissionError('unsupported registered knowledge scope')
        out.mkdir(mode=0o700)  # Existing outputs are never replaced or resumed.
        statuses = Counter(); categories = Counter(); file_results = []
        self.source_reads = 0; self.source_bytes = 0; body_reads = 0; total = 0; ids = set(); emitted = 0
        with (out / 'records.jsonl').open('x', encoding='utf-8') as handle:
            for spec in files:
                guard(recheck=True); row = self.reader.entries[spec['path']]
                owner = self.reader.owners[row['path']]
                ordinary(private_path(self.root, owner.path.parent / row['snapshot']), LIMITS['file_bytes'])
                raw = self.reader.owners[row['path']].read(row); body_reads += 1
                value = decode(raw, Path(row['path']).suffix)
                count = 0; local = Counter()
                for category, record, pointer in records(value, spec['family']):
                    guard(); total += 1; count += 1
                    if total > LIMITS['records']:
                        raise ValueError('sealed census record bound exceeded')
                    rid = digest([row['path'], row['sha256'], pointer])
                    if rid in ids:
                        raise ValueError('duplicate sealed knowledge record')
                    ids.add(rid)
                    if category in {'tm_pair', 'derived_hint', 'creative_pattern', 'metadata', 'unknown'}:
                        status, locations = 'derived_or_unsupported_provenance', []
                    else:
                        status, locations = self._evidence(record, guard)
                    # Every result stays withheld. Exact quotation proves only
                    # geometry; it never qualifies this proposition for prompts.
                    result = {'record_id': rid, 'artifact_path': row['path'],
                              'artifact_revision': row['sha256'], 'record_pointer': pointer,
                              'record_sha256': digest(record), 'category': category,
                              'provenance_status': status, 'disposition': 'withheld_unverified',
                              'semantic_truth': 'not_verified', 'human_approved_final': False,
                              'consumer_eligible': False, 'source_locations': locations}
                    line = json.dumps(result, ensure_ascii=False, sort_keys=True) + '\n'
                    emitted += len(line.encode('utf-8'))
                    if emitted > LIMITS['output_bytes']:
                        raise ValueError('sealed census output bound exceeded')
                    handle.write(line)
                    statuses[status] += 1; categories[category] += 1; local[category] += 1
                file_results.append({'path': row['path'], 'sha256': row['sha256'],
                                     'records': count, 'categories': dict(local),
                                     'status': 'sealed_census_complete_semantics_unverified'})
                del value, raw
        guard(recheck=True)
        summary = {'schema': 'knowledge-audit-summary/1', 'plan_sha256': plan_hash,
                   'candidate_sha256': candidate_sha256, 'files': file_results,
                   'file_denominator': len(files), 'record_denominator': total,
                   'categories': {k: categories[k] for k in CATEGORIES},
                   'provenance_statuses': dict(statuses), 'withheld_records': total,
                   'knowledge_snapshot_reads': body_reads, 'source_snapshot_reads': self.source_reads,
                   'source_snapshot_bytes': self.source_bytes,
                   'model_body_releases': 0, 'target_field_releases': 0,
                   'holdout_source_reads': 0, 'model_operations': 0,
                   'records_sha256': hashlib.sha256((out / 'records.jsonl').read_bytes()).hexdigest(),
                   'inline_unknown_fields': 'unexamined; absence of a category is not proof of no inline facts',
                   'semantic_truth': 'not_verified', 'P3_R01_T02_complete': False,
                   'production_adoption': False, 'human_approved_final': False}
        (out / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
        return summary
