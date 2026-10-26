"""Source calibration preserves missing/repeated evidence and unknown denominators."""
from copy import deepcopy
from pathlib import Path
import sys
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from quality_review.calibration import sha, packet_identity, validate_view, summarize_source


def sample(kind='omission_gap'):
    source='戸を閉めた。灯りを消した。'
    candidates={'A':'关了门，也熄了灯。','B':'关了门。' if kind=='omission_gap' else '关了门，也熄了灯。关了门。'}
    packet={'schema':'source-blind-evaluation/1','order':1,'cases':[{
        'case_id':'x','source':source,'source_context':'','source_revision':sha(source),
        'candidates':candidates,'target_versions':{k:sha(v) for k,v in candidates.items()}}]}
    issue={'candidate':'B','issue_type':'OMISSION' if kind=='omission_gap' else 'ADDITION',
        'severity':'high','confidence':0.8,'source_quote':'灯りを消した' if kind=='omission_gap' else '戸を閉めた',
        'target_quote':'' if kind=='omission_gap' else '关了门',
        'target_span':[4,4] if kind=='omission_gap' else [9,12],
        'target_evidence_kind':kind,'reason':'missing light action' if kind=='omission_gap' else 'unjustified repeated action'}
    view={'schema':'source-calibration-view/1','order':1,'input_packet_sha256':packet_identity(packet),'cases':[{
        'case_id':'x','preferred':'A','literary_preference':'B','blocked':['B'],'issues':[issue],'note':'source evidence first'}]}
    return packet,view


def test_omission_evidence_uses_explicit_gap_not_invented_target_quote():
    packet,view=sample()
    issue=validate_view(packet,view)['cases'][0]['issues'][0]
    assert issue['source_span']==[6,12] and issue['target_span']==[4,4]
    assert issue['target_evidence_kind']=='omission_gap'


def test_repeated_target_quote_can_bind_exact_second_occurrence():
    packet,view=sample('text_span')
    assert validate_view(packet,view)['cases'][0]['issues'][0]['target_span']==[9,12]


@pytest.mark.parametrize('change', ['missing_gap_span','nonzero_gap','outside','bool_offset','wrong_quote',
                                  'wrong_gap_type','unknown_kind','unhashable_kind','approval_field','wrong_source_span'])
def test_bad_locators_cannot_become_source_evidence(change):
    packet,view=sample();issue=view['cases'][0]['issues'][0]
    if change=='missing_gap_span':del issue['target_span']
    elif change=='nonzero_gap':issue['target_span']=[1,2]
    elif change=='outside':issue['target_span']=[5,5]
    elif change=='bool_offset':issue['target_span']=[True,True]
    elif change=='wrong_quote':issue['target_quote']='invented translation'
    elif change=='wrong_gap_type':issue['issue_type']='ADDITION'
    elif change=='unknown_kind':issue['target_evidence_kind']='inferred'
    elif change=='unhashable_kind':issue['target_evidence_kind']=[]
    elif change=='approval_field':issue['human_approved_final']=True
    elif change=='wrong_source_span':issue['source_span']=[0,6]
    with pytest.raises(ValueError):validate_view(packet,view)


def test_repeated_quote_without_exact_coordinates_remains_ambiguous():
    packet,view=sample('text_span');del view['cases'][0]['issues'][0]['target_span']
    with pytest.raises(ValueError,match='exactly once'):validate_view(packet,view)


def pair():
    packet,view=sample();second=deepcopy(packet);second['order']=2
    for field in ('candidates','target_versions'):
        second['cases'][0][field]={'A':packet['cases'][0][field]['B'],'B':packet['cases'][0][field]['A']}
    two=deepcopy(view);two['order']=2;two['input_packet_sha256']=packet_identity(second)
    two['cases'][0].update(preferred='B',blocked=['A'],literary_preference='A')
    two['cases'][0]['issues'][0]['candidate']='A'
    case=packet['cases'][0]
    gold={'schema':'source-control-labels/1','cases':[{
        'case_id':'x','source_revision':case['source_revision'],'target_versions':case['target_versions'],
        'case_identity_sha256':packet_identity(case),'expected_status':{'A':'unknown','B':'severe'},
        'expected_preference':None,'probe_class':'omission','label_authority':'author control,not human gold',
        'reason':'complete missing clause;baseline not verified'}]}
    return packet,second,gold,view,two


def test_detection_and_severity_disagreement_have_separate_denominators():
    first,second,gold,one,two=pair()
    one['cases'][0]['issues'][0]['severity']='medium';one['cases'][0]['blocked']=[]
    result=summarize_source(first,second,gold,one,two)
    assert result['candidate_judgments_per_view']==2
    assert all(r['issue_detection']['tp']==1 for r in result['by_view'])
    assert result['by_view'][0]['severe_veto']['fn']==1
    assert result['by_view'][0]['severe_veto']['recall']==0
    assert result['by_view'][1]['severe_veto']['recall']==1
    assert all(r['severe_veto']['unknown_reference']==1 and r['severe_veto']['tn']==0 for r in result['by_view'])
    assert result['severe_veto_disagreement_cases']==['x']
    assert result['auto_acceptance_enabled'] is False and result['human_approval'] is False
    assert result['default_action']=='preserve_original'


def test_abstention_cannot_improve_recall_by_removing_a_positive_reference():
    first,second,gold,one,two=pair()
    for view in (one,two):view['cases'][0].update(preferred='abstain',blocked=[],issues=[])
    result=summarize_source(first,second,gold,one,two)
    for row in result['by_view']:
        assert row['severe_veto']['reference_positive']==1
        assert row['severe_veto']['unknown_prediction_positive']==1
        assert row['severe_veto']['recall']==0
        assert row['severe_veto']['precision'] is None
        assert row['severe_veto']['tn']==0 and row['severe_veto']['unknown_reference']==1


@pytest.mark.parametrize('change', ['context','candidate','second_metadata','denominator','duplicate_label',
                                  'label_unknown_field','label_status','label_case_hash','order'])
def test_control_versions_and_original_cases_cannot_be_relabeled_or_dropped(change):
    first,second,gold,one,two=pair()
    if change=='context':
        first['cases'][0]['source_context']='new context'
        one['input_packet_sha256']=packet_identity(first)
    elif change=='candidate':first['cases'][0]['candidates']['A']+='changed'
    elif change=='second_metadata':second['cases'][0]['unreviewed']='new info'
    elif change=='denominator':gold['cases']=[]
    elif change=='duplicate_label':gold['cases']*=2
    elif change=='label_unknown_field':gold['cases'][0]['human_approved_final']=True
    elif change=='label_status':gold['cases'][0]['expected_status']['A']='approved'
    elif change=='label_case_hash':gold['cases'][0]['case_identity_sha256']='0'*64
    elif change=='order':first['order']=2
    with pytest.raises(ValueError):summarize_source(first,second,gold,one,two)
