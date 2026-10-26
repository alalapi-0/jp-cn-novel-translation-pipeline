"""Separate historical text from a frozen-prompt, controlled execution baseline.

These are comparison records, never canonical/approval writers. Declared condition
identity is not external provenance; callers must use the pinned development reader.
"""
from copy import deepcopy
import hashlib
import json
import re

from .response_extractor import extract_translations
from .validator import validate_draft_items

FIELDS = ('source', 'code', 'prompt', 'knowledge', 'provider', 'model', 'parameters', 'context')


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode()).hexdigest()


def text_sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def condition(identity, detail):
    value = {'status': 'unknown' if identity is None else 'known', 'identity': identity, 'detail': detail}
    _validate_condition(value)
    return value


def _validate_condition(value):
    if (not isinstance(value, dict) or set(value) != {'status', 'identity', 'detail'}
            or value['status'] not in ('known', 'unknown') or not isinstance(value['detail'], str)
            or not value['detail']
            or value['status'] == 'unknown' and value['identity'] is not None
            or value['status'] == 'known' and (not isinstance(value['identity'], str)
                or re.fullmatch('[0-9a-f]{64}', value['identity']) is None)):
        raise ValueError('unverified baseline condition identity')


def compare_conditions(old, rerun, adaptations):
    if (not isinstance(adaptations, list) or not adaptations
            or any(not isinstance(x, str) or not x for x in adaptations)):
        raise ValueError('controlled baseline requires explicit adapter differences')
    for values in (old, rerun):
        if not isinstance(values, dict) or set(values) != set(FIELDS):
            raise ValueError('incomplete baseline condition set')
        for value in values.values():
            _validate_condition(value)
    rows = {}
    for field in FIELDS:
        a, b = old[field], rerun[field]
        status = ('unknown' if a['status'] == 'unknown' or b['status'] == 'unknown'
                  else 'match' if a['identity'] == b['identity'] else 'different')
        rows[field] = {'status': status, 'B_old': deepcopy(a), 'B_framework_adapter': deepcopy(b)}
    return {'condition_comparison': rows,
            'known_condition_identities_match': all(x['status'] == 'match' for x in rows.values()),
            'strict_same_conditions': False,
            'comparability': 'not_same_condition_reproduction',
            'adapter_differences': list(adaptations),
            'framework_effect_attribution': 'prohibited',
            'reason': 'Historical text and adapted rerun are distinct baselines;unknowns are not matching evidence.'}


def source_identity(case):
    if not isinstance(case, dict):
        raise ValueError('baseline source case must be an object')
    source = case.get('source'); anchor = case.get('source_anchor'); span = case.get('source_span')
    unit = case.get('whole_source_unit')
    if (not isinstance(source, str) or not source.strip() or not isinstance(anchor, list) or len(anchor) != 3
            or anchor[0] not in ('JP_TO_CN', 'CN_TO_JP') or not isinstance(anchor[1], str) or not anchor[1]
            or not isinstance(anchor[2], str) or re.fullmatch('[0-9a-f]{64}', anchor[2]) is None
            or not isinstance(span, list) or len(span) != 2 or any(type(x) is not int for x in span)
            or not 0 <= span[0] < span[1] or span[1] - span[0] != len(source)
            or not isinstance(unit, dict) or unit.get('source_revision') != anchor[2]
            or unit.get('partition') != 'whole_source/1' or unit.get('coordinate') != 'unicode_codepoint_half_open'):
        raise ValueError('unknown complete-source baseline lineage')
    whole_span = unit.get('document_span')
    if (not isinstance(whole_span, list) or len(whole_span) != 2 or whole_span[0] != 0
            or any(type(x) is not int for x in whole_span) or whole_span[1] < span[1]):
        raise ValueError('fragment cannot replace complete-source budget identity')
    return digest({'anchor': anchor, 'span': span, 'excerpt_sha256': text_sha(source)})


def build_pair(case, raw_output, old_conditions, rerun_conditions, adaptations):
    """Build a validated private record, retaining failed raw-output identities."""
    if not isinstance(case, dict) or not isinstance(case.get('case_id'), str) or not case['case_id']:
        raise ValueError('baseline source case identity required')
    identity = source_identity(case)
    comparison = compare_conditions(old_conditions, rerun_conditions, adaptations)
    for values in (old_conditions, rerun_conditions):
        if values['source']['status'] != 'known' or values['source']['identity'] != identity:
            raise ValueError('baseline source conditions differ from registered case')
    old = case.get('old_target')
    if (not isinstance(old, dict) or old.get('partition') != 'development'
            or old.get('source_anchor') != case['source_anchor'] or not isinstance(old.get('target_text'), str)
            or text_sha(old['target_text']) != old.get('target_revision')
            or not isinstance(old.get('record_id'), str) or re.fullmatch('[0-9a-f]{64}', old['record_id']) is None):
        raise ValueError('old baseline is not a version-bound development target')
    if not isinstance(raw_output, str):
        raise ValueError('raw baseline response must be retained as text')
    cid = case['case_id']; extraction = extract_translations(raw_output, [cid])
    validation = validate_draft_items(extraction.items, [cid], {cid: len(case['source'])})
    passed = extraction.parse_status == 'ok' and validation.passed
    new_text = extraction.items[0].translation if passed else None
    return {'schema': 'translation-baseline-pair/1', 'case_id': cid,
            'source_anchor': list(case['source_anchor']), 'source_span': list(case['source_span']),
            'source_excerpt_sha256': text_sha(case['source']), 'source_identity': identity,
            'whole_source_unit': deepcopy(case['whole_source_unit']),
            'B_old': {'status': 'unverified_legacy_candidate', 'record_id': old['record_id'],
                      'text': old['target_text'], 'target_revision': old['target_revision'],
                      'conditions': deepcopy(old_conditions), 'legacy_approval': 'unverified;not a reference truth'},
            'B_framework': {'status': 'strict_historical_execution_unavailable',
                            'reason': 'Original provider/model/assets/runtime not reproduced;see explicit adapter baseline.'},
            'B_framework_adapter': {'status': 'structurally_validated_candidate' if passed else 'failed',
                                    'execution_mode': 'agent_quota_translation', 'text': new_text,
                                    'target_revision': text_sha(new_text) if passed else None,
                                    'raw_output_sha256': text_sha(raw_output), 'parse_status': extraction.parse_status,
                                    'parse_errors': list(extraction.parse_errors), 'validation': validation.to_dict(),
                                    'conditions': deepcopy(rerun_conditions)},
            'comparison': comparison, 'review_actor_type': 'agent_proxy', 'approval_state': 'not_granted',
            'auto_acceptance_enabled': False, 'canonical_write': False,
            'interpretation': 'Paired text observations only;not a framework improvement estimate or semantic acceptance.'}
