"""Synthetic observations exercise cross-work admission without private data."""
from pathlib import Path
import json
import hashlib
import sys
import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'src')]


def segment(source='TOKEN',draft='旧称'):
    return {'s1':{'segment_id':'s1','source_text':source,'draft_text':draft,'_chapter_id':'ch-002'}}


def test_english_observation_does_not_inherit_ambient_allowlist(monkeypatch):
    import audit_actual_chapter_content as module
    monkeypatch.setattr(module,'ENGLISH_RESIDUAL_TERM_ALLOWLIST',{'foreign'},raising=False)
    assert len(module.target_english_residuals(segment(draft='FOREIGN')))==1


def test_context_hint_never_silently_hides_observation(monkeypatch):
    import audit_actual_chapter_content as module
    monkeypatch.setattr(module,'is_allowed_contextual_hint',lambda *args:True,raising=False)
    hints=[{'kind':'term','source':'TOKEN','target':'新称','known_variants':['旧称']}]
    assert len(module.registry_hint_observations(segment(),hints))==1


def test_source_literal_has_no_ambient_kana_exemption(monkeypatch):
    import audit_actual_chapter_content as module
    monkeypatch.setattr(module,'PROTECTED_LITERAL_SOURCE_RESIDUALS',('オペーク',),raising=False)
    assert len(module.target_kana_residuals(segment('オペーク','オペーク')))==1


def test_audit_does_not_prefer_historical_refinement():
    import audit_actual_chapter_content as module
    assert module.cn_text({'draft_text':'selected candidate','refined_text':'historical'})=='selected candidate'


def test_unselected_cli_denies_before_run_or_asset_read(tmp_path,monkeypatch):
    import audit_actual_chapter_content as module
    def forbidden(*args,**kwargs):raise AssertionError('ambient run or asset read')
    monkeypatch.setattr(module,'load_segments',forbidden)
    monkeypatch.setattr(sys,'argv',['audit','--chapters','2','4','--output',str(tmp_path/'report.json')])
    with pytest.raises(SystemExit) as error:module.main()
    assert error.value.code==2


def test_load_segments_requires_selection_before_discovery(monkeypatch):
    import audit_actual_chapter_content as module
    def forbidden(*args):raise AssertionError('unselected run discovery')
    monkeypatch.setattr(module,'discover_canonical_files',forbidden,raising=False)
    with pytest.raises(ValueError):module.load_segments(2,4)


def test_previous_issues_require_binding_before_any_file_read(tmp_path,monkeypatch):
    import audit_actual_chapter_content as module
    foreign=tmp_path/'foreign.json';foreign.write_text('[]')
    read=Path.read_text
    def forbidden(p,*args,**kwargs):
        if p==foreign:raise AssertionError('unbound previous evidence read')
        return read(p,*args,**kwargs)
    monkeypatch.setattr(Path,'read_text',forbidden)
    with pytest.raises(ValueError):module.revalidate_previous_issues(segment(),foreign)


def selected(root,*,direction='JP_TO_CN',rules=None,document=None,previous=None):
    from types import SimpleNamespace
    from consistency.work_rules import load_work_rules
    binding={'work_id':'synthetic-a','source_revision':'1'*64,'language_direction':direction}
    target=root/'workspace/runs/selected/segments.json';target.parent.mkdir(parents=True)
    doc={**binding,'chapters':[{'chapter_id':'ch-002','segments':[
        {'segment_id':'s1','source_text':'TOKEN context オペーク 「CHAR I_MARK」',
         'draft_text':'旧称 FOREIGN オペーク "...','refined_text':'historical'}]}]}
    if document is not None:doc.update(document)
    target.write_text(json.dumps(doc,ensure_ascii=False))
    targets=[{'path':str(target.relative_to(root)),'sha256':hashlib.sha256(target.read_bytes()).hexdigest()}]
    rules={'chapter_range':[2,4],**(rules or {})};previous_path=None
    if previous is not None:
        previous_path=root/'workspace/review/previous.json';previous_path.parent.mkdir(parents=True)
        value={'schema':'work-review-input/1',**binding,'target_files':targets,'issues':[],**previous}
        previous_path.write_text(json.dumps(value))
        rules={**rules,'audit':{**rules.get('audit',{}),'previous_issues':[
            {'path':str(previous_path.relative_to(root)),'sha256':hashlib.sha256(previous_path.read_bytes()).hexdigest()}]}}
    folder=root/'configs';folder.mkdir();path=folder/'selected.json'
    value={'schema':'work-rules/1','activation':'review_only',**binding,'rules':rules,'target_files':targets}
    path.write_text(json.dumps(value));sha=hashlib.sha256(path.read_bytes()).hexdigest()
    return SimpleNamespace(root=root,target=target,binding=binding,path=path,sha=sha,value=value,
        previous=previous_path,policy=load_work_rules(root,path,sha,document=binding))


def argv(value,output,previous=False):
    command=['audit','--output',str(output),'--work-rules',str(value.path),'--work-rules-sha256',value.sha,
        '--work-id',value.binding['work_id'],'--source-revision',value.binding['source_revision'],
        '--language-direction',value.binding['language_direction']]
    return command+(['--previous-issues',str(value.previous)] if previous else [])


@pytest.mark.parametrize('direction',['JP_TO_CN','CN_TO_JP'])
def test_selected_audit_preserves_observations_and_never_claims_acceptance(tmp_path,monkeypatch,direction):
    import audit_actual_chapter_content as module
    value=selected(tmp_path,direction=direction,rules={
        'term_registry':[{'term_id':'t1','source':'TOKEN','canonical':'新称','aliases':['旧称'],'kind':'term'}],
        'contextual_variants':[{'source':'TOKEN','source_contains':'context','target_contains_any':['旧称']}],
        'audit':{'english_terms':['FOREIGN'],'protected_literals':['オペーク'],'punctuation_rules':['synthetic hint'],
            'characters':[{'character_id':'c1','source_names':['CHAR'],'target_names':['角色'],
                'voice_markers':[{'source':'I_MARK','targets':['translatedmark']}]}]}},
        previous={'issues':[{'segment_id':'s1','description':'surface only','suggested_fix':'旧称 FOREIGN オペーク "...','status':'human_approved_final'}]})
    before=value.target.read_bytes();output=tmp_path/'workspace/tooling/actual_chapter_audits/report.json'
    monkeypatch.setattr(module,'REPO_ROOT',tmp_path)
    def forbidden(*args,**kwargs):raise AssertionError('ambient data loader entered')
    monkeypatch.setattr(module,'_read_yaml',forbidden,raising=False)
    monkeypatch.setattr(module,'discover_canonical_files',forbidden,raising=False)
    monkeypatch.setattr(sys,'argv',argv(value,output,True))
    assert module.main()==0 and value.target.read_bytes()==before
    report=json.loads(output.read_text());assert report['mode']=='review_only' and report['acceptance']=='not_evaluated'
    assert report['target_field']=='draft_text' and report['segments_total']==1
    english=report['target_english_residuals'];assert english['count']==1
    assert english['items'][0]['policy_explained_tokens']==['FOREIGN']
    assert english['items'][0]['source_revision']==value.binding['source_revision']
    registry=report['registry_hint_observations'];assert registry['count']==1
    assert registry['items'][0]['context_explanations'][0]['segment_id']=='s1'
    assert report['character_voice_style_residuals']['count']==1
    kana=report['target_kana_residuals'];assert kana['direction_applicable']==(direction=='JP_TO_CN')
    assert kana['count']==(1 if direction=='JP_TO_CN' else 0)
    if direction=='JP_TO_CN':assert kana['items'][0]['selected_literal_explanation'] is True
    prior=report['previous_issue_revalidation'];assert prior['acceptance']=='not_evaluated'
    assert prior['issues'][0]['current_status']=='surface_equals_previous_suggestion'
    assert not any('resolved' in key for key in prior['summary'])


@pytest.mark.parametrize('kind',['duplicate','empty_scope','empty_source','foreign_work'])
def test_invalid_selected_scope_never_produces_a_successful_audit(tmp_path,monkeypatch,kind):
    import audit_actual_chapter_content as module
    doc={'chapters':[{'chapter_id':'ch-002','segments':[{'segment_id':'s1','source_text':'TOKEN','draft_text':'target'}]}]}
    if kind=='duplicate':doc['chapters'][0]['segments']*=2
    if kind=='empty_scope':doc['chapters'][0]['chapter_id']='ch-009'
    if kind=='empty_source':doc['chapters'][0]['segments'][0]['source_text']=''
    if kind=='foreign_work':doc['work_id']='synthetic-foreign'
    value=selected(tmp_path,document=doc);monkeypatch.setattr(module,'REPO_ROOT',tmp_path)
    with pytest.raises(ValueError):module.load_segments(2,4,value.policy)


def test_changed_target_hash_and_existing_output_are_preserved(tmp_path,monkeypatch):
    import audit_actual_chapter_content as module
    value=selected(tmp_path);value.target.write_text(value.target.read_text()+' ')
    modified=value.target.read_bytes();output=tmp_path/'workspace/tooling/actual_chapter_audits/report.json'
    monkeypatch.setattr(module,'REPO_ROOT',tmp_path);monkeypatch.setattr(sys,'argv',argv(value,output))
    with pytest.raises(SystemExit):module.main()
    assert not output.exists() and value.target.read_bytes()==modified
    output.parent.mkdir(parents=True);output.write_text('manual prior result')
    with pytest.raises(SystemExit):module.main()
    assert output.read_text()=='manual prior result'


def test_unselected_previous_report_denied_before_open(tmp_path,monkeypatch):
    import consistency.work_rules as module
    value=selected(tmp_path);foreign=tmp_path/'workspace/review/foreign.json'
    foreign.parent.mkdir();foreign.write_text('[]')
    def forbidden(*args,**kwargs):raise AssertionError('unselected previous body opened')
    monkeypatch.setattr(module.os,'open',forbidden)
    with pytest.raises(ValueError):module.read_previous_review(tmp_path,value.policy,foreign)


@pytest.mark.parametrize('change',['work','source','direction','legacy','target_scope','hash'])
def test_previous_report_foreign_identity_or_version_cannot_be_used(tmp_path,monkeypatch,change):
    import audit_actual_chapter_content as module
    changes={'work':{'work_id':'other'},'source':{'source_revision':'2'*64},'direction':{'language_direction':'CN_TO_JP'},
        'legacy':{'schema':'legacy/issues'},'target_scope':{'target_files':[{'path':'workspace/runs/foreign/segments.json','sha256':'3'*64}]}}
    value=selected(tmp_path,previous=changes.get(change,{}));monkeypatch.setattr(module,'REPO_ROOT',tmp_path)
    if change=='hash':value.previous.write_text(value.previous.read_text()+' ')
    segments=module.load_segments(2,4,value.policy)
    with pytest.raises(ValueError):module.revalidate_previous_issues(segments,value.previous,value.policy)


def test_fresh_work_does_not_reuse_previous_policy_hints(tmp_path):
    import audit_actual_chapter_content as module
    value=selected(tmp_path,rules={'audit':{'english_terms':['FOREIGN']}})
    rows=module.target_english_residuals(segment(draft='FOREIGN'),value.policy)
    assert rows[0]['policy_explained_tokens']==['FOREIGN']
    assert module.target_english_residuals(segment(draft='FOREIGN'))[0]['policy_explained_tokens']==[]


def test_source_and_target_voice_markers_are_explicitly_mapped(tmp_path,monkeypatch):
    import audit_actual_chapter_content as module
    value=selected(tmp_path,rules={'audit':{'characters':[{'character_id':'c1','source_names':['CHAR'],
        'target_names':['角色'],'voice_markers':[{'source':'I_MARK','targets':['合语境自称']}]}]}})
    monkeypatch.setattr(module,'REPO_ROOT',tmp_path)
    segments=module.load_segments(2,4,value.policy)
    assert len(module.detect_voice_style_drift(segments,value.policy))==1
    segments['s1']['draft_text']='角色说：「合语境自称」'
    assert module.detect_voice_style_drift(segments,value.policy)==[]


def test_same_source_multiple_selected_senses_are_not_merged(tmp_path,monkeypatch):
    import audit_actual_chapter_content as module
    value=selected(tmp_path,rules={'term_registry':[
        {'term_id':'sense-a','source':'TOKEN','canonical':'甲义','aliases':[],'kind':'term'},
        {'term_id':'sense-b','source':'TOKEN','canonical':'乙义','aliases':[],'kind':'term'}]})
    monkeypatch.setattr(module,'REPO_ROOT',tmp_path)
    rows=module.registry_hint_observations(module.load_segments(2,4,value.policy),module.build_registry_hints(value.policy),value.policy)
    assert {row['term_id'] for row in rows}=={'sense-a','sense-b'}
    assert {row['hint_target'] for row in rows}=={'甲义','乙义'}


def test_missing_selected_target_field_is_visible_in_report(tmp_path,monkeypatch):
    import audit_actual_chapter_content as module
    value=selected(tmp_path,document={'chapters':[{'chapter_id':'ch-002','segments':[
        {'segment_id':'s1','source_text':'source with no target','refined_text':'old historical field'}]}]})
    output=tmp_path/'workspace/tooling/actual_chapter_audits/report.json'
    monkeypatch.setattr(module,'REPO_ROOT',tmp_path);monkeypatch.setattr(sys,'argv',argv(value,output))
    assert module.main()==0
    report=json.loads(output.read_text())
    assert report['target_missing_content']['count']==1 and report['acceptance']=='not_evaluated'
