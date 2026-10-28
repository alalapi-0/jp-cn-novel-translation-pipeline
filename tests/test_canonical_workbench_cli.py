"""Synthetic CLI integration through the same recovery service."""
import json
from pathlib import Path
import subprocess
import sys
import importlib.util
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from workbench.canonical_service import import_sources, import_candidates


def cli_module():
    script=Path(__file__).resolve().parents[1]/'scripts/canonical_workbench.py'
    spec=importlib.util.spec_from_file_location('canonical_cli_test',script)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def test_cli_full_shared_service_selection_export_and_body_free_output(tmp_path,capsys):
    (tmp_path/'workspace').mkdir()
    cli=cli_module();file=tmp_path/'003-synthetic.md';file.write_text('# 章\n\n合成原文。')
    base=['--root',str(tmp_path),'--project','cli-complete']
    assert cli.main(base+['source-import','--direction','JP_TO_CN','--source-file',str(file)])==0
    state=json.loads(capsys.readouterr().out)['selection'];assert state['segments_total']==1
    from workbench.canonical_service import selection_status
    full=selection_status(tmp_path,'cli-complete')
    state=import_candidates(tmp_path,'cli-complete',expected_manifest_sha256=state['manifest_sha256'],
        source_inventory_sha256=state['source_inventory_sha256'],candidates=[{'segment_id':r['segment_id'],'target_text':'合成译文。'} for r in full['segments']])
    select=['select-version','--expected-manifest-sha256',state['manifest_sha256'],'--confirm-select']
    assert cli.main(base+select)==1;assert 'stale accepted review' in capsys.readouterr().err
    from workbench.project_registry import get_project_manifest,patch_project_review_state_cas
    from workbench.review_state import DecisionActor,approval_identity
    manifest=get_project_manifest(tmp_path,'cli-complete')
    patch_project_review_state_cas(tmp_path,'cli-complete',decision_actor=DecisionActor('agent','synthetic-cli-review'),
        segments={r['id']:{'status':'approved','expected_identity':approval_identity(project_id='cli-complete',language_direction='JP_TO_CN',segment=r)} for r in manifest.segments})
    assert cli.main(base+select)==0;selected=json.loads(capsys.readouterr().out)['selection'];assert selected['selected_current']
    assert cli.main(base+['export-selected','--expected-manifest-sha256',selected['manifest_sha256'],'--confirm-replace'])==0
    output=capsys.readouterr().out;export=json.loads(output)
    assert export['segments_exported']==1 and not export['human_approved_final']
    assert '合成原文' not in output and '合成译文' not in output and 'segments' not in export['selection']


@pytest.mark.parametrize('action',['generate','review'])
def test_cli_native_command_delegates_exact_job_and_scrubs_bodies(tmp_path,monkeypatch,capsys,action):
    cli=cli_module();seen=[]
    def execute(root,project,**kwargs):
        seen.append((root,project,kwargs))
        return {'action':action,'native':{'thread_id':'private-thread','prompt':'PRIVATE_BODY'},
            'selection':{'project_id':project,'segments':[{'source':'PRIVATE_BODY','target_text':'PRIVATE_BODY'}],'human_approved_final':False}}
    import workbench.native_agent
    monkeypatch.setattr(workbench.native_agent,'execute_job',execute)
    args=['--root',str(tmp_path),'--project','native-cli','native-job','--action',action,
        '--request-id','synthetic-job','--expected-manifest-sha256','a'*64,'--confirm-native']
    assert cli.main(args)==0
    assert seen==[(tmp_path,'native-cli',{'expected_manifest_sha256':'a'*64,'request_id':'synthetic-job','action':action})]
    assert 'PRIVATE_BODY' not in capsys.readouterr().out
    with pytest.raises(SystemExit):cli.main(args[:-1])
    assert len(seen)==1


@pytest.mark.parametrize('command,flag',[('select-version','--confirm-select'),('export-selected','--confirm-replace')])
def test_cli_requires_explicit_irreversible_selection_intent(tmp_path,command,flag):
    cli=cli_module();args=['--root',str(tmp_path),'--project','synthetic',command,'--expected-manifest-sha256','a'*64]
    with pytest.raises(SystemExit):cli.main(args)


def test_cli_source_symlink_and_forged_model_or_actor_are_refused(tmp_path):
    cli=cli_module();file=tmp_path/'003-source.md';file.write_text('Synthetic source');link=tmp_path/'004-link.md';link.symlink_to(file)
    base=['--root',str(tmp_path),'--project','synthetic']
    assert cli.main(base+['source-import','--direction','JP_TO_CN','--source-file',str(link)])==1
    for extra in [['--actor-type','agent'],['--model','forged']]:
        with pytest.raises(SystemExit):cli.main(base+['status']+extra)


def test_cli_source_import_preserves_original_newline_bytes(tmp_path,capsys):
    (tmp_path/'workspace').mkdir()
    cli=cli_module();file=tmp_path/'003-crlf.md';raw='# 章\r\n\r\n合成源文。\r\n'.encode();file.write_bytes(raw)
    assert cli.main(['--root',str(tmp_path),'--project','crlf','source-import','--direction','JP_TO_CN','--source-file',str(file)])==0
    assert (tmp_path/'input_jp/crlf/003-crlf.md').read_bytes()==raw


def test_cli_export_completed_with_unavailable_followup_is_success(tmp_path,monkeypatch,capsys):
    (tmp_path/'workspace').mkdir()
    leaf=tmp_path/'workspace/review_state.json';leaf.write_text('{"projects":{}}')
    cli=cli_module();effect=tmp_path/'synthetic-output'
    def completed(*_args,**_kwargs):
        effect.write_text('synthetic output')
        leaf.write_text('{')
        return {'project_id':'cli-warning','segments_exported':1,'human_approved_final':False}
    monkeypatch.setattr(cli,'export_selected',completed)
    args=['--root',str(tmp_path),'--project','cli-warning','export-selected',
          '--expected-manifest-sha256','a'*64,'--confirm-replace']
    assert cli.main(args)==0
    captured=capsys.readouterr();result=json.loads(captured.out)
    assert effect.exists() and result['effect_applied'] is True and result['selection'] is None
    assert result['selection_status_available'] is False and '请勿重复提交' in captured.err


def test_cli_native_unknown_history_does_not_claim_no_previous_effect(tmp_path,monkeypatch,capsys):
    import workbench.native_agent
    from workbench.canonical_service import NativeRequestHistoryUnknown
    cli=cli_module()
    def unknown(*_a,**_k):raise NativeRequestHistoryUnknown()
    monkeypatch.setattr(workbench.native_agent,'execute_job',unknown)
    args=['--root',str(tmp_path),'--project','synthetic','native-job','--action','generate',
          '--request-id','same-id','--expected-manifest-sha256','a'*64,'--confirm-native']
    assert cli.main(args)==1
    result=json.loads(capsys.readouterr().err)
    assert result['invocation_effect_applied'] is False and result['request_effect_status']=='unknown'
    assert result['idempotent_replay']=='unknown' and result['retry_operation'] is False
    assert 'effect_applied' not in result and 'mutation_committed' not in result


def test_cli_status_restore_confirmation_and_stale_cas(tmp_path):
    (tmp_path/'workspace').mkdir()
    script=Path(__file__).resolve().parents[1]/'scripts/canonical_workbench.py'
    state=import_sources(tmp_path,project_id='cli-recovery',name='Synthetic',language_direction='JP_TO_CN',
        chapters=[{'filename':'003-synthetic.md','text':'# 章\n\n合成原文。'}])
    state=import_candidates(tmp_path,'cli-recovery',expected_manifest_sha256=state['manifest_sha256'],
        source_inventory_sha256=state['source_inventory_sha256'],candidates=[{'segment_id':r['segment_id'],'target_text':'合成候选。'} for r in state['segments']])
    command=[sys.executable,str(script),'--root',str(tmp_path),'--project','cli-recovery']
    status=subprocess.run(command+['status'],capture_output=True,text=True)
    assert status.returncode==0 and 'segments' not in json.loads(status.stdout)['selection']
    args=['restore-previous','--expected-manifest-sha256',state['manifest_sha256']]
    assert subprocess.run(command+args,capture_output=True).returncode==2
    success=subprocess.run(command+args+['--confirm-restore'],capture_output=True,text=True)
    assert success.returncode==0 and json.loads(success.stdout)['action']=='restore_unreviewed_drafts'
    assert '合成原文' not in success.stdout and '合成候选' not in success.stdout
    path=tmp_path/'workspace/manifests/cli-recovery.json';raw=path.read_bytes()
    stale=subprocess.run(command+args+['--confirm-restore'],capture_output=True,text=True)
    assert stale.returncode==1 and json.loads(stale.stderr)['error_type']=='CanonicalVersionConflict'
    assert path.read_bytes()==raw
