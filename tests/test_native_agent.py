import subprocess
"""Native boundary and state tests. All model/native subprocesses are substitutes.

These tests cannot establish real native capability or semantic acceptance.
"""
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from workbench import native_agent as native
from workbench import canonical_service as canonical
from workbench import generation_jobs as jobs
from workbench import project_registry as registry
real_complete_admission=native.complete_admission


@pytest.fixture
def project(tmp_path,monkeypatch):
    root=tmp_path
    state=canonical.import_sources(root,project_id='native-bound',name='Synthetic',
        language_direction='JP_TO_CN',chapters=[{'filename':'001-native.md','text':'# 一\n\n雨が降っていた。\n\n彼は扉を閉めた。'}])
    monkeypatch.setattr(native,'complete_admission',lambda *args,**kwargs:{'model_confinement_verified':True,'configured_model':'SYNTHETIC_NOT_A_MODEL'})
    calls=[]
    def invoke(prompt,schema,directory,**kwargs):
        directory.mkdir(parents=True,exist_ok=True)
        packet=json.loads(prompt.split('No tools or file reads are needed.\n')[1])
        rows=packet['segments']; action='candidates' if 'candidates' in schema['properties'] else 'verdicts'
        # Observe the durable reservation while the fake native callback runs.
        checkpoints=list((root/'workspace/checkpoints/content_units').glob('*.json'))
        saved=json.loads(checkpoints[0].read_text())['metadata']['content_unit_budget']
        assert saved['operations'][-1]['status']=='reserved'
        calls.append(action)
        if action=='candidates':
            result=[{'segment_id':r['segment_id'],'target_text':text} for r,text in zip(rows,['雨下着。','他关上了门。'])]
        else:
            result=[{'segment_id':r['segment_id'],'accepted':True,'confidence':.99,'severity':'none',
                     'source_quote':r['source'],'target_quote':r['target_text'],'reason':'Synthetic evidence: meaning retained in this explicit fake review.'} for r in rows]
        return {action:result},{'thread_id':'synthetic-'+action,'execution_mode':'agent_quota_translation','human_approved_final':False}
    monkeypatch.setattr(native,'invoke',invoke)
    return root,state,calls


def run(project,action,request_id):
    root,_,_=project
    state=canonical.selection_status(root,'native-bound')
    return native.execute_job(root,'native-bound',expected_manifest_sha256=state['manifest_sha256'],request_id=request_id,action=action)


def test_persisted_rejection_creates_one_semantic_rereview_without_replay(project, monkeypatch):
    root, _, calls = project
    prompts = []; original = native.invoke
    def observe(prompt, *args, **kwargs):
        prompts.append(prompt)
        return original(prompt, *args, **kwargs)
    monkeypatch.setattr(native, 'invoke', observe)
    run(project, 'generate', 'generation')
    run(project, 'review', 'first-review')
    with pytest.raises(RuntimeError): run(project, 'review', 'unchanged-review')
    manifest = registry.get_project_manifest(root, 'native-bound'); row = manifest.segments[0]
    registry.patch_project_review_state_cas(root, 'native-bound', segments={row['id']:{
        'status':'rejected', 'note':'Recheck the negation against the source.',
        'expected_identity':native.approval_identity(project_id='native-bound', language_direction=manifest.language_direction, segment=row)}})
    run(project, 'review', 'after-persisted-rejection')
    assert calls == ['candidates', 'verdicts', 'verdicts']
    assert prompts[1] != prompts[2]
    assert 'Recheck the negation against the source.' in prompts[2]
    with pytest.raises(RuntimeError): run(project, 'review', 'unchanged-after-rereview')
    assert calls == ['candidates', 'verdicts', 'verdicts']
    budget = json.loads(next((root/'workspace/checkpoints/content_units').glob('*.json')).read_text())['metadata']['content_unit_budget']
    assert len(budget['operations']) == 3 and budget['revision'] == 0
    assert all(row['status'] == 'succeeded' for row in budget['operations'])


def test_review_context_ignores_transport_fields_and_stale_feedback(project):
    from copy import deepcopy
    root, _, _ = project; run(project, 'generate', 'generation')
    _, _, data, digest = canonical._read(root, 'native-bound')
    row = registry.get_project_manifest(root, 'native-bound').segments[0]
    identity = native.approval_identity(project_id='native-bound', language_direction='JP_TO_CN', segment=row)
    state={'segments':{row['id']:{'status':'rejected','approval_identity':identity,'note':'Check negation.'}}}
    first,_=native._review_context(data,state)
    changed=deepcopy(state);changed['at']='other time';changed['segments'][row['id']].update(at='new time',request_id='other-request',thread_id='other-thread',nonce='not-semantic')
    data['updated_at']='transport-only';data['name']='renamed metadata'
    second,_=native._review_context(data,changed)
    assert first==second
    changed['segments'][row['id']]['approval_identity']='sha256:'+'0'*64
    stale,_=native._review_context(data,changed)
    assert stale['segments'][0]['status']=='pending' and stale['segments'][0]['rejection_feedback']==''
    changed['segments'][row['id']].update(approval_identity=identity,note='x'*4097)
    with pytest.raises(ValueError,match='bounded'):native._review_context(data,changed)


@pytest.fixture
def receipt_project(project, monkeypatch):
    import hashlib
    original=native.invoke
    def documented_fake(prompt,schema,directory,**kwargs):
        answer,meta=original(prompt,schema,directory,**kwargs)
        raw=json.dumps(answer,ensure_ascii=False).encode()
        meta.update(turn_id='synthetic-turn',model='SYNTHETIC_NOT_A_MODEL',model_provider='openai',
            configured_model='SYNTHETIC_NOT_A_MODEL',model_override=False,model_identity_status='same_app_server_thread_start',
            prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),answer_sha256=hashlib.sha256(raw).hexdigest())
        (directory/'answer.json').write_bytes(raw)
        (directory/'native-receipt.json').write_text(json.dumps(meta))
        return answer,meta
    monkeypatch.setattr(native,'invoke',documented_fake)
    run(project,'generate','generation')
    return project


@pytest.mark.parametrize('mutation',[None,'missing_receipt','answer','mode','target','receipt','job_selection','symlink'])
def test_native_label_provenance_requires_bound_receipt(receipt_project,mutation):
    root,_,_=receipt_project;directory=root/'workspace/runs/workbench-native/generation'
    if mutation=='missing_receipt':(directory/'native-receipt.json').unlink()
    if mutation=='answer':(directory/'answer.json').write_text('{}')
    if mutation in {'mode','target'}:
        p=root/'workspace/manifests/native-bound.json';data=json.loads(p.read_text())
        if mutation=='mode':data['generation_mode']='mock'
        else:data['segments'][0]['draft']='Different candidate.'
        p.write_text(json.dumps(data,ensure_ascii=False))
    if mutation=='receipt':
        p=directory/'native-receipt.json';data=json.loads(p.read_text());data['model']='unmatched';p.write_text(json.dumps(data))
    if mutation=='job_selection':
        p=root/'workspace/generation_jobs.json';data=json.loads(p.read_text());data['projects']['native-bound']['current']['response_payload']['selection']['source_inventory_sha256']='0'*64;p.write_text(json.dumps(data))
    if mutation=='symlink':
        p=directory/'native-receipt.json';saved=directory/'saved.json';p.rename(saved);p.symlink_to(saved)
    proof=canonical.native_generation_provenance(root,'native-bound')
    assert proof==({'status':'verified','execution_mode':'agent_quota_translation'} if mutation is None else {'status':'unverified','execution_mode':None})


def test_http_native_provenance_projection_is_receipt_bound(receipt_project):
    import threading
    from http.server import ThreadingHTTPServer
    from http.client import HTTPConnection
    from workbench.server import make_handler
    root,_,_=receipt_project
    server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(root,Path(__file__).resolve().parents[1]/'frontend'))
    thread=threading.Thread(target=server.serve_forever);thread.start()
    try:
        for valid in [True,False]:
            if not valid:(root/'workspace/runs/workbench-native/generation/native-receipt.json').unlink()
            connection=HTTPConnection('127.0.0.1',server.server_port)
            try:
                connection.request('GET','/api/projects/native-bound/workbench-data');response=connection.getresponse();payload=json.loads(response.read());assert response.status==200
            finally:connection.close()
            assert all(s['native_provenance']['status']==('verified' if valid else 'unverified') for s in payload['segments'])
            assert 'thread_id' not in json.dumps(payload) and 'turn_id' not in json.dumps(payload)
    finally:
        server.shutdown();server.server_close();thread.join(timeout=2)
    assert not thread.is_alive()


def test_bound_jobs_reserve_before_callback_and_separate_native_roles(project):
    root,state,calls=project
    generated=run(project,'generate','generation')
    assert calls==['candidates'] and generated['selection']['current_agent_accepted']==0
    reviewed=run(project,'review','review')
    assert calls==['candidates','verdicts'] and reviewed['selection']['current_agent_accepted']==2
    assert reviewed['selection']['human_approved_final'] is False
    _,_,manifest,_=canonical._read(root,'native-bound')
    assert manifest['native_generation']['thread_id']=='synthetic-candidates'
    state=reviewed['selection']
    selected=canonical.select_revision(root,'native-bound',expected_manifest_sha256=state['manifest_sha256'],target_fields={r['segment_id']:'draft' for r in state['segments']})
    exported=canonical.export_selected(root,'native-bound',expected_manifest_sha256=selected['manifest_sha256'])
    assert exported['segments_exported']==2 and not exported['human_approved_final']
    saved=json.loads(next((root/'workspace/checkpoints/content_units').glob('*.json')).read_text())['metadata']['content_unit_budget']
    assert len(saved['operations'])==2 and [r['role'] for r in saved['operations']]==['generation','review']


def test_replay_is_bound_to_input_and_does_not_call_again(project):
    root,original,calls=project
    run(project,'generate','same-id')
    result=native.execute_job(root,'native-bound',expected_manifest_sha256=original['manifest_sha256'],request_id='same-id',action='generate')
    assert result['idempotent_replay'] and calls==['candidates']
    with pytest.raises(ValueError,match='input/action conflict'):run(project,'review','same-id')


def test_native_preflight_failure_is_terminal_and_has_zero_content_attempts(project,monkeypatch):
    root,state,calls=project
    def failed(*args,**kwargs):raise RuntimeError('synthetic unavailable native configuration')
    monkeypatch.setattr(native,'complete_admission',failed)
    with pytest.raises(RuntimeError,match='unavailable'):run(project,'generate','unavailable')
    assert jobs.get_project_generation_job(root,'native-bound')['status']=='failed'
    assert not list((root/'workspace/checkpoints').glob('content_units/*.json')) and not calls
    with pytest.raises(RuntimeError,match='already attempted'):run(project,'generate','unavailable')


def test_missing_confinement_refuses_before_native_callback(project,monkeypatch):
    _,_,calls=project
    monkeypatch.setattr(native,'complete_admission',lambda *a,**k:{'configured_model':'SYNTHETIC'})
    with pytest.raises(RuntimeError,match='confinement_probe_required'):run(project,'generate','no-proof')
    assert not calls


def test_changed_full_source_is_rejected_before_any_native_admission(project):
    root,_,calls=project
    (root/'input_jp/native-bound/001-native.md').write_text('Changed source, not authorized in pinned manifest.')
    with pytest.raises(ValueError,match='source version changed'):run(project,'generate','changed')
    assert not calls and jobs.get_project_generation_job(root,'native-bound') is None


def test_unknown_ids_partial_or_empty_output_preserve_prior_candidate(project,monkeypatch):
    root,_,calls=project
    before=(root/'workspace/manifests/native-bound.json').read_bytes()
    monkeypatch.setattr(native,'invoke',lambda *a,**k:({'candidates':[{'segment_id':'wrong','target_text':''}]},{'thread_id':'fake'}))
    with pytest.raises(Exception):run(project,'generate','bad-output')
    assert (root/'workspace/manifests/native-bound.json').read_bytes()==before
    assert jobs.get_project_generation_job(root,'native-bound')['status']=='failed'


def test_stale_candidate_during_native_review_does_not_bless_new_content(project,monkeypatch):
    root,_,_=project
    run(project,'generate','generation')
    original=native.patch_project_review_state_cas
    def race(*args,**kwargs):
        _,_,data,_=canonical._read(root,'native-bound')
        data['segments'][0]['draft']='Concurrent owner candidate edit.'
        registry._save_project_manifest_unlocked(root,data)
        return original(*args,**kwargs)
    monkeypatch.setattr(native,'patch_project_review_state_cas',race)
    with pytest.raises(Exception):run(project,'review','race-review')
    assert not canonical.selection_status(root,'native-bound')['can_select']


def test_review_cannot_reuse_its_generator_identity(project,monkeypatch):
    run(project,'generate','generation')
    original=native.invoke
    def same(*a,**k):
        answer,meta=original(*a,**k);meta['thread_id']='synthetic-candidates';return answer,meta
    monkeypatch.setattr(native,'invoke',same)
    with pytest.raises(ValueError,match='separate ephemeral'):run(project,'review','same-reviewer')


def test_feedback_changed_during_native_review_is_preserved(project,monkeypatch):
    root,_,_=project;run(project,'generate','generation');original=native.invoke
    def feedback(*a,**k):
        answer,meta=original(*a,**k)
        manifest=registry.get_project_manifest(root,'native-bound');row=manifest.segments[0]
        registry.patch_project_review_state_cas(root,'native-bound',segments={row['id']:{'status':'rejected',
            'expected_identity':native.approval_identity(project_id='native-bound',language_direction=manifest.language_direction,segment=row)}})
        return answer,meta
    monkeypatch.setattr(native,'invoke',feedback)
    with pytest.raises(Exception,match='review changed'):run(project,'review','feedback-race')
    state=native.get_project_review_state(root,'native-bound')
    assert next(iter(state['segments'].values()))['status']=='rejected'
    assert not canonical.selection_status(root,'native-bound')['can_select']


def test_feedback_racing_at_review_write_boundary_is_not_overwritten(project,monkeypatch):
    import threading
    from workbench import review_state
    root,_,_=project;run(project,'generate','generation')
    original=review_state.patch_project_review_state
    at_write=threading.Event();written=threading.Event();errors=[]
    def competitor():
        assert at_write.wait(2)
        try:original(root,'native-bound',segments={'competing-note':{'status':'rejected','note':'SYNTHETIC newer owner decision'}})
        except BaseException as e:errors.append(e)
        finally:written.set()
    def boundary(*args,**kwargs):
        # Runs after registry identity validation, immediately before atomic
        # review compare+write; reproduce the Judge's check-to-write gap.
        at_write.set();assert written.wait(2)
        return original(*args,**kwargs)
    monkeypatch.setattr(review_state,'patch_project_review_state',boundary)
    child=threading.Thread(target=competitor);child.start()
    try:
        with pytest.raises(review_state.ReviewStateConflictError):run(project,'review','write-boundary-race')
    finally:child.join(timeout=3)
    assert not child.is_alive() and not errors
    current=review_state.get_project_review_state(root,'native-bound')
    assert current['segments']['competing-note']['note']=='SYNTHETIC newer owner decision'
    assert not canonical.selection_status(root,'native-bound')['can_select']


@pytest.mark.parametrize('mutation',['bad_quote','critical','low_confidence','reject'])
def test_uncertain_rejected_or_unsupported_evidence_never_unlocks(project,monkeypatch,mutation):
    root,_,_=project;run(project,'generate','generation');original=native.invoke
    def altered(*a,**k):
        answer,meta=original(*a,**k)
        for row in answer['verdicts']:
            if mutation=='bad_quote':row['source_quote']='Not a source quotation'
            if mutation=='critical':row['severity']='critical'
            if mutation=='low_confidence':row['confidence']=.2
            if mutation=='reject':row['accepted']=False
        return answer,meta
    monkeypatch.setattr(native,'invoke',altered)
    if mutation=='bad_quote':
        with pytest.raises(ValueError,match='evidence'):run(project,'review','negative')
    else:run(project,'review','negative')
    assert not canonical.selection_status(root,'native-bound')['can_select']


def test_current_candidate_is_preserved_on_generation_reentry(project):
    _,_,calls=project;run(project,'generate','first')
    with pytest.raises(ValueError,match='existing candidate preserved'):run(project,'generate','second')
    assert calls==['candidates']


@pytest.mark.parametrize('request_id',['../escape','with space','', 'x'*97])
def test_request_ids_cannot_choose_output_paths(project,request_id):
    root,state,calls=project
    with pytest.raises(ValueError):native.execute_job(root,'native-bound',expected_manifest_sha256=state['manifest_sha256'],request_id=request_id,action='generate')
    assert not calls


def test_child_environment_does_not_forward_api_keys_or_physical_desktop(tmp_path,monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','SYNTHETIC_NOT_A_SECRET');monkeypatch.setenv('DISPLAY',':999')
    env=native._environment(tmp_path)
    assert 'OPENAI_API_KEY' not in env and 'DISPLAY' not in env and 'WAYLAND_DISPLAY' not in env


def test_startup_diagnostic_does_not_expose_values():
    error=native._safe_error(SimpleNamespace(returncode=1,stderr='unknown field `synthetic_field`, value SYNTHETIC_PRIVATE_VALUE'),'configuration')
    assert error.native_diagnostic['unknown_key_count']==1
    assert 'synthetic_field' not in str(error) and 'SYNTHETIC_PRIVATE_VALUE' not in str(error)


def test_failed_admission_survives_new_request_and_recreated_reader(tmp_path,monkeypatch):
    calls=[]
    monkeypatch.setattr(native,'_configuration_input',lambda root:'stable-config-input')
    def failed(*a,**k):calls.append(True);raise RuntimeError('synthetic metadata failure')
    monkeypatch.setattr(native,'preflight',failed)
    with pytest.raises(RuntimeError,match='metadata failure'):
        native.complete_admission(tmp_path,tmp_path/'run-one')
    # No root cache: a fresh checkpoint reader/new request still sees failure.
    with pytest.raises(RuntimeError,match='blocked_across_request_ids'):
        native.complete_admission(tmp_path,tmp_path/'run-two')
    assert len(calls)==1 and native.admission_status(tmp_path)['blocked']
    monkeypatch.setattr(native,'_configuration_input',lambda root:'changed-config-input')
    with pytest.raises(RuntimeError,match='metadata failure'):
        native.complete_admission(tmp_path,tmp_path/'run-three')
    assert len(calls)==2 and native.admission_status(tmp_path)['attempts']==2


def test_each_invoke_rechecks_current_admission_before_thread_or_turn(tmp_path,monkeypatch):
    closed=[]
    rpc=SimpleNamespace(owned=SimpleNamespace(close=lambda:closed.append(True),cleanup_verified=True))
    monkeypatch.setattr(native,'_open_native',lambda *a:(rpc,{'configured_model':'changed'}))
    with pytest.raises(RuntimeError,match='native_stage_failed:turn'):
        native.invoke('synthetic',{},tmp_path/'run',timeout=1,
            admission={'configured_model':'pinned','model_confinement_verified':True})
    assert closed==[True]


def test_cancel_is_bound_to_root_project_and_active_request(tmp_path):
    import threading
    key=(str(tmp_path.resolve()),'native-bound');event=threading.Event()
    with native._active_lock:native._active[key]=('exact-request',event)
    try:
        with pytest.raises(ValueError):native.cancel_job(tmp_path,'native-bound','wrong-request')
        assert not event.is_set()
        value=native.cancel_job(tmp_path,'native-bound','exact-request')
        assert event.is_set() and value['terminal'] is False
    finally:
        with native._active_lock:native._active.pop(key,None)


def test_probe_and_generation_share_the_real_source_operation_budget(project,monkeypatch):
    root,_,_=project;calls=[]
    monkeypatch.setattr(native,'complete_admission',real_complete_admission)
    monkeypatch.setattr(native,'_configuration_input',lambda root:'synthetic-config')
    monkeypatch.setattr(native,'preflight',lambda *a:{'configured_model':'SYNTHETIC_NOT_A_MODEL'})
    generation=native.invoke
    def invoke(prompt,schema,directory,**kwargs):
        if kwargs.get('_probe'):
            directory.mkdir(parents=True);(directory/'native-receipt.json').write_text('{}')
            calls.append('probe');return {'ready':True,'available_tools':[]},{}
        return generation(prompt,schema,directory,**kwargs)
    monkeypatch.setattr(native,'invoke',invoke)
    run(project,'generate','probe-and-generate')
    saved=json.loads(next((root/'workspace/checkpoints/content_units').glob('*.json')).read_text())['metadata']['content_unit_budget']
    assert len(saved['operations'])==2 and calls==['probe']


@pytest.mark.parametrize('state',['absent','missing_receipt','changed_fingerprint'])
def test_review_cannot_start_another_confinement_probe(project,monkeypatch,state):
    root,_,calls=project;run(project,'generate','synthetic-generation');probes=[]
    monkeypatch.setattr(native,'complete_admission',real_complete_admission)
    monkeypatch.setattr(native,'_configuration_input',lambda root:'same-config')
    admission={'configured_model':'synthetic-model'}
    monkeypatch.setattr(native,'preflight',lambda *a:admission)
    if state!='absent':
        manager,_=native._gate(root)
        native._save_gate(manager,{'schema':1,'attempts':[{'input_fingerprint':'same-config','status':'succeeded','probe_fingerprint':native._fingerprint(admission) if state=='missing_receipt' else 'changed','receipt_sha256':'0'*64}]})
    def invoke(*a,**kwargs):
        probes.append(kwargs.get('_probe'));raise RuntimeError('unexpected new review probe')
    monkeypatch.setattr(native,'invoke',invoke)
    with pytest.raises(RuntimeError,match='native_probe_requires_bound_source_budget'):run(project,'review','review-no-fresh-probe')
    assert probes==[] and calls==['candidates']
    assert jobs.get_project_generation_job(root,'native-bound')['status']=='failed'
    ledger=json.loads(next((root/'workspace/checkpoints/content_units').glob('*.json')).read_text())['metadata']['content_unit_budget']
    assert len(ledger['operations'])==1


def test_preflight_uses_fresh_same_lifecycle_config_and_account(tmp_path,monkeypatch):
    from workbench import native_process
    calls=[];closed=[];models=iter(['first-default','first-default','changed-default','changed-default'])
    class Owned:
        def __init__(self,*a,**k):self.process=SimpleNamespace(poll=lambda:None);self.err=bytearray();self.cleanup_verified=False
        def close(self):closed.append(True);self.cleanup_verified=True
    class RPC:
        def __init__(self,owned):self.owned=owned
        def notify(self,method):calls.append(method)
        def call(self,method,params):
            calls.append(method)
            if method=='config/read':
                cfg={k:v for k,v in native.CONFIG.items() if not k.startswith('features.')}
                cfg['features']={k[9:]:v for k,v in native.CONFIG.items() if k.startswith('features.')}
                self.model=next(models);return {'config':{**cfg,'model':self.model,'model_provider':'openai'}}
            if method=='account/read':return {'account':{'type':'chatgpt'}}
            if method=='thread/start':return {'model':self.model,'modelProvider':'openai','approvalPolicy':'never','sandbox':{'type':'readOnly'},'runtimeWorkspaceRoots':[],'thread':{'id':'fixture','environments':[],'ephemeral':True}}
            if method=='experimentalFeature/list':return {'data':[{'name':k[9:],'enabled':False,'stage':'stable'} for k in native.CONFIG if k.startswith('features.')],'nextCursor':None}
            return {}
    def metadata(command,*a,**k):
        if 'login' in command:return 'Logged in using ChatGPT'
        if 'features' in command:return '\n'.join(k[9:]+' stable false' for k in native.CONFIG if k.startswith('features.'))
        if 'mcp' in command:return '[]'
        return 'synthetic-cli'
    monkeypatch.setattr(native,'_metadata',metadata);monkeypatch.setattr(native,'CLI',sys.executable)
    monkeypatch.setattr(native_process,'OwnedProcess',Owned);monkeypatch.setattr(native_process,'NativeRPC',RPC)
    assert native.preflight(tmp_path/'one')['configured_model']=='first-default'
    assert native.preflight(tmp_path/'two')['configured_model']=='changed-default'
    assert calls.count('config/read')==4 and calls.count('account/read')==2 and len(closed)==4


def test_status_reads_persisted_failure_without_hashing_or_native_activity(tmp_path,monkeypatch):
    manager,_=native._gate(tmp_path)
    native._save_gate(manager,{'schema':1,'attempts':[{'input_fingerprint':'old-version','status':'failed'}]})
    before=manager.checkpoint_path.read_bytes()
    def forbidden(*a,**k):raise AssertionError('ordinary status attempted native admission work')
    monkeypatch.setattr(native,'_configuration_input',forbidden)
    monkeypatch.setattr(native,'_metadata',forbidden)
    monkeypatch.setattr(native.subprocess,'Popen',forbidden)
    # Recreated readers and arbitrary repeated reads preserve the failed fact.
    assert native.admission_status(tmp_path)['blocked'] is True
    assert native.admission_status(Path(str(tmp_path)))['blocked'] is True
    assert manager.checkpoint_path.read_bytes()==before


def test_write_admission_still_fingerprints_before_every_attempt(tmp_path,monkeypatch):
    reads=[]
    def fingerprint(root):reads.append(root);return 'same-content-input'
    def unavailable(*a,**k):raise RuntimeError('synthetic metadata unavailable')
    monkeypatch.setattr(native,'_configuration_input',fingerprint)
    monkeypatch.setattr(native,'preflight',unavailable)
    with pytest.raises(RuntimeError,match='metadata unavailable'):
        native.complete_admission(tmp_path,tmp_path/'first')
    assert native.admission_status(tmp_path)['blocked']
    with pytest.raises(RuntimeError,match='blocked_across_request_ids'):
        native.complete_admission(tmp_path,tmp_path/'different-id')
    assert len(reads)==2


def test_write_fingerprint_uses_current_full_binary_contents(tmp_path,monkeypatch):
    binary=tmp_path/'synthetic-cli-never-executed';binary.write_bytes(b'one')
    monkeypatch.setattr(native,'CLI',str(binary))
    first=native._configuration_input(tmp_path)
    binary.write_bytes(b'two')
    assert native._configuration_input(tmp_path)!=first


@pytest.fixture
def diagnostic_substitutes(monkeypatch):
    from workbench import native_process
    calls=[];objects=[];rpc_calls=[]
    private='SYNTHETIC_PRIVATE_VALUE /private/path user@example.invalid https://private.invalid'
    class Owned:
        failure=None;timeout=False;oversize=False;feature_output=None
        def __init__(self,command,**kwargs):
            self.command=command;calls.append(command);objects.append(self)
            self.initial={'pid':123,'pgid':123,'sid':123,'start_ticks':1,'excluded':private}
            self.closed=False;self.cleanup_verified=False;self.err=bytearray()
            self.process=SimpleNamespace(returncode=None,poll=lambda:self.process.returncode)
        def communicate(self,timeout):
            assert timeout==10
            if self.timeout:raise TimeoutError(private)
            stage=next((x for x in ['--version','login','features','mcp'] if x in self.command),None)
            self.process.returncode=1 if stage==self.failure else 0
            if self.oversize:return b'x'*131073,private.encode()
            if self.process.returncode:return private.encode(),("unexpected argument '--strict-config' found "+private).encode()
            if stage=='--version':return b'codex-cli 0.0.0',b''
            if stage=='login':return b'Logged in using ChatGPT',private.encode()
            if stage=='features':
                if self.feature_output is not None:return self.feature_output.encode(),b''
                return '\n'.join(k[9:]+' stable false' for k in native.CONFIG if k.startswith('features.')).encode(),b''
            return b'[]',b''
        def close(self):
            self.closed=True;self.cleanup_verified=True
            if self.process.returncode is None:self.process.returncode=-15
    class RPC:
        timeout=False
        def __init__(self,owned):self.owned=owned
        def notify(self,method):assert method=='initialized'
        def call(self,method,params):
            rpc_calls.append(method)
            assert method in {'initialize','config/read','account/read','thread/start','experimentalFeature/list'}
            if self.timeout:raise TimeoutError(private)
            if method=='config/read':
                cfg={k:v for k,v in native.CONFIG.items() if not k.startswith('features.')}
                cfg['features']={k[9:]:v for k,v in native.CONFIG.items() if k.startswith('features.')}
                return {'config':{**cfg,'model_provider':'openai','model':'synthetic-model'}}
            if method=='account/read':return {'account':{'type':'chatgpt','email':private,'id':private}}
            if method=='thread/start':return {'model':'synthetic-model','modelProvider':'openai','approvalPolicy':'never','sandbox':{'type':'readOnly'},'runtimeWorkspaceRoots':[],'thread':{'id':'fixture','environments':[],'ephemeral':True}}
            if method=='experimentalFeature/list':return {'data':[{'name':k[9:],'enabled':False,'stage':'stable'} for k in native.CONFIG if k.startswith('features.')],'nextCursor':None}
            return {'unobserved':private}
    monkeypatch.setattr(native_process,'OwnedProcess',Owned);monkeypatch.setattr(native_process,'NativeRPC',RPC)
    monkeypatch.setattr(native,'CLI',sys.executable)
    return SimpleNamespace(Owned=Owned,RPC=RPC,calls=calls,objects=objects,rpc_calls=rpc_calls,private=private)


@pytest.mark.parametrize('flag,stage',[('--version','cli_version'),('login','login_status'),('features','features'),('mcp','mcp')])
def test_metadata_stage_and_failure_never_retain_raw_values(tmp_path,diagnostic_substitutes,flag,stage):
    fake=diagnostic_substitutes;fake.Owned.failure=flag;events=[]
    with pytest.raises(RuntimeError) as failed:
        native._metadata([native.CLI,flag],tmp_path,include_stderr=True,observer=events.append)
    assert failed.value.native_stage==stage
    serialized=str(failed.value)+json.dumps(events)
    assert fake.private not in serialized and 'user@example.invalid' not in serialized and '/private/path' not in serialized
    assert events[-1]['stage']==stage and events[-1]['cleanup_verified']
    assert all(p.closed and p.cleanup_verified for p in fake.objects)


@pytest.mark.parametrize('mode,category',[('timeout','timeout'),('oversize','output_limit')])
def test_metadata_timeout_and_output_bounds_are_sanitized_and_closed(tmp_path,diagnostic_substitutes,mode,category):
    fake=diagnostic_substitutes;setattr(fake.Owned,mode,True);events=[]
    with pytest.raises((RuntimeError,TimeoutError)) as failed:
        native._metadata([native.CLI,'login','status'],tmp_path,observer=events.append)
    assert failed.value.native_diagnostic['category']==category
    assert fake.private not in str(failed.value)+json.dumps(events)
    assert events[-1]['cleanup_verified']


def test_preflight_stops_at_first_exact_failed_stage(tmp_path,diagnostic_substitutes):
    fake=diagnostic_substitutes;fake.Owned.failure='features';events=[]
    with pytest.raises(RuntimeError) as failed:native.preflight(tmp_path,observer=events.append)
    assert failed.value.native_stage=='features'
    assert failed.value.native_diagnostic['category']=='unsupported_strict_config_flag'
    assert len(fake.calls)==3 and not fake.rpc_calls
    assert [e['stage'] for e in events]==['cli_version','login_status','features']
    assert events[-1]['status']=='failed' and all(e['cleanup_verified'] for e in events)


def test_zero_turn_preflight_observes_only_safe_facts_and_closes(tmp_path,diagnostic_substitutes):
    fake=diagnostic_substitutes;events=[];admission=native.preflight(tmp_path,observer=events.append)
    assert len(fake.calls)==5 and fake.rpc_calls==['initialize','config/read','initialize','config/read','account/read','thread/start','experimentalFeature/list']
    assert len(events)==8 and events[-1]['stage']=='shutdown' and events[-1]['cleanup_verified']
    assert events[0]['version']=='codex-cli 0.0.0'
    assert fake.private not in json.dumps(events) and 'email' not in json.dumps(events)
    assert admission['model_turns']==0 and all(p.cleanup_verified for p in fake.objects)


def test_appserver_timeout_is_sanitized_and_cleans_its_session(tmp_path,diagnostic_substitutes):
    fake=diagnostic_substitutes;fake.RPC.timeout=True;events=[]
    with pytest.raises(TimeoutError) as failed:native.preflight(tmp_path,observer=events.append)
    assert failed.value.native_stage=='initialize' and fake.rpc_calls==['initialize']
    assert fake.private not in str(failed.value)+json.dumps(events)
    assert events[-1]['stage']=='shutdown' and events[-1]['cleanup_verified']


def test_unknown_config_key_and_values_are_not_echoed():
    raw="unknown field `SYNTHETIC_PRIVATE_VALUE` value /private/path token=user@example.invalid"
    error=native._safe_error(SimpleNamespace(returncode=1,stderr=raw),'metadata')
    assert error.native_diagnostic['unknown_key_count']==1 and not error.native_diagnostic['unknown_fields']
    assert 'SYNTHETIC_PRIVATE_VALUE' not in str(error) and '/private/path' not in str(error)


def test_strict_config_is_kept_on_runtime_without_unsupported_metadata_flag(tmp_path,diagnostic_substitutes):
    fake=diagnostic_substitutes
    native.preflight(tmp_path)
    metadata=[command for command in fake.calls if 'features' in command or 'mcp' in command]
    assert len(metadata)==1
    for command in metadata:
        assert '--strict-config' not in command
        for option in native._config_arguments():assert option in command
    runtime=[command for command in fake.calls if 'app-server' in command]
    assert len(runtime)==2 and all('--strict-config' in cmd for cmd in runtime)
    for option in native._config_arguments():assert option in runtime[0]


def test_installed_strict_config_unsupported_template_is_safe():
    error=native._safe_error(SimpleNamespace(returncode=1,
        stderr='`--strict-config` is not supported for `codex features`. SYNTHETIC_PRIVATE_VALUE /private/path'),'metadata')
    assert error.native_diagnostic['category']=='unsupported_strict_config_flag'
    assert 'SYNTHETIC_PRIVATE_VALUE' not in str(error) and '/private/path' not in str(error)


def test_feature_projection_discards_unknown_names_and_private_values():
    raw='SYNTHETIC_PRIVATE_NAME stable true\n/private/path user@example.invalid https://private.invalid'
    report=native._feature_mismatches(raw)
    assert set(report)=={key for key in native.CONFIG if key.startswith('features.')}
    assert set(report.values())=={'missing'}
    assert 'SYNTHETIC_PRIVATE' not in json.dumps(report) and '/private/path' not in json.dumps(report)


@pytest.mark.parametrize('value,state',[('true','unexpected_enabled'),('SYNTHETIC_PRIVATE_VALUE','invalid')])
def test_feature_projection_reports_only_bounded_fixed_control_state(value,state):
    raw='\n'.join(key[9:]+' stable false' for key in native.CONFIG if key.startswith('features.') and key!='features.shell_tool')
    report=native._feature_mismatches(raw+'\nshell_tool stable '+value+'\nSYNTHETIC_PRIVATE_NAME stable true')
    assert report=={'features.shell_tool':state}
    assert 'SYNTHETIC_PRIVATE' not in json.dumps(report)


def test_duplicate_feature_rows_are_invalid_even_if_both_claim_disabled():
    assert native._feature_mismatches('shell_tool stable false\nshell_tool stable false')['features.shell_tool']=='invalid'


def test_missing_feature_stays_fail_closed_with_safe_diagnostic_and_cleanup(tmp_path,diagnostic_substitutes):
    fake=diagnostic_substitutes;fake.Owned.feature_output='SYNTHETIC_PRIVATE_NAME stable SYNTHETIC_PRIVATE_VALUE';events=[]
    with pytest.raises(RuntimeError) as failed:native.preflight(tmp_path,observer=events.append)
    detail=failed.value.native_diagnostic
    assert failed.value.native_stage=='features' and detail['category']=='fixed_feature_controls_unverified'
    assert set(detail['feature_mismatches'])=={key for key in native.CONFIG if key.startswith('features.')}
    assert set(detail['feature_mismatches'].values())=={'missing'}
    assert 'SYNTHETIC_PRIVATE' not in str(failed.value)+json.dumps(events)
    assert len(fake.calls)==3 and not fake.rpc_calls and all(p.cleanup_verified for p in fake.objects)
    assert events[-1]['status']=='failed'


@pytest.mark.parametrize('kind,expected',[
    ('absent',{'state':'absent'}),('null',{'state':'null'}),
    ('private_entry',{'state':'nonempty_object','entry_count':1,'explicitly_enabled_count':1}),
    ('disabled_entry',{'state':'nonempty_object','entry_count':1,'explicitly_enabled_count':0}),
    ('invalid',{'state':'invalid'}),
])
def test_mcp_echo_failure_distinguishes_safe_shape_before_account(tmp_path,monkeypatch,diagnostic_substitutes,kind,expected):
    fake=diagnostic_substitutes;original=fake.RPC.call;events=[]
    def call(self,method,params):
        response=original(self,method,params)
        if method=='config/read':
            if kind=='absent':response['config'].pop('mcp_servers')
            elif kind=='null':response['config']['mcp_servers']=None
            elif kind=='invalid':response['config']['mcp_servers']=[fake.private]
            else:response['config']['mcp_servers']={fake.private:{'enabled':kind=='private_entry','command':fake.private}}
        return response
    monkeypatch.setattr(fake.RPC,'call',call)
    with pytest.raises(RuntimeError) as failed:native.preflight(tmp_path,observer=events.append)
    detail=failed.value.native_diagnostic
    assert failed.value.native_stage=='config_read'
    assert detail=={'category':'fixed_mcp_controls_unverified','mcp_state':expected,'raw_output_retained':False,
        'reason_code':'unknown','lifecycle_milestone':'unknown'}
    assert fake.rpc_calls==['initialize','config/read']
    assert all(p.cleanup_verified for p in fake.objects)
    assert fake.private not in str(failed.value)+json.dumps(events)
    assert any(event['stage']=='config_read' and event['status']=='failed' for event in events)
    assert events[-1]['stage']=='shutdown' and events[-1]['cleanup_verified'] is True


@pytest.mark.parametrize('echo',[None,[{'environmentId':'synthetic-active'}],'missing'])
def test_invoke_refuses_unconfirmed_environment_denial_before_turn(tmp_path,monkeypatch,echo):
    calls=[];closed=[]
    class RPC:
        owned=SimpleNamespace(close=lambda:closed.append(True),cleanup_verified=True)
        def call(self,method,params):
            calls.append((method,params))
            if method=='thread/start':
                thread={'id':'synthetic-thread','ephemeral':True}
                if echo!='missing':thread['environments']=echo
                return {'model':'synthetic-default','modelProvider':'openai','approvalPolicy':'never',
                        'sandbox':{'type':'readOnly'},'runtimeWorkspaceRoots':[],'thread':thread}
            raise AssertionError('turn started without confirmed environment denial')
    monkeypatch.setattr(native,'_open_native',lambda *a:(RPC(),{'configured_model':None}))
    with pytest.raises(RuntimeError,match='native_stage_failed:turn'):
        native.invoke('synthetic',{},tmp_path/'refused',timeout=1,
            admission={'configured_model':None,'model_confinement_verified':True})
    assert [m for m,_ in calls]==['thread/start'] and closed==[True]
    assert not (tmp_path/'refused'/'native-receipt.json').exists()


def test_invoke_denies_environment_access_on_thread_and_turn_without_model_override(tmp_path,monkeypatch):
    calls=[];closed=[]
    class RPC:
        owned=SimpleNamespace(close=lambda:closed.append(True),initial={'pid':123,'start_ticks':1},cleanup_verified=True)
        notifications=[{'method':'item/completed','params':{'threadId':'t','turnId':'v',
                        'item':{'type':'agentMessage','text':'{"result":"synthetic"}'}}},
                       {'method':'turn/completed','params':{'threadId':'t','turn':{'id':'v','status':'completed'}}}]
        def call(self,method,params):
            calls.append((method,params))
            if method=='thread/start':return {'model':'synthetic-default','modelProvider':'openai',
                'approvalPolicy':'never','sandbox':{'type':'readOnly'},'runtimeWorkspaceRoots':[],
                'thread':{'id':'t','environments':[],'ephemeral':True}}
            if method=='experimentalFeature/list':return {'data':[{'name':k[9:],'enabled':False,'stage':'stable'} for k in native.CONFIG if k.startswith('features.')],'nextCursor':None}
            if method=='turn/start':return {'turn':{'id':'v'}}
            raise AssertionError(method)
    monkeypatch.setattr(native,'_open_native',lambda *a:(RPC(),{'configured_model':None}))
    result,_=native.invoke('synthetic',{'type':'object','required':['result']},tmp_path/'run',timeout=1,
        admission={'configured_model':None,'model_confinement_verified':True})
    assert result=={'result':'synthetic'} and closed==[True]
    for method,params in calls:
        if method not in {'thread/start','turn/start'}:continue
        assert params['environments']==[] and params['runtimeWorkspaceRoots']==[]
        assert 'model' not in params
    assert calls[0][1]['selectedCapabilityRoots']==[] and calls[0][1]['dynamicTools']==[]
    assert native.CONFIG['features.stable_environment_tools'] is False


def test_per_session_MCP_disable_is_verified_before_account_and_thread(tmp_path,monkeypatch,diagnostic_substitutes):
    fake=diagnostic_substitutes;original=fake.RPC.call
    def call(self,method,params):
        value=original(self,method,params)
        if method=='config/read':
            disabled='mcp_servers.fixture-server.enabled=false' in self.owned.command
            value['config']['mcp_servers']={'fixture-server':{'enabled':not disabled,'command':fake.private}}
        return value
    monkeypatch.setattr(fake.RPC,'call',call)
    admission=native.preflight(tmp_path)
    assert admission['mcp_servers_disabled']==1 and admission['protected_capability_paths_verified'] is True
    runtime=[p for p in fake.objects if 'app-server' in p.command]
    assert len(runtime)==2
    assert 'mcp_servers.fixture-server.enabled=false' not in runtime[0].command
    assert 'mcp_servers.fixture-server.enabled=false' in runtime[1].command
    assert fake.rpc_calls==['initialize','config/read','initialize','config/read','account/read','thread/start','experimentalFeature/list']
    assert all(p.cleanup_verified for p in fake.objects)


@pytest.mark.parametrize('mode',['key_drift','enabled_true','enabled_missing','enabled_string'])
def test_MCP_second_session_must_match_keys_and_explicit_false_before_account(tmp_path,monkeypatch,diagnostic_substitutes,mode):
    fake=diagnostic_substitutes;original=fake.RPC.call
    def call(self,method,params):
        value=original(self,method,params)
        if method=='config/read':
            second='mcp_servers.fixture.enabled=false' in self.owned.command
            row={'enabled':False} if second else {'enabled':True}
            if second and mode=='enabled_true':row={'enabled':True}
            if second and mode=='enabled_missing':row={}
            if second and mode=='enabled_string':row={'enabled':'false'}
            value['config']['mcp_servers']={'fixture':row}
            if second and mode=='key_drift':value['config']['mcp_servers']['added']={'enabled':False}
        return value
    monkeypatch.setattr(fake.RPC,'call',call)
    with pytest.raises(RuntimeError) as failed:native.preflight(tmp_path)
    assert failed.value.native_stage=='config_read'
    assert 'account/read' not in fake.rpc_calls and 'thread/start' not in fake.rpc_calls
    assert len([p for p in fake.objects if 'app-server' in p.command])==2
    assert all(p.cleanup_verified for p in fake.objects)


@pytest.mark.parametrize('key',['a.b','a"b','a b','a=b','a\nb','日本語','x'*129])
def test_MCP_override_rejects_keys_outside_proved_CLI_bare_components(key):
    with pytest.raises(RuntimeError):native._mcp_disable_arguments({'mcp_servers':{key:{'enabled':True}}})


@pytest.mark.parametrize('mode',['missing','duplicate','pagination','invalid_boolean','shell_enabled','wrong_binary'])
def test_thread_effective_features_fail_closed_on_coverage_or_capability_mismatch(mode):
    rows=[{'name':k[9:],'enabled':k=='features.unified_exec','stage':'stable'} for k in native.CONFIG if k.startswith('features.')]
    current={'version':'codex-cli 0.163.0','binary_sha256':'399ff69c431c066e40de318fba45c2b07f45a76b19939d247ee4828fc70c4215'}
    response={'data':rows,'nextCursor':None}
    if mode=='missing':rows.pop()
    if mode=='duplicate':rows.append(dict(rows[0]))
    if mode=='pagination':response['nextCursor']='synthetic-continuation'
    if mode=='invalid_boolean':rows[0]['enabled']=0
    if mode=='shell_enabled':rows[0]['enabled']=True
    if mode=='wrong_binary':current['binary_sha256']='different'
    with pytest.raises(RuntimeError):native._thread_feature_proof(response,current)


def test_unified_backend_exception_is_bound_to_proved_binary_and_complete_denial_flags():
    rows=[{'name':k[9:],'enabled':k=='features.unified_exec','stage':'stable'} for k in native.CONFIG if k.startswith('features.')]
    current={'version':'codex-cli 0.163.0','binary_sha256':'399ff69c431c066e40de318fba45c2b07f45a76b19939d247ee4828fc70c4215'}
    proof=native._thread_feature_proof({'data':rows,'nextCursor':None},current)
    assert proof['features.unified_exec'] is True
    assert all(enabled is False for name,enabled in proof.items() if name!='features.unified_exec')


@pytest.mark.parametrize('place',['configured','thread'])
@pytest.mark.parametrize('private',['/private/path user@example.invalid','/private/path','user@example.invalid','gpt/model','x'*129])
def test_invalid_model_identifier_rejected_without_private_retention(tmp_path,monkeypatch,diagnostic_substitutes,place,private):
    fake=diagnostic_substitutes;original=fake.RPC.call;events=[]
    def call(self,method,params):
        value=original(self,method,params)
        if method=='config/read':value['config']['model']=private if place=='configured' else None
        if method=='thread/start':value['model']=private
        return value
    monkeypatch.setattr(fake.RPC,'call',call)
    with pytest.raises(RuntimeError) as failed:native.preflight(tmp_path,observer=events.append)
    assert failed.value.native_stage in {'config_read','thread_start'}
    assert private not in str(failed.value)+json.dumps(events)
    if place=='configured':assert 'account/read' not in fake.rpc_calls
    assert all(p.cleanup_verified for p in fake.objects)


@pytest.mark.parametrize('where',['metadata','bootstrap','bootstrap_both','main_failure','preflight'])
def test_cleanup_exception_chain_is_safe_and_truthful(tmp_path,monkeypatch,diagnostic_substitutes,where):
    fake=diagnostic_substitutes;original_call=fake.RPC.call;original_close=fake.Owned.close;events=[]
    def call(self,method,params):
        value=original_call(self,method,params)
        runtimes=[p for p in fake.objects if 'app-server' in p.command]
        if method=='config/read' and ((where=='bootstrap_both' and len(runtimes)==1) or (where=='main_failure' and len(runtimes)==2)):
            raise RuntimeError(fake.private)
        return value
    def close(self):
        original_close(self)
        runtimes=[p for p in fake.objects if 'app-server' in p.command]
        if (where=='metadata' and '--version' in self.command) or ('app-server' in self.command and ((where.startswith('bootstrap') and len(runtimes)==1) or (not where.startswith('bootstrap') and len(runtimes)==2))):
            self.cleanup_verified=False
            error=subprocess.TimeoutExpired(['mcp_servers.'+fake.private+'.enabled=false'],1)
            error.extra={'nested':[ValueError(fake.private)]}
            error.__cause__=ExceptionGroup('SYNTHETIC_PRIVATE',[ValueError(fake.private)])
            raise error
    monkeypatch.setattr(fake.RPC,'call',call);monkeypatch.setattr(fake.Owned,'close',close)
    with pytest.raises(RuntimeError) as failed:
        try:raise ValueError(fake.private+' OUTER_OPERATION')
        except ValueError:native.preflight(tmp_path,observer=events.append)
    assert failed.value.native_stage=='shutdown'
    assert failed.value.native_diagnostic['cleanup_verified'] is False
    assert fake.private not in str(failed.value)+json.dumps(events)
    assert events[-1]['stage']=='shutdown' and events[-1]['status']=='failed' and events[-1]['cleanup_verified'] is False
    _assert_safe_exception_graph(failed.value,fake.private,events)


def test_invoke_cleanup_exception_chain_has_safe_precedence_over_operation_error(tmp_path,monkeypatch):
    private='SYNTHETIC_PRIVATE_MCP /private/path user@example.invalid'
    def close():raise subprocess.TimeoutExpired([private],1)
    owned=SimpleNamespace(close=close,cleanup_verified=False)
    monkeypatch.setattr(native,'_open_native',lambda *a:(SimpleNamespace(owned=owned),{'configured_model':'different'}))
    with pytest.raises(RuntimeError) as failed:
        native.invoke('synthetic',{},tmp_path/'invoke',timeout=1,admission={'configured_model':'old','model_confinement_verified':True})
    assert failed.value.native_stage=='shutdown' and failed.value.native_diagnostic['cleanup_verified'] is False
    assert private not in str(failed.value)
    _assert_safe_exception_graph(failed.value,private,[])


def _assert_safe_exception_graph(error,private,events):
    """Inspect suppressed and explicit chains, nested args/attrs and groups."""
    pending=[error,events];seen=set();strings=[]
    while pending:
        value=pending.pop()
        if id(value) in seen:continue
        seen.add(id(value))
        if isinstance(value,BaseException):
            strings.append(str(value));pending.extend([value.__context__,value.__cause__,value.args,vars(value)])
            if isinstance(value,BaseExceptionGroup):pending.extend(value.exceptions)
        elif isinstance(value,dict):pending.extend(value.keys());pending.extend(value.values())
        elif isinstance(value,(list,tuple,set,frozenset)):pending.extend(value)
        elif isinstance(value,(str,bytes)):strings.append(str(value))
    serialized='\n'.join(strings)
    for marker in [private,'/private/path','user@example.invalid','SYNTHETIC_PRIVATE']:
        assert marker not in serialized
    assert error.__context__ is None and error.__cause__ is None


@pytest.mark.parametrize('where',['metadata','bootstrap','main'])
def test_operation_exception_chain_drops_raw_arguments_causes_and_attributes(tmp_path,monkeypatch,diagnostic_substitutes,where):
    fake=diagnostic_substitutes;events=[];original_call=fake.RPC.call;original_communicate=fake.Owned.communicate
    raw=RuntimeError({'argv':['mcp_servers.SYNTHETIC_PRIVATE.enabled=false',fake.private]})
    raw.extra={'nested':[ValueError(fake.private)]};raw.extra['cycle']=raw.extra
    raw.__cause__=ExceptionGroup('SYNTHETIC_PRIVATE',[ValueError(fake.private)])
    def communicate(self,*a,**k):
        if where=='metadata':raise raw
        return original_communicate(self,*a,**k)
    def call(self,method,params):
        runtimes=[p for p in fake.objects if 'app-server' in p.command]
        if method=='config/read' and ((where=='bootstrap' and len(runtimes)==1) or (where=='main' and len(runtimes)==2)):raise raw
        return original_call(self,method,params)
    monkeypatch.setattr(fake.Owned,'communicate',communicate);monkeypatch.setattr(fake.RPC,'call',call)
    with pytest.raises(RuntimeError) as failed:
        try:raise ValueError(fake.private+' OUTER_OPERATION')
        except ValueError:native.preflight(tmp_path,observer=events.append)
    _assert_safe_exception_graph(failed.value,fake.private,events)
    assert all(p.cleanup_verified for p in fake.objects)


def test_invoke_operation_exception_chain_drops_raw_rpc_error(tmp_path,monkeypatch):
    private='SYNTHETIC_PRIVATE_MCP /private/path user@example.invalid'
    closed=[];owned=SimpleNamespace(close=lambda:closed.append(True),cleanup_verified=True)
    def call(*a,**k):raise ValueError(private)
    current={'configured_model':'synthetic-model'}
    rpc=SimpleNamespace(owned=owned,native_thread={'id':'synthetic-thread','model':'synthetic-model','provider':'openai'},call=call)
    monkeypatch.setattr(native,'_open_native',lambda *a:(rpc,current))
    with pytest.raises(RuntimeError) as failed:
        native.invoke('synthetic',{},tmp_path/'invoke',timeout=1,admission={**current,'model_confinement_verified':True})
    _assert_safe_exception_graph(failed.value,private,[])
    assert closed==[True] and not (tmp_path/'invoke/native-receipt.json').exists()


@pytest.mark.parametrize('verification',[False,None])
def test_cleanup_without_verification_stays_fail_closed(verification):
    calls=[];owned=SimpleNamespace(close=lambda:calls.append(True),cleanup_verified=verification)
    with pytest.raises(RuntimeError) as failed:native._close_native(owned)
    assert calls==[True] and owned.cleanup_verified is False
    assert failed.value.native_stage=='shutdown'
    assert failed.value.native_diagnostic['cleanup_verified'] is False
    _assert_safe_exception_graph(failed.value,'SYNTHETIC_PRIVATE',[])


@pytest.mark.parametrize('mode',['nested','known_fields','wrong_types'])
def test_native_diagnostic_attributes_never_bypass_safe_projection(mode):
    private='SYNTHETIC_PRIVATE /private/path user@example.invalid'
    raw=RuntimeError(private)
    diagnostics={
        'nested':{'category':'protocol_or_confinement_failure','detail':{'nested':private}},
        'known_fields':{'category':'cleanup_failure','unknown_fields':[private],'mcp_state':{'state':private,'entry_count':private},'feature_mismatches':{'features.shell_tool':private},'cleanup_verified':private},
        'wrong_types':{'category':[private],'exit_status':{'private':private},'unknown_key_count':True,'strict_config_rejection':private,'raw_output_retained':private},
    }
    raw.native_diagnostic=diagnostics[mode]
    safe=native._stage_error('initialize',raw);events=[]
    native._observe(events.append,'initialize',error=safe)
    _assert_safe_exception_graph(safe,private,events)
    assert safe.native_diagnostic['raw_output_retained'] is False
    # The observer is also a boundary when handed an unsanitized exception.
    native._observe(events.append,'initialize',error=raw)
    _assert_safe_exception_graph(safe,private,events)


@pytest.mark.parametrize('fault,reason,milestone',[
    ('admission','admission_changed','admission_check'),
    ('tool','unexpected_tool_event','turn_started'),
    ('thread','thread_event_mismatch','turn_started'),
    ('error','turn_error','turn_started'),
    ('schema','schema_validation_failed','response_validation'),
    ('missing','answer_missing_or_too_large','turn_completed'),
])
def test_r40_trusted_turn_branches_keep_distinct_redacted_reasons(tmp_path,monkeypatch,fault,reason,milestone):
    private='SYNTHETIC_PRIVATE /private/path user@example.invalid';closed=[]
    current={'configured_model':'synthetic-model'}
    messages=[{'method':'item/completed','params':{'item':{'type':'agentMessage','text':'{"result":"ok"}'}}},
              {'method':'turn/completed','params':{'turn':{'id':'safe-turn','status':'completed'}}}]
    if fault=='tool':messages=[{'method':'item/started','params':{'item':{'type':'commandExecution','argv':[private]}}}]
    elif fault=='thread':messages=[{'method':'item/started','params':{'threadId':private}}]
    elif fault=='error':messages=[{'method':'error','params':{'code':{'nested':private}}}]
    elif fault=='schema':messages[0]['params']['item']['text']=json.dumps({'wrong':private})
    elif fault=='missing':messages.pop(0)
    owned=SimpleNamespace(close=lambda:closed.append(True),cleanup_verified=True)
    rpc=SimpleNamespace(owned=owned,native_thread={'id':'safe-thread','model':'synthetic-model','provider':'openai'},
        notifications=messages,call=lambda *a,**k:{'turn':{'id':'safe-turn'}})
    monkeypatch.setattr(native,'_open_native',lambda *a:(rpc,current))
    admission={**current,'model_confinement_verified':True}
    if fault=='admission':admission['configured_model']='different'
    with pytest.raises(RuntimeError) as failed:
        native.invoke('synthetic',{'type':'object','required':['result']},tmp_path/'invoke',timeout=1,admission=admission)
    detail=native._diagnostic(failed.value)
    assert detail['reason_code']==reason and detail['lifecycle_milestone']==milestone
    assert failed.value.native_stage=='turn' and closed==[True]
    _assert_safe_exception_graph(failed.value,private,[])


@pytest.mark.parametrize('field',['reason_code','lifecycle_milestone','stage'])
def test_r40_arbitrary_error_attributes_and_stage_cannot_supply_public_facts(field):
    private='SYNTHETIC_PRIVATE /private/path user@example.invalid'
    raw=RuntimeError(private);raw.native_diagnostic={'reason_code':'schema_validation_failed','lifecycle_milestone':'response_validated','detail':{'nested':private}}
    raw.extra={'cycle':raw};raw.__cause__=ExceptionGroup(private,[ValueError(private)])
    safe=native._stage_error(private if field=='stage' else 'turn',raw)
    detail=native._diagnostic(safe)
    assert detail['reason_code']=='unknown' and detail['lifecycle_milestone']=='unknown'
    assert safe.native_stage==('unknown' if field=='stage' else 'turn')
    _assert_safe_exception_graph(safe,private,[])


def test_r40_diagnostic_never_stringifies_an_untrusted_exception():
    class Bomb(RuntimeError):
        def __str__(self):raise AssertionError('SYNTHETIC_PRIVATE stringify')
    detail=native._diagnostic(Bomb())
    assert detail['reason_code']=='unknown' and detail['raw_output_retained'] is False


def test_r40_rpc_rejection_records_attempt_without_claiming_turn_started(tmp_path,monkeypatch):
    from workbench.native_process import NativeFailure
    closed=[];current={'configured_model':'synthetic-model'}
    def reject(*a,**k):raise NativeFailure('rpc_rejected')
    rpc=SimpleNamespace(owned=SimpleNamespace(close=lambda:closed.append(True),cleanup_verified=True),
        native_thread={'id':'synthetic-thread','model':'synthetic-model','provider':'openai'},call=reject)
    monkeypatch.setattr(native,'_open_native',lambda *a:(rpc,current))
    with pytest.raises(RuntimeError) as failure:
        native.invoke('synthetic',{},tmp_path/'invoke',timeout=1,admission={**current,'model_confinement_verified':True})
    detail=native._diagnostic(failure.value)
    assert detail['reason_code']=='rpc_rejected' and detail['lifecycle_milestone']=='turn_start_call'
    assert closed==[True] and not (tmp_path/'invoke/native-receipt.json').exists()


def _r50_identity_failure(tmp_path,monkeypatch,event):
    private='SYNTHETIC_PRIVATE /private/path user@example.invalid';closed=[]
    current={'configured_model':'synthetic-model'}
    rpc=SimpleNamespace(owned=SimpleNamespace(close=lambda:closed.append(True),cleanup_verified=True),
        native_thread={'id':'safe-thread','model':'synthetic-model','provider':'openai'},
        notifications=[event],call=lambda *a,**k:{'turn':{'id':'safe-turn'}})
    monkeypatch.setattr(native,'_open_native',lambda *a:(rpc,current))
    with pytest.raises(RuntimeError) as failed:
        native.invoke('synthetic',{},tmp_path/'invoke',timeout=1,
            admission={**current,'model_confinement_verified':True})
    detail=native._diagnostic(failed.value)
    _assert_safe_exception_graph(failed.value,private,[])
    assert closed==[True] and not (tmp_path/'invoke/native-receipt.json').exists()
    return detail


def test_r50_distinguishes_identity_failure_envelopes(tmp_path,monkeypatch):
    private='SYNTHETIC_PRIVATE /private/path user@example.invalid'
    wrong_thread=_r50_identity_failure(tmp_path,monkeypatch,{'method':'item/started',
        'params':{'threadId':private,'turnId':'safe-turn'}})
    null_scope=_r50_identity_failure(tmp_path,monkeypatch,{'method':'thread/status/changed',
        'params':{'threadId':None,'turnId':None}})
    # The old four-field diagnostic collapses these different failure envelopes.
    assert wrong_thread!=null_scope
    assert wrong_thread['reason_code']==null_scope['reason_code']=='thread_event_mismatch'
    assert wrong_thread['protocol_event']=={'method':'item/started','thread_id_state':'mismatch','turn_id_state':'match'}
    assert null_scope['protocol_event']=={'method':'thread/status/changed','thread_id_state':'null','turn_id_state':'null'}


@pytest.mark.parametrize('method',['item/started','item/completed','thread/started','thread/status/changed','SYNTHETIC_PRIVATE /private/path user@example.invalid'])
@pytest.mark.parametrize('wrong_field',['threadId','turnId'])
def test_r50_finite_facts_never_accept_foreign_identity(tmp_path,monkeypatch,method,wrong_field):
    params={'threadId':'safe-thread','turnId':'safe-turn'}
    params[wrong_field]='SYNTHETIC_PRIVATE /private/path user@example.invalid'
    detail=_r50_identity_failure(tmp_path,monkeypatch,{'method':method,'params':params})
    assert detail['reason_code']==('thread_event_mismatch' if wrong_field=='threadId' else 'turn_event_mismatch')
    assert detail['protocol_event']=={'method':method if method.startswith(('item/','thread/')) else 'other',
        'thread_id_state':'mismatch' if wrong_field=='threadId' else 'match',
        'turn_id_state':'mismatch' if wrong_field=='turnId' else 'match'}


@pytest.mark.parametrize('value,state',[(None,'null'),(False,'invalid'),(12,'invalid'),({},'invalid'),([], 'invalid'),('', 'invalid'),('safe-thread','match')])
def test_r50_identity_shape_has_no_raw_value(tmp_path,monkeypatch,value,state):
    detail=_r50_identity_failure(tmp_path,monkeypatch,{'method':'item/started',
        'params':{'threadId':value,'turnId':'SYNTHETIC_PRIVATE /private/path user@example.invalid'}})
    assert detail['protocol_event']['thread_id_state']==state
    assert detail['protocol_event']['turn_id_state']=='mismatch'


def test_r50_missing_identity_is_distinct_from_null(tmp_path,monkeypatch):
    detail=_r50_identity_failure(tmp_path,monkeypatch,{'method':'item/started',
        'params':{'turnId':'SYNTHETIC_PRIVATE /private/path user@example.invalid'}})
    assert detail['protocol_event']=={'method':'item/started','thread_id_state':'missing','turn_id_state':'mismatch'}


@pytest.mark.parametrize('payload',[None,False,'SYNTHETIC_PRIVATE /private/path user@example.invalid',[],
    {'method':'SYNTHETIC_PRIVATE /private/path user@example.invalid','thread_id_state':{'private':'SYNTHETIC_PRIVATE'},'turn_id_state':False,'raw':'SYNTHETIC_PRIVATE'},
    {'method':'item/started','thread_id_state':'mismatch','turn_id_state':'match','raw':'SYNTHETIC_PRIVATE'}])
def test_r50_protocol_fact_boundary_rejects_arbitrary_values(payload):
    private='SYNTHETIC_PRIVATE /private/path user@example.invalid'
    raw=native._SafeNativeError('synthetic safe wrapper')
    raw.native_diagnostic={'reason_code':'thread_event_mismatch','lifecycle_milestone':'turn_started','protocol_event':payload}
    raw.arbitrary={'private':private,'self':raw};raw.__cause__=ExceptionGroup(private,[ValueError(private)])
    safe=native._stage_error('turn',raw);events=[];native._observe(events.append,'initialize',error=safe)
    _assert_safe_exception_graph(safe,private,events)
    detail=native._diagnostic(safe)
    if type(payload) is dict:
        assert detail['protocol_event']=={'method':'item/started' if payload.get('method')=='item/started' else 'other',
            'thread_id_state':'mismatch' if payload.get('thread_id_state')=='mismatch' else 'invalid',
            'turn_id_state':'match' if payload.get('turn_id_state')=='match' else 'invalid'}
        assert events[0]['diagnostic']['protocol_event']==detail['protocol_event']
    else:assert 'protocol_event' not in detail


def test_r50_protocol_projection_does_not_stringify_objects():
    class Bomb:
        def __str__(self):raise AssertionError('SYNTHETIC_PRIVATE stringify')
        def __hash__(self):raise AssertionError('SYNTHETIC_PRIVATE hash')
    raw=native._SafeNativeError('safe wrapper');raw.native_diagnostic={'reason_code':'thread_event_mismatch',
        'protocol_event':{'method':Bomb(),'thread_id_state':Bomb(),'turn_id_state':Bomb()}}
    assert native._diagnostic(raw)['protocol_event']=={'method':'other','thread_id_state':'invalid','turn_id_state':'invalid'}


@pytest.mark.parametrize('with_ids',[False,True])
def test_r50_matching_and_omitted_scope_success_is_unchanged(tmp_path,monkeypatch,with_ids):
    closed=[];current={'configured_model':'synthetic-model'}
    scope={'threadId':'safe-thread','turnId':'safe-turn'} if with_ids else {}
    owned=SimpleNamespace(close=lambda:closed.append(True),cleanup_verified=True,initial={'pid':1,'start_ticks':1})
    rpc=SimpleNamespace(owned=owned,native_thread={'id':'safe-thread','model':'synthetic-model','provider':'openai'},
        notifications=[{'method':'item/completed','params':{**scope,'item':{'type':'agentMessage','text':'{"result":"ok"}'}}},
            {'method':'turn/completed','params':{**scope,'turn':{'id':'safe-turn','status':'completed'}}}],
        call=lambda *a,**k:{'turn':{'id':'safe-turn'}})
    monkeypatch.setattr(native,'_open_native',lambda *a:(rpc,current))
    answer,receipt=native.invoke('synthetic',{'type':'object','required':['result']},tmp_path/'invoke',timeout=1,
        admission={**current,'model_confinement_verified':True})
    assert answer=={'result':'ok'} and receipt['thread_id']=='safe-thread' and closed==[True]
    assert (tmp_path/'invoke/native-receipt.json').is_file() and 'protocol_event' not in receipt


@pytest.mark.parametrize('unsafe',[None,False,123,{'reason':'schema_validation_failed'},['turn_started']])
def test_r40_invalid_typed_fields_fall_back_to_unknown(unsafe):
    from workbench.native_process import NativeFailure
    raw=NativeFailure(unsafe)
    raw.reason_code=unsafe
    safe=native._stage_error(unsafe,raw,milestone=unsafe)
    detail=native._diagnostic(safe)
    assert detail['reason_code']=='unknown' and detail['lifecycle_milestone']=='unknown'
    assert safe.native_stage=='unknown'


@pytest.mark.parametrize('reply',[{}, {'turn':{'id':False}}, {'turn':{'id':{'private':'SYNTHETIC_PRIVATE'}}}])
def test_r40_malformed_turn_reply_cannot_claim_started(tmp_path,monkeypatch,reply):
    closed=[];current={'configured_model':'synthetic-model'}
    rpc=SimpleNamespace(owned=SimpleNamespace(close=lambda:closed.append(True),cleanup_verified=True),
        native_thread={'id':'synthetic-thread','model':'synthetic-model','provider':'openai'},call=lambda *a,**k:reply)
    monkeypatch.setattr(native,'_open_native',lambda *a:(rpc,current))
    with pytest.raises(RuntimeError) as failure:
        native.invoke('synthetic',{},tmp_path/'invoke',timeout=1,admission={**current,'model_confinement_verified':True})
    detail=native._diagnostic(failure.value)
    assert detail['reason_code']=='turn_start_unverified' and detail['lifecycle_milestone']=='turn_start_call'
    assert closed==[True]
    _assert_safe_exception_graph(failure.value,'SYNTHETIC_PRIVATE',[])


def test_r40_missing_typed_reason_is_unknown():
    from workbench.native_process import NativeFailure
    raw=NativeFailure('turn_error');del raw.reason_code
    safe=native._stage_error('turn',raw)
    assert native._diagnostic(safe)['reason_code']=='unknown'
