"""Source-version evidence and invalidation on synthetic copies only."""
from pathlib import Path
import copy
import hashlib
import json
import os
import sys

import pytest


def test_recovery_revision_is_an_explicit_validated_review_dependency():
    from translation.source_versions import review_dependencies
    assert review_dependencies({'draft_recovery_revision':'a'*64},'synthetic')=={'draft_recovery_revision':'a'*64}
    assert 'draft_recovery_revision' not in review_dependencies({},'synthetic')
    for value in ['../snapshot','X'*64,None,True]:
        with pytest.raises(ValueError):review_dependencies({'draft_recovery_revision':value},'synthetic')

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))


def parse(tmp_path, text):
    from translation.chapter_parser import parse_chapter_file
    path=tmp_path/'001-synthetic.md'
    return parse_chapter_file(path, source_bytes=text.encode())


def test_parser_binds_exact_document_and_unique_logical_id_survives_insert(tmp_path):
    old=parse(tmp_path,'# title\n\n甲。\n\n乙。\n')
    new=parse(tmp_path,'# title\n\n前置。\n\n甲。\n\n乙。\n')
    assert old.source_revision != new.source_revision
    assert old.segments[0].source_binding['logical_id'] == new.segments[1].source_binding['logical_id']
    assert old.segments[0].segment_id != new.segments[1].segment_id
    assert old.segments[0].source_binding['binding_sha256'] != new.segments[1].source_binding['binding_sha256']


def test_source_spans_reconstruct_crlf_unicode_and_excluded_headings(tmp_path):
    from translation.source_versions import validate_source_binding
    text='# title\r\n\r\n α行\r\nβ行 \r\n\r\n# hidden\r\n\r\n'+'\r\n\r\n'.join(f'段{i}。' for i in range(10))
    chapter=parse(tmp_path,text)
    assert chapter.source_revision == hashlib.sha256(text.encode()).hexdigest()
    assert all(validate_source_binding(s.source_binding,s.source_text,document_text=text) for s in chapter.segments)
    assert chapter.segments[0].source_text == 'α行\nβ行'
    assert '# hidden' not in ''.join(text[a:b] for s in chapter.segments for a,b in s.source_binding['source_spans'])


def test_header_only_change_invalidates_catalog_and_missing_binding_cannot_downgrade(tmp_path):
    from translation.context_policy import SourceContextCatalog
    from translation.exporter import export_segments_doc
    old=parse(tmp_path,'# old\n\n本文。');new=parse(tmp_path,'# new\n\n本文。')
    assert old.segments[0].source_text==new.segments[0].source_text
    assert SourceContextCatalog([old]).sha256!=SourceContextCatalog([new]).sha256
    new.segments[0].source_binding=None
    with pytest.raises(ValueError): SourceContextCatalog([new])
    path=tmp_path/'out.json';path.write_text('prior candidate')
    with pytest.raises(ValueError): export_segments_doc([new],path)
    assert path.read_text()=='prior candidate'


@pytest.mark.parametrize('replacement',['# title\n\n前。\n\n甲。\n\n乙。\n',
    '# title\n\n甲。乙。\n','# title\n\n甲\n\n。\n\n乙。\n','# title\n\n丙。\n\n乙。\n'])
def test_source_edit_invalidates_review_even_when_current_text_stays_same(tmp_path,replacement):
    from workbench.review_state import approval_identity
    old=parse(tmp_path,'# title\n\n甲。\n\n乙。\n\n末。');new=parse(tmp_path,replacement+'\n\n末。')
    def identity(ch):
        s=next(s for s in ch.segments if s.source_text=='末。')
        return approval_identity(project_id='p',language_direction='JP_TO_CN',
            segment={'id':'stable-current','source':s.source_text,'draft':'候选。','source_binding':s.source_binding})
    assert identity(old)!=identity(new)


def test_many_to_many_migration_is_proposal_only_and_duplicates_stay_uncertain(tmp_path):
    from translation.source_versions import propose_source_migration
    old=parse(tmp_path,'# title\n\n甲。\n\n乙。\n');merged=parse(tmp_path,'# title\n\n甲。乙。\n')
    forward=propose_source_migration(old,merged);reverse=propose_source_migration(merged,old)
    assert any(len(r['old_ids'])==2 and len(r['new_ids'])==1 for r in forward['mappings'])
    assert any(len(r['old_ids'])==1 and len(r['new_ids'])==2 for r in reverse['mappings'])
    assert forward['apply_allowed'] is reverse['apply_allowed'] is False
    duplicate=parse(tmp_path,'# title\n\n同じ。\n\n同じ。\n')
    uncertain=propose_source_migration(duplicate,duplicate)
    assert uncertain['uncertain_old_ids'] and not uncertain['mappings']
    assert all(s.source_binding['mapping_status']=='duplicate_source_requires_review' for s in duplicate.segments)


def test_legacy_segments_remain_readable_without_fabricated_version(tmp_path):
    from translation.chapter_parser import Segment,ParsedChapter
    from translation.source_versions import propose_source_migration
    legacy=ParsedChapter('ch-001','','legacy',[Segment('legacy-1','甲。','旧稿。','approved')])
    proposal=propose_source_migration(legacy,parse(tmp_path,'# title\n\n甲。'))
    assert proposal['uncertain_old_ids']==['legacy-1'] and proposal['apply_allowed'] is False
    assert legacy.segments[0].draft_text=='旧稿。' and legacy.segments[0].status=='approved'


@pytest.mark.parametrize('change',[{'source_revision':'0'*64},{'source_spans':[[0,9999]]},
    {'logical_id':'foreign'},{'source_sha256':'0'*64}])
def test_corrupt_source_binding_cannot_mint_review_identity(tmp_path,change):
    from workbench.review_state import approval_identity
    s=parse(tmp_path,'# t\n\n甲。').segments[0];binding={**s.source_binding,**change}
    with pytest.raises(ValueError):
        approval_identity(project_id='p',language_direction='JP_TO_CN',segment={'id':s.segment_id,'source':s.source_text,'draft':'译文。','source_binding':binding})


def test_export_keeps_versions_and_cn_to_jp_interface(tmp_path):
    from translation.exporter import export_segments_doc
    from translation.prompt_builder import build_batch_messages
    ch=parse(tmp_path,'# t\n\n中文原文。');path=tmp_path/'out.json'
    export_segments_doc([ch],path,language_direction='CN_TO_JP')
    doc=json.loads(path.read_text());row=doc['chapters'][0]['segments'][0]
    assert doc['language_direction']=='CN_TO_JP' and row['source_binding']==ch.segments[0].source_binding
    assert doc['chapters'][0]['source_revision']==ch.source_revision
    text=build_batch_messages(ch.segments,chapter_label='synthetic')[1].content
    assert json.loads(text[text.index('{'):])['segments'][0]['source_binding']==row['source_binding']


def test_equal_size_same_timestamp_edit_rebuilds_segment_cache_and_content_hash(tmp_path):
    from consistency.segment_index import build_segment_index
    root=tmp_path/'workspace/runs/run_synthetic_draft_stage_b_50ch';root.mkdir(parents=True)
    doc={'chapters':[{'chapter_id':'ch-001','segments':[{'segment_id':'ch-001-seg-001','source_text':'甲。','draft_text':'译甲','status':'machine_translated'}]}]}
    path=root/'segments.json';path.write_text(json.dumps(doc,ensure_ascii=False))
    (root/'run_progress.json').write_text(json.dumps({'total_segments':1,'completed_segments':1}))
    (root/'run_metadata.json').write_text(json.dumps({'phase':'draft','run_id':root.name}))
    first=build_segment_index(tmp_path);stamp=path.stat();old_size=stamp.st_size
    doc['chapters'][0]['segments'][0]['source_text']='乙。';path.write_text(json.dumps(doc,ensure_ascii=False));os.utime(path,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
    assert path.stat().st_size==old_size
    second=build_segment_index(tmp_path,previous_index=first)
    assert second['stats']['files_scanned']==1 and second['stats']['files_reused']==0
    assert first['chapters']['ch-001']['content_hash']!=second['chapters']['ch-001']['content_hash']
    third=build_segment_index(tmp_path,previous_index=second)
    assert third['stats']['files_scanned']==0 and third['stats']['files_reused']==1


def test_pinned_source_resume_makes_no_new_calls_and_preserves_on_equal_length_edit(tmp_path,monkeypatch):
    from translation.draft_runner import run_draft_stage_b
    from providers.fake_provider import FakeProvider
    monkeypatch.setenv('CONTROLLED_RUN_ENABLED','true');monkeypatch.setenv('REAL_API_TESTS_ENABLED','false')
    source=tmp_path/'input_jp';source.mkdir();path=source/'001-synthetic.md';path.write_text('# t\n\n甲。\n\n乙。')
    calls=[]
    class Observer(FakeProvider):
        def generate(self,messages,options=None):
            calls.append(messages);return super().generate(messages,options)
    def run():return run_draft_stage_b(repo_root=tmp_path,input_dir=source,limit_chapters=1,run_id='versions',provider_factory=lambda _:Observer())
    _,root=run();before=(root/'segments.json').read_bytes();count=len(calls);run();assert len(calls)==count
    path.write_text('# t\n\n丙。\n\n乙。')
    with pytest.raises(RuntimeError,match='identity changed'):run()
    assert (root/'segments.json').read_bytes()==before and len(calls)==count


def test_flat_manifest_source_change_invalidates_other_segment_review_without_mutating_legacy(tmp_path):
    from workbench.project_registry import create_project_manifest,update_project_segments,patch_project_review_state_cas,get_project_manifest
    from workbench.review_state import approval_identity,DecisionActor,review_decision_summary,get_project_review_state
    rows=[{'id':'a','source':'甲。','draft':'甲译。'},{'id':'b','source':'乙。','draft':'乙译。'}]
    original=copy.deepcopy(rows)
    create_project_manifest(tmp_path,project_id='scope',name='scope',language_direction='JP_TO_CN',segments=rows)
    old=approval_identity(project_id='scope',language_direction='JP_TO_CN',segment=rows[1])
    patch_project_review_state_cas(tmp_path,'scope',decision_actor=DecisionActor('agent','synthetic'),segments={'b':{'status':'approved','expected_identity':old}})
    before_review=(tmp_path/'workspace/review_state.json').read_bytes()
    changed=[{'id':'a','source':'丙。','draft':'甲译。'},rows[1]]
    manifest=update_project_segments(tmp_path,'scope',changed,source_segments=changed)
    current=manifest.segments[1]
    new=approval_identity(project_id='scope',language_direction='JP_TO_CN',segment=current)
    entry=get_project_review_state(tmp_path,'scope')['segments']['b']
    assert old!=new and not review_decision_summary(entry,new,segment=current)['candidate_accepted']
    assert rows==original and (tmp_path/'workspace/review_state.json').read_bytes()==before_review
    # Dropping all per-row metadata or returning to old content cannot resurrect a v1 decision.
    restored=update_project_segments(tmp_path,'scope',rows,source_segments=rows)
    identity=approval_identity(project_id='scope',language_direction='JP_TO_CN',segment=restored.segments[1])
    assert identity!=old
    stable=update_project_segments(tmp_path,'scope',rows,source_segments=rows)
    assert approval_identity(project_id='scope',language_direction='JP_TO_CN',segment=stable.segments[1])==identity


@pytest.mark.parametrize('kind',['entity','usage'])
def test_index_dependencies_include_equal_length_text_and_glossary_versions(tmp_path,kind):
    from glossary import GlossaryEntry
    from consistency.entity_index import build_entity_index
    from glossary.usage_index import build_usage_index
    builder=build_entity_index if kind=='entity' else build_usage_index
    path=tmp_path/'segments.json'
    doc={'chapters':[{'chapter_id':'ch-001','segments':[{'segment_id':'ch-001-seg-001','source_text':'甲国へ。','draft_text':'去甲国。'}]}]}
    path.write_text(json.dumps(doc,ensure_ascii=False));terms=[GlossaryEntry(source_term='甲国',target_term='甲国',category='place_name')]
    first=builder(terms,[path]);stamp=path.stat()
    doc['chapters'][0]['segments'][0]['draft_text']='去乙国。';path.write_text(json.dumps(doc,ensure_ascii=False));os.utime(path,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
    second=builder(terms,[path],previous_index=first)
    assert second['stats']['files_scanned']==1 and second['stats']['files_reused']==0
    changed=[GlossaryEntry(source_term='甲国',target_term='乙国',category='place_name')]
    third=builder(changed,[path],previous_index=second)
    assert third['stats']['files_scanned']==1 and third['dependency_sha256']!=second['dependency_sha256']
    fourth=builder(changed,[path],previous_index=third)
    assert fourth['stats']['files_scanned']==0 and fourth['stats']['files_reused']==1


def _r42_dependency_manifest():
    from translation.source_versions import text_sha
    return {'project_id':'dependency-proof','name':'Synthetic','language_direction':'JP_TO_CN',
        'dependency_versions':{'glossary:a':text_sha('term v1'),'knowledge:k':text_sha('claim active'),
                               'tm:pair':text_sha('pair v1'),'psh:bundle':text_sha('pinned style v1')},
        'segments':[{'id':'a','source':'Alpha source.','draft':'Alpha target.','status':'machine_translated',
                     'dependency_keys':['glossary:a','knowledge:k','tm:pair','psh:bundle']},
                    {'id':'b','source':'Beta source.','draft':'Beta target.','status':'machine_translated',
                     'dependency_keys':[]}]}


@pytest.mark.parametrize('key',['glossary:a','knowledge:k','tm:pair','psh:bundle'])
def test_r42_dependency_change_invalidates_only_bound_review_and_tm(tmp_path,key):
    from workbench.project_registry import save_project_manifest,parse_project_manifest,patch_project_review_state_cas
    from workbench.review_state import approval_identity,DecisionActor
    from assets.translation_memory import build_translation_memory_assets,render_translation_asset_context
    from translation.source_versions import text_sha
    data=_r42_dependency_manifest();save_project_manifest(tmp_path,data);parsed=parse_project_manifest(data)
    identities={s['id']:approval_identity(project_id=parsed.project_id,language_direction=parsed.language_direction,segment=s)
                for s in parsed.segments}
    patch_project_review_state_cas(tmp_path,parsed.project_id,decision_actor=DecisionActor('agent','synthetic'),
        segments={sid:{'status':'approved','expected_identity':identity} for sid,identity in identities.items()})
    doc=build_translation_memory_assets(repo_root=tmp_path,project_id=parsed.project_id);path=Path(doc['asset_path'])
    before=path.read_bytes();data['dependency_versions'][key]=text_sha('new or withdrawn version')
    save_project_manifest(tmp_path,data);changed=parse_project_manifest(data)
    new={s['id']:approval_identity(project_id=changed.project_id,language_direction=changed.language_direction,segment=s)
         for s in changed.segments}
    assert identities['a']!=new['a'] and identities['b']==new['b']
    context=render_translation_asset_context(path)
    assert 'Alpha target.' not in context and 'Beta target.' in context and path.read_bytes()==before
    # A stale UI request cannot approve the changed dependency snapshot.
    from workbench.project_registry import ApprovalIdentityConflictError
    with pytest.raises(ApprovalIdentityConflictError):
        patch_project_review_state_cas(tmp_path,parsed.project_id,decision_actor=DecisionActor('agent','synthetic'),
            segments={'a':{'status':'approved','expected_identity':identities['a']}})


@pytest.mark.parametrize('versions',[None,[],{'psh:bundle':'bad'}, {'bad path':'0'*64},{'psh:bundle':None}])
def test_r42_malformed_pinned_dependency_versions_refused(versions):
    from workbench.review_state import approval_identity
    with pytest.raises(ValueError):
        approval_identity(project_id='p',language_direction='JP_TO_CN',segment={
            'id':'a','source':'Source','draft':'Target','dependency_versions':versions})


@pytest.mark.parametrize('mutation',['missing','duplicate','unknown','bad_catalog'])
def test_r42_selected_dependencies_cannot_silently_fall_back(mutation):
    from workbench.project_registry import parse_project_manifest
    data=_r42_dependency_manifest()
    if mutation=='missing':data.pop('dependency_versions')
    elif mutation=='duplicate':data['segments'][0]['dependency_keys']=['tm:pair','tm:pair']
    elif mutation=='unknown':data['segments'][0]['dependency_keys']=['unknown:key']
    else:data['dependency_versions']['psh:bundle']='bad'
    with pytest.raises(ValueError):parse_project_manifest(data)


def test_r42_canonical_target_selection_keeps_dependencies():
    from translation.canonical_export import selected_segment
    from workbench.review_state import approval_identity
    from translation.source_versions import text_sha
    row={'id':'a','source':'Source','draft':'Target','dependency_versions':{'psh:bundle':text_sha('v1')}}
    selected=selected_segment(row,'draft')
    def identity(s):return approval_identity(project_id='p',language_direction='JP_TO_CN',segment=s)
    assert identity(row)==identity(selected)
    selected['dependency_versions']={'psh:bundle':text_sha('v2')};assert identity(row)!=identity(selected)


def test_r42_entity_glossary_changes_rescan_only_relevant_files(tmp_path):
    from consistency.entity_index import build_entity_index
    from glossary.models import GlossaryEntry
    paths=[]
    for name,source,target in [('a','アルファ','阿尔法'),('b','ベータ','贝塔')]:
        folder=tmp_path/name;folder.mkdir();path=folder/'segments.json';paths.append(path)
        path.write_text(json.dumps({'chapters':[{'chapter_id':'ch-001','segments':[
            {'segment_id':name,'source_text':source,'draft_text':target}]}]},ensure_ascii=False))
    terms=[GlossaryEntry(source_term='アルファ',target_term='阿尔法',category='person_name'),
           GlossaryEntry(source_term='ベータ',target_term='贝塔',category='person_name')]
    first=build_entity_index(terms,paths);assert first['stats']['files_scanned']==2
    terms[0].target_term='阿爾法';second=build_entity_index(terms,paths,previous_index=first)
    assert second['stats']['files_scanned']==1 and second['stats']['files_reused']==1
    assert second['entities']['アルファ']['canonical_target']=='阿爾法'
    terms.append(GlossaryEntry(source_term='unrelated',target_term='unrelated',category='person_name'))
    third=build_entity_index(terms,paths,previous_index=second)
    assert third['stats']['files_scanned']==0 and third['stats']['files_reused']==2
    terms[0].deleted=True;fourth=build_entity_index(terms,paths,previous_index=third)
    assert fourth['stats']['files_scanned']==1 and fourth['stats']['files_reused']==1
    assert 'アルファ' not in fourth['entities']


def test_r42_new_entity_target_hit_invalidates_previous_no_hit(tmp_path):
    from consistency.entity_index import build_entity_index
    from glossary.models import GlossaryEntry
    folder=tmp_path/'r';folder.mkdir();path=folder/'segments.json'
    path.write_text(json.dumps({'chapters':[{'chapter_id':'ch-001','segments':[
        {'segment_id':'a','source_text':'quiet','draft_text':'新增译名'}]}]}))
    first=build_entity_index([], [path]);term=GlossaryEntry(source_term='新名',target_term='新增译名',category='person_name')
    second=build_entity_index([term],[path],previous_index=first)
    assert second['stats']['files_scanned']==1 and second['entities']['新名']['target_hits']==1


def test_r42_segment_dependency_change_changes_content_not_unrelated_file(tmp_path):
    from consistency.segment_index import build_segment_index
    from translation.source_versions import text_sha
    folder=tmp_path/'workspace/runs/run_synthetic_draft_stage_b_50ch';folder.mkdir(parents=True)
    data={'chapters':[{'chapter_id':'ch-001','segments':[{'segment_id':'ch-001-seg-001',
        'source_text':'Source','draft_text':'Target','status':'machine_translated',
        'dependency_versions':{'psh:bundle':text_sha('v1')}}]}]}
    path=folder/'segments.json';path.write_text(json.dumps(data))
    (folder/'run_metadata.json').write_text(json.dumps({'phase':'draft','run_id':folder.name}))
    (folder/'run_progress.json').write_text(json.dumps({'total_segments':1,'completed_segments':1}))
    first=build_segment_index(tmp_path);data['chapters'][0]['segments'][0]['dependency_versions']['psh:bundle']=text_sha('v2')
    path.write_text(json.dumps(data));second=build_segment_index(tmp_path,previous_index=first)
    assert first['chapters']['ch-001']['content_hash']!=second['chapters']['ch-001']['content_hash']
    assert second['stats']['files_scanned']==1
    third=build_segment_index(tmp_path,previous_index=second);assert third['stats']['files_reused']==1
    assert 'Source' not in json.dumps(second) and 'Target' not in json.dumps(second)


@pytest.mark.parametrize('during_commit',[False,True])
def test_r42_live_dependency_change_cannot_reexport_prior_accepted_snapshot(tmp_path,during_commit):
    from test_canonical_export import fixture,current_bytes
    from translation.canonical_export import export_accepted_revision,build_accepted_revision,selected_segment
    from workbench.project_registry import _resolve_manifest_dependencies
    from workbench.review_state import approval_identity,decision_provenance,DecisionActor
    from translation.source_versions import text_sha
    cfg=tmp_path/'workspace/configs';cfg.mkdir(parents=True);path=cfg/'glossary.yaml'
    path.write_text('entries:\n- source_term: Alpha\n  target_term: One\n')
    data,old_reviews=fixture(tmp_path);data['dependency_sources']={'glossary:one':{'kind':'glossary','entry':'Alpha'}}
    data['dependency_versions']={'glossary:one':text_sha('placeholder')}
    for row in data['segments']:row['dependency_keys']=['glossary:one']
    data=_resolve_manifest_dependencies(tmp_path,data)
    from workbench.project_registry import parse_project_manifest
    manifest=parse_project_manifest(data);reviews={}
    for row in manifest.segments:
        identity=approval_identity(project_id=manifest.project_id,language_direction=manifest.language_direction,segment=selected_segment(row,'draft'))
        reviews[row['id']]={'status':'approved','approval_identity':identity,
            'decision_provenance':decision_provenance(identity,'approved',DecisionActor('agent','synthetic'))}
    data['accepted_revision']=build_accepted_revision(data,reviews,{r['id']:'draft' for r in manifest.segments})
    export_accepted_revision(tmp_path,data,reviews);before=current_bytes(tmp_path/'output_cn')
    def change():path.write_text('entries:\n- source_term: Alpha\n  target_term: New\n')
    if not during_commit:change()
    with pytest.raises(ValueError):
        export_accepted_revision(tmp_path,data,reviews,before_commit=change if during_commit else None)
    assert current_bytes(tmp_path/'output_cn')==before


def test_r42_canonical_service_reads_live_dependency_not_only_manifest_sha(tmp_path):
    from test_canonical_service import source,candidate,agent
    from workbench.canonical_service import selection_status,select_revision,export_selected
    from workbench.project_registry import save_project_manifest
    from translation.source_versions import text_sha
    state=candidate(tmp_path,source(tmp_path));path=tmp_path/'workspace/manifests/native-flow.json'
    data=json.loads(path.read_text());data['dependency_sources']={'glossary:one':{'kind':'glossary','entry':'Alpha'}}
    data['dependency_versions']={'glossary:one':text_sha('placeholder')}
    for row in data['segments']:row['dependency_keys']=['glossary:one']
    cfg=tmp_path/'workspace/configs';cfg.mkdir();asset=cfg/'glossary.yaml'
    asset.write_text('entries:\n- source_term: Alpha\n  target_term: One\n');save_project_manifest(tmp_path,data);agent(tmp_path)
    state=selection_status(tmp_path,'native-flow')
    state=select_revision(tmp_path,'native-flow',expected_manifest_sha256=state['manifest_sha256'],
        target_fields={r['segment_id']:'draft' for r in state['segments']})
    assert state['selected_current'] and state['can_select']
    before=path.read_bytes();asset.write_text('entries:\n- source_term: Alpha\n  target_term: New\n')
    changed=selection_status(tmp_path,'native-flow')
    assert changed['manifest_sha256']==state['manifest_sha256'] and not changed['selected_current'] and not changed['can_select']
    with pytest.raises(ValueError):export_selected(tmp_path,'native-flow',expected_manifest_sha256=state['manifest_sha256'])
    assert path.read_bytes()==before and not (tmp_path/'output_cn').exists()
