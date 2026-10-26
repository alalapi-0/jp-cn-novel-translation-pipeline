"""Draft admission, simulation and recovery fault injection; synthetic inputs only."""
from __future__ import annotations
import json,sys
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from translation.draft_runner import run_draft_stage_b,RunBudget
from providers.types import ModelResult


def setup_input(tmp_path,monkeypatch):
    monkeypatch.setenv('CONTROLLED_RUN_ENABLED','true')
    monkeypatch.setenv('REAL_API_TESTS_ENABLED','false')
    monkeypatch.setenv('MAX_TEST_COST_USD','1')
    monkeypatch.setenv('MAX_TOKENS_PER_RUN','100000')
    monkeypatch.setattr('translation.draft_runner.time.sleep',lambda _:None)
    source=tmp_path/'input_jp';source.mkdir(exist_ok=True)
    (source/'001-test.md').write_text('# Synthetic\n\n## Unit\n\n合成入力です。\n')
    return source


class SyntheticProvider:
    provider_id='synthetic';model_name='synthetic';network_calls=0
    def __init__(self,guard,callback=None):self.cost_guard=guard;self.callback=callback
    def generate(self,messages,options=None):
        self.network_calls+=1
        if self.callback:self.callback(self,messages)
        return ModelResult(provider_id=self.provider_id,model_name=self.model_name,
             raw_output=json.dumps({'items':[{'segment_id':'ch-001-seg-001','translation':'合成译文。'}]}))


def run(tmp_path,source,factory,cap=2,run_id='bounded'):
    return run_draft_stage_b(repo_root=tmp_path,input_dir=source,limit_chapters=1,run_id=run_id,
                            provider_factory=factory,run_budget=RunBudget(max_api_calls=cap))


def test_explicit_zero_cap_never_enters_draft_provider(tmp_path,monkeypatch):
    source=setup_input(tmp_path,monkeypatch);p=SyntheticProvider(None)
    summary,_=run(tmp_path,source,lambda g:p,cap=0)
    assert p.network_calls==0 and summary.tick_paused


def test_failure_is_reserved_and_not_blindly_retried(tmp_path,monkeypatch):
    source=setup_input(tmp_path,monkeypatch)
    def fail(*_):raise RuntimeError('synthetic unknown delivery')
    p=SyntheticProvider(None,fail);summary,root=run(tmp_path,source,lambda g:p,cap=1)
    assert p.network_calls==summary.api_calls==1
    cp=json.loads((tmp_path/'workspace/checkpoints/bounded.json').read_text())
    assert cp['metadata']['draft_execution']['api_calls_used']==1
    assert not cp['completed_segments'] and summary.aborted


def test_new_process_budget_object_cannot_reset_failed_call(tmp_path,monkeypatch):
    source=setup_input(tmp_path,monkeypatch)
    def fail(*_):raise RuntimeError('synthetic unknown delivery')
    p=SyntheticProvider(None,fail);run(tmp_path,source,lambda g:p,cap=1)
    newer=SyntheticProvider(None);summary,_=run(tmp_path,source,lambda g:newer,cap=1)
    assert newer.network_calls==0 and summary.api_calls==1


def test_simulation_has_no_real_done_state_or_real_namespace(tmp_path,monkeypatch):
    source=setup_input(tmp_path,monkeypatch)
    class Fake(SyntheticProvider):
        provider_id='fake'
        def generate(self,*args,**kwargs):
            result=super().generate(*args,**kwargs);result.dry_run=True;return result
    p=Fake(None);summary,root=run(tmp_path,source,lambda g:p)
    assert summary.simulated is True and summary.translated_segments==0
    assert root==tmp_path/'workspace/simulations/runs/bounded'
    assert not (tmp_path/'workspace/runs/bounded').exists()
    assert not (tmp_path/'workspace/checkpoints/bounded.json').exists()
    cp=json.loads((tmp_path/'workspace/simulations/checkpoints/bounded.json').read_text())
    assert cp['completed_segments']==[] and cp['status']=='simulated'
    assert json.loads((root/'draft_quality_report.json').read_text())['passed'] is False


def test_guard_ledger_is_bound_to_selected_run(tmp_path,monkeypatch):
    source=setup_input(tmp_path,monkeypatch)
    def check(p,_):assert p.cost_guard.config.attempt_ledger_path==tmp_path/'workspace/runs/bounded/provider_attempt_budget.json'
    holder=[]
    def factory(g):p=SyntheticProvider(g,check);holder.append(p);return p
    summary,_=run(tmp_path,source,factory)
    assert holder[0].network_calls==1 and not summary.aborted


def test_changed_source_refuses_resume_without_writing_candidate(tmp_path,monkeypatch):
    source=setup_input(tmp_path,monkeypatch);run(tmp_path,source,lambda g:SyntheticProvider(g))
    cp=tmp_path/'workspace/checkpoints/bounded.json';before=cp.read_bytes()
    (source/'001-test.md').write_text('# Synthetic\n\n## Unit\n\n変更した入力です。\n')
    p=SyntheticProvider(None)
    with pytest.raises(RuntimeError):run(tmp_path,source,lambda g:p)
    assert p.network_calls==0 and cp.read_bytes()==before


def test_unpinned_legacy_target_is_preserved_and_refused(tmp_path,monkeypatch):
    source=setup_input(tmp_path,monkeypatch);root=tmp_path/'workspace/runs/bounded';root.mkdir(parents=True)
    target=root/'segments.json';target.write_bytes(b'{"chapters":[],"owner":"legacy"}');before=target.read_bytes()
    p=SyntheticProvider(None)
    with pytest.raises(RuntimeError):run(tmp_path,source,lambda g:p)
    assert p.network_calls==0 and target.read_bytes()==before


def test_same_run_exclusion_precedes_nested_writer(tmp_path,monkeypatch):
    source=setup_input(tmp_path,monkeypatch);nested=SyntheticProvider(None)
    def during(*_):
        with pytest.raises(RuntimeError,match='in use'):run(tmp_path,source,lambda g:nested)
    p=SyntheticProvider(None,during);summary,_=run(tmp_path,source,lambda g:p)
    assert not summary.aborted and nested.network_calls==0


def test_pinned_resume_skips_verified_outputs_and_counts_cumulatively(tmp_path,monkeypatch):
    source=setup_input(tmp_path,monkeypatch)
    (source/'001-test.md').write_text('# Synthetic\n\n## Unit\n\n合成入力一です。\n\n合成入力二です。\n')
    calls=[]
    class P(SyntheticProvider):
        def generate(self,messages,options=None):
            text=messages[-1].content
            contract=json.loads(text[text.index('{'):])
            ids=[row['segment_id'] for row in contract['segments']]
            calls.extend(ids)
            return ModelResult(provider_id=self.provider_id,model_name=self.model_name,
                raw_output=json.dumps({'items':[{'segment_id':sid,'translation':'合成候选。'} for sid in ids]}))
    def execute():
        return run_draft_stage_b(repo_root=tmp_path,input_dir=source,limit_chapters=1,run_id='resume',
             provider_factory=lambda g:P(g),run_budget=RunBudget(max_api_calls=4),tick_max_segments=1,
             batch_token_budget=10000,max_segments_per_call=1)
    first,_=execute();second,root=execute();third,_=execute()
    assert calls==['ch-001-seg-001','ch-001-seg-002']
    assert second.api_calls==third.api_calls==2 and third.translated_segments==2
    cp=json.loads((tmp_path/'workspace/checkpoints/resume.json').read_text())
    assert cp['status']=='completed' and len(cp['completed_segments'])==2


def test_change_during_provider_call_preserves_source_and_old_candidate(tmp_path,monkeypatch):
    source=setup_input(tmp_path,monkeypatch);target=source/'001-test.md'
    def change(*_):target.write_text('# Owner\n\n## Edit\n\n用户改过原文。\n')
    p=SyntheticProvider(None,change)
    with pytest.raises(RuntimeError,match='source version'):run(tmp_path,source,lambda g:p)
    cp=json.loads((tmp_path/'workspace/checkpoints/bounded.json').read_text())
    assert not cp['completed_segments'] and '用户改过' in target.read_text()
    doc=json.loads((tmp_path/'workspace/runs/bounded/segments.json').read_text())
    assert not doc['chapters'][0]['segments'][0]['draft_text']


def test_owner_target_edit_during_call_is_not_overwritten(tmp_path,monkeypatch):
    source=setup_input(tmp_path,monkeypatch);target=tmp_path/'workspace/runs/bounded/segments.json'
    def change(*_):target.write_bytes(b'{"owner":"manual edit"}')
    p=SyntheticProvider(None,change)
    with pytest.raises(RuntimeError,match='owner edit'):run(tmp_path,source,lambda g:p)
    assert target.read_bytes()==b'{"owner":"manual edit"}'
    cp=json.loads((tmp_path/'workspace/checkpoints/bounded.json').read_text());assert not cp['completed_segments']


def test_corrupt_counter_is_preserved_and_not_used_for_new_call(tmp_path,monkeypatch):
    source=setup_input(tmp_path,monkeypatch);run(tmp_path,source,lambda g:SyntheticProvider(g))
    cp=tmp_path/'workspace/checkpoints/bounded.json';doc=json.loads(cp.read_text())
    doc['metadata']['draft_execution']['api_calls_used']=0
    cp.write_text(json.dumps(doc));before=cp.read_bytes();p=SyntheticProvider(None)
    with pytest.raises(RuntimeError,match='invalid durable'):run(tmp_path,source,lambda g:p)
    assert p.network_calls==0 and cp.read_bytes()==before


def test_restart_does_not_raise_existing_call_limit(tmp_path,monkeypatch):
    source=setup_input(tmp_path,monkeypatch);run(tmp_path,source,lambda g:SyntheticProvider(g),cap=1)
    cp=tmp_path/'workspace/checkpoints/bounded.json';before=cp.read_bytes();p=SyntheticProvider(None)
    with pytest.raises(RuntimeError,match='identity changed'):run(tmp_path,source,lambda g:p,cap=2)
    assert p.network_calls==0 and cp.read_bytes()==before


def test_keyboard_interrupt_reserves_without_done_id(tmp_path,monkeypatch):
    source=setup_input(tmp_path,monkeypatch)
    def stop(*_):raise KeyboardInterrupt()
    p=SyntheticProvider(None,stop)
    with pytest.raises(KeyboardInterrupt):run(tmp_path,source,lambda g:p)
    cp=json.loads((tmp_path/'workspace/checkpoints/bounded.json').read_text())
    assert cp['metadata']['draft_execution']['api_calls_used']==1
    assert cp['metadata']['draft_execution']['attempts'][0]['status']=='interrupted'
    assert cp['completed_segments']==[]
    newer=SyntheticProvider(None);summary,_=run(tmp_path,source,lambda g:newer)
    assert newer.network_calls==0 and summary.aborted


def test_output_commit_then_checkpoint_failure_recovers_without_second_call(tmp_path,monkeypatch):
    from translation.draft_execution import DraftExecution
    source=setup_input(tmp_path,monkeypatch);original=DraftExecution.update;injected=[]
    def update(self,state):
        if state['api_calls_used'] and state['output_sha256'] and not state['pending_output'] and not injected and any(
            seg['draft_text'] for chapter in json.loads((self.root/'segments.json').read_text())['chapters'] for seg in chapter['segments']):
            injected.append(True);raise OSError('synthetic after output commit')
        return original(self,state)
    monkeypatch.setattr(DraftExecution,'update',update)
    p=SyntheticProvider(None)
    with pytest.raises(OSError):run(tmp_path,source,lambda g:p)
    monkeypatch.setattr(DraftExecution,'update',original)
    newer=SyntheticProvider(None);summary,root=run(tmp_path,source,lambda g:newer)
    assert p.network_calls==1 and newer.network_calls==0
    assert summary.api_calls==1 and summary.translated_segments==1
    cp=json.loads((tmp_path/'workspace/checkpoints/bounded.json').read_text())
    assert cp['status']=='completed' and cp['completed_segments']==['ch-001-seg-001']


def test_pending_output_before_commit_recovers_without_second_call(tmp_path,monkeypatch):
    import translation.draft_execution as module
    source=setup_input(tmp_path,monkeypatch);original=module.os.replace
    def replace(src,dst):
        cp=tmp_path/'workspace/checkpoints/bounded.json'
        state=json.loads(cp.read_text())['metadata']['draft_execution'] if cp.exists() else {}
        if Path(src).name=='.segments.pending.json' and state.get('api_calls_used',0)>0:
            raise OSError('synthetic before candidate promotion')
        return original(src,dst)
    monkeypatch.setattr(module.os,'replace',replace)
    p=SyntheticProvider(None)
    with pytest.raises(OSError):run(tmp_path,source,lambda g:p)
    assert (tmp_path/'workspace/runs/bounded/.segments.pending.json').is_file()
    monkeypatch.setattr(module.os,'replace',original)
    newer=SyntheticProvider(None);summary,_=run(tmp_path,source,lambda g:newer)
    assert summary.translated_segments==1 and newer.network_calls==0 and p.network_calls==1


def test_one_extra_confirmed_transient_retry_is_counted(tmp_path,monkeypatch):
    source=setup_input(tmp_path,monkeypatch)
    class Transient(RuntimeError):status_code=429
    def fail_once(p,_):
        if p.network_calls==1:raise Transient('synthetic429')
    p=SyntheticProvider(None,fail_once);summary,_=run(tmp_path,source,lambda g:p,cap=2)
    assert not summary.aborted and p.network_calls==summary.api_calls==2
    cp=json.loads((tmp_path/'workspace/checkpoints/bounded.json').read_text())
    assert [r['status'] for r in cp['metadata']['draft_execution']['attempts']]==['failed','succeeded']


def test_absolute_provider_deadline_denies_dispatch(tmp_path):
    import time
    from providers.cost_guard import CostGuard,CostGuardConfig,CostGuardError
    from providers.types import Message
    guard=CostGuard(CostGuardConfig(real_api_tests_enabled=True,max_test_cost_usd=1,
        max_tokens_per_run=10000,log_dir=tmp_path,deadline_at_unix=time.time()-1))
    with pytest.raises(CostGuardError,match='deadline'):
        with guard.attempt([Message('user','synthetic')],20):
            raise AssertionError('provider entered after deadline')


def test_parser_uses_the_same_bytes_that_are_pinned_even_during_aba_edit(tmp_path,monkeypatch):
    import translation.draft_runner as module
    source=setup_input(tmp_path,monkeypatch);path=source/'001-test.md';before=path.read_bytes()
    original=module.parse_chapter_file
    def parse(path,**kwargs):
        path.write_text('# Synthetic\n\n## Unit\n\nSOURCE_CHANGED_DURING_PARSE\n')
        try:return original(path,**kwargs)
        finally:path.write_bytes(before)
    monkeypatch.setattr(module,'parse_chapter_file',parse)
    def check(_,messages):
        assert not any('SOURCE_CHANGED_DURING_PARSE' in m.content for m in messages)
    p=SyntheticProvider(None,check);summary,_=run(tmp_path,source,lambda g:p)
    assert not summary.aborted and p.network_calls==1


def test_zero_usd_denial_is_not_reported_as_real_api_call(tmp_path,monkeypatch):
    source=setup_input(tmp_path,monkeypatch)
    monkeypatch.setenv('REAL_API_TESTS_ENABLED','true');monkeypatch.setenv('MAX_TEST_COST_USD','0')
    summary,root=run_draft_stage_b(repo_root=tmp_path,input_dir=source,limit_chapters=1,
        run_id='blocked-money',run_budget=RunBudget(max_api_calls=2))
    assert summary.aborted
    metadata=json.loads((root/'run_metadata.json').read_text())
    assert metadata['real_api_called'] is False


def test_empty_unpinned_checkpoint_cannot_reset_unknown_prior_spend(tmp_path,monkeypatch):
    source=setup_input(tmp_path,monkeypatch);cp=tmp_path/'workspace/checkpoints/bounded.json'
    cp.parent.mkdir(parents=True);cp.write_text(json.dumps({'run_id':'bounded','completed_segments':[],
        'spent_usd':0.01,'spent_tokens':100,'status':'aborted:legacy','metadata':{}}));before=cp.read_bytes()
    p=SyntheticProvider(None)
    with pytest.raises(RuntimeError,match='unverified legacy'):run(tmp_path,source,lambda g:p)
    assert p.network_calls==0 and cp.read_bytes()==before


def test_process_death_reconciles_physical_attempt_before_reporting_no_network(tmp_path,monkeypatch):
    import subprocess
    import translation.draft_runner as module
    source=setup_input(tmp_path,monkeypatch);monkeypatch.setenv('REAL_API_TESTS_ENABLED','true')
    program='''import sys,os
from pathlib import Path
sys.path.insert(0,sys.argv[2])
from translation import draft_runner as m
class P:
 provider_id='model_router';model_name='synthetic'
 def __init__(self,g):self.cost_guard=g
 def generate(self,messages,options=None):
  with self.cost_guard.attempt(messages,20):os._exit(23)
m.get_provider=lambda mode,cost_guard:P(cost_guard)
m.run_draft_stage_b(repo_root=Path(sys.argv[1]),input_dir=Path(sys.argv[1])/'input_jp',limit_chapters=1,run_id='killed',run_budget=m.RunBudget(max_api_calls=2))
'''
    proc=subprocess.run([sys.executable,'-c',program,str(tmp_path),str(ROOT/'src')])
    assert proc.returncode==23
    p=SyntheticProvider(None);p.provider_id='model_router'
    monkeypatch.setattr(module,'get_provider',lambda mode,cost_guard:p)
    summary,root=run_draft_stage_b(repo_root=tmp_path,input_dir=source,limit_chapters=1,
          run_id='killed',run_budget=RunBudget(max_api_calls=2))
    assert p.network_calls==0 and summary.aborted
    metadata=json.loads((root/'run_metadata.json').read_text())
    assert metadata['real_api_called'] is None
    assert metadata['real_network_observation']=='unknown'
    assert metadata['provider_method_attempts']==1
