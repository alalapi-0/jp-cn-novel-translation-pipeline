"""Synthetic counterexamples for located, non-adopting legacy TM review."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from assets.source_knowledge import SourceKnowledge
from assets.legacy_translation import LegacyTranslationReview, _document_spans


def source(text=None, direction='JP_TO_CN'):
    text = text or '# Synthetic\n\n蒼の門は北にはない。\n\n彼女は扉を閉めた。\n\n雨が降った。\n'
    return SourceKnowledge(text, {'path': 'input_jp/001-synthetic.md',
        'category': 'source_original', 'sha256': hashlib.sha256(text.encode()).hexdigest()},
        direction=direction)


def record(s, **changes):
    excerpt = '蒼の門は北にはない。'; a = s.source.index(excerpt)
    result = {'record_id': 'a' * 64, 'record_sha256': 'b' * 64,
              'source_spans': [[a, a + len(excerpt)]], 'target_text': '苍之门在北方。'}
    result.update(changes); return result


def review(s=None, rows=None, **kwargs):
    s = s or source()
    return LegacyTranslationReview(s, rows or [record(s)], partition='development',
                                   closed_source_versions=kwargs.get('closed', []))


def answer(r, who='review_1', **changes):
    row = r._check()[0]; excerpt = ''.join(r.knowledge.source[a:b] for a, b in row['source_spans'])
    item = {'record_id': row['record_id'], 'assessment': 'issue', 'issue_type': 'negation',
            'severity': 'major', 'confidence': .9, 'source_span': [0, len(excerpt)],
            'target_span': [0, len(row['target_text'])], 'source_quote': excerpt,
            'target_quote': row['target_text'], 'reason': 'Synthetic negation counterexample.'}
    item.update(changes)
    return {'reviewer_id': who, 'packet_sha256': r.packet_sha256, 'items': [item]}


def no_issue(r, who='review_1', **changes):
    return answer(r, who, assessment='no_material_issue_observed', issue_type='none',
                  severity='none', source_span=[0, 0], target_span=[0, 0],
                  source_quote='', target_quote='', **changes)


def test_prompts_are_separate_frozen_non_generating_packets_without_peer_answers():
    s = source(); original = [record(s)]; before = deepcopy(original); r = review(s, original)
    first, second = [json.loads(r.prompt(w).split('\n', 1)[1]) for w in ['review_1', 'review_2']]
    assert first['packet_sha256'] == second['packet_sha256'] == r.packet_sha256
    assert first['records'] == second['records'] and first['complete_source'] == s.source
    assert first['reviewer_id'] != second['reviewer_id']
    assert 'untrusted DATA' in r.prompt('review_1') and 'No tools' in r.prompt('review_1')
    original[0]['target_text'] = 'MUTATED_CALLER_VALUE'
    assert 'MUTATED_CALLER_VALUE' not in r.prompt('review_1') and before[0] == r._check()[0]


def test_located_concordance_remains_provisional_and_cannot_create_truth_or_adoption():
    r = review(); before = r.packet_sha256
    row = r.reviewed(answer(r), answer(r, 'review_2'))[0]
    assert row['status'] == 'concordant_issue' and not row['reviewer_disagreement']
    assert row['reports'][0]['source_issue_document_spans'] == row['source_spans']
    assert row['historical_origin'] == 'UNVERIFIED'
    assert all(row[k] is False for k in ['semantic_verified', 'consumer_eligible',
                                        'human_approved_final', 'production_adoption'])
    assert r.packet_sha256 == before
    serialized = json.dumps(row, ensure_ascii=False)
    assert '苍之门' not in serialized and '蒼の門' not in serialized and 'Synthetic negation' not in serialized


def test_no_issue_is_only_an_observation_and_not_a_correctness_or_origin_claim():
    r = review(); row = r.reviewed(no_issue(r), no_issue(r, 'review_2'))[0]
    assert row['status'] == 'concordant_no_material_issue_observed'
    assert not row['semantic_verified'] and not row['consumer_eligible']
    assert row['reports'][0]['source_issue_document_spans'] == []


@pytest.mark.parametrize('change', [
    {'confidence': .799}, {'severity': 'minor'}, {'issue_type': 'meaning'},
    {'source_span': [1, 3], 'source_quote': 'の門'}])
def test_weaker_or_different_independent_issue_reports_stay_uncertain(change):
    r = review(); result = r.reviewed(answer(r), answer(r, 'review_2', **change))[0]
    assert result['status'] == 'uncertain' and not result['consumer_eligible']


def test_uncertain_or_no_issue_peer_cannot_be_overridden_by_confident_issue():
    r = review()
    uncertain = no_issue(r, 'review_2'); uncertain['items'][0]['assessment'] = 'uncertain'
    for second in [uncertain, no_issue(r, 'review_2')]:
        assert r.reviewed(answer(r), second)[0]['status'] == 'uncertain'


@pytest.mark.parametrize('change', [
    {'source_quote': 'fabricated'}, {'target_quote': 'fabricated'},
    {'source_span': [0, 999]}, {'target_span': [1, 0]}, {'source_span': [True, 2]},
    {'source_quote': '', 'source_span': [0, 0]}, {'target_quote': '', 'target_span': [0, 0]},
    {'issue_type': 'none'}, {'severity': 'none'}, {'confidence': float('nan')},
    {'human_approved_final': True}])
def test_fabricated_evidence_wrong_offsets_empty_issue_and_privilege_fields_refused(change):
    r = review()
    with pytest.raises(ValueError): r.validate_review(answer(r, **change), 'review_1')


def test_omission_and_addition_allow_only_the_relevant_one_sided_insertion_point():
    r = review()
    omission = answer(r, issue_type='omission', target_quote='', target_span=[2, 2])
    addition = answer(r, issue_type='addition', source_quote='', source_span=[2, 2])
    assert r.validate_review(omission, 'review_1') and r.validate_review(addition, 'review_1')
    invalid = answer(r, issue_type='addition', source_quote='', source_span=[2, 2],
                     target_quote='', target_span=[1, 1])
    with pytest.raises(ValueError): r.validate_review(invalid, 'review_1')


@pytest.mark.parametrize('change', [
    {'assessment': 'uncertain'}, {'assessment': 'no_material_issue_observed'}])
def test_non_issue_assessments_cannot_smuggle_material_issue_fields(change):
    r = review()
    with pytest.raises(ValueError): r.validate_review(answer(r, **change), 'review_1')


def test_duplicate_missing_wrong_packet_and_swapped_reviewer_answers_refused():
    r = review()
    for kind in ['duplicate', 'missing', 'packet', 'reviewer', 'unknown_record']:
        value = answer(r)
        if kind == 'duplicate': value['items'] *= 2
        elif kind == 'missing': value['items'] = []
        elif kind == 'packet': value['packet_sha256'] = '0' * 64
        elif kind == 'reviewer': value['reviewer_id'] = 'review_2'
        else: value['items'][0]['record_id'] = '0' * 64
        with pytest.raises(ValueError): r.validate_review(value, 'review_1')


@pytest.mark.parametrize('spans', [[], [[0, 999999]], [[True, 3]], [[3, 2]],
                                  [[2, 5], [4, 7]], [[6, 8], [2, 5]], [[0, 1]] * 9])
def test_invalid_overlapping_or_reordered_source_coordinates_refused(spans):
    s = source()
    with pytest.raises(ValueError): review(s, [record(s, source_spans=spans)])


def test_split_source_evidence_keeps_both_document_ranges_and_gap_ambiguity():
    s = source(); a = record(s)['source_spans'][0][0]; spans = [[a, a + 2], [a + 4, a + 6]]
    r = review(s, [record(s, source_spans=spans)])
    excerpt = ''.join(s.source[x:y] for x, y in spans)
    first = answer(r, source_quote=excerpt[1:3], source_span=[1, 3])
    second = deepcopy(first); second['reviewer_id'] = 'review_2'
    row = r.reviewed(first, second)[0]
    assert row['reports'][0]['source_issue_document_spans'] == [[a + 1, a + 2], [a + 4, a + 5]]
    assert _document_spans(spans, 2, 2) == [[a + 2, a + 2], [a + 4, a + 4]]


def test_closed_and_holdout_sources_are_refused_before_prompt_construction():
    s = source()
    with pytest.raises(ValueError): review(s, closed=[s.identity['source_revision']])
    with pytest.raises(ValueError): LegacyTranslationReview(s, [record(s)], partition='holdout', closed_source_versions=[])
    with pytest.raises(ValueError): review(s, closed=['not-a-version'])


@pytest.mark.parametrize('kind', ['source', 'catalog', 'identity'])
def test_source_or_catalog_drift_refuses_existing_review_packet(kind):
    r = review()
    if kind == 'source': r.knowledge.source += 'changed'
    elif kind == 'catalog': r.knowledge.chapter.segments[0].source_text += 'changed'
    else: r.knowledge.identity['direction'] = 'CN_TO_JP'
    with pytest.raises(ValueError): r.prompt('review_1')


def test_record_count_text_bounds_and_extra_legacy_fields_are_not_relaxed():
    s = source()
    for rows in [[record(s)] * 2, [record(s, notes='PRIVATE_NOTES')],
                 [record(s, target_text=' ')], [record(s, target_text='x' * 8193)],
                 [record(s, target_text='a\x00b')], [record(s, record_sha256='invalid')],
                 [record(s, record_id=f'{i:064x}') for i in range(9)]]:
        with pytest.raises(ValueError): review(s, rows)


def test_total_quoted_evidence_cap_applies_to_the_entire_view():
    text = '# Synthetic\n\n' + '甲' * 600 + '\n'
    s = source(text); start = text.index('甲'); rows = [
        {'record_id': f'{i:064x}', 'record_sha256': 'b' * 64,
         'source_spans': [[start, start + 600]], 'target_text': '乙' * 600} for i in range(3)]
    r = review(s, rows); item = answer(r)['items'][0]; items = []
    for row in rows:
        copied = deepcopy(item); copied['record_id'] = row['record_id']; items.append(copied)
    with pytest.raises(ValueError, match='evidence bound'):
        r.validate_review({'reviewer_id': 'review_1', 'packet_sha256': r.packet_sha256, 'items': items}, 'review_1')


def test_cn_to_jp_direction_and_unknown_reviewer_are_explicit():
    s = source(direction='CN_TO_JP'); r = review(s)
    assert 'Chinese-to-Japanese' in r.prompt('review_1')
    with pytest.raises(ValueError): r.prompt('generation')
    with pytest.raises(ValueError): r.schema('review_3')
