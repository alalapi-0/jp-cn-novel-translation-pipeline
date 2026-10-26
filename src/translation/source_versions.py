"""Source-version bindings and read-only legacy correspondence proposals.

Logical IDs locate text across revisions; they never transfer translation,
review, approval or cache validity. Duplicate/resegmented matches remain
proposals requiring their own dependency checks.
"""
from collections import Counter
import hashlib
import json
import re

SCHEMA = 'segment-source-binding/1'
NORMALIZATION = 'splitlines_to_lf_and_outer_strip'


def text_sha(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def value_sha(value):
    return text_sha(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')))


def _digest(value):
    return isinstance(value, str) and re.fullmatch(r'[0-9a-f]{64}', value) is not None


def make_source_binding(*, chapter_id, source_revision, document_length, source_text,
                        source_spans, occurrence=1, duplicate_count=1):
    digest = text_sha(source_text)
    value = {'schema': SCHEMA, 'chapter_id': chapter_id, 'source_revision': source_revision,
             'document_length': document_length, 'source_sha256': digest,
             'logical_id': f'{chapter_id}:seg:{digest}:{occurrence}',
             'source_spans': [list(span) for span in source_spans], 'normalization': NORMALIZATION,
             'occurrence': occurrence, 'duplicate_count': duplicate_count,
             'mapping_status': 'unique_source' if duplicate_count == 1 else 'duplicate_source_requires_review'}
    value['binding_sha256'] = value_sha(value)
    return validate_source_binding(value, source_text)


def validate_source_binding(value, source_text, *, document_text=None):
    fields = {'schema', 'chapter_id', 'source_revision', 'document_length', 'source_sha256',
              'logical_id', 'source_spans', 'normalization', 'occurrence', 'duplicate_count',
              'mapping_status', 'binding_sha256'}
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError('missing or unknown source binding fields')
    if (value['schema'] != SCHEMA or value['normalization'] != NORMALIZATION
            or not isinstance(source_text, str) or not source_text.strip()
            or not isinstance(value['chapter_id'], str) or not value['chapter_id'].strip()
            or not _digest(value['source_revision']) or not _digest(value['binding_sha256'])
            or value['source_sha256'] != text_sha(source_text)
            or type(value['document_length']) is not int or value['document_length'] <= 0
            or type(value['occurrence']) is not int or type(value['duplicate_count']) is not int
            or not 1 <= value['occurrence'] <= value['duplicate_count']
            or value['logical_id'] != f"{value['chapter_id']}:seg:{value['source_sha256']}:{value['occurrence']}"
            or value['mapping_status'] != ('unique_source' if value['duplicate_count'] == 1 else 'duplicate_source_requires_review')):
        raise ValueError('invalid source binding identity')
    spans = value['source_spans']; end = -1
    if not isinstance(spans, list) or not spans: raise ValueError('source spans required')
    for span in spans:
        if (not isinstance(span, list) or len(span) != 2 or any(type(n) is not int for n in span)
                or not 0 <= span[0] < span[1] <= value['document_length'] or span[0] < end):
            raise ValueError('invalid or overlapping source span')
        end = span[1]
    payload = {k: v for k, v in value.items() if k != 'binding_sha256'}
    if value_sha(payload) != value['binding_sha256']: raise ValueError('source binding digest changed')
    if document_text is not None:
        if len(document_text) != value['document_length'] or text_sha(document_text) != value['source_revision']:
            raise ValueError('source document revision changed')
        extracted = ''.join(document_text[a:b] for a, b in spans)
        if '\n'.join(extracted.splitlines()).strip() != source_text:
            raise ValueError('source spans do not reconstruct parsed text')
    return json.loads(json.dumps(value))  # callers cannot mutate the validated input through this copy


def dependency_versions(value):
    """Pinned selected dependencies only; withdrawal is represented by a new digest.

    Names are caller-selected local aliases, not paths or executable references.
    No source, knowledge, TM, or PSH approval is issued by this validation.
    """
    if not isinstance(value, dict) or len(value)>256:
        raise ValueError('invalid dependency versions')
    if any(not isinstance(k,str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,180}',k)
           or not _digest(v) for k,v in value.items()):
        raise ValueError('invalid dependency version entry')
    return dict(sorted(value.items()))


def review_dependencies(segment, source_text):
    """Optional modern dependencies; legacy content identities retain their shape."""
    result = {}
    if 'dependency_versions' in segment:
        result['dependency_versions_sha256'] = value_sha(dependency_versions(segment['dependency_versions']))
    if segment.get('source_binding') is not None:
        result['source_binding_sha256'] = validate_source_binding(segment['source_binding'], source_text)['binding_sha256']
    if 'dependency_sha256' in segment:
        if not _digest(segment['dependency_sha256']): raise ValueError('invalid review dependency digest')
        result['dependency_sha256'] = segment['dependency_sha256']
    if 'source_context_revision' in segment:
        if not _digest(segment['source_context_revision']): raise ValueError('invalid source context revision')
        result['source_context_revision'] = segment['source_context_revision']
    if 'draft_recovery_revision' in segment:
        if not _digest(segment['draft_recovery_revision']): raise ValueError('invalid draft recovery revision')
        result['draft_recovery_revision'] = segment['draft_recovery_revision']
    return result


def propose_source_migration(old, new, *, max_group=4):
    """Bounded text-location proposals. No file access and no target/approval copy."""
    if type(max_group) is not int or not 1 <= max_group <= 4:
        raise ValueError('migration groups require a bounded size from 1 to 4')
    mappings = []; old_used = set(); new_used = set()
    old_rows = list(old.segments); new_rows = list(new.segments)

    def usable(row):
        binding = getattr(row, 'source_binding', None)
        if binding is None: return False
        return validate_source_binding(binding, row.source_text)['mapping_status'] == 'unique_source'

    old_ok = [usable(row) for row in old_rows]; new_ok = [usable(row) for row in new_rows]
    if old.chapter_id != new.chapter_id:
        old_ok = [False] * len(old_rows); new_ok = [False] * len(new_rows)
    for i, row in enumerate(old_rows):
        matches = [j for j, other in enumerate(new_rows) if old_ok[i] and new_ok[j]
                   and row.source_binding['logical_id'] == other.source_binding['logical_id']]
        if len(matches) == 1:
            j = matches[0]; old_used.add(i); new_used.add(j)
            mappings.append({'old_ids': [row.segment_id], 'new_ids': [new_rows[j].segment_id],
                'status': 'same_version' if row.source_binding == new_rows[j].source_binding else 'same_text_new_source_revision',
                'old_spans': [row.source_binding['source_spans']], 'new_spans': [new_rows[j].source_binding['source_spans']]})

    def groups(rows, ok, used):
        result = {}
        for start in range(len(rows)):
            for end in range(start + 1, min(len(rows), start + max_group) + 1):
                indexes = tuple(range(start, end))
                if any(i in used or not ok[i] for i in indexes): break
                key = ''.join(char for i in indexes for char in rows[i].source_text if not char.isspace())
                result.setdefault(key, []).append(indexes)
        return result

    left = groups(old_rows, old_ok, old_used); right = groups(new_rows, new_ok, new_used)
    for key, candidates in left.items():
        matches = right.get(key, [])
        if len(candidates) != 1 or len(matches) != 1: continue
        before, after = candidates[0], matches[0]
        if any(i in old_used for i in before) or any(i in new_used for i in after): continue
        old_used.update(before); new_used.update(after)
        mappings.append({'old_ids': [old_rows[i].segment_id for i in before],
                         'new_ids': [new_rows[i].segment_id for i in after],
                         'status': 'resegmented_location_candidate_not_semantic_proof',
                         'old_spans': [old_rows[i].source_binding['source_spans'] for i in before],
                         'new_spans': [new_rows[i].source_binding['source_spans'] for i in after]})
    return {'schema': 'source-migration-proposal/1', 'old_source_revision': getattr(old, 'source_revision', ''),
            'new_source_revision': getattr(new, 'source_revision', ''), 'mappings': mappings,
            'uncertain_old_ids': [row.segment_id for i, row in enumerate(old_rows) if i not in old_used],
            'unmapped_new_ids': [row.segment_id for i, row in enumerate(new_rows) if i not in new_used],
            'apply_allowed': False, 'target_reuse': False, 'approval_reuse': False,
            'dependency_validation': 'required_separately_before_any_consumer_reuse'}
