"""Synthetic cross-work policy and legacy entry regressions, no corpus inputs."""
from pathlib import Path
import json
import sys
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'scripts')]


def test_other_work_issue_is_not_suppressed_by_ambient_literal_set(monkeypatch):
    import quality_review.checkers as module
    monkeypatch.setattr(module, '_AUTO_FIX_DENYLIST', {'旧称'}, raising=False)
    doc={'project_id':'other-work','language_direction':'JP_TO_CN','paragraphs':[
        {'segments':[{'segment_id':'s1','source_text':'TOKEN','target_text':'旧称'}]}]}
    glossary={'terms':[{'source':'TOKEN','canonical_zh':'新称','aliases_zh':['旧称'],'locked':True}]}
    issues=module.check_term_consistency(doc,glossary)
    assert len(issues)==1 and issues[0].auto_fixable is False


def test_new_work_pure_fixer_does_not_inherit_ambient_instances(monkeypatch):
    import fix_terminology_consistency as module
    monkeypatch.setattr(module,'SPECIAL_SOURCE_RULES',(('旧称','新称','TOKEN',(),('s1',)),),raising=False)
    text,hits=module.apply_rules('旧称','TOKEN',{},'s1')
    assert text=='旧称' and not hits


def test_legacy_write_cli_refuses_before_assets_or_target_read(tmp_path,monkeypatch):
    import fix_terminology_consistency as module
    calls=[]
    def forbidden(*_):calls.append(1);raise AssertionError('unselected old work assets were read')
    monkeypatch.setattr(module,'build_rules',forbidden,raising=False)
    monkeypatch.setattr(sys,'argv',['fixer','--segments-file',str(tmp_path/'missing.json'),'--chapters','1','2'])
    with pytest.raises(SystemExit) as error:module.main()
    assert error.value.code==2 and not calls


def test_wrapper_has_no_implicit_whole_book_range(monkeypatch):
    import run_consistency_fix_all as module
    calls=[]
    def forbidden():calls.append(1);raise AssertionError('unscoped run discovery entered')
    monkeypatch.setattr(module,'discover_canonical_files',forbidden)
    monkeypatch.setattr(sys,'argv',['fix-all','--dry-run'])
    with pytest.raises(SystemExit) as error:module.main()
    assert error.value.code==2 and not calls


def policy_fixture(root, *, work='work-a', revision='1'*64, direction='JP_TO_CN', rules=None, targets=None):
    import hashlib
    from consistency.work_rules import load_work_rules
    folder=root/'configs';folder.mkdir(exist_ok=True)
    path=folder/'selected.json'
    binding={'work_id':work,'source_revision':revision,'language_direction':direction}
    value={'schema':'work-rules/1','activation':'review_only',**binding,'target_files':targets or [],'rules':rules or {
        'source_rules':[{'variant':'旧称','target':'新称','source':'TOKEN','segment_ids':['s1']}],
        'chapter_range':[2,4]}}
    path.write_text(json.dumps(value,ensure_ascii=False));sha=hashlib.sha256(path.read_bytes()).hexdigest()
    return path,sha,binding,value,load_work_rules(root,path,sha,document=binding)


@pytest.mark.parametrize('field,value', [('work_id','work-b'),('source_revision','2'*64),('language_direction','CN_TO_JP')])
def test_foreign_work_source_or_direction_is_rejected(tmp_path,field,value):
    from consistency.work_rules import load_work_rules
    path,sha,binding,_,policy=policy_fixture(tmp_path)
    wrong={**binding,field:value}
    with pytest.raises(ValueError,match='work/source/direction'):
        load_work_rules(tmp_path,path,sha,document=wrong)
    with pytest.raises(ValueError):policy.require_document(wrong)


def test_selected_policy_applies_only_to_bound_pure_candidate(tmp_path):
    import fix_terminology_consistency as module
    _,_,binding,_,policy=policy_fixture(tmp_path)
    assert module.apply_rules('旧称','TOKEN',{},'s1',work_rules=policy,document=binding)[0]=='新称'
    assert module.apply_rules('旧称','OTHER',{},'s1',work_rules=policy,document=binding)[0]=='旧称'
    assert module.apply_rules('旧称','TOKEN',{},'other-id',work_rules=policy,document=binding)[0]=='旧称'
    with pytest.raises(ValueError):module.apply_rules('旧称','TOKEN',{},'s1',work_rules=policy)
    assert module.apply_rules('旧称','TOKEN',{},'s1')[0]=='旧称'


def test_policy_snapshot_is_immutable_and_next_work_has_no_cache_leak(tmp_path):
    from dataclasses import FrozenInstanceError
    _,_,binding,_,first=policy_fixture(tmp_path)
    with pytest.raises(TypeError):first.rules['source_rules'][0]['target']='silently changed'
    with pytest.raises(FrozenInstanceError):first.work_id='work-b'
    _,_,other,_,second=policy_fixture(tmp_path,work='work-b',revision='2'*64,rules={'auto_fix_denylist':['different']})
    assert first.work_id==binding['work_id'] and first.get('auto_fix_denylist')==()
    assert second.get('source_rules')==() and second.work_id==other['work_id']


@pytest.mark.parametrize('change', ['hash','activation','legacy','human_claim','unanchored','invalid_type'])
def test_changed_legacy_or_unsupported_policy_cannot_be_selected(tmp_path,change):
    import hashlib
    from consistency.work_rules import load_work_rules
    path,sha,binding,value,_=policy_fixture(tmp_path)
    if change=='hash':sha='0'*64
    elif change=='activation':value['activation']='apply'
    elif change=='legacy':value['schema']='legacy-work-rules-archive/1'
    elif change=='human_claim':value['human_approved_final']=True
    elif change=='unanchored':value['rules']['source_rules'][0].update(source='',segment_ids=[])
    elif change=='invalid_type':value['rules']['auto_fix_denylist']='not a list'
    if change!='hash':
        path.write_text(json.dumps(value));sha=hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(ValueError):load_work_rules(tmp_path,path,sha,document=binding)


@pytest.mark.parametrize('kind',['outside','symlink','dotenv'])
def test_unregistered_policy_path_is_denied_before_body_read(tmp_path,monkeypatch,kind):
    import consistency.work_rules as module
    path,sha,binding,_,_=policy_fixture(tmp_path)
    if kind=='outside':selected=tmp_path/'outside.json';selected.write_bytes(path.read_bytes())
    elif kind=='symlink':selected=path.parent/'alias.json';selected.symlink_to(path)
    else:selected=path.parent/'.env';selected.write_bytes(path.read_bytes())
    def forbidden(*_,**__):raise AssertionError('unregistered policy body opened')
    monkeypatch.setattr(module.os,'open',forbidden)
    with pytest.raises(ValueError):module.load_work_rules(tmp_path,selected,sha,document=binding)


def test_selected_chapter_range_has_no_default_or_override(tmp_path):
    from types import SimpleNamespace
    from consistency.work_rules import selected_chapter_range
    _,_,_,_,policy=policy_fixture(tmp_path)
    assert selected_chapter_range(SimpleNamespace(chapters=None),policy)==(2,4)
    with pytest.raises(ValueError):selected_chapter_range(SimpleNamespace(chapters=None),None)
    with pytest.raises(ValueError):selected_chapter_range(SimpleNamespace(chapters=[1,612]),policy)


def test_selected_cn_to_jp_preview_preserves_direction_and_target_bytes(tmp_path,monkeypatch,capsys):
    import hashlib
    import fix_terminology_consistency as module
    binding={'work_id':'work-a','source_revision':'1'*64,'language_direction':'CN_TO_JP'}
    target=tmp_path/'workspace/runs/selected/segments.json';target.parent.mkdir(parents=True)
    target.write_text(json.dumps({**binding,'chapters':[
        {'chapter_id':'ch-002','segments':[{'segment_id':'s1','source_text':'TOKEN','draft_text':'旧称'}]}]}))
    path,sha,binding,_,_=policy_fixture(tmp_path,direction='CN_TO_JP',targets=[
        {'path':str(target.relative_to(tmp_path)),'sha256':hashlib.sha256(target.read_bytes()).hexdigest()}])
    before=target.read_bytes();monkeypatch.setattr(module,'REPO_ROOT',tmp_path)
    monkeypatch.setattr(sys,'argv',['preview','--dry-run','--segments-file',str(target),'--work-rules',str(path),
        '--work-rules-sha256',sha,'--work-id',binding['work_id'],'--source-revision',binding['source_revision'],
        '--language-direction','CN_TO_JP'])
    assert module.main()==0
    result=json.loads(capsys.readouterr().out)
    assert result['chapter_range']==[2,4] and result['changed_segments']==1
    assert result['work_rules_mode']=='review_only' and target.read_bytes()==before
    assert not (tmp_path/'output_refined').exists()


def test_wrapper_forwards_selected_binding_and_reports_failed_child(tmp_path,monkeypatch,capsys):
    import hashlib
    from types import SimpleNamespace
    import run_consistency_fix_all as module
    target=tmp_path/'workspace/runs/selected/segments.json';target.parent.mkdir(parents=True);target.write_text('{}')
    path,sha,binding,_,_=policy_fixture(tmp_path,targets=[
        {'path':str(target.relative_to(tmp_path)),'sha256':hashlib.sha256(target.read_bytes()).hexdigest()}])
    monkeypatch.setattr(module,'REPO_ROOT',tmp_path)
    def foreign():raise AssertionError('ambient discovery entered despite selected manifest')
    monkeypatch.setattr(module,'discover_canonical_files',foreign);calls=[]
    def failed(command,**kwargs):calls.append(command);return SimpleNamespace(returncode=2,stderr='unverified target binding')
    monkeypatch.setattr(module.subprocess,'run',failed)
    monkeypatch.setattr(sys,'argv',['preview-all','--dry-run','--work-rules',str(path),'--work-rules-sha256',sha,
        '--work-id',binding['work_id'],'--source-revision',binding['source_revision'],'--language-direction','JP_TO_CN'])
    assert module.main()==2
    result=json.loads(capsys.readouterr().out);assert result['failed_files']==1 and result['status']=='failed'
    command=calls[0];assert command[command.index('--chapters')+1:command.index('--chapters')+3]==['2','4']
    assert command[command.index('--work-rules-sha256')+1]==sha


def test_general_omission_hint_has_no_work_literal_exemption():
    from quality_review.checkers import _likely_omission
    assert _likely_omission(10,1,'JP_TO_CN',source_text='ありがとうございます')


def test_refinement_comparison_is_only_explicit_historical_review(tmp_path):
    from quality_review.checkers import check_refinement_diff,run_all_checkers
    _,_,binding,_,policy=policy_fixture(tmp_path,rules={'legacy_refinement_targets':['NEW_TERM']})
    doc={'project_id':binding['work_id'],**binding,'expected_segment_ids':['s1'],'paragraphs':[{'segments':[
        {'segment_id':'s1','source_text':'TOKEN','target_text':'OLD_TERM','draft_text':'OLD_TERM','refined_text':'NEW_TERM'}]}]}
    assert check_refinement_diff(doc)==[]
    assert len(check_refinement_diff(doc,policy))==1
    assert all(issue.issue_type!='OVER_REFINEMENT' for issue in run_all_checkers(doc,{'terms':[]}))


def test_selected_wrapper_never_discovers_unselected_run_bodies(tmp_path,monkeypatch):
    import run_consistency_fix_all as module
    path,sha,binding,_,_=policy_fixture(tmp_path)
    monkeypatch.setattr(module,'REPO_ROOT',tmp_path)
    def foreign():raise AssertionError('unselected run discovery/body read')
    monkeypatch.setattr(module,'discover_canonical_files',foreign)
    monkeypatch.setattr(sys,'argv',['preview','--dry-run','--work-rules',str(path),'--work-rules-sha256',sha,
        '--work-id',binding['work_id'],'--source-revision',binding['source_revision'],'--language-direction','JP_TO_CN'])
    with pytest.raises((ValueError,SystemExit)):module.main()


def test_term_report_requires_selection_before_ambient_assets(tmp_path,monkeypatch):
    import build_term_variant_report as module
    def foreign(*_):raise AssertionError('ambient foreign asset registry read')
    monkeypatch.setattr(module,'build_registry',foreign)
    monkeypatch.setattr(module,'reroute_legacy_review_path',lambda p:p)
    monkeypatch.setattr(sys,'argv',['terms','--chapters','2','4','--output',str(tmp_path/'report.json')])
    with pytest.raises((ValueError,SystemExit)):module.main()


def test_single_preview_constrains_target_before_body_read(tmp_path,monkeypatch):
    import fix_terminology_consistency as module
    path,sha,binding,_,_=policy_fixture(tmp_path);foreign=tmp_path/'foreign.json'
    original=Path.read_text
    def read(p,*args,**kwargs):
        if p==foreign:raise AssertionError('foreign target body read')
        return original(p,*args,**kwargs)
    monkeypatch.setattr(Path,'read_text',read);monkeypatch.setattr(module,'REPO_ROOT',tmp_path)
    monkeypatch.setattr(sys,'argv',['preview','--dry-run','--segments-file',str(foreign),'--work-rules',str(path),
        '--work-rules-sha256',sha,'--work-id',binding['work_id'],'--source-revision',binding['source_revision'],
        '--language-direction','JP_TO_CN'])
    with pytest.raises((ValueError,SystemExit)):module.main()


def test_selected_target_version_and_membership_before_open(tmp_path,monkeypatch):
    import hashlib
    import consistency.work_rules as module
    binding={'work_id':'work-a','source_revision':'1'*64,'language_direction':'JP_TO_CN'}
    target=tmp_path/'workspace/runs/selected/segments.json';target.parent.mkdir(parents=True)
    target.write_text(json.dumps(binding))
    _,_,_,_,policy=policy_fixture(tmp_path,targets=[{'path':str(target.relative_to(tmp_path)),
        'sha256':hashlib.sha256(target.read_bytes()).hexdigest()}])
    assert module.read_target_document(tmp_path,policy,target)==binding
    target.write_text(json.dumps({**binding,'work_id':'changed'}))
    with pytest.raises(ValueError,match='version mismatch'):module.read_target_document(tmp_path,policy,target)
    foreign=tmp_path/'workspace/runs/foreign/segments.json';foreign.parent.mkdir();foreign.write_text('{}')
    def forbidden(*_,**__):raise AssertionError('unselected target opened')
    monkeypatch.setattr(module.os,'open',forbidden)
    with pytest.raises(ValueError,match='not in selected'):module.read_target_document(tmp_path,policy,foreign)


def test_selected_context_explains_but_never_hides_variant(tmp_path,monkeypatch):
    import hashlib
    import build_term_variant_report as module
    binding={'work_id':'work-a','source_revision':'1'*64,'language_direction':'JP_TO_CN'}
    target=tmp_path/'workspace/runs/selected/segments.json';target.parent.mkdir(parents=True)
    target.write_text(json.dumps({**binding,'chapters':[{'chapter_id':'ch-002','segments':[
        {'segment_id':'s1','source_text':'TOKEN context','draft_text':'旧称'}]}]}))
    path,sha,_,_,_=policy_fixture(tmp_path,rules={'chapter_range':[2,4],
        'term_registry':[{'term_id':'t1','source':'TOKEN','canonical':'新称','aliases':['旧称'],'kind':'term'}],
        'contextual_variants':[{'source':'TOKEN','source_contains':'context','target_contains_any':['旧称']}]},
        targets=[{'path':str(target.relative_to(tmp_path)),'sha256':hashlib.sha256(target.read_bytes()).hexdigest()}])
    monkeypatch.setattr(module,'REPO_ROOT',tmp_path)
    monkeypatch.setattr(module,'reroute_legacy_review_path',lambda p:p)
    output=tmp_path/'report.json'
    monkeypatch.setattr(sys,'argv',['terms','--output',str(output),'--work-rules',str(path),
        '--work-rules-sha256',sha,'--work-id','work-a','--source-revision','1'*64,'--language-direction','JP_TO_CN'])
    assert module.main()==0
    report=json.loads(output.read_text())
    assert report['terms_with_variance']==1 and report['issues'][0]['term_id']=='t1'
    assert report['contextual_explanations']==[{'term_id':'t1','segment_id':'s1','policy_sha256':sha}]
