"""Located correction evidence reaches the existing bounded retranslation path."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from consistency.retranslate import _build_retranslate_messages, run_consistency_retranslate
from translation.chapter_parser import Segment
from providers.types import ModelResult

def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()

def case(mode='problem_driven'):
    context = '# 合成\n\n'
    source = '雨が降る。彼はまだ帰らない。'
    target = '下雨了。他已回家。'
    full = context + source
    issue = {'issue_type':'MISTRANSLATION','severity':'high','confidence':0.9,
             'source_quote':'まだ帰らない','target_quote':'已回家','reason':'否定变为肯定'}
    revision = {'mode':mode,'source_revision':sha(full),'source_span':[len(context),len(full)],
                'target_revision':sha(target),'source_context':{'text':context,'span':[0,len(context)]},
                'issues':[issue] if mode=='problem_driven' else []}
    return Segment(segment_id='seg-1',source_text=source,draft_text=target), full, revision

def test_located_problem_and_source_context_reach_actual_messages():
    segment, full, revision = case()
    messages = _build_retranslate_messages([segment], 'synthetic', revision_context={'seg-1':revision},
                                           full_sources={'seg-1':full})
    payload = json.loads(messages[1].content.split('\n\n',1)[1])
    assert payload['revision_context']['seg-1']['issues'][0]['source_span'] == [7,13]
    assert payload['revision_context']['seg-1']['target_revision'] == sha(segment.draft_text)
    assert payload['revision_context']['seg-1']['source_context']['text'] in full
    assert '日文残留' not in messages[0].content
    assert payload['revision_context']['seg-1']['issues_are_unverified_claims'] is True

@pytest.mark.parametrize('fault',['source_version','target_version','source_span','future_context',
    'context_text','issue_quote','omission_gap','actor','mode','confidence','simple_hints','empty_problem'])
def test_bad_evidence_is_refused_before_a_request_can_be_built(fault):
    segment, full, revision = case()
    if fault=='source_version':revision['source_revision']='0'*64
    elif fault=='target_version':revision['target_revision']='0'*64
    elif fault=='source_span':revision['source_span']=[0,3]
    elif fault=='future_context':revision['source_context']={'text':full[-1:],'span':[len(full)-1,len(full)]}
    elif fault=='context_text':revision['source_context']['text']='fiction'
    elif fault=='issue_quote':revision['issues'][0]['source_quote']='invented'
    elif fault=='omission_gap':revision['issues'][0].update(target_evidence_kind='omission_gap',target_quote='',target_span=[0,0])
    elif fault=='actor':revision['actor_type']='agent'
    elif fault=='mode':revision['mode']=[]
    elif fault=='confidence':revision['issues'][0]['confidence']=float('nan')
    elif fault=='simple_hints':revision['mode']='simple'
    elif fault=='empty_problem':revision['issues']=[]
    with pytest.raises(ValueError):
        _build_retranslate_messages([segment],'test',revision_context={'seg-1':revision},full_sources={'seg-1':full})

def test_simple_and_problem_conditions_share_context_but_only_problem_gets_issues():
    segment, full, simple = case('simple');problem=case()[2]
    build=lambda row:_build_retranslate_messages([segment],'ignored display label',revision_context={'seg-1':row},full_sources={'seg-1':full})
    one,two=build(simple),build(problem)
    assert one[0]==two[0]
    a=json.loads(one[1].content.split('\n\n',1)[1]);b=json.loads(two[1].content.split('\n\n',1)[1])
    assert a['segments']==b['segments'] and a['source_inventory_sha256']==b['source_inventory_sha256']
    assert a['revision_context']['seg-1']['source_context']==b['revision_context']['seg-1']['source_context']
    assert a['revision_context']['seg-1']['issues']==[]
    assert b['revision_context']['seg-1']['issues']

def test_valid_explicit_omission_gap_and_reverse_language_are_supported():
    segment,full,row=case();row['issues'][0].update(issue_type='OMISSION',target_quote='',target_span=[len(segment.draft_text)]*2,target_evidence_kind='omission_gap')
    result=_build_retranslate_messages([segment],'test','CN_TO_JP',revision_context={'seg-1':row},full_sources={'seg-1':full})
    assert 'Japanese' in result[0].content

def fixture(tmp_path, row):
    segment,full,_=case();source=tmp_path/'input_jp/001-fixture.md';source.parent.mkdir();source.write_text(full)
    run=tmp_path/'workspace/runs/run_fixture_draft_stage_b_50ch';run.mkdir(parents=True)
    (run/'run_metadata.json').write_text(json.dumps({'run_id':run.name,'phase':'draft'}))
    (run/'run_progress.json').write_text(json.dumps({'status':'completed','total_segments':1,'completed_segments':1}))
    path=run/'segments.json';path.write_text(json.dumps({'language_direction':'JP_TO_CN','chapters':[{'chapter_id':'ch-001','source_path':str(source),'segments':[{'segment_id':'seg-1','source_text':segment.source_text,'draft_text':segment.draft_text,'status':'machine_translated'}]}]}))
    plan={'project_id':'fixture','retranslate_tasks':[{'segment_ids':['seg-1'],'revision_context':{'seg-1':row}}]}
    return plan,path

class Spy:
    calls=0
    messages=None
    def generate(self,messages,options):
        self.calls+=1;self.messages=messages
        return ModelResult(provider_id='synthetic',model_name='synthetic',raw_output=json.dumps({'items':[{'segment_id':'seg-1','translation':'下雨了。他还没有回家。'}]}))

def test_existing_runner_receives_evidence_and_changed_issue_cannot_resume(tmp_path):
    row=case()[2];plan,path=fixture(tmp_path,row);spy=Spy()
    result=run_consistency_retranslate(plan,tmp_path,provider=spy,max_api_calls=1)
    assert result['completed_segments']==1 and spy.calls==1
    assert '否定变为肯定' in spy.messages[1].content
    repeat=Spy();again=run_consistency_retranslate(plan,tmp_path,provider=repeat,max_api_calls=1)
    assert repeat.calls==0 and again['completed_segments']==1
    before=path.read_bytes();changed=deepcopy(plan);changed['retranslate_tasks'][0]['revision_context']['seg-1']['issues'][0]['reason']='different evidence'
    unused=Spy()
    with pytest.raises(ValueError):run_consistency_retranslate(changed,tmp_path,provider=unused,max_api_calls=1)
    assert unused.calls==0 and path.read_bytes()==before

def test_stale_evidence_refuses_before_checkpoint_or_budget_mutation(tmp_path):
    row=case()[2];row['target_revision']='0'*64;plan,path=fixture(tmp_path,row);before=path.read_bytes();spy=Spy()
    with pytest.raises(ValueError):run_consistency_retranslate(plan,tmp_path,provider=spy,max_api_calls=1)
    assert spy.calls==0 and path.read_bytes()==before
    assert not (tmp_path/'workspace/consistency_audit/retranslate_progress.json').exists()
    assert not list((tmp_path/'workspace/checkpoints').glob('content_units/*.json'))

def test_committed_revision_recovers_without_reissuing_a_model_call(tmp_path,monkeypatch):
    import consistency.retranslate as module
    plan,path=fixture(tmp_path,case()[2]);original=module.atomic_write_json
    def interrupt(destination,value):
        original(destination,value)
        if destination==path:raise KeyboardInterrupt()
    monkeypatch.setattr(module,'atomic_write_json',interrupt)
    with pytest.raises(KeyboardInterrupt):run_consistency_retranslate(plan,tmp_path,provider=Spy(),max_api_calls=1)
    monkeypatch.setattr(module,'atomic_write_json',original);unused=Spy()
    result=run_consistency_retranslate(plan,tmp_path,provider=unused,max_api_calls=1)
    assert unused.calls==0 and result['completed_segments']==1
