"""Shared Workbench domain paths; synthetic source/decisions only."""
from pathlib import Path
from copy import deepcopy
import sys,json,hashlib
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from workbench.canonical_service import import_sources,import_candidates,selection_status,select_revision,export_selected,CanonicalVersionConflict
from workbench.project_registry import get_project_manifest,patch_project_review_state_cas
from workbench.review_state import DecisionActor,approval_identity
from workbench.canonical_service import prepare_revision_comparison,apply_revision_comparison
from translation.revision_comparison import method_evaluation_packets
from quality_review.calibration import packet_identity
from workbench.canonical_service import restore_previous_candidates


def source(root,direction='JP_TO_CN'):
    (root/'workspace').mkdir(exist_ok=True)
    return import_sources(root,project_id='native-flow',name='Synthetic',language_direction=direction,chapters=[{'filename':'003-synthetic.md','text':'# 章\n\n甲。\n\n乙。'},{'filename':'718-synthetic.md','text':'# 章\n\n丙。'}])


def candidate(root,state):
    return import_candidates(root,'native-flow',expected_manifest_sha256=state['manifest_sha256'],source_inventory_sha256=state['source_inventory_sha256'],candidates=[{'segment_id':r['segment_id'],'target_text':'候选'+r['source']} for r in state['segments']])


def agent(root):
    manifest=get_project_manifest(root,'native-flow')
    patch_project_review_state_cas(root,'native-flow',decision_actor=DecisionActor('agent','synthetic-native-review'),segments={r['id']:{'status':'approved','expected_identity':approval_identity(project_id=manifest.project_id,language_direction=manifest.language_direction,segment=r)} for r in manifest.segments})


def recovery_fixture(root, direction='JP_TO_CN'):
    state=candidate(root,source(root,direction));agent(root)
    state=select_revision(root,'native-flow',expected_manifest_sha256=state['manifest_sha256'],
        target_fields={r['segment_id']:'draft' for r in state['segments']})
    accepted=json.loads((root/'workspace/manifests/native-flow.json').read_bytes())
    state=import_candidates(root,'native-flow',expected_manifest_sha256=state['manifest_sha256'],
        source_inventory_sha256=state['source_inventory_sha256'],candidates=[
            {'segment_id':r['segment_id'],'target_text':r['target_text']+('新' if i==0 else '')}
            for i,r in enumerate(state['segments'])])
    return state,accepted


@pytest.mark.parametrize('direction',['JP_TO_CN','CN_TO_JP'])
def test_recovery_never_resurrects_old_acceptance_and_can_undo(tmp_path,direction):
    state,accepted=recovery_fixture(tmp_path,direction)
    path=tmp_path/'workspace/manifests/native-flow.json';raw=path.read_bytes();before=json.loads(raw)
    review=tmp_path/'workspace/review_state.json';review_raw=review.read_bytes()
    result=restore_previous_candidates(tmp_path,'native-flow',expected_manifest_sha256=state['manifest_sha256'])
    after=json.loads(path.read_bytes());changed=after['segments'][0]
    assert changed['draft']==accepted['segments'][0]['draft'] and changed['status']=='pending'
    assert changed['generated_by']=='recovered_unreviewed_draft' and len(changed['draft_recovery_revision'])==64
    assert approval_identity(project_id='native-flow',language_direction=direction,segment=changed)!=approval_identity(
        project_id='native-flow',language_direction=direction,segment=accepted['segments'][0])
    assert after['segments'][1:]==before['segments'][1:] and review.read_bytes()==review_raw
    assert 'accepted_revision' not in after and 'native_generation' not in after
    assert result['selection']['current_agent_accepted']==2 and not result['selection']['can_select']
    assert not result['approval_issued'] and not result['canonical_adoption'] and not result['human_approved_final']
    assert (path.parent/'.versions/native-flow'/f"{state['manifest_sha256']}.json").read_bytes()==raw
    with pytest.raises(ValueError,match='stale accepted review'):
        select_revision(tmp_path,'native-flow',expected_manifest_sha256=result['selection']['manifest_sha256'],
            target_fields={r['segment_id']:'draft' for r in state['segments']})
    again=restore_previous_candidates(tmp_path,'native-flow',expected_manifest_sha256=result['selection']['manifest_sha256'])
    undone=json.loads(path.read_bytes());assert undone['segments'][0]['draft']==before['segments'][0]['draft']
    assert undone['segments'][0]['draft_recovery_revision']!=changed['draft_recovery_revision']
    assert again['selection']['current_agent_accepted']==2 and review.read_bytes()==review_raw
    assert not (tmp_path/'workspace/checkpoints/content_units').exists()


@pytest.mark.parametrize('failure',['stale','tampered','path','symlink','source','dependency','active','generation_lock','write_lock','write_failure'])
def test_recovery_failures_preserve_current_candidate_and_review(tmp_path,monkeypatch,failure):
    import workbench.canonical_service as service
    import workbench.generation_jobs as jobs
    from workbench.project_registry import _project_write_lock
    state,_=recovery_fixture(tmp_path);path=tmp_path/'workspace/manifests/native-flow.json'
    doc=json.loads(path.read_bytes());snapshot=path.parent/'.versions/native-flow'/f"{doc['previous_manifest_sha256']}.json"
    held=None
    if failure=='tampered':snapshot.write_bytes(snapshot.read_bytes()+b' ')
    if failure=='path':doc['previous_manifest_sha256']='../outside'
    if failure=='symlink':
        raw=snapshot.read_bytes();snapshot.unlink();other=tmp_path/'outside.json';other.write_bytes(raw);snapshot.symlink_to(other)
    if failure=='source':next((tmp_path/'input_jp/native-flow').glob('*.md')).write_text('source changed')
    if failure=='dependency':doc['segments'][0]['dependency_versions']={'synthetic':'a'*64}
    if failure in {'path','dependency'}:path.write_text(json.dumps(doc,ensure_ascii=False));state=selection_status(tmp_path,'native-flow')
    if failure=='active':monkeypatch.setattr(jobs,'get_project_generation_job',lambda *a:{'status':'running'})
    if failure in {'generation_lock','write_lock'}:
        held=jobs.project_generation_lock('native-flow') if failure=='generation_lock' else _project_write_lock('native-flow')
        assert held.acquire(blocking=False)
    if failure=='write_failure':
        def fail(*a):raise OSError('synthetic atomic save failure')
        monkeypatch.setattr(service,'_save_project_manifest_unlocked',fail)
    before=path.read_bytes();review=tmp_path/'workspace/review_state.json';reviews=review.read_bytes()
    try:
        with pytest.raises((ValueError,OSError,RuntimeError)):
            restore_previous_candidates(tmp_path,'native-flow',expected_manifest_sha256='0'*64 if failure=='stale' else state['manifest_sha256'])
    finally:
        if held:held.release()
    assert path.read_bytes()==before and review.read_bytes()==reviews
    assert not (tmp_path/'workspace/checkpoints/content_units').exists()


def test_recovery_of_empty_drafts_is_pending_and_metadata_cannot_be_replayed(tmp_path):
    state=candidate(tmp_path,source(tmp_path));path=tmp_path/'workspace/manifests/native-flow.json'
    doc=json.loads(path.read_bytes());doc['native_generation']={'actor':'synthetic'}
    for row in doc['segments']:row.update(human_reviewed=True,actor_type='agent',model='synthetic',approved=True)
    path.write_text(json.dumps(doc));state=selection_status(tmp_path,'native-flow')
    result=restore_previous_candidates(tmp_path,'native-flow',expected_manifest_sha256=state['manifest_sha256'])
    doc=json.loads(path.read_bytes());assert all(r['draft']=='' and r['status']=='pending' for r in doc['segments'])
    assert all(not ({'human_reviewed','actor_type','model','approved'}&set(r)) for r in doc['segments'])
    assert not result['selection']['can_select'] and 'native_generation' not in doc


def test_recovery_noop_does_not_create_history_or_change_identity(tmp_path):
    from workbench.canonical_service import _archive
    state,_=recovery_fixture(tmp_path);path=tmp_path/'workspace/manifests/native-flow.json'
    raw=path.read_bytes();doc=json.loads(raw);doc['previous_manifest_sha256']=_archive(tmp_path,'native-flow',raw)
    path.write_text(json.dumps(doc));raw=path.read_bytes();state=selection_status(tmp_path,'native-flow')
    versions={p.name:p.read_bytes() for p in (path.parent/'.versions/native-flow').iterdir()}
    result=restore_previous_candidates(tmp_path,'native-flow',expected_manifest_sha256=state['manifest_sha256'])
    assert result['action']=='preserve_original' and result['changed_segment_ids']==[]
    assert not state['recovery']['available'] and path.read_bytes()==raw
    assert versions=={p.name:p.read_bytes() for p in (path.parent/'.versions/native-flow').iterdir()}


def test_recovery_rechecks_live_dependencies_before_archival(tmp_path,monkeypatch):
    import workbench.canonical_service as service
    state,_=recovery_fixture(tmp_path);path=tmp_path/'workspace/manifests/native-flow.json';raw=path.read_bytes()
    original=service._read;calls=0
    def changing(*args,**kwargs):
        nonlocal calls
        result=original(*args,**kwargs);calls+=1
        if calls==2:result[2]['dependency_versions']={'changed-live-entry':'a'*64}
        return result
    monkeypatch.setattr(service,'_read',changing)
    with pytest.raises(CanonicalVersionConflict,match='依赖'):
        restore_previous_candidates(tmp_path,'native-flow',expected_manifest_sha256=state['manifest_sha256'])
    assert path.read_bytes()==raw


def test_recovered_draft_can_be_selected_only_after_fresh_bound_review(tmp_path):
    state,_=recovery_fixture(tmp_path)
    result=restore_previous_candidates(tmp_path,'native-flow',expected_manifest_sha256=state['manifest_sha256'])
    assert not result['selection']['can_select']
    agent(tmp_path);state=selection_status(tmp_path,'native-flow');assert state['can_select']
    state=select_revision(tmp_path,'native-flow',expected_manifest_sha256=state['manifest_sha256'],
        target_fields={r['segment_id']:'draft' for r in state['segments']})
    assert state['selected_current']
    assert export_selected(tmp_path,'native-flow',expected_manifest_sha256=state['manifest_sha256'])['segments_exported']==3


@pytest.mark.parametrize('direction',['JP_TO_CN','CN_TO_JP'])
def test_full_import_candidate_native_accept_select_export(tmp_path,direction):
    root=tmp_path;state=source(root,direction);assert state['segments_total']==3 and not state['can_select']
    state=candidate(root,state);assert not state['can_select']
    with pytest.raises(ValueError,match='stale accepted review'):select_revision(root,'native-flow',expected_manifest_sha256=state['manifest_sha256'],target_fields={r['segment_id']:'draft' for r in state['segments']})
    agent(root);state=selection_status(root,'native-flow');assert state['can_select'] and state['human_approved_final'] is False
    state=select_revision(root,'native-flow',expected_manifest_sha256=state['manifest_sha256'],target_fields={r['segment_id']:'draft' for r in state['segments']})
    result=export_selected(root,'native-flow',expected_manifest_sha256=state['manifest_sha256'])
    assert result['segments_exported']==3 and result['chapters_exported']==2 and result['human_approved_final'] is False


def test_candidate_input_cannot_import_review_actor_or_partial_results(tmp_path):
    state=source(tmp_path);path=tmp_path/'workspace/manifests/native-flow.json';before=path.read_bytes()
    for rows in [[{'segment_id':state['segments'][0]['segment_id'],'target_text':'x'}],[{'segment_id':r['segment_id'],'target_text':'x','actor_type':'agent'} for r in state['segments']]]:
        with pytest.raises(ValueError):import_candidates(tmp_path,'native-flow',expected_manifest_sha256=state['manifest_sha256'],source_inventory_sha256=state['source_inventory_sha256'],candidates=rows)
        assert path.read_bytes()==before


def test_stale_selection_and_candidate_preserve_old_recovery_version(tmp_path):
    state=source(tmp_path);old=(tmp_path/'workspace/manifests/native-flow.json').read_bytes();new=candidate(tmp_path,state)
    assert list((tmp_path/'workspace/manifests/.versions/native-flow').glob('*.json'))[0].read_bytes()==old
    with pytest.raises(CanonicalVersionConflict):candidate(tmp_path,state)
    assert selection_status(tmp_path,'native-flow')['manifest_sha256']==new['manifest_sha256']


def revision_fixture(root, direction='JP_TO_CN', targets=None):
    state=candidate(root,source(root,direction))
    path=root/'workspace/manifests/native-flow.json';doc=json.loads(path.read_text())
    for r in doc['segments']:r['generated_by']='synthetic_original_producer'
    path.write_text(json.dumps(doc,ensure_ascii=False))
    state=selection_status(root,'native-flow');agent(root)
    state=select_revision(root,'native-flow',expected_manifest_sha256=state['manifest_sha256'],
        target_fields={r['segment_id']:'draft' for r in state['segments']})
    row=get_project_manifest(root,'native-flow').segments[0]
    targets=targets or {'simple':'简单候选甲。','problem_driven':'问题候选甲。'}
    origins={name:{'target_revision':hashlib.sha256(text.encode()).hexdigest(),
        'provenance':{'kind':'synthetic_claim','condition':name,
            'source_revision':row['source_binding']['source_revision']}} for name,text in targets.items()}
    plan=prepare_revision_comparison(root,'native-flow',expected_manifest_sha256=state['manifest_sha256'],
        segment_id=row['id'],candidates=targets,origins=origins)
    return state,row,plan


def revision_views(plan, winner='problem_driven'):
    representative=plan['lineages'][winner]['representative'];views=[]
    for packet,reverse in zip(method_evaluation_packets(plan),(False,True)):
        rows=[]
        for case in packet['cases']:
            names=plan['private_mapping'][case['case_id']]
            chosen=representative if representative in names.values() else next(iter(names.values()))
            label=next(k for k,v in names.items() if v==chosen)
            if reverse:label={'A':'B','B':'A'}[label]
            rows.append({'case_id':case['case_id'],'preferred':label,'blocked':[],
                'issues':[],'literary_preference':label,'note':'Synthetic claim; no native/model execution'})
        views.append({'schema':'source-calibration-view/1','order':packet['order'],
            'input_packet_sha256':packet_identity(packet),'cases':rows})
    return views


def apply_revision(root,state,row,plan,views,**overrides):
    kwargs={'expected_manifest_sha256':state['manifest_sha256'],'segment_id':row['id'],
        'plan':plan,'view1':views[0] if views else None,'view2':views[1] if views else None,
        'chosen_target_revision':plan['lineages']['problem_driven']['target_revision'],
        'decision_actor':DecisionActor('agent','synthetic-draft-selector')}
    kwargs.update(overrides)
    return apply_revision_comparison(root,'native-flow',**kwargs)


@pytest.mark.parametrize('direction',['JP_TO_CN','CN_TO_JP'])
def test_revision_changes_only_selected_draft_then_requires_its_fresh_review(tmp_path,direction):
    state,row,plan=revision_fixture(tmp_path,direction)
    path=tmp_path/'workspace/manifests/native-flow.json';raw=path.read_bytes();before=json.loads(raw)
    review_path=tmp_path/'workspace/review_state.json';reviews=review_path.read_bytes()
    sources={p:p.read_bytes() for p in tmp_path.glob('input_*/*/*')}
    result=apply_revision(tmp_path,state,row,plan,revision_views(plan))
    after=json.loads(path.read_bytes());selection=result['selection']
    assert result['action']=='import_unreviewed_draft' and result['changed_segment_ids']==[row['id']]
    assert not result['canonical_adoption'] and not result['human_approved_final']
    assert selection['current_agent_accepted']==2 and not selection['can_select'] and not selection['selected_current']
    assert after['segments'][1:]==before['segments'][1:]
    assert after['source_inventory']==before['source_inventory'] and review_path.read_bytes()==reviews
    assert sources=={p:p.read_bytes() for p in sources}
    archive=tmp_path/'workspace/manifests/.versions/native-flow'/f"{state['manifest_sha256']}.json"
    assert archive.read_bytes()==raw and 'accepted_revision' not in after
    trace=after['segments'][0]['revision_application']
    assert trace['new_target_revision']==plan['lineages']['problem_driven']['target_revision']
    assert trace['cost']['model_operations_in_application']==0 and not trace['approval_issued']
    assert trace['origin_verification']=='unverified_claim' and trace['diff']
    assert not (tmp_path/'workspace/checkpoints/content_units').exists()
    with pytest.raises(ValueError,match='stale accepted review'):
        select_revision(tmp_path,'native-flow',expected_manifest_sha256=selection['manifest_sha256'],
            target_fields={r['segment_id']:'draft' for r in selection['segments']})
    current=get_project_manifest(tmp_path,'native-flow');changed=current.segments[0]
    patch_project_review_state_cas(tmp_path,'native-flow',decision_actor=DecisionActor('agent','synthetic-fresh-source-review'),
        segments={changed['id']:{'status':'approved','expected_identity':approval_identity(
            project_id=current.project_id,language_direction=current.language_direction,segment=changed)}})
    selection=select_revision(tmp_path,'native-flow',expected_manifest_sha256=selection['manifest_sha256'],
        target_fields={r['segment_id']:'draft' for r in selection['segments']})
    assert export_selected(tmp_path,'native-flow',expected_manifest_sha256=selection['manifest_sha256'])['segments_exported']==3


@pytest.mark.parametrize('mode',['old_wins','tie','abstain','disagreement','missing','tampered','identity','normalized','joint'])
def test_revision_preserves_original_without_benefit_or_complete_safe_evidence(tmp_path,mode):
    targets=None
    if mode=='identity':targets={'simple':'候选甲。','problem_driven':'候选甲。'}
    if mode=='normalized':targets={'simple':'共同稿。','problem_driven':' 共同稿。'}
    if mode=='joint':targets={'simple':'共同稿。','problem_driven':'共同稿。'}
    state,row,plan=revision_fixture(tmp_path,targets=targets)
    views=revision_views(plan,'B_old' if mode=='old_wins' else 'problem_driven') if mode!='identity' else []
    kwargs={}
    if mode=='old_wins':kwargs['chosen_target_revision']=plan['lineages']['B_old']['target_revision']
    if mode in {'tie','abstain'}:
        for view in views:
            for r in view['cases']:r['preferred']=mode;r['literary_preference']=mode
    if mode=='disagreement':views[1]['cases'][0]['preferred']={'A':'B','B':'A'}[views[1]['cases'][0]['preferred']]
    if mode=='missing':views[1]=None
    if mode=='tampered':plan['packets'][0]['cases'][0]['source']='篡改原文'
    path=tmp_path/'workspace/manifests/native-flow.json';before=path.read_bytes()
    versions=list((path.parent/'.versions/native-flow').glob('*.json'))
    result=apply_revision(tmp_path,state,row,plan,views,**kwargs)
    if mode=='joint':
        assert result['action']=='import_unreviewed_draft'
        assert result['decision']['experimental_winner'] is None
        assert result['decision']['byte_identical_winner_conditions']==['simple','problem_driven']
    else:
        assert result['action']=='preserve_original' and path.read_bytes()==before
        assert list((path.parent/'.versions/native-flow').glob('*.json'))==versions


@pytest.mark.parametrize('actor',[None,{'actor_type':'agent'},DecisionActor('unknown','x'),DecisionActor('machine','x')])
def test_revision_rejects_untrusted_selector_without_writes(tmp_path,actor):
    state,row,plan=revision_fixture(tmp_path);path=tmp_path/'workspace/manifests/native-flow.json';before=path.read_bytes()
    with pytest.raises(ValueError,match='trusted local'):
        apply_revision(tmp_path,state,row,plan,revision_views(plan),decision_actor=actor)
    assert path.read_bytes()==before


@pytest.mark.parametrize('change',['selected_review','selected_draft','source_file','source_symlink','wrong_choice','active_job','active_lock'])
def test_revision_refuses_stale_or_conflicting_selection(tmp_path,change):
    state,row,plan=revision_fixture(tmp_path);views=revision_views(plan);kwargs={}
    path=tmp_path/'workspace/manifests/native-flow.json'
    if change=='selected_review':
        patch_project_review_state_cas(tmp_path,'native-flow',decision_actor=DecisionActor('agent','another-review'),
            segments={row['id']:{'status':'rejected','expected_identity':plan['input']['binding']['candidate_identity']}})
    if change=='selected_draft':
        doc=json.loads(path.read_text());doc['segments'][0]['draft']='其他改动';path.write_text(json.dumps(doc))
        state={**state,'manifest_sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    if change in {'source_file','source_symlink'}:
        doc=json.loads(path.read_text());p=tmp_path/doc['source_documents'][0]['path']
        if change=='source_file':p.write_text('已变化的源文')
        else:
            other=p.with_name('other.txt');other.write_bytes(p.read_bytes());p.unlink();p.symlink_to(other)
    if change=='wrong_choice':kwargs['chosen_target_revision']='0'*64
    if change=='active_job':
        from workbench.generation_jobs import prepare_generation_job
        prepare_generation_job(tmp_path,'native-flow',request_id='revision-conflict',mode='agent_quota_translation',sample_text='synthetic')
    from workbench.generation_jobs import project_generation_lock
    lock=project_generation_lock('native-flow')
    if change=='active_lock':lock.acquire()
    before=path.read_bytes()
    try:
        with pytest.raises((ValueError,RuntimeError)):
            apply_revision(tmp_path,state,row,plan,views,**kwargs)
    finally:
        if change=='active_lock':lock.release()
    assert path.read_bytes()==before


def test_revision_reuses_plan_after_unrelated_target_and_review_change(tmp_path):
    state,row,plan=revision_fixture(tmp_path);path=tmp_path/'workspace/manifests/native-flow.json'
    doc=json.loads(path.read_text());doc['segments'][2]['draft']='另一个段落独立修订';path.write_text(json.dumps(doc))
    manifest=get_project_manifest(tmp_path,'native-flow');other=manifest.segments[2]
    patch_project_review_state_cas(tmp_path,'native-flow',decision_actor=DecisionActor('agent','other-review'),
        segments={other['id']:{'status':'approved','expected_identity':approval_identity(
            project_id=manifest.project_id,language_direction=manifest.language_direction,segment=other)}})
    state=selection_status(tmp_path,'native-flow');untouched=json.loads(path.read_text())['segments'][1:]
    result=apply_revision(tmp_path,state,row,plan,revision_views(plan))
    assert result['selection']['current_agent_accepted']==2
    assert json.loads(path.read_text())['segments'][1:]==untouched


def test_whole_import_counterexample_does_not_preserve_selected_only_provenance(tmp_path):
    # Existing whole-project import intentionally replaces every producer label;
    # the bounded revision route above must preserve untouched rows instead.
    state,row,plan=revision_fixture(tmp_path);path=tmp_path/'workspace/manifests/native-flow.json'
    before=json.loads(path.read_text());targets=[{'segment_id':r['segment_id'],
        'target_text':plan['input']['candidates']['problem_driven'] if r['segment_id']==row['id']
        else r['target_text']} for r in state['segments']]
    import_candidates(tmp_path,'native-flow',expected_manifest_sha256=state['manifest_sha256'],
        source_inventory_sha256=state['source_inventory_sha256'],candidates=targets)
    after=json.loads(path.read_text())
    assert before['segments'][1]['generated_by']=='synthetic_original_producer'
    assert after['segments'][1]['generated_by']=='imported_candidate'
    assert after['segments'][1]['draft']==before['segments'][1]['draft']


@pytest.mark.parametrize('severity',['high','critical'])
def test_revision_severe_fidelity_veto_preserves_original(tmp_path,severity):
    state,row,plan=revision_fixture(tmp_path,targets={'simple':'共同候选甲。','problem_driven':'共同候选甲。'})
    views=revision_views(plan,'B_old')
    for packet,view in zip(method_evaluation_packets(plan),views):
        for case,result in zip(packet['cases'],view['cases']):
            for label,target in case['candidates'].items():
                if target==plan['input']['candidates']['problem_driven']:
                    result['blocked']=[label]
                    result['literary_preference']=label
                    result['issues']=[{'candidate':label,'issue_type':'MISTRANSLATION','severity':severity,
                        'confidence':1.0,'source_quote':case['source'],'target_quote':target,
                        'reason':'Synthetic severe issue, not real source evaluation'}]
    path=tmp_path/'workspace/manifests/native-flow.json';before=path.read_bytes()
    result=apply_revision(tmp_path,state,row,plan,views,
        chosen_target_revision=plan['lineages']['B_old']['target_revision'])
    assert result['action']=='preserve_original' and path.read_bytes()==before
    assert result['decision']['complete'] and result['decision']['experimental_winner']=='B_old'
    assert result['decision']['severe_candidate_vetoes']==['simple']
    assert result['reason']=='no_benefit_original_wins'


def test_revision_dependency_drift_and_stale_manifest_do_not_change_draft(tmp_path):
    state,row,plan=revision_fixture(tmp_path);path=tmp_path/'workspace/manifests/native-flow.json'
    doc=json.loads(path.read_text());doc['segments'][0]['dependency_versions']={'synthetic.rule':'a'*64}
    path.write_text(json.dumps(doc));before=path.read_bytes()
    with pytest.raises(CanonicalVersionConflict):apply_revision(tmp_path,state,row,plan,revision_views(plan))
    state=selection_status(tmp_path,'native-flow')
    with pytest.raises(CanonicalVersionConflict):apply_revision(tmp_path,state,row,plan,revision_views(plan))
    assert path.read_bytes()==before


def test_revision_retains_existing_cumulative_budget_bytes(tmp_path):
    from providers.content_unit_budget import ContentUnitBudget
    state,row,plan=revision_fixture(tmp_path);doc=json.loads((tmp_path/'workspace/manifests/native-flow.json').read_text())
    text=(tmp_path/doc['source_documents'][0]['path']).read_text()
    unit=ContentUnitBudget(tmp_path/'workspace/checkpoints',text)
    manager,budget=unit._load();manager.checkpoint.metadata['content_unit_budget']=budget;manager.save()
    before=unit.path.read_bytes()
    result=apply_revision(tmp_path,state,row,plan,revision_views(plan))
    snapshot=result['trace']['cost']
    assert snapshot['status']=='recorded' and snapshot['observable_operations']==0
    assert snapshot['revision']==0 and snapshot['model_operations_in_application']==0
    assert snapshot['ledger_sha256']==hashlib.sha256(before).hexdigest() and unit.path.read_bytes()==before


def test_revision_accepts_registered_noncontiguous_source_spans(tmp_path):
    from translation.source_versions import make_source_binding
    from workbench.project_registry import build_source_inventory
    state=source(tmp_path);path=tmp_path/'workspace/manifests/native-flow.json';doc=json.loads(path.read_text())
    first,second=doc['segments'][:2];full=(tmp_path/doc['source_documents'][0]['path']).read_text()
    spans=first['source_binding']['source_spans']+second['source_binding']['source_spans']
    first['source']=first['source']+second['source']
    first['source_binding']=make_source_binding(chapter_id=first['source_binding']['chapter_id'],
        source_revision=first['source_binding']['source_revision'],document_length=len(full),
        source_text=first['source'],source_spans=spans)
    doc['segments'].pop(1);doc.pop('source_context_revision',None)
    doc['source_inventory']=build_source_inventory(doc['segments'],language_direction=doc['language_direction'],
        origin=doc['source_inventory']['origin'])
    path.write_text(json.dumps(doc));state=candidate(tmp_path,selection_status(tmp_path,'native-flow'))
    row=get_project_manifest(tmp_path,'native-flow').segments[0]
    targets={'simple':'合并候选一。','problem_driven':'合并候选二。'}
    origins={k:{'target_revision':hashlib.sha256(v.encode()).hexdigest(),'provenance':{'condition':k,
        'source_revision':row['source_binding']['source_revision']}} for k,v in targets.items()}
    plan=prepare_revision_comparison(tmp_path,'native-flow',expected_manifest_sha256=state['manifest_sha256'],
        segment_id=row['id'],candidates=targets,origins=origins)
    assert plan['input']['binding']['source_binding']['source_spans']==spans
    assert plan['input']['context']==full[:spans[0][0]]
    assert apply_revision(tmp_path,state,row,plan,revision_views(plan))['changed_segment_ids']==[row['id']]


@pytest.mark.parametrize('chapters',[[{'filename':'001-a.md','text':'# empty'}],[{'filename':'001-a.md','text':'a'},{'filename':'001-b.md','text':'b'}],[{'filename':'../001-a.md','text':'a'}]])
def test_invalid_source_import_preserves_no_partial_manifest(tmp_path,chapters):
    (tmp_path/'workspace').mkdir()
    with pytest.raises(ValueError):import_sources(tmp_path,project_id='native-flow',name='x',language_direction='JP_TO_CN',chapters=chapters)
    assert not (tmp_path/'workspace/manifests/native-flow.json').exists()


def test_non_numbered_chapter_is_preserved_and_active_job_blocks_candidate(tmp_path):
    from workbench.generation_jobs import prepare_generation_job
    (tmp_path/'workspace').mkdir()
    state=import_sources(tmp_path,project_id='native-flow',name='序章',language_direction='JP_TO_CN',chapters=[{'filename':'序章.md','text':'# 序章\n\n本文。'}])
    assert state['chapters']==1 and state['segments_total']==1
    before=(tmp_path/'workspace/manifests/native-flow.json').read_bytes()
    prepare_generation_job(tmp_path,'native-flow',request_id='synthetic-active',mode='dry_run',sample_text='source')
    with pytest.raises(ValueError,match='生成仍在运行'):candidate(tmp_path,state)
    assert (tmp_path/'workspace/manifests/native-flow.json').read_bytes()==before


@pytest.mark.parametrize('route',['source','candidate','restore','select','revision'])
@pytest.mark.parametrize('failure',['link','hardlink','corrupt','unsupported','missing_workspace'])
def test_review_preflight_blocks_effects_for_canonical_mutations(tmp_path,monkeypatch,route,failure):
    import os
    from assets import translation_memory as memory
    from workbench import canonical_service as service
    root=tmp_path/'repo';root.mkdir()
    if route == 'source':
        if failure != 'missing_workspace': (root/'workspace').mkdir()
        invoke=lambda:import_sources(root,project_id='native-flow',name='Synthetic',language_direction='JP_TO_CN',
            chapters=[{'filename':'001-synthetic.md','text':'# 章\n\n合成。'}])
    else:
        state=candidate(root,source(root))
        if route == 'candidate':
            invoke=lambda:import_candidates(root,'native-flow',expected_manifest_sha256=state['manifest_sha256'],
                source_inventory_sha256=state['source_inventory_sha256'],candidates=[
                    {'segment_id':r['segment_id'],'target_text':'更改'} for r in state['segments']])
        elif route == 'restore':
            invoke=lambda:restore_previous_candidates(root,'native-flow',expected_manifest_sha256=state['manifest_sha256'])
        elif route == 'select':
            invoke=lambda:select_revision(root,'native-flow',expected_manifest_sha256=state['manifest_sha256'],target_fields={})
        else:
            invoke=lambda:apply_revision_comparison(root,'native-flow',expected_manifest_sha256=state['manifest_sha256'],
                segment_id='synthetic',plan={},view1={},view2={},chosen_target_revision='0'*64,
                decision_actor=DecisionActor('agent','synthetic'))
    workspace=root/'workspace';leaf=workspace/'review_state.json'
    external=tmp_path/'external-review';external.write_bytes(b'{"projects":{}}')
    if failure in {'link','hardlink','corrupt'}:
        if leaf.exists() or leaf.is_symlink(): leaf.unlink()
        if failure == 'link': leaf.symlink_to(external)
        elif failure == 'hardlink': os.link(external,leaf)
        else: leaf.write_bytes(b'{')
    original_open=memory._open_at2
    if failure in {'unsupported','missing_workspace'} and not (route == 'source' and failure == 'missing_workspace'):
        def unavailable(fd,relative,*,resolve):
            if failure == 'unsupported' or relative == Path('workspace'): raise ValueError('synthetic unavailable')
            return original_open(fd,relative,resolve=resolve)
        monkeypatch.setattr(memory,'_open_at2',unavailable)
    original_read=os.read;forbidden=external.stat()
    def guarded_read(fd,count):
        item=os.fstat(fd)
        assert (item.st_dev,item.st_ino)!=(forbidden.st_dev,forbidden.st_ino)
        return original_read(fd,count)
    monkeypatch.setattr(os,'read',guarded_read)
    def identity():
        return sorted((str(p.relative_to(root)),p.lstat().st_mode,p.lstat().st_size,p.lstat().st_mtime_ns)
                      for p in root.rglob('*'))
    before=identity();writes=[]
    def forbidden_write(*_a,**_k):writes.append(True);raise AssertionError('preflight allowed a write')
    monkeypatch.setattr(service,'_save_project_manifest_unlocked',forbidden_write)
    monkeypatch.setattr(service,'_archive',forbidden_write)
    monkeypatch.setattr(service,'selection_status',forbidden_write)
    with pytest.raises(service.CanonicalPreflightUnavailable):invoke()
    assert writes==[] and identity()==before


@pytest.mark.parametrize('route',['source','candidate','restore','select','revision'])
@pytest.mark.parametrize('change',['link','hardlink','corrupt','content','new_identity'])
def test_review_change_after_effect_returns_completed_warning(tmp_path,monkeypatch,route,change):
    import os
    from workbench import canonical_service as service
    root=tmp_path/'repo';root.mkdir();(root/'workspace').mkdir()
    if route == 'source':
        invoke=lambda:import_sources(root,project_id='native-flow',name='Synthetic',language_direction='JP_TO_CN',
            chapters=[{'filename':'001-synthetic.md','text':'# 章\n\n合成。'}])
    elif route == 'candidate':
        state=source(root)
        invoke=lambda:candidate(root,state)
    elif route == 'restore':
        state,_=recovery_fixture(root)
        invoke=lambda:restore_previous_candidates(root,'native-flow',expected_manifest_sha256=state['manifest_sha256'])
    elif route == 'select':
        state=candidate(root,source(root));agent(root)
        invoke=lambda:select_revision(root,'native-flow',expected_manifest_sha256=state['manifest_sha256'],
            target_fields={r['segment_id']:'draft' for r in state['segments']})
    else:
        state,row,plan=revision_fixture(root);views=revision_views(plan)
        invoke=lambda:apply_revision(root,state,row,plan,views)
    leaf=root/'workspace/review_state.json'
    if change == 'new_identity' and not leaf.exists(): leaf.write_bytes(b'{"projects":{}}')
    outside=tmp_path/'external-review';outside.write_bytes(b'{"projects":{}}')
    forbidden=outside.stat();original_read=os.read
    def guarded_read(fd,count):
        item=os.fstat(fd)
        assert (item.st_dev,item.st_ino)!=(forbidden.st_dev,forbidden.st_ino)
        return original_read(fd,count)
    monkeypatch.setattr(os,'read',guarded_read)
    original=service._save_project_manifest_unlocked;writes=[]
    def save_then_change(repo,data):
        result=original(repo,data);writes.append(True)
        if change == 'new_identity':
            body=leaf.read_bytes();leaf.rename(tmp_path/'previous-review');leaf.write_bytes(body)
        elif change == 'content':leaf.write_bytes(b'{"projects":{},"changed":true}')
        elif change == 'corrupt':leaf.write_bytes(b'{')
        else:
            if leaf.exists() or leaf.is_symlink():leaf.unlink()
            if change == 'link':leaf.symlink_to(outside)
            else:os.link(outside,leaf)
        return result
    monkeypatch.setattr(service,'_save_project_manifest_unlocked',save_then_change)
    result=invoke()
    assert writes==[True] and result['effect_applied'] and result['mutation_committed']
    assert result['selection_status_available'] is False
    assert result['warning_code']=='review_state_unavailable_after_effect'
    assert '已完成' in result['warning'] and '请勿重复提交' in result['warning']
    if route in {'restore','revision'}:assert result['selection'] is None
