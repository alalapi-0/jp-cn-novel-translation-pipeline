"""Synthetic source-only extraction/review and non-authoritative correspondence."""
from copy import deepcopy
import hashlib
import json
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from assets.source_knowledge import SourceKnowledge, digest, correspondence


def source():
    text = '# Synthetic\n\n蒼の門は北にある。\n\n彼女は静かに扉を閉めた。\n\n後で雨が降った。\n'
    descriptor = {'path': 'input_jp/001-synthetic.md', 'category': 'source_original',
                  'sha256': hashlib.sha256(text.encode()).hexdigest()}
    return SourceKnowledge(text, descriptor, direction='JP_TO_CN')


def extraction(s, **changes):
    row = {'claim_id': 'k1', 'category': 'glossary', 'statement': '苍之门位于北方。',
           'paragraph_id': s.chapter.segments[0].segment_id,
           'source_name': '蒼の門', 'target_name': '苍之门', 'epistemic_status': 'assertion',
           'confidence': .9, 'quote': '蒼の門は北にある。'}
    row.update(changes)
    return {'input_sha256': s.input_sha256, 'claims': [row]}


def review(candidates, **changes):
    row = {'claim_id': 'k1', 'verdict': 'source_supported', 'severity': 'none',
           'paragraph_id': candidates[0]['paragraph_id'],
           'confidence': .9, 'quote': '蒼の門は北にある。', 'reason': 'The source states this directly.'}
    row.update(changes)
    return {'candidate_sha256': digest(candidates), 'items': [row]}


def test_original_source_descriptor_and_byte_version_required():
    s = source()
    with pytest.raises(ValueError, match='identity'):
        SourceKnowledge(s.source + ' ', {'path': 'input_jp/001.md', 'category': 'source_original',
            'sha256': s.identity['source_revision']}, direction='JP_TO_CN')


def test_source_only_prompt_and_located_current_evidence():
    s = source(); answer = extraction(s); before = deepcopy(answer)
    candidates = s.extraction(answer)
    row = candidates[0]; evidence = row['knowledge_claim']['evidence'][0]
    assert row['source_revision'] == s.identity['source_revision']
    a, b = row['source_document_span']; assert s.source[a:b] == evidence['quote']
    assert evidence['source_catalog_sha256'] == s.catalog.sha256
    assert row['knowledge_claim']['effective_from'] == evidence['segment_id']
    assert row['knowledge_claim']['semantic_truth'] == 'not_verified'
    assert answer == before
    assert 'PRIVATE_LEGACY_VALUE' not in s.extraction_prompt()


@pytest.mark.parametrize('patch', [
    {'quote': 'fabricated'}, {'quote': '彼'}, {'source_name': 'not in quote'},
    {'source_name': ''}, {'category': 'owner_truth'}, {'confidence': 1.1},
    {'statement': ''}, {'human_approved_final': True}])
def test_invalid_extraction_never_fabricates_evidence(patch):
    s = source()
    with pytest.raises(ValueError): s.extraction(extraction(s, **patch))


def test_duplicate_ids_wrong_input_and_excess_claims_rejected():
    s = source(); answer = extraction(s)
    answer['claims'] *= 2
    with pytest.raises(ValueError, match='duplicate'): s.extraction(answer)
    answer = extraction(s); answer['input_sha256'] = '0' * 64
    with pytest.raises(ValueError): s.extraction(answer)
    answer = extraction(s); answer['claims'] *= 9
    with pytest.raises(ValueError): s.extraction(answer)


def test_duplicate_quote_is_not_unique_evidence():
    text = '# S\n\n同じ文。\n\n同じ文。\n'
    s = SourceKnowledge(text, {'path': 'input_jp/001.md', 'category': 'source_original',
        'sha256': hashlib.sha256(text.encode()).hexdigest()}, direction='JP_TO_CN')
    with pytest.raises(ValueError, match='unique'):
        s.extraction(extraction(s, source_name='同じ', quote='同じ文。'))


def test_separate_review_preserves_input_and_never_issues_truth_or_consumer_authority():
    s = source(); candidates = s.extraction(extraction(s)); before = deepcopy(candidates)
    reviewed = s.reviewed(candidates, review(candidates)); row = reviewed[0]
    assert row['agent_evidence_status'] == 'source_supported'
    assert not row['consumer_eligible'] and not row['human_approved_final'] and not row['production_adoption']
    assert row['semantic_truth'] == 'not_verified' and candidates == before
    assert 'PRIVATE_LEGACY_VALUE' not in s.review_prompt(candidates)


@pytest.mark.parametrize('changes', [{'verdict': 'uncertain', 'quote': '', 'paragraph_id': ''}, {'severity': 'major'},
                                    {'confidence': .79}])
def test_uncertainty_and_material_issues_cannot_become_supported(changes):
    s = source(); candidates = s.extraction(extraction(s))
    assert s.reviewed(candidates, review(candidates, **changes))[0]['agent_evidence_status'] == 'uncertain'


def test_inference_cannot_become_assertion_through_reviewer_vote():
    s = source(); candidates = s.extraction(extraction(s, epistemic_status='inference'))
    assert s.reviewed(candidates, review(candidates))[0]['agent_evidence_status'] == 'uncertain'


@pytest.mark.parametrize('changes', [{'quote': ''}, {'quote': 'fabricated'}, {'claim_id': 'k2'}])
def test_supported_review_requires_current_located_proof_and_exact_coverage(changes):
    s = source(); candidates = s.extraction(extraction(s))
    with pytest.raises(ValueError): s.reviewed(candidates, review(candidates, **changes))


def test_review_candidate_identity_cannot_change():
    s = source(); candidates = s.extraction(extraction(s)); answer = review(candidates)
    candidates[0]['name_mapping']['target'] = 'different'
    with pytest.raises(ValueError): s.reviewed(candidates, answer)


def test_empty_extraction_is_valid_without_claim_invention():
    s = source(); assert s.extraction({'input_sha256': s.input_sha256, 'claims': []}) == []
    assert s.reviewed([], {'candidate_sha256': digest([]), 'items': []}) == []


def test_sealed_correspondence_exact_and_ambiguous_matches_remain_unverified():
    s = source(); candidates = s.extraction(extraction(s)); rows = s.reviewed(candidates, review(candidates))
    legacy = {'entries': [{'source_term': '蒼の門', 'target_term': '苍之门', 'notes': 'PRIVATE_LEGACY_VALUE'},
                          {'source_term': '蒼の門', 'target_term': 'another'}]}
    before = deepcopy(legacy)
    result = correspondence(rows, glossary=legacy, characters={'characters': []},
                            glossary_revision='a' * 64, character_revision='b' * 64)
    assert len(result['items'][0]['matched_legacy_records']) == 2
    assert [r['target_exact_equal'] for r in result['items'][0]['matched_legacy_records']] == [True, False]
    assert result['all_legacy_dispositions'] == 'withheld_unverified'
    assert result['original_census_denominator'] == 22242 and result['old_value_model_releases'] == 0
    assert 'PRIVATE_LEGACY_VALUE' not in str(result) and legacy == before


def test_quote_only_context_stays_narratively_scoped_without_forwarding_proposition():
    from assets.knowledge import build_knowledge_context
    s = source(); candidates = s.extraction(extraction(s, statement='PRIVATE_MODEL_PROPOSITION'))
    catalog = build_knowledge_context(s.catalog, [candidates[0]['knowledge_claim']])
    rendered = catalog.for_batch(s.chapter.segments[-1:]).to_dict()
    assert 'PRIVATE_MODEL_PROPOSITION' not in str(rendered)
    assert '蒼の門は北にある。' in str(rendered)


def test_both_model_inputs_expose_the_same_versioned_paragraph_catalog():
    s = source(); candidates = s.extraction(extraction(s))
    payloads = [json.loads(prompt.split('\n', 1)[1]) for prompt in
                [s.extraction_prompt(), s.review_prompt(candidates)]]
    expected = [{'paragraph_id': p.segment_id, 'text': p.source_text} for p in s.chapter.segments]
    assert all(p['quote_paragraphs'] == expected and p['complete_source'] == s.source for p in payloads)
    assert payloads[0]['identity']['quote_catalog_sha256'] == digest(expected)
    assert s.extraction_schema()['properties']['claims']['items']['properties']['paragraph_id']['enum'] == [p['paragraph_id'] for p in expected]


def test_paragraph_identity_is_required_and_cannot_misidentify_a_literal_quote():
    s = source(); answer = extraction(s); del answer['claims'][0]['paragraph_id']
    with pytest.raises(ValueError): s.extraction(answer)
    with pytest.raises(ValueError, match='paragraph identity'):
        s.extraction(extraction(s, paragraph_id=s.chapter.segments[1].segment_id))
    candidates = s.extraction(extraction(s)); checked = review(candidates); del checked['items'][0]['paragraph_id']
    with pytest.raises(ValueError): s.reviewed(candidates, checked)
    with pytest.raises(ValueError, match='paragraph identity'):
        s.reviewed(candidates, review(candidates, paragraph_id=s.chapter.segments[1].segment_id))


def test_literal_review_quote_cannot_combine_two_catalog_entries():
    s = source(); candidates = s.extraction(extraction(s))
    quote = '\n\n'.join(p.source_text for p in s.chapter.segments[:2])
    assert s.source.count(quote) == 1
    with pytest.raises(ValueError, match='parsed source paragraph'):
        s.reviewed(candidates, review(candidates, quote=quote))
    result = s.reviewed(candidates, review(candidates, verdict='uncertain', quote='', paragraph_id=''))[0]
    assert result['agent_evidence_status'] == 'uncertain' and not result['consumer_eligible']


def test_single_multiline_parser_paragraph_is_still_valid():
    paragraphs = ['第一行。\n第二行。'] + [f'別の段落{i}。' for i in range(2, 9)]
    text = '# Synthetic\n\n' + '\n\n'.join(paragraphs) + '\n'
    s = SourceKnowledge(text, {'path': 'input_jp/001-synthetic.md', 'category': 'source_original',
        'sha256': hashlib.sha256(text.encode()).hexdigest()}, direction='JP_TO_CN')
    assert s.quote_paragraphs()[0]['text'] == paragraphs[0]
    candidates = s.extraction(extraction(s, category='world', source_name='', target_name='', quote=paragraphs[0]))
    checked = s.reviewed(candidates, review(candidates, quote=paragraphs[0]))[0]
    assert checked['agent_evidence_status'] == 'source_supported' and not checked['human_approved_final']


@pytest.mark.parametrize('change', ['source', 'paragraph', 'identity'])
def test_prompt_catalog_drift_is_refused(change):
    s = source()
    if change == 'source': s.source += 'changed'
    elif change == 'paragraph': s.chapter.segments[0].source_text += 'changed'
    else: s.identity['quote_catalog_sha256'] = '0' * 64
    with pytest.raises(ValueError): s.extraction_prompt()


def test_paragraph_catalog_is_bounded_and_returned_values_cannot_mutate_it(monkeypatch):
    from assets import source_knowledge as module
    s = source(); detached = s.quote_paragraphs(); detached[0]['text'] = 'changed'
    assert s.quote_paragraphs()[0]['text'] != 'changed'
    monkeypatch.setattr(module, 'MAX_QUOTE_CATALOG_BYTES', 1)
    with pytest.raises(ValueError, match='bound'): s.extraction_prompt()


def test_duplicate_paragraph_text_cannot_be_disambiguated_by_an_arbitrary_id():
    text = '# Synthetic\n\n同じ文。\n\n同じ文。\n'
    s = SourceKnowledge(text, {'path': 'input_jp/001.md', 'category': 'source_original',
        'sha256': hashlib.sha256(text.encode()).hexdigest()}, direction='JP_TO_CN')
    assert len({p['paragraph_id'] for p in s.quote_paragraphs()}) == 2
    with pytest.raises(ValueError, match='unique'):
        s.extraction(extraction(s, source_name='同じ', quote='同じ文。'))


@pytest.mark.parametrize('quote,paragraph_id', [('', 'ch-001-seg-002'), ('蒼の門は北にある。', '')])
def test_review_quote_and_paragraph_identity_must_be_present_together(quote, paragraph_id):
    s = source(); candidates = s.extraction(extraction(s))
    with pytest.raises(ValueError, match='provided together'):
        s.reviewed(candidates, review(candidates, verdict='uncertain', quote=quote, paragraph_id=paragraph_id))


def legacy_case():
    from assets.source_knowledge import select_legacy_mappings, LegacyKnowledgeReview
    s = source()
    docs = [({'path': 'workspace/configs/glossary.yaml', 'sha256': 'a' * 64},
             {'entries': [{'source_term': '蒼の門', 'target_term': '苍之门', 'locked': True,
                           'notes': 'PRIVATE_LEGACY_NOTE'}]}),
            ({'path': 'workspace/configs/character_profile.yaml', 'sha256': 'b' * 64},
             {'characters': [{'name': '彼女', 'target_name': '她', 'speech_style': 'PRIVATE_STYLE'}]})]
    prior = []
    for descriptor, doc in docs:
        collection = 'entries' if 'entries' in doc else 'characters'
        category = 'glossary' if collection == 'entries' else 'character'
        for i, row in enumerate(doc[collection]):
            pointer = f'$.{collection}[{i}]'
            prior.append({'artifact_path': descriptor['path'], 'artifact_revision': descriptor['sha256'],
                'record_pointer': pointer, 'record_id': digest([descriptor['path'], descriptor['sha256'], pointer]),
                'record_sha256': digest(row), 'category': category})
    mappings = select_legacy_mappings(s, docs, prior)
    return s, docs, prior, mappings, LegacyKnowledgeReview(s, mappings)


def legacy_answer(review, **changes):
    rows = review._check()
    return {'mapping_set_sha256': review.mapping_sha256, 'items': [dict(
        record_id=r['record_id'], paragraph_id=r['paragraph_id'], quote=r['quote'],
        verdict='source_supported', severity='none', confidence=.9, reason='Supported in synthetic context.',
        **{}) | changes for r in rows]}


def test_legacy_selection_is_record_ordered_located_and_minimizes_fields():
    s, docs, prior, mappings, review = legacy_case()
    assert [r['category'] for r in mappings] == ['character', 'glossary']
    prompt = review.prompt()
    assert 'PRIVATE_' not in prompt and 'locked' in prompt  # instruction only, no legacy flags
    assert 'notes' not in json.loads(prompt.split('\n', 1)[1])['mappings'][0]
    for r in mappings:
        a, b = r['source_document_span']
        assert s.source[a:b] == r['quote'] and r['quote'].count(r['source_name']) == 1
    original = deepcopy(mappings); mappings[0]['target_name'] = 'CHANGED'
    assert review._check() == original


def test_two_legacy_reviews_remain_non_authoritative():
    *_, review = legacy_case()
    rows = review.reviewed(legacy_answer(review), legacy_answer(review))
    assert all(r['status'] == 'provisionally_supported' for r in rows)
    assert all(not any(r[k] for k in ['semantic_verified', 'consumer', 'human_approved', 'adoption']) for r in rows)
    assert '苍之门' not in json.dumps(rows, ensure_ascii=False)


@pytest.mark.parametrize('change,status', [({'verdict': 'uncertain'}, 'uncertain'),
    ({'severity': 'major'}, 'uncertain'), ({'confidence': .79}, 'uncertain'),
    ({'verdict': 'contradicted'}, 'uncertain')])
def test_legacy_disagreement_and_material_issues_are_withheld(change, status):
    *_, review = legacy_case()
    rows = review.reviewed(legacy_answer(review), legacy_answer(review, **change))
    assert all(r['status'] == status and not r['consumer'] for r in rows)


def test_concordant_legacy_contradiction_is_separate_from_uncertainty():
    *_, review = legacy_case()
    rows = review.reviewed(legacy_answer(review, verdict='contradicted'), legacy_answer(review, verdict='contradicted'))
    assert all(r['status'] == 'contradicted' and not r['semantic_verified'] for r in rows)


@pytest.mark.parametrize('change', [{'quote': 'invented'}, {'paragraph_id': 'unknown'}, {'record_id': '0' * 64}])
def test_legacy_review_wrong_locator_or_identity_is_rejected(change):
    *_, review = legacy_case()
    with pytest.raises(ValueError): review.validate_review(legacy_answer(review, **change))


def test_legacy_stale_set_and_duplicate_coverage_refused():
    *_, review = legacy_case()
    answer = legacy_answer(review); answer['mapping_set_sha256'] = '0' * 64
    with pytest.raises(ValueError): review.validate_review(answer)
    answer = legacy_answer(review); answer['items'][1] = deepcopy(answer['items'][0])
    with pytest.raises(ValueError): review.validate_review(answer)


@pytest.mark.parametrize('field,value', [('source_term', ['not scalar']), ('target_term', 'x' * 101),
                                        ('target_term', 'bad\nfield')])
def test_legacy_malformed_or_control_fields_refuse_release(field, value):
    from assets.source_knowledge import select_legacy_mappings
    s, docs, prior, *_ = legacy_case(); docs[0][1]['entries'][0][field] = value
    with pytest.raises(ValueError): select_legacy_mappings(s, docs, prior)


def test_legacy_mapping_requires_pinned_original_record_hash():
    from assets.source_knowledge import select_legacy_mappings
    s, docs, prior, *_ = legacy_case(); prior[0]['artifact_revision'] = '0' * 64
    with pytest.raises(ValueError): select_legacy_mappings(s, docs, prior)


def test_legacy_repeated_names_use_an_unambiguous_located_occurrence():
    from assets.source_knowledge import select_legacy_mappings
    s, docs, prior, *_ = legacy_case()
    full = s.source + '\n\n蒼の門は南にない。\n'
    s = SourceKnowledge(full, {'path': 'input_jp/001-synthetic.md', 'category': 'source_original',
                              'sha256': hashlib.sha256(full.encode()).hexdigest()}, direction='JP_TO_CN')
    mappings = select_legacy_mappings(s, docs, prior)
    assert next(r for r in mappings if r['category'] == 'glossary')['quote'] == '蒼の門は北にある。'


def test_two_independent_legacy_reviews_have_distinct_budget_request_identity():
    *_, review = legacy_case()
    assert review.prompt('review_1') != review.prompt('review_2')
    assert json.loads(review.prompt('review_1').split('\n', 1)[1])['mappings'] == json.loads(review.prompt('review_2').split('\n', 1)[1])['mappings']
    with pytest.raises(ValueError): review.prompt('review_3')


def test_r66_legacy_record_hash_must_equal_the_parsed_record():
    from assets.source_knowledge import select_legacy_mappings
    s, docs, prior, *_ = legacy_case()
    prior[0]['record_sha256'] = '0' * 64
    with pytest.raises(ValueError): select_legacy_mappings(s, docs, prior)


def test_r66_overlapping_quote_occurrences_are_not_unique():
    full = '# Synthetic\n\nあああ\n'
    s = SourceKnowledge(full, {'path': 'input_jp/001-synthetic.md', 'category': 'source_original',
        'sha256': hashlib.sha256(full.encode()).hexdigest()}, direction='JP_TO_CN')
    with pytest.raises(ValueError, match='unique'): s.locate('ああ')


def test_r66_overlapping_name_occurrences_are_not_unambiguous():
    from assets.source_knowledge import select_legacy_mappings
    full = '# Synthetic\n\n蒼の門蒼の門蒼の門\n'
    s, docs, prior, *_ = legacy_case()
    # Two overlapping occurrences of the legacy name inside the same quote.
    docs[0][1]['entries'][0]['source_term'] = '蒼の門蒼の門'
    prior[0]['record_sha256'] = digest(docs[0][1]['entries'][0])
    s = SourceKnowledge(full, {'path': 'input_jp/001-synthetic.md', 'category': 'source_original',
        'sha256': hashlib.sha256(full.encode()).hexdigest()}, direction='JP_TO_CN')
    assert select_legacy_mappings(s, docs, prior) == []
