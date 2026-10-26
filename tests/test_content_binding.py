"""Synthetic full-source lineage and cross-entry observable budget regressions."""
from pathlib import Path
import json
import sys
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from providers.content_unit_budget import ContentUnitBudget
from providers.types import Message, ModelResult
from consistency.arbitration import run_arbitration
from consistency.retranslate import run_consistency_retranslate

SOURCE = '# Synthetic\n\n## Unit\n\n風が吹く。\n'


class Spy:
    def __init__(self): self.calls = 0
    def generate(self, *_):
        self.calls += 1
        return ModelResult(provider_id='synthetic', model_name='synthetic',
            raw_output=json.dumps({'items':[{'segment_id':'seg-1','translation':'风吹过。'}],
                                   'canonical_target':'示例'}))


def arbitration_candidate(root, chapters):
    # Explicit original evidence keeps these budget tests on the dispatch path.
    import hashlib
    folder=root/'input_cn' if (root/'input_cn').is_dir() else root/'input_jp'
    evidence=[]
    for chapter in chapters:
        path=next(folder.glob(f"{int(chapter.split('-')[-1]):03d}-*.md"));text=path.read_text()
        evidence.append({'chapter_id':chapter,'source_revision':hashlib.sha256(text.encode()).hexdigest(),
            'start_char':0,'end_char':len(text),'quote':text})
    return {'kind':'shared_target','chapters':chapters,'source_evidence':evidence}


def fixture(root, *, source=True):
    run = root/'workspace/runs/test_draft_stage_b';run.mkdir(parents=True)
    (run/'run_metadata.json').write_text(json.dumps({'run_id':run.name,'phase':'draft'}))
    (run/'run_progress.json').write_text(json.dumps({'status':'completed','total_segments':1,'completed_segments':1}))
    path = run/'segments.json'
    path.write_text(json.dumps({'language_direction':'JP_TO_CN','chapters':[{
        'chapter_id':'ch-001','source_path':'input_jp/001-synthetic.md','segments':[
            {'segment_id':'seg-1','source_text':'風が吹く。','draft_text':'旧候选。'}]}]}))
    if source:
        target = root/'input_jp/001-synthetic.md';target.parent.mkdir();target.write_text(SOURCE)
    return {'retranslate_tasks':[{'segment_ids':['seg-1']}]} , path


def test_missing_full_source_cannot_dispatch_from_stored_fragment(tmp_path):
    plan, path = fixture(tmp_path, source=False);before=path.read_bytes();spy=Spy()
    try: run_consistency_retranslate(plan, tmp_path, provider=spy, max_api_calls=1)
    except (ValueError, RuntimeError): pass
    assert spy.calls == 0 and path.read_bytes() == before


def test_exhausted_draft_unit_cannot_reset_through_new_retranslation_checkpoint(tmp_path):
    plan, path = fixture(tmp_path);before=path.read_bytes()
    unit=ContentUnitBudget(tmp_path/'workspace/checkpoints', SOURCE)
    for i in range(8):
        with unit.operation([Message(role='user',content=f'previous synthetic {i}')],role='review'): pass
    spy=Spy()
    try:
        run_consistency_retranslate(plan,tmp_path,provider=spy,max_api_calls=1,
            checkpoint_path=tmp_path/'renamed-checkpoint.json')
    except (ValueError, RuntimeError): pass
    assert spy.calls == 0 and path.read_bytes() == before


def test_arbitration_without_proven_chapter_lineage_cannot_dispatch(tmp_path):
    spy=Spy()
    try:
        run_arbitration([{'kind':'shared_target'}],provider=spy,max_api_calls=1,
            checkpoint_path=tmp_path/'arbitration.json')
    except (ValueError, RuntimeError): pass
    assert spy.calls == 0


def test_arbitration_and_retranslation_share_same_whole_source_budget(tmp_path):
    plan, target = fixture(tmp_path);before=target.read_bytes()
    unit=ContentUnitBudget(tmp_path/'workspace/checkpoints', SOURCE)
    for i in range(7):
        with unit.operation([Message(role='user',content=f'earlier review {i}')],role='review'): pass
    review=Spy()
    result=run_arbitration([arbitration_candidate(tmp_path,['ch-001'])],provider=review,
        max_api_calls=1,checkpoint_path=tmp_path/'arb.json',repo_root=tmp_path)
    assert review.calls == 1 and result['status']=='PASS'
    repair=Spy();result=run_consistency_retranslate(plan,tmp_path,provider=repair,max_api_calls=1)
    assert repair.calls==result['completed_segments']==0 and target.read_bytes()==before
    rows=json.loads(unit.path.read_text())['metadata']['content_unit_budget']['operations']
    assert len(rows)==8 and rows[-1]['role']=='review'


def test_two_controlled_corrections_are_shared_across_new_checkpoints(tmp_path):
    plan, target=fixture(tmp_path)
    class Repair(Spy):
        def __init__(self, text):super().__init__();self.text=text
        def generate(self,*args):
            result=super().generate(*args)
            result.raw_output=json.dumps({'items':[{'segment_id':'seg-1','translation':self.text}]})
            return result
    for number,text in [(1,'候选一。'),(2,'候选二。')]:
        provider=Repair(text)
        report=run_consistency_retranslate(plan,tmp_path,provider=provider,max_api_calls=1,
            checkpoint_path=tmp_path/f'correction-{number}.json')
        assert provider.calls==report['completed_segments']==1
    before=target.read_bytes();third=Repair('候选三。')
    report=run_consistency_retranslate(plan,tmp_path,provider=third,max_api_calls=1,
        checkpoint_path=tmp_path/'renamed-agent-checkpoint.json')
    assert third.calls==report['completed_segments']==0 and target.read_bytes()==before
    unit=ContentUnitBudget(tmp_path/'workspace/checkpoints', SOURCE)
    record=json.loads(unit.path.read_text())['metadata']['content_unit_budget']
    assert record['revision']==2 and len(record['correction_keys'])==2
    assert len(record['operations'])==2


def test_multi_source_review_counts_each_physical_retry_for_every_source(tmp_path):
    from providers.cost_guard import CostGuard,CostGuardConfig
    fixture(tmp_path)
    second='# Second\n\n雨が降る。\n';(tmp_path/'input_jp/002-synthetic.md').write_text(second)
    units=[ContentUnitBudget(tmp_path/'workspace/checkpoints',text) for text in [SOURCE,second]]
    class Transient(RuntimeError):status_code=503
    class Retried(Spy):
        def __init__(self):
            super().__init__();self.cost_guard=CostGuard(CostGuardConfig(real_api_tests_enabled=True,
                max_test_cost_usd=1,max_tokens_per_run=100000,log_dir=tmp_path/'provider'))
        def generate(self,messages,options):
            for i in range(2):
                try:
                    with self.cost_guard.attempt(messages,20):
                        for unit in units:
                            rows=json.loads(unit.path.read_text())['metadata']['content_unit_budget']['operations']
                            assert len(rows)==i+1 and rows[-1]['status']=='reserved'
                        self.calls+=1
                        if i==0:raise Transient()
                except Transient:continue
            return ModelResult(provider_id='synthetic',model_name='synthetic',raw_output='{"canonical_target":"示例"}')
    provider=Retried()
    report=run_arbitration([arbitration_candidate(tmp_path,['ch-001','ch-002'])],provider=provider,
        max_api_calls=1,checkpoint_path=tmp_path/'arb.json',repo_root=tmp_path)
    assert report['status']=='PASS' and provider.calls==provider.cost_guard.call_count==2
    assert provider.cost_guard.content_unit_lease is None
    for unit in units:
        assert len(json.loads(unit.path.read_text())['metadata']['content_unit_budget']['operations'])==2


def test_ambiguous_repeated_fragment_is_not_a_new_budget_unit(tmp_path):
    plan,target=fixture(tmp_path)
    (tmp_path/'input_jp/001-synthetic.md').write_text(SOURCE+'\n風が吹く。\n')
    before=target.read_bytes();provider=Spy()
    with pytest.raises(ValueError,match='ambiguous'):
        run_consistency_retranslate(plan,tmp_path,provider=provider,max_api_calls=1)
    assert provider.calls==0 and target.read_bytes()==before


def test_source_path_escape_is_denied_before_reading_outside_input(tmp_path,monkeypatch):
    root=tmp_path/'repo';plan,target=fixture(root)
    outside=tmp_path/'001-outside.md';outside.write_text(SOURCE)
    doc=json.loads(target.read_text());doc['chapters'][0]['source_path']='input_jp/../../001-outside.md'
    target.write_text(json.dumps(doc));read=Path.read_bytes
    def check(path):
        assert path.resolve()!=outside,'outside source content was read'
        return read(path)
    monkeypatch.setattr(Path,'read_bytes',check);provider=Spy()
    with pytest.raises(ValueError,match='path'):
        run_consistency_retranslate(plan,root,provider=provider,max_api_calls=1)
    assert provider.calls==0


def test_whole_source_edit_outside_fragment_invalidates_completed_checkpoint(tmp_path):
    plan,target=fixture(tmp_path)
    report=run_consistency_retranslate(plan,tmp_path,provider=Spy(),max_api_calls=1)
    cp=Path(report['checkpoint_path']);before=cp.read_bytes();draft=target.read_bytes()
    (tmp_path/'input_jp/001-synthetic.md').write_text(SOURCE+'\n別の文。\n')
    provider=Spy()
    with pytest.raises(ValueError,match='changed-input'):
        run_consistency_retranslate(plan,tmp_path,provider=provider,max_api_calls=1)
    assert provider.calls==0 and cp.read_bytes()==before and target.read_bytes()==draft


def test_unknown_simulation_result_never_applies_target(tmp_path):
    plan,target=fixture(tmp_path);before=target.read_bytes()
    class Simulation(Spy):
        def generate(self,*args):
            result=super().generate(*args);result.dry_run=True;return result
    provider=Simulation();report=run_consistency_retranslate(plan,tmp_path,provider=provider,max_api_calls=1)
    assert provider.calls==1 and report['completed_segments']==0 and target.read_bytes()==before


def test_cn_to_jp_source_binding_and_request_direction_are_preserved(tmp_path):
    plan,target=fixture(tmp_path)
    source=tmp_path/'input_cn/001-synthetic.md';source.parent.mkdir();source.write_text('# 合成\n\n风吹过。\n')
    doc=json.loads(target.read_text());doc['language_direction']='CN_TO_JP'
    doc['chapters'][0]['source_path']=str(source);doc['chapters'][0]['segments'][0]['source_text']='风吹过。'
    target.write_text(json.dumps(doc))
    class Check(Spy):
        def generate(self,messages,options):
            assert options.language_direction=='CN_TO_JP'
            assert 'into accurate natural Japanese' in messages[-1].content
            assert 'Simplified Chinese' not in messages[-1].content
            return super().generate(messages,options)
    provider=Check();run_consistency_retranslate(plan,tmp_path,provider=provider,max_api_calls=1)
    assert provider.calls==1


def test_round_ten_unit_limit_survives_checkpoint_resume(tmp_path):
    folder=tmp_path/'input_jp';folder.mkdir()
    candidates=[]
    for i in range(1,12):
        (folder/f'{i:03d}-synthetic.md').write_text(f'# Synthetic {i}\n\n合成原文{i}。\n')
        candidates.append(arbitration_candidate(tmp_path,[f'ch-{i:03d}']))
    provider=Spy();cp=tmp_path/'arb.json'
    report=run_arbitration(candidates,provider=provider,max_api_calls=20,checkpoint_path=cp,repo_root=tmp_path)
    assert provider.calls==10 and report['budget_exhausted'] and report['arbitrated_count']==10
    other=Spy();resumed=run_arbitration(candidates,provider=other,max_api_calls=20,checkpoint_path=cp,repo_root=tmp_path)
    assert other.calls==0 and resumed['budget_exhausted']
    assert len(json.loads(cp.read_text())['content_unit_ids_used'])==10


def test_round_duration_is_not_reset_after_interruption(tmp_path):
    import time
    plan,target=fixture(tmp_path)
    class Interrupt(Spy):
        def generate(self,*_):raise KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt):
        run_consistency_retranslate(plan,tmp_path,provider=Interrupt(),max_api_calls=2)
    cp=tmp_path/'workspace/consistency_audit/retranslate_progress.json'
    state=json.loads(cp.read_text());state['content_round_started_at']=time.time()-2401
    cp.write_text(json.dumps(state));provider=Spy()
    report=run_consistency_retranslate(plan,tmp_path,provider=provider,max_api_calls=2)
    assert provider.calls==0 and report['budget_exhausted']


@pytest.mark.parametrize('kind',['router','openrouter'])
def test_registered_content_adapter_denies_unbound_dispatch(tmp_path,monkeypatch,kind):
    from providers.cost_guard import CostGuard,CostGuardConfig
    from providers.router_provider import RouterProvider
    from providers.openrouter_provider import OpenRouterProvider
    from providers.types import GenerateOptions
    monkeypatch.setenv('OPENROUTER_API_KEY','synthetic-key')
    guard=CostGuard(CostGuardConfig(real_api_tests_enabled=True,max_test_cost_usd=1,
        max_tokens_per_run=100000,log_dir=tmp_path/'provider'))
    provider=(RouterProvider if kind=='router' else OpenRouterProvider)(cost_guard=guard,max_tokens=20)
    entries=[]
    def inner(*_,**__):entries.append(1);raise RuntimeError('unbound synthetic provider entered')
    if kind=='router':provider._chat=inner
    else:monkeypatch.setattr(provider._inner,'chat',inner)
    with pytest.raises(RuntimeError):
        provider.generate([Message(role='user',content='synthetic content')],GenerateOptions(pipeline_stage='draft_translation'))
    assert entries==[]


def test_legacy_refinement_direct_entry_refuses_before_effects(tmp_path,monkeypatch):
    from translation.refine_runner import run_refine_controlled
    plan,target=fixture(tmp_path);root=target.parent
    monkeypatch.setenv('REAL_API_TESTS_ENABLED','false')
    monkeypatch.delenv('TRANSLATION_ROUND_ID',raising=False)
    before={str(p):p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()};calls=[]
    def factory(guard):calls.append(1);return Spy()
    try:
        run_refine_controlled(repo_root=tmp_path,run_id=root.name,limit_segments=1,provider_factory=factory)
    except RuntimeError:pass
    after={str(p):p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    assert calls==[] and after==before


def test_registered_router_accepts_bound_content_and_observes_reservation_before_entry(tmp_path,monkeypatch):
    from providers.cost_guard import CostGuard,CostGuardConfig
    from providers.router_provider import RouterProvider
    from model_router.chat_types import ChatResult,UsageInfo
    from model_router.config_loader import RouterConfig,ProfileConfig,ProviderConfig
    from model_router.modelRouter import ModelRouter
    fixture(tmp_path)
    unit=ContentUnitBudget(tmp_path/'workspace/checkpoints',SOURCE)
    guard=CostGuard(CostGuardConfig(real_api_tests_enabled=True,max_test_cost_usd=1,
        max_tokens_per_run=100000,log_dir=tmp_path/'provider'))
    config=RouterConfig('consistency_arbitration',{'consistency_arbitration':ProfileConfig(
        'consistency_arbitration','p','synthetic',max_tokens=20)},
        {'p':ProviderConfig('p','openai',max_retries=0)},Path('synthetic'))
    router=ModelRouter(config);entries=[]
    class Inner:
        def chat(self,*_,**__):
            rows=json.loads(unit.path.read_text())['metadata']['content_unit_budget']['operations']
            physical=json.loads((tmp_path/'provider/attempt_budget.json').read_text())
            assert len(rows)==physical['call_count']==1
            assert rows[0]['status']==physical['attempts'][0]['status']=='reserved'
            entries.append(1)
            return ChatResult('{"canonical_target":"示例"}','synthetic','p',UsageInfo(2,1,3),{})
    monkeypatch.setattr(router,'_get_provider',lambda _:Inner())
    provider=RouterProvider(cost_guard=guard,profile='consistency_arbitration',max_tokens=20)
    provider._chat=router.chat
    report=run_arbitration([arbitration_candidate(tmp_path,['ch-001'])],provider=provider,
        max_api_calls=1,checkpoint_path=tmp_path/'arb.json',repo_root=tmp_path)
    assert report['status']=='PASS' and entries==[1]
    assert guard.content_unit_lease is None


def test_cn_to_jp_arbitration_keeps_target_direction(tmp_path):
    folder=tmp_path/'input_cn';folder.mkdir();(folder/'001-synthetic.md').write_text('# 合成\n\n风吹过。\n')
    class Check(Spy):
        def generate(self,messages,options):
            assert options.language_direction=='CN_TO_JP'
            assert 'canonical Japanese target' in messages[-1].content
            assert 'Simplified Chinese' not in messages[-1].content
            return super().generate(messages,options)
    provider=Check();report=run_arbitration([arbitration_candidate(tmp_path,['ch-001'])],
        provider=provider,max_api_calls=1,checkpoint_path=tmp_path/'arb.json',repo_root=tmp_path,
        language_direction='CN_TO_JP')
    assert provider.calls==1 and report['status']=='PASS'


def test_duplicate_draft_chapter_identity_is_rejected_before_artifacts(tmp_path,monkeypatch):
    from translation.draft_runner import run_draft_stage_b,RunBudget
    folder=tmp_path/'input_jp';folder.mkdir()
    (folder/'001-a.md').write_text(SOURCE)
    (folder/'001-b.md').write_text('# Different\n\n雨が降る。\n')
    monkeypatch.setenv('CONTROLLED_RUN_ENABLED','true')
    monkeypatch.setenv('REAL_API_TESTS_ENABLED','false')
    provider=Spy()
    with pytest.raises((ValueError,RuntimeError),match='duplicate'):
        run_draft_stage_b(repo_root=tmp_path,input_dir=folder,limit_chapters=2,run_id='duplicates',
            provider_factory=lambda _:provider,run_budget=RunBudget(max_api_calls=8))
    assert provider.calls==0 and not (tmp_path/'workspace/runs/duplicates').exists()


def test_source_edit_during_final_target_write_restores_exact_preimage(tmp_path,monkeypatch):
    import consistency.retranslate as module
    plan,target=fixture(tmp_path);before=target.read_bytes();original=module.atomic_write_json
    source=tmp_path/'input_jp/001-synthetic.md'
    def race(path,payload):
        if path==target:source.write_text(SOURCE+'\nOwner source edit.\n')
        return original(path,payload)
    monkeypatch.setattr(module,'atomic_write_json',race)
    with pytest.raises((ValueError,RuntimeError),match='source'):
        run_consistency_retranslate(plan,tmp_path,provider=Spy(),max_api_calls=1)
    assert target.read_bytes()==before
    cp=json.loads((tmp_path/'workspace/consistency_audit/retranslate_progress.json').read_text())
    assert cp['completed_segment_ids']==[] and cp['provider_invocations_used']==1


def test_interrupted_target_commit_then_source_edit_recovers_before_new_model_call(tmp_path,monkeypatch):
    import consistency.retranslate as module
    plan,target=fixture(tmp_path);before=target.read_bytes();original=module.atomic_write_json
    def interrupted(path,payload):
        original(path,payload)
        if path==target:raise KeyboardInterrupt()
    monkeypatch.setattr(module,'atomic_write_json',interrupted)
    with pytest.raises(KeyboardInterrupt):
        run_consistency_retranslate(plan,tmp_path,provider=Spy(),max_api_calls=1)
    assert target.read_bytes()!=before
    (tmp_path/'input_jp/001-synthetic.md').write_text(SOURCE+'\nOwner changed source after crash.\n')
    monkeypatch.setattr(module,'atomic_write_json',original);unused=Spy()
    with pytest.raises(ValueError,match='source changed'):
        run_consistency_retranslate(plan,tmp_path,provider=unused,max_api_calls=1)
    assert unused.calls==0 and target.read_bytes()==before
    cp=json.loads((tmp_path/'workspace/consistency_audit/retranslate_progress.json').read_text())
    assert cp['completed_segment_ids']==[] and 'source_bound_write' not in cp


@pytest.mark.parametrize('mismatch', [
    'simulation', 'input', 'correction', 'request', 'checkpoint_path', 'plan',
    'transaction_input', 'transaction_correction', 'target_versions', 'budget_increase',
    'legacy_transaction', 'run_metadata', 'transaction_sources',
])
def test_unverified_pending_transaction_cannot_restore_target_or_rewrite_checkpoint(tmp_path,monkeypatch,mismatch):
    import consistency.retranslate as module
    plan,target=fixture(tmp_path);original=module.atomic_write_json
    def interrupted(path,payload):
        original(path,payload)
        if path==target:raise KeyboardInterrupt()
    with monkeypatch.context() as patch:
        patch.setattr(module,'atomic_write_json',interrupted)
        with pytest.raises(KeyboardInterrupt):
            run_consistency_retranslate(plan,tmp_path,provider=Spy(),max_api_calls=1)
    cp=tmp_path/'workspace/consistency_audit/retranslate_progress.json'
    state=json.loads(cp.read_text());assert state.get('source_bound_write')
    if mismatch=='simulation':state['mode']='simulation'
    elif mismatch=='input':state['input_sha256']='0'*64
    elif mismatch=='correction':state['correction_key']='0'*64
    elif mismatch=='request':state['request_sha256']='0'*64
    elif mismatch=='checkpoint_path':cp=cp.with_name('copied-run.json')
    elif mismatch=='plan':plan['retranslate_tasks'][0]['reason']='different correction request'
    elif mismatch=='transaction_input':state['source_bound_write']['input_sha256']='0'*64
    elif mismatch=='transaction_correction':state['source_bound_write']['correction_key']='0'*64
    elif mismatch=='target_versions':state['target_versions']={'seg-1':'0'*64}
    elif mismatch=='legacy_transaction':state['source_bound_write'].pop('request_sha256')
    elif mismatch=='run_metadata':
        metadata=target.parent/'run_metadata.json';doc=json.loads(metadata.read_text())
        doc['run_id']='replaced-run';metadata.write_text(json.dumps(doc))
    elif mismatch=='transaction_sources':state['source_bound_write']['sources'][0]['sha256']='0'*64
    cp.write_text(json.dumps(state))
    # This is a plausible committed postimage, rather than a conflicting owner edit.
    (tmp_path/'input_jp/001-synthetic.md').write_text(SOURCE+'\nChanged outside fragment.\n')
    before_target=target.read_bytes();before_cp=cp.read_bytes();unused=Spy()
    with pytest.raises(ValueError):
        run_consistency_retranslate(plan,tmp_path,provider=unused,max_api_calls=(2 if mismatch=='budget_increase' else 1),
            checkpoint_path=cp)
    assert unused.calls==0 and target.read_bytes()==before_target and cp.read_bytes()==before_cp


def test_verified_recovery_can_restore_when_changed_source_no_longer_contains_fragment(tmp_path,monkeypatch):
    import consistency.retranslate as module
    plan,target=fixture(tmp_path);before=target.read_bytes();original=module.atomic_write_json
    def interrupted(path,payload):
        original(path,payload)
        if path==target:raise KeyboardInterrupt()
    with monkeypatch.context() as patch:
        patch.setattr(module,'atomic_write_json',interrupted)
        with pytest.raises(KeyboardInterrupt):
            run_consistency_retranslate(plan,tmp_path,provider=Spy(),max_api_calls=1)
    (tmp_path/'input_jp/001-synthetic.md').write_text('# Replaced source\n\n雨が降る。\n')
    unused=Spy()
    with pytest.raises(ValueError,match='source changed'):
        run_consistency_retranslate(plan,tmp_path,provider=unused,max_api_calls=1)
    assert unused.calls==0 and target.read_bytes()==before


@pytest.mark.parametrize('kind',['fake','dry_run'])
def test_registered_simulation_provider_ids_use_only_simulation_draft_namespace(tmp_path,monkeypatch,kind):
    from providers.fake_provider import FakeProvider
    from providers.dry_run_provider import DryRunProvider
    from translation.draft_runner import run_draft_stage_b,RunBudget
    folder=tmp_path/'input_jp';folder.mkdir();(folder/'001-synthetic.md').write_text(SOURCE)
    monkeypatch.setenv('CONTROLLED_RUN_ENABLED','true');monkeypatch.setenv('REAL_API_TESTS_ENABLED','false')
    monkeypatch.setenv('MAX_TEST_COST_USD','1');monkeypatch.setenv('MAX_TOKENS_PER_RUN','100000')
    summary,output=run_draft_stage_b(repo_root=tmp_path,input_dir=folder,limit_chapters=1,run_id='simulation',
        provider_factory=lambda guard:(FakeProvider if kind=='fake' else DryRunProvider)(cost_guard=guard),
        run_budget=RunBudget(max_api_calls=8))
    assert summary.simulated and summary.translated_segments==0
    assert output==tmp_path/'workspace/simulations/runs/simulation'
    assert not (tmp_path/'workspace/runs/simulation').exists()
    cp=json.loads((tmp_path/'workspace/simulations/checkpoints/simulation.json').read_text())
    assert cp['completed_segments']==[]
