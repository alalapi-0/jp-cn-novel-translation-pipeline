"""Incomparable historical baselines cannot be presented as framework gains."""
from copy import deepcopy
from pathlib import Path
import sys
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from translation.baselines import FIELDS,condition,digest,text_sha,source_identity,build_pair,compare_conditions


def sample():
    text='戸を閉めた。';rev=text_sha(text)
    case={'case_id':'s','source':text,'source_anchor':['JP_TO_CN','ch-1',rev],'source_span':[0,len(text)],
          'whole_source_unit':{'source_revision':rev,'document_span':[0,len(text)],
                               'coordinate':'unicode_codepoint_half_open','partition':'whole_source/1'},
          'old_target':{'partition':'development','source_anchor':['JP_TO_CN','ch-1',rev],
                        'target_text':'关了门。','target_revision':text_sha('关了门。'),'record_id':digest('record'),
                        'human_approved_final':True}}
    old={key:condition(None,'historical condition unavailable') for key in FIELDS}
    new=deepcopy(old)
    for values in (old,new):values['source']=condition(source_identity(case),'same registered source')
    new['code']=condition(digest('legacy prompt plus guarded adapter'),'frozen prompt;runtime adapted')
    return case,old,new


def test_unknown_equals_unknown_is_never_same_condition_reproduction():
    case,old,new=sample();result=build_pair(case,'{"items":[{"segment_id":"s","translation":"把门关上了。"}]}',old,new,['native backend replaces historical provider'])
    assert result['comparison']['condition_comparison']['source']['status']=='match'
    assert result['comparison']['condition_comparison']['model']['status']=='unknown'
    assert result['comparison']['known_condition_identities_match'] is False
    assert result['comparison']['strict_same_conditions'] is False
    assert result['comparison']['framework_effect_attribution']=='prohibited'
    assert result['B_framework']['status']=='strict_historical_execution_unavailable'
    assert result['B_framework_adapter']['status']=='structurally_validated_candidate'
    assert result['B_old']['legacy_approval']=='unverified;not a reference truth'
    assert result['approval_state']=='not_granted' and result['auto_acceptance_enabled'] is False
    assert result['canonical_write'] is False and 'human_approved_final' not in result['B_old']


@pytest.mark.parametrize('raw',['not json','{"items":[]}',
    '{"items":[{"segment_id":"s","translation":"一"},{"segment_id":"s","translation":"二"}]}',
    '{"items":[{"segment_id":"foreign","translation":"别的"}]}',
    '{"items":[{"segment_id":"s","translation":""}]}',
    '{"items":[{"segment_id":"s","translation":4}]}'])
def test_failed_response_retained_but_never_becomes_a_baseline_success(raw):
    case,old,new=sample();r=build_pair(case,raw,old,new,['controlled adapter'])
    assert r['B_framework_adapter']['status']=='failed'
    assert r['B_framework_adapter']['text'] is None and r['B_framework_adapter']['target_revision'] is None
    assert r['B_framework_adapter']['raw_output_sha256']==text_sha(raw)
    assert r['B_old']['target_revision']==case['old_target']['target_revision']


@pytest.mark.parametrize('change',['holdout','target_drift','foreign_anchor','fragment_budget','bad_span','wrong_source_condition'])
def test_mismatched_lineage_cannot_enter_paired_comparison(change):
    case,old,new=sample()
    if change=='holdout':case['old_target']['partition']='holdout'
    elif change=='target_drift':case['old_target']['target_text']+='altered'
    elif change=='foreign_anchor':case['old_target']['source_anchor'][1]='ch-2'
    elif change=='fragment_budget':case['whole_source_unit']['partition']='fragment'
    elif change=='bad_span':case['source_span'][1]+=1
    elif change=='wrong_source_condition':new['source']=condition(digest('different'),'other source')
    with pytest.raises(ValueError):build_pair(case,'{}',old,new,['adapter'])


@pytest.mark.parametrize('change',['missing_condition','unknown_claims_identity','known_without_identity','bad_digest','missing_adaptations'])
def test_comparison_requires_explicit_known_or_unknown_conditions(change):
    case,old,new=sample();adapt=['adapter']
    if change=='missing_condition':del old['model']
    elif change=='unknown_claims_identity':old['model']['identity']=digest('unknown')
    elif change=='known_without_identity':old['model']['status']='known'
    elif change=='bad_digest':old['model']=dict(status='known',identity='unknown',detail='not proof')
    elif change=='missing_adaptations':adapt=[]
    with pytest.raises(ValueError):compare_conditions(old,new,adapt)


def test_matching_declared_conditions_still_do_not_identify_framework_effect():
    values={key:condition(digest(key),'declared identity') for key in FIELDS}
    result=compare_conditions(values,values,['safety adapter differs from old runtime'])
    assert result['known_condition_identities_match'] is True
    assert result['strict_same_conditions'] is False and result['framework_effect_attribution']=='prohibited'
    changed=deepcopy(values);changed['model']=condition(digest('newmodel'),'different model')
    assert compare_conditions(values,changed,['adapter'])['condition_comparison']['model']['status']=='different'
