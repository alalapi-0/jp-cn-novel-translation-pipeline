"""Calibration evidence rejects stale identity and severe-error score override."""
from pathlib import Path
import sys
from copy import deepcopy
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from quality_review.calibration import sha,packet_identity,validate_view,summarize


def sample(order=1):
    source='甲は窓を閉めた。';correct='甲关上了窗户。';wrong='甲打开了窗户。'
    values={'A':correct,'B':wrong} if order==1 else {'A':wrong,'B':correct}
    packet={'schema':'synthetic-blind-evaluation/1','order':order,'cases':[{
        'case_id':'x','source':source,'source_context':'','source_revision':sha(source),
        'candidates':values,'target_versions':{k:sha(v) for k,v in values.items()}}]}
    bad='B' if order==1 else 'A';good='A' if order==1 else 'B'
    view={'schema':'calibration-view/1','order':order,'input_packet_sha256':packet_identity(packet),'cases':[{
        'case_id':'x','preferred':good,'literary_preference':bad,'blocked':[bad],'note':'fluency cannot overturn source conflict',
        'issues':[{'candidate':bad,'issue_type':'MISTRANSLATION','severity':'critical','confidence':0.9,
            'source_quote':'閉めた','target_quote':'打开','reason':'action reversed'}]}]}
    return packet,view


def test_severe_source_conflict_veto_survives_literary_preference():
    packet,view=sample();result=validate_view(packet,view)
    assert result['cases'][0]['issues'][0]['source_span']==[4,7]
    assert result['cases'][0]['issues'][0]['target_span']==[1,3]
    assert result['auto_acceptance_enabled'] is False and result['approval_state']=='not_granted'
    view['cases'][0]['preferred']='B'
    with pytest.raises(ValueError,match='override'):validate_view(packet,view)


@pytest.mark.parametrize('change',['stale_packet','source','target','bad_quote','confidence','missing','duplicate','human_field','unexplained_veto'])
def test_bad_evidence_cannot_be_laundered_into_a_calibrated_judgment(change):
    packet,view=sample()
    if change=='stale_packet':view['input_packet_sha256']='0'*64
    elif change=='source':packet['cases'][0]['source']+='源改'
    elif change=='target':packet['cases'][0]['candidates']['A']+='目标改'
    elif change=='bad_quote':view['cases'][0]['issues'][0]['source_quote']='不存在'
    elif change=='confidence':view['cases'][0]['issues'][0]['confidence']=float('nan')
    elif change=='missing':view['cases']=[]
    elif change=='duplicate':view['cases']*=2
    elif change=='human_field':view['cases'][0]['human_approved_final']=True
    elif change=='unexplained_veto':view['cases'][0]['issues']=[]
    with pytest.raises(ValueError):validate_view(packet,view)


def test_counterbalance_uses_same_versions_and_keeps_original_denominator():
    first,one=sample();second,two=sample(2)
    labels={'cases':[{'case_id':'x','source_revision':first['cases'][0]['source_revision'],'target_versions':first['cases'][0]['target_versions'],
        'case_identity_sha256':packet_identity(first['cases'][0]),
        'expected_preference':'A','expected_blocked':['B']}]}
    result=summarize(first,second,labels,one,two)
    assert result['source_units']==1 and result['candidate_judgments_per_view']==2
    assert result['order_normalized_preference_agreement']==1
    assert all(row['tp']==1 and row['tn']==1 for row in result['by_view'])
    second['cases'][0]['candidates']['A']='different pair'
    with pytest.raises(ValueError):summarize(first,second,labels,one,two)


def test_abstention_is_unknown_not_a_true_negative():
    packet,view=sample();view['cases'][0].update(preferred='abstain',blocked=[],issues=[])
    second,two=sample(2);two['cases'][0].update(preferred='abstain',blocked=[],issues=[])
    labels={'cases':[{'case_id':'x','source_revision':packet['cases'][0]['source_revision'],'target_versions':packet['cases'][0]['target_versions'],
        'case_identity_sha256':packet_identity(packet['cases'][0]),
        'expected_preference':'A','expected_blocked':['B']}]}
    result=summarize(packet,second,labels,view,two)
    assert all(row['unknown']==2 and row['tn']==0 for row in result['by_view'])


def test_ambiguous_repeated_quote_requires_an_exact_unique_span():
    packet,view=sample();packet['cases'][0]['source']='閉めた。閉めた。'
    packet['cases'][0]['source_revision']=sha(packet['cases'][0]['source']);view['input_packet_sha256']=packet_identity(packet)
    with pytest.raises(ValueError,match='exactly once'):validate_view(packet,view)


def test_prior_grade_is_stale_even_when_its_evidence_quotes_still_match():
    packet,view=sample()
    packet['cases'][0]['source_context']='different narrative context, same quoted strings'
    with pytest.raises(ValueError,match='match blinded packet'):validate_view(packet,view)


def test_stale_author_labels_cannot_score_new_candidate_versions():
    first,one=sample();second,two=sample(2)
    labels={'cases':[{'case_id':'x','source_revision':first['cases'][0]['source_revision'],
        'target_versions':{'A':'0'*64,'B':'1'*64},'expected_preference':'A','expected_blocked':['B']}]}
    with pytest.raises(ValueError,match='target version changed'):summarize(first,second,labels,one,two)


def test_context_only_change_cannot_reuse_original_author_expectations():
    first,one=sample();second,two=sample(2)
    labels={'cases':[{'case_id':'x','source_revision':first['cases'][0]['source_revision'],
        'target_versions':first['cases'][0]['target_versions'],'case_identity_sha256':packet_identity(first['cases'][0]),
        'expected_preference':'A','expected_blocked':['B']}]}
    for packet,view in ((first,one),(second,two)):
        packet['cases'][0]['source_context']='new semantic context with same source and targets'
        view['input_packet_sha256']=packet_identity(packet)
    with pytest.raises(ValueError):summarize(first,second,labels,one,two)
