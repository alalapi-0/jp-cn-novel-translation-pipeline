"""Real job/domain integration with synthetic text and a fake native transport."""
from pathlib import Path
from copy import deepcopy
from types import SimpleNamespace
import hashlib,json,sys,threading
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from workbench import native_agent as native, native_revision as revision
from workbench import canonical_service as canonical, generation_jobs as jobs
from workbench.project_registry import get_project_manifest,patch_project_review_state_cas
from workbench.review_state import DecisionActor,approval_identity
from quality_review.calibration import packet_identity

def sha(text):return hashlib.sha256(text.encode()).hexdigest()

@pytest.fixture
def case(tmp_path,monkeypatch):
    root=tmp_path;(root/'workspace').mkdir();state=canonical.import_sources(root,project_id='revision-job',name='Synthetic',
        language_direction='JP_TO_CN',chapters=[{'filename':'001-synthetic.md',
            'text':'# 合成\n\n雨が降る。彼はまだ帰らない。\n\n扉は閉まっている。'}])
    state=canonical.import_candidates(root,'revision-job',expected_manifest_sha256=state['manifest_sha256'],
        source_inventory_sha256=state['source_inventory_sha256'],candidates=[
            {'segment_id':r['segment_id'],'target_text':'下雨了。他已回家。' if i==0 else '门关着。'}
            for i,r in enumerate(state['segments'])])
    m=get_project_manifest(root,'revision-job')
    patch_project_review_state_cas(root,'revision-job',decision_actor=DecisionActor('agent','synthetic-prior-review'),
        segments={r['id']:{'status':'approved','expected_identity':approval_identity(project_id='revision-job',
            language_direction='JP_TO_CN',segment=r)} for r in m.segments})
    state=canonical.selection_status(root,'revision-job');sid=state['segments'][0]['segment_id']
    calls=[];controls={};admissions=[]
    model={'model_confinement_verified':True,'configured_model':'SYNTHETIC_NOT_A_MODEL'}
    def admission(*args,**kwargs):
        admissions.append(True)
        if controls.get('probe'):
            prompt='Zero-source capability check: do not use any tool or read files. Return ready=true and available_tools=[].'
            schema=native._object({'ready':{'type':'boolean','const':True},'available_tools':{'type':'array','items':{'type':'string'},'maxItems':0}})
            args[2](prompt,schema,args[1]/'fixed',model)
        return dict(model)
    monkeypatch.setattr(native,'complete_admission',admission)
    def invoke(prompt,schema,directory,**kwargs):
        props=schema['properties']
        name=('probe' if 'ready' in props else 'diagnosis' if 'input_sha256' in props else
            ('simple' if '"mode": "simple"' in prompt else 'problem_driven') if 'items' in props else
            'comparison-'+str(props['order']['const']))
        unit=json.loads(next((root/'workspace/checkpoints/content_units').glob('*.json')).read_text())['metadata']['content_unit_budget']
        assert unit['operations'][-1]['status']=='reserved'
        assert jobs.get_project_generation_job(root,'revision-job')['status']=='running'
        assert (str(root),'revision-job') in native._active
        calls.append(name)
        if controls.get('during'):controls['during'](name)
        if controls.get('fail')==name:raise RuntimeError('synthetic native failure')
        if name=='probe':answer={'ready':True,'available_tools':[]}
        elif name=='diagnosis':
            data=json.loads(prompt.rsplit('\n',1)[1]);issues=[] if controls.get('no_issue') else [
                {'issue_type':'MISTRANSLATION','severity':'high','confidence':.95,
                'source_quote':'まだ帰らない','target_quote':'已回家','reason':'Synthetic negation evidence.'}]
            if controls.get('bad_issue'):issues[0]['source_quote']='不存在的引文'
            answer={'input_sha256':data['input_sha256'],'issues':issues}
        elif name in {'simple','problem_driven'}:
            target={'simple':'雨下着。他尚未归来。','problem_driven':'下雨了。他还没有回家。'}[name]
            if controls.get('same'):target='共同修订。他仍未归来。'
            if controls.get('identity'):target='下雨了。他已回家。'
            if controls.get('normalized'):target='共同修订。' if name=='simple' else ' 共同修订。'
            answer={'items':[{'segment_id':sid,'translation':target,'notes':'Synthetic fixture, not semantic evidence.'}]}
        else:
            data=json.loads(prompt.rsplit('\n',1)[1]);packet=data['packet'];rows=[]
            for pair in packet['cases']:
                def rank(text):return 3 if text=='下雨了。他还没有回家。' or text.strip().startswith('共同修订') else 2 if text=='雨下着。他尚未归来。' else 1
                preferred=max(pair['candidates'],key=lambda label:rank(pair['candidates'][label]))
                if controls.get('old_wins'):preferred=max(pair['candidates'],key=lambda label:(4 if pair['candidates'][label]=='下雨了。他已回家。' else rank(pair['candidates'][label])))
                if controls.get('tie'):preferred='tie'
                if controls.get('asymmetric') and name=='comparison-2':preferred='abstain'
                blocked=[];issues=[]
                if controls.get('severe'):
                    blocked=[label for label,text in pair['candidates'].items() if text=='下雨了。他还没有回家。']
                    issues=[{'candidate':label,'issue_type':'MISTRANSLATION','severity':'critical',
                        'confidence':.99,'source_quote':'まだ帰らない','target_quote':'还没有回家',
                        'reason':'Synthetic contradictory source-veto control; not a semantic claim.'} for label in blocked]
                rows.append({'case_id':pair['case_id'],'preferred':preferred,'blocked':blocked,
                    'issues':issues,'literary_preference':preferred,'note':'Synthetic comparison only.'})
            answer={'schema':'source-calibration-view/1','order':packet['order'],
                'input_packet_sha256':packet_identity(packet),'cases':rows}
        raw=json.dumps(answer,ensure_ascii=False).encode();meta={
            'thread_id':'synthetic-thread-'+str(len(calls)), 'turn_id':'synthetic-turn-'+str(len(calls)),
            'model':'SYNTHETIC_NOT_A_MODEL','configured_model':'SYNTHETIC_NOT_A_MODEL','model_provider':'openai',
            'model_override':False,'model_identity_status':'same_app_server_thread_start',
            'execution_mode':'agent_quota_translation','human_approved_final':False,
            'prompt_sha256':sha(prompt),'answer_sha256':hashlib.sha256(raw).hexdigest()}
        if controls.get('reused_thread'):meta['thread_id']='same-synthetic-thread'
        if controls.get('receipt_model')==name:meta['model']=meta['configured_model']='OTHER_SYNTHETIC'
        directory.mkdir(parents=True,exist_ok=True)
        if not controls.get('missing_receipt'):
            (directory/'answer.json').write_bytes(raw);(directory/'native-receipt.json').write_text(json.dumps(meta))
        return answer,meta
    monkeypatch.setattr(native,'invoke',invoke)
    return SimpleNamespace(root=root,state=state,sid=sid,calls=calls,controls=controls,admissions=admissions)

def run(c,request='comparison',**kw):
    return native.execute_job(c.root,'revision-job',expected_manifest_sha256=c.state['manifest_sha256'],
        request_id=request,action='compare_revision',segment_id=c.sid,**kw)
def budget(c):return json.loads(next((c.root/'workspace/checkpoints/content_units').glob('*.json')).read_text())['metadata']['content_unit_budget']
def manifest(c):return c.root/'workspace/manifests/revision-job.json'
def apply(c,result,actor=DecisionActor('agent','synthetic-explicit-selector')):
    return revision.apply_completed(c.root,'revision-job','comparison',
        chosen_target_revision=result['experimental_winner_target_revision'],decision_actor=actor)

def test_job_comparison_then_explicit_selected_draft_requires_fresh_review(case):
    c=case;before=manifest(c).read_bytes();reviews=(c.root/'workspace/review_state.json').read_bytes()
    result=run(c)
    assert c.calls==['diagnosis','simple','problem_driven','comparison-1','comparison-2']
    assert budget(c)['revision']==2 and len(budget(c)['operations'])==5
    assert all(r['status']=='succeeded' for r in budget(c)['operations'])
    assert result['comparison_complete'] and result['experimental_winner']=='problem_driven'
    assert not result['human_approved_final'] and not result['canonical_adoption']
    assert manifest(c).read_bytes()==before and (c.root/'workspace/review_state.json').read_bytes()==reviews
    assert all(x not in json.dumps(result) for x in ['下雨','thread_id','prompt','source_binding','native-receipt'])
    record,_=revision.completed(c.root,'revision-job','comparison')
    assert len(record['calls'])==5 and record['plan']['input']['candidates']['B_old']=='下雨了。他已回家。'
    replay=run(c);assert replay['idempotent_replay'] and len(c.calls)==5
    applied=apply(c,result);after=json.loads(manifest(c).read_text());old=json.loads(before)
    assert applied['action']=='import_unreviewed_draft' and applied['changed_segment_ids']==[c.sid]
    assert after['segments'][1:]==old['segments'][1:] and (c.root/'workspace/review_state.json').read_bytes()==reviews
    assert not applied['selection']['can_select'] and applied['selection']['current_agent_accepted']==1
    assert not (c.root/'output_cn').exists() and 'accepted_revision' not in after
    assert len(budget(c)['operations'])==5

@pytest.mark.parametrize('mode,reason',[('no_issue','no_supported_issue'),('identity','all_conditions_normalized_equivalent'),
    ('tie','tie_or_uncertainty'),('asymmetric','swapped_view_disagreement'),('normalized','normalized_variants_not_fully_evaluated')])
def test_nonconclusive_comparisons_preserve_without_more_callbacks(case,mode,reason):
    c=case;c.controls[mode]=True;before=manifest(c).read_bytes();result=run(c)
    assert result['reason']==reason and result['experimental_winner_target_revision'] is None
    assert apply(c,result)['action']=='preserve_original' and manifest(c).read_bytes()==before
    assert len(c.calls)==(1 if mode=='no_issue' else 3 if mode=='identity' else 5)

def test_byte_identical_conditions_keep_joint_winner_without_method_advantage(case):
    c=case;c.controls['same']=True;result=run(c);record,_=revision.completed(c.root,'revision-job','comparison')
    assert result['experimental_winner'] is None and result['experimental_winner_target_revision']
    assert record['decision']['byte_identical_winner_conditions']==['simple','problem_driven']
    assert record['plan']['unique_target_count']==2 and len(c.calls)==5
    assert apply(c,result)['action']=='import_unreviewed_draft'

@pytest.mark.parametrize('stage',['diagnosis','simple','problem_driven','comparison-1','comparison-2'])
def test_failed_callback_charged_terminal_no_same_input_or_request_replay(case,stage):
    c=case;c.controls['fail']=stage;before=manifest(c).read_bytes()
    with pytest.raises(RuntimeError):run(c)
    assert budget(c)['operations'][-1]['status']=='failed'
    assert jobs.get_project_generation_job(c.root,'revision-job')['status']=='failed'
    count=len(c.calls)
    with pytest.raises(RuntimeError):run(c)
    c.controls.pop('fail')
    with pytest.raises(RuntimeError):run(c,'new-request')
    assert len(c.calls)==count and manifest(c).read_bytes()==before

@pytest.mark.parametrize('mode',['bad_issue','missing_receipt','reused_thread','receipt_model'])
def test_invalid_evidence_stops_before_dependent_callbacks(case,mode):
    c=case;c.controls[mode]='simple' if mode=='receipt_model' else True;before=manifest(c).read_bytes()
    with pytest.raises((ValueError,RuntimeError)):run(c)
    assert len(c.calls)<5 and manifest(c).read_bytes()==before
    assert jobs.get_project_generation_job(c.root,'revision-job')['status']=='failed'

@pytest.mark.parametrize('drift',['cancel','manifest','review','source'])
def test_callback_races_preserve_new_state_and_prevent_dependent_calls(case,drift):
    c=case
    def mutate(name):
        if name!='simple':return
        if drift=='cancel':native.cancel_job(c.root,'revision-job','comparison')
        elif drift=='manifest':
            d=json.loads(manifest(c).read_text());d['name']='Concurrent edit';manifest(c).write_text(json.dumps(d))
        elif drift=='review':
            m=get_project_manifest(c.root,'revision-job');r=m.segments[0]
            patch_project_review_state_cas(c.root,'revision-job',segments={r['id']:{'status':'rejected',
                'expected_identity':approval_identity(project_id='revision-job',language_direction='JP_TO_CN',segment=r)}})
        else:next((c.root/'input_jp').rglob('*.md')).write_text('Different source')
    c.controls['during']=mutate
    with pytest.raises((ValueError,RuntimeError)):run(c)
    assert c.calls==['diagnosis','simple'] and jobs.get_project_generation_job(c.root,'revision-job')['status']=='failed'
    assert json.loads(manifest(c).read_text())['segments'][0]['draft']=='下雨了。他已回家。'
    assert (str(c.root),'revision-job') not in native._active

@pytest.mark.parametrize('part',['comparison','answer','receipt','review','manifest','source'])
def test_completed_revalidation_refuses_tamper_and_stale_application(case,part):
    c=case;result=run(c);directory=c.root/'workspace/runs/workbench-native/comparison'
    if part in {'comparison','answer','receipt'}:
        p=directory/('comparison.json' if part=='comparison' else 'simple/'+('answer.json' if part=='answer' else 'native-receipt.json'))
        p.write_text('{}')
    elif part=='review':
        m=get_project_manifest(c.root,'revision-job');r=m.segments[0]
        patch_project_review_state_cas(c.root,'revision-job',segments={r['id']:{'status':'rejected',
            'expected_identity':approval_identity(project_id='revision-job',language_direction='JP_TO_CN',segment=r)}})
    elif part=='manifest':
        d=json.loads(manifest(c).read_text());d['segments'][0]['draft']='Another draft';manifest(c).write_text(json.dumps(d))
    else:next((c.root/'input_jp').rglob('*.md')).write_text('Another source')
    before=manifest(c).read_bytes()
    with pytest.raises((ValueError,RuntimeError)):apply(c,result)
    assert manifest(c).read_bytes()==before and len(c.calls)==5

def test_probe_uses_same_durable_source_budget_before_any_revision(case):
    c=case;c.controls['probe']=True;run(c)
    assert c.calls[0]=='probe' and len(c.calls)==len(budget(c)['operations'])==6 and budget(c)['revision']==2

def test_old_draft_can_win_without_an_application_or_approval(case):
    c=case;c.controls['old_wins']=True;before=manifest(c).read_bytes();result=run(c)
    assert result['experimental_winner']=='B_old' and apply(c,result)['action']=='preserve_original'
    assert manifest(c).read_bytes()==before

def test_severe_source_veto_cannot_be_offset_by_literary_preference(case):
    c=case;c.controls['severe']=True;before=manifest(c).read_bytes()
    with pytest.raises(ValueError,match='severe source conflict'):run(c)
    assert c.calls==['diagnosis','simple','problem_driven','comparison-1']
    assert manifest(c).read_bytes()==before
    assert jobs.get_project_generation_job(c.root,'revision-job')['status']=='failed'

@pytest.mark.parametrize('kind',['operations','revisions','elapsed'])
def test_existing_whole_source_limits_do_not_reset_for_new_job(case,kind):
    from providers.types import Message
    c=case;p=revision.prepare(c.root,'revision-job',c.state['manifest_sha256'],c.sid);unit=p['full']['unit']
    for i in range(8 if kind=='operations' else 2 if kind=='revisions' else 1):
        messages=[Message('user','Synthetic prior '+str(i))]
        with unit.operation(messages,role='generation' if kind=='revisions' else 'review',
                correction_key=sha('synthetic correction'+str(i)) if kind=='revisions' else None) as lease:
            with lease.physical_attempt(messages):pass
    if kind=='elapsed':
        value=json.loads(unit.path.read_text());value['metadata']['content_unit_budget']['started_at_unix']-=1201
        unit.path.write_text(json.dumps(value))
    before=budget(c);clock=before['started_at_unix'];old=manifest(c).read_bytes()
    with pytest.raises(RuntimeError):run(c)
    assert len(c.calls)==(1 if kind=='revisions' else 0)
    assert budget(c)['started_at_unix']==clock and manifest(c).read_bytes()==old
    assert budget(c)['revision']==before['revision']

@pytest.mark.parametrize('actor',[None,{'actor_type':'agent'},DecisionActor('unknown','fake'),DecisionActor('machine','fake')])
def test_untrusted_local_selector_is_refused_even_for_no_issue(case,actor):
    c=case;c.controls['no_issue']=True;result=run(c);before=manifest(c).read_bytes()
    with pytest.raises(ValueError,match='trusted local'):apply(c,result,actor)
    assert manifest(c).read_bytes()==before

@pytest.mark.parametrize('mode',['lock','active_job','wrong_segment','wrong_version'])
def test_occupied_or_stale_job_selection_never_calls_native(case,mode):
    c=case;lock=jobs.project_generation_lock('revision-job')
    if mode=='lock':lock.acquire()
    if mode=='active_job':jobs.prepare_generation_job(c.root,'revision-job',request_id='other',mode='mock',sample_text='')
    if mode=='wrong_segment':c.sid='unknown-segment'
    if mode=='wrong_version':c.state['manifest_sha256']='0'*64
    try:
        with pytest.raises((ValueError,RuntimeError)):run(c)
    finally:
        if mode=='lock':lock.release()
    assert not c.calls and not c.admissions

def test_live_selected_dependency_change_stops_after_current_callback(case):
    c=case;folder=c.root/'workspace/configs';folder.mkdir(parents=True,exist_ok=True)
    file=folder/'glossary.yaml';file.write_text('entries:\n- source_term: 雨\n  target_term: 雨\n')
    data=json.loads(manifest(c).read_text());data['dependency_versions']={'glossary:rain':'0'*64}
    data['dependency_sources']={'glossary:rain':{'kind':'glossary','entry':'雨'}}
    data['segments'][0]['dependency_keys']=['glossary:rain'];manifest(c).write_text(json.dumps(data))
    c.state=canonical.selection_status(c.root,'revision-job')
    c.controls['during']=lambda name:file.write_text('entries:\n- source_term: 雨\n  target_term: Different\n') if name=='simple' else None
    with pytest.raises(ValueError):run(c)
    assert c.calls==['diagnosis','simple'] and budget(c)['operations'][-1]['status']=='failed'

def test_unavailable_selected_dependency_is_not_silently_ignored(case):
    c=case;data=json.loads(manifest(c).read_text());data['dependency_versions']={'glossary:rain':'0'*64}
    data['dependency_sources']={'glossary:rain':{'kind':'glossary','entry':'雨'}}
    data['segments'][0]['dependency_keys']=['glossary:rain'];manifest(c).write_text(json.dumps(data))
    c.state=canonical.selection_status(c.root,'revision-job')
    with pytest.raises(ValueError,match='unavailable'):run(c)
    assert not c.calls and not c.admissions

def test_selected_work_policy_file_change_is_not_a_nonce_or_unbound_context(case):
    c=case;p=revision.prepare(c.root,'revision-job',c.state['manifest_sha256'],c.sid)
    folder=c.root/'configs';folder.mkdir();path=folder/'synthetic-work.json'
    policy={'schema':'work-rules/1','activation':'review_only','work_id':'revision-job',
        'source_revision':p['case']['source_binding']['source_revision'],'language_direction':'JP_TO_CN',
        'rules':{'source_rules':[]},'target_files':[]}
    raw=json.dumps(policy);path.write_text(raw);data=json.loads(manifest(c).read_text())
    data['work_rules']={'path':'configs/synthetic-work.json','sha256':sha(raw)}
    manifest(c).write_text(json.dumps(data));c.state=canonical.selection_status(c.root,'revision-job')
    c.controls['during']=lambda name:path.write_text(raw+' ') if name=='simple' else None
    with pytest.raises(ValueError,match='policy version'):run(c)
    assert c.calls==['diagnosis','simple'] and budget(c)['revision']==1

@pytest.mark.parametrize('part',['missing','status','request','role','symlink'])
def test_saved_output_requires_its_real_source_reservation_and_ordinary_receipt(case,part):
    c=case;result=run(c);path=next((c.root/'workspace/checkpoints/content_units').glob('*.json'))
    if part=='missing':path.unlink()
    elif part=='symlink':
        p=c.root/'workspace/runs/workbench-native/comparison/simple/native-receipt.json'
        saved=p.with_name('preserved-receipt.json');p.rename(saved);p.symlink_to(saved)
    else:
        doc=json.loads(path.read_text());row=doc['metadata']['content_unit_budget']['operations'][1]
        row[{'status':'status','request':'request_sha256','role':'role'}[part]]={'status':'failed','request':'0'*64,'role':'style'}[part]
        path.write_text(json.dumps(doc))
    before=manifest(c).read_bytes()
    with pytest.raises((ValueError,RuntimeError)):apply(c,result)
    assert manifest(c).read_bytes()==before and len(c.calls)==5

@pytest.mark.parametrize('bad_request',['../outside','bad/slash','',None])
def test_invalid_request_cannot_open_native_or_escape(case,bad_request):
    c=case
    with pytest.raises(ValueError):run(c,bad_request)
    assert not c.calls and not c.admissions and not (c.root/'workspace/checkpoints/content_units').exists()

def test_http_revision_input_is_strict_loopback_and_response_content_free(case):
    from http.server import ThreadingHTTPServer
    from http.client import HTTPConnection
    from workbench.server import make_handler
    c=case;server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(c.root,Path(__file__).resolve().parents[1]/'frontend'))
    thread=threading.Thread(target=server.serve_forever);thread.start()
    try:
        body={'expected_manifest_sha256':c.state['manifest_sha256'],'request_id':'comparison',
            'action':'compare_revision','segment_id':c.sid}
        for allowed,extra,status in [(False,{},403),(True,{'actor_type':'agent'},400),(True,{},200)]:
            conn=HTTPConnection('127.0.0.1',server.server_port)
            try:
                conn.request('POST','/api/projects/revision-job/native-agent-job',json.dumps({**body,**extra}),
                    {'Content-Type':'application/json','Origin':f'http://127.0.0.1:{server.server_port}' if allowed else 'https://foreign.invalid'})
                response=conn.getresponse();raw=response.read();assert response.status==status
                assert '下雨'.encode() not in raw and b'thread_id' not in raw and b'prompt' not in raw
            finally:conn.close()
        assert len(c.calls)==5
    finally:server.shutdown();server.server_close();thread.join(timeout=5)
