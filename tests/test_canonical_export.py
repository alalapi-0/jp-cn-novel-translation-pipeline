"""Synthetic accepted-version and crash-safe bundle boundaries."""
import copy
import hashlib
import json
import os
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from translation.atomic_bundle import publish_bundle, read_current
from translation.canonical_export import build_accepted_revision, export_accepted_revision, selected_segment
from translation.chapter_parser import parse_chapter_file
from workbench.project_registry import build_source_inventory
from workbench.review_state import DecisionActor, approval_identity, decision_provenance


def fixture(root, direction='JP_TO_CN'):
    prefix = 'input_jp' if direction == 'JP_TO_CN' else 'input_cn'
    rows=[]; documents=[]
    for number in (3, 718):
        path=root/prefix/f'{number:03d}-synthetic.md';path.parent.mkdir(exist_ok=True)
        path.write_text(f'# chapter {number}\n\n甲{number}。\n\n乙{number}。')
        chapter=parse_chapter_file(path)
        documents.append({'chapter_id':chapter.chapter_id,'path':str(path.relative_to(root)),'source_revision':chapter.source_revision})
        for s in chapter.segments:
            rows.append({'id':s.segment_id,'source':s.source_text,'source_binding':s.source_binding,'draft':'选定 '+s.source_text,
                         'refined_text':'未选 '+s.source_text, 'dependency_sha256':'a'*64})
    data={'project_id':'synthetic-export','name':'Synthetic','language_direction':direction,'chapters':2,'segments':rows,
          'source_inventory':build_source_inventory(rows,language_direction=direction),'source_documents':documents}
    reviews={}
    for row in rows:
        identity=approval_identity(project_id=data['project_id'],language_direction=direction,segment=selected_segment(row,'draft'))
        reviews[row['id']]={'status':'approved','approval_identity':identity,'decision_provenance':decision_provenance(identity,'approved',DecisionActor('agent','synthetic-existing-review'))}
    data['accepted_revision']=build_accepted_revision(data,reviews,{r['id']:'draft' for r in rows})
    return data,reviews


def current_bytes(root):
    return ((root/'translated/full_volume_cn.md').read_bytes(),(root/'final_export_manifest.json').read_bytes(),os.readlink(root/'.current'))


def test_complete_explicit_revision_ignores_unselected_refined_and_mtime(tmp_path):
    data,review=fixture(tmp_path);result=export_accepted_revision(tmp_path,data,review)
    output=tmp_path/'output_cn'; text=(output/'translated/full_volume_cn.md').read_text()
    assert '选定' in text and '未选' not in text and '718' in text
    manifest=json.loads((output/'final_export_manifest.json').read_bytes())
    assert manifest['accepted_revision']==data['accepted_revision'] and manifest['human_approved_final'] is False
    assert hashlib.sha256((output/'translated/full_volume_cn.md').read_bytes()).hexdigest()==manifest['volume_sha256']
    assert read_current(output)['revision']==result['bundle_revision']
    before=current_bytes(output)
    for row in data['segments']: row['refined_text']='更晚的新稿'
    again=export_accepted_revision(tmp_path,data,review)
    assert current_bytes(output)==before and again['bundle_revision']==result['bundle_revision']


@pytest.mark.parametrize('change',['missing','empty','duplicate','stale_review','target','dependency','inventory','documents','reorder','empty_chapter','chapter_count'])
def test_invalid_complete_scope_preserves_prior_export(tmp_path,change):
    data,review=fixture(tmp_path);export_accepted_revision(tmp_path,data,review);output=tmp_path/'output_cn';before=current_bytes(output)
    if change=='missing':data['segments'].pop()
    if change=='empty':data['segments'][0]['draft']=' '
    if change=='duplicate':data['segments'].append(data['segments'][0])
    if change=='stale_review':review[data['segments'][0]['id']]['status']='pending'
    if change=='target':data['segments'][0]['draft']='新目标'
    if change=='dependency':data['segments'][0]['dependency_sha256']='b'*64
    if change=='inventory':data['source_inventory']['entries'].pop()
    if change=='documents':data['source_documents'].pop()
    if change=='reorder':data['segments'].reverse()
    if change=='empty_chapter':data['source_documents'].append({'chapter_id':'empty','path':'input_jp/empty.md','source_revision':'a'*64})
    if change=='chapter_count':data['chapters']=3
    with pytest.raises(ValueError):export_accepted_revision(tmp_path,data,review)
    assert current_bytes(output)==before


def test_source_document_same_size_and_timestamp_change_blocks(tmp_path):
    data,review=fixture(tmp_path);export_accepted_revision(tmp_path,data,review);before=current_bytes(tmp_path/'output_cn')
    path=tmp_path/data['source_documents'][0]['path'];stamp=path.stat();path.write_text(path.read_text().replace('甲','丙'));os.utime(path,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
    with pytest.raises(ValueError,match='source document version'):export_accepted_revision(tmp_path,data,review)
    assert current_bytes(tmp_path/'output_cn')==before


def test_source_change_during_staging_rechecks_before_commit(tmp_path,monkeypatch):
    from translation import atomic_bundle
    data,review=fixture(tmp_path);export_accepted_revision(tmp_path,data,review);before=current_bytes(tmp_path/'output_cn')
    original=atomic_bundle._snapshot
    def stage(root,files):
        result=original(root,files);path=tmp_path/data['source_documents'][0]['path'];path.write_bytes(path.read_bytes()+b' ');return result
    monkeypatch.setattr(atomic_bundle,'_snapshot',stage)
    with pytest.raises(ValueError,match='source document version'):export_accepted_revision(tmp_path,data,review)
    assert current_bytes(tmp_path/'output_cn')==before


@pytest.mark.parametrize('fault',['write','fsync','pointer','callback'])
def test_faults_preserve_both_files_and_pointer(tmp_path,monkeypatch,fault):
    from translation import atomic_bundle
    aliases={'translated/full_volume_cn.md':'volume.md','final_export_manifest.json':'manifest.json'}
    publish_bundle(tmp_path,{'volume.md':b'old volume','manifest.json':b'old manifest'},aliases);before=current_bytes(tmp_path)
    def fail(*a,**k):raise OSError('injected '+fault)
    if fault=='write':monkeypatch.setattr(atomic_bundle,'_snapshot',fail)
    if fault=='fsync':monkeypatch.setattr(atomic_bundle,'_sync',fail)
    if fault=='pointer':
        original=atomic_bundle._link
        def link(path,target):
            if path.name=='.current':fail()
            original(path,target)
        monkeypatch.setattr(atomic_bundle,'_link',link)
    with pytest.raises(OSError):publish_bundle(tmp_path,{'volume.md':b'new volume','manifest.json':b'new manifest'},aliases,before_commit=fail if fault=='callback' else None)
    assert current_bytes(tmp_path)==before


def test_legacy_conversion_failure_preserves_original_bytes(tmp_path):
    (tmp_path/'translated').mkdir();(tmp_path/'translated/full_volume_cn.md').write_bytes(b'owner original');(tmp_path/'final_export_manifest.json').write_bytes(b'owner manifest')
    def fail():raise OSError('stop before switch')
    with pytest.raises(OSError):publish_bundle(tmp_path,{'volume.md':b'new','manifest.json':b'new'},
        {'translated/full_volume_cn.md':'volume.md','final_export_manifest.json':'manifest.json'},before_commit=fail)
    assert (tmp_path/'translated/full_volume_cn.md').read_bytes()==b'owner original'
    assert (tmp_path/'final_export_manifest.json').read_bytes()==b'owner manifest'


def test_foreign_store_symlink_preserved(tmp_path):
    outside=tmp_path/'outside';outside.mkdir();output=tmp_path/'output';output.mkdir();(output/'.revisions').symlink_to(outside,target_is_directory=True)
    with pytest.raises(ValueError,match='store symlink'):publish_bundle(output,{'v':b'new'},{'v.txt':'v'})
    assert not list(outside.iterdir())


def test_cn_to_jp_uses_same_contract(tmp_path):
    data,review=fixture(tmp_path,'CN_TO_JP');result=export_accepted_revision(tmp_path,data,review)
    assert (tmp_path/'output_jp/translated/full_volume_jp.md').is_file() and result['chapters_exported']==2


def test_no_implicit_selection_or_extra_output_cleanup(tmp_path):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
    from export_consistency_final_volume import export_final
    output=tmp_path/'output_cn';output.mkdir();prior=output/'final_export_manifest.json';prior.write_bytes(b'old')
    with pytest.raises(ValueError,match='pinned selection'):export_final(output,repo_root=tmp_path)
    assert prior.read_bytes()==b'old'
    data,review=fixture(tmp_path);(output/'translated').mkdir();extra=output/'translated/owner.md';extra.write_bytes(b'owner')
    with pytest.raises(ValueError,match='extra canonical'):export_accepted_revision(tmp_path,data,review)
    assert extra.read_bytes()==b'owner' and prior.read_bytes()==b'old'


def test_auxiliary_pair_failure_preserves_both(tmp_path,monkeypatch):
    from translation import atomic_bundle
    from workbench.export_service import export_from_manifest
    from workbench.project_registry import create_project_manifest
    from workbench.review_state import patch_project_review_state
    create_project_manifest(tmp_path,project_id='preview-test',name='Synthetic',language_direction='JP_TO_CN',segments=[{'id':'a','source':'source','draft':'old'}])
    export_from_manifest(tmp_path,project_id='preview-test',status_mode='draft')
    paths=[tmp_path/'workspace/workbench_exports'/p for p in ['translated/workbench_preview-test_cn.md','bilingual/workbench_preview-test_bilingual.md']]
    before=[p.read_bytes() for p in paths]
    def fail(*args):raise OSError('staging failure')
    monkeypatch.setattr(atomic_bundle,'_snapshot',fail)
    with pytest.raises(OSError):export_from_manifest(tmp_path,project_id='preview-test',status_mode='draft')
    assert [p.read_bytes() for p in paths]==before


def test_current_snapshot_status_pins_manifest_and_volume(tmp_path):
    from workbench.export_service import export_status
    data,review=fixture(tmp_path);result=export_accepted_revision(tmp_path,data,review)
    status=export_status(tmp_path)['production_summary']
    assert status['snapshot_integrity']=='verified_snapshot_only'
    assert status['bundle_revision']==result['bundle_revision']
    assert status['accepted_revision_sha256']==data['accepted_revision']['revision_sha256']
    snapshot=read_current(tmp_path/'output_cn')['path'];(snapshot/'volume.md').chmod(0o644);(snapshot/'volume.md').write_bytes(b'tampered')
    assert export_status(tmp_path)['production_summary']['snapshot_integrity']=='invalid_snapshot'


def test_rebuilt_truncated_inventory_cannot_omit_source_paragraph(tmp_path):
    data,review=fixture(tmp_path)
    data['segments'].pop()
    data['source_inventory']=build_source_inventory(data['segments'],language_direction='JP_TO_CN')
    data['accepted_revision']=build_accepted_revision(data,review,{r['id']:'draft' for r in data['segments']})
    with pytest.raises(ValueError,match='parser coverage'):export_accepted_revision(tmp_path,data,review)
    assert not (tmp_path/'output_cn').exists()


def test_explicit_refined_selection_requires_its_own_current_acceptance(tmp_path):
    data,review=fixture(tmp_path);choices={r['id']:'refined_text' for r in data['segments']}
    with pytest.raises(ValueError,match='stale accepted review'):build_accepted_revision(data,review,choices)
    for row in data['segments']:
        identity=approval_identity(project_id=data['project_id'],language_direction='JP_TO_CN',segment=selected_segment(row,'refined_text'))
        review[row['id']]={'status':'approved','approval_identity':identity,'decision_provenance':decision_provenance(identity,'approved',DecisionActor('agent','synthetic-refined-review'))}
    data['accepted_revision']=build_accepted_revision(data,review,choices)
    export_accepted_revision(tmp_path,data,review)
    assert '未选' in (tmp_path/'output_cn/translated/full_volume_cn.md').read_text()


def test_pinned_cli_selection_and_current_review_pair(tmp_path,monkeypatch):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
    from export_consistency_final_volume import export_final
    from translation import atomic_bundle
    data,review=fixture(tmp_path)
    path=tmp_path/'workspace/manifests/synthetic-export.json';path.parent.mkdir(parents=True);path.write_text(json.dumps(data))
    state=tmp_path/'workspace/review_state.json';state.write_text(json.dumps({'projects':{data['project_id']:{'segments':review,'issues':{}}}}))
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(ValueError,match='selection manifest version'):export_final(None,repo_root=tmp_path,selection_manifest=path,selection_sha256='0'*64)
    export_final(None,repo_root=tmp_path,selection_manifest=path,selection_sha256=digest);before=current_bytes(tmp_path/'output_cn')
    original=atomic_bundle._snapshot
    def stage(root,files):
        result=original(root,files);state.write_bytes(state.read_bytes()+b' ');return result
    monkeypatch.setattr(atomic_bundle,'_snapshot',stage)
    with pytest.raises(RuntimeError,match='review state changed'):export_final(None,repo_root=tmp_path,selection_manifest=path,selection_sha256=digest)
    assert current_bytes(tmp_path/'output_cn')==before


def test_process_exit_before_pointer_switch_keeps_old_revision(tmp_path):
    import subprocess
    aliases={'translated/full_volume_cn.md':'volume.md','final_export_manifest.json':'manifest.json'}
    publish_bundle(tmp_path,{'volume.md':b'old','manifest.json':b'old manifest'},aliases);before=current_bytes(tmp_path)
    script="from translation.atomic_bundle import publish_bundle; import os,sys; publish_bundle(sys.argv[1],{'volume.md':b'new','manifest.json':b'new manifest'},{'translated/full_volume_cn.md':'volume.md','final_export_manifest.json':'manifest.json'},before_commit=lambda:os._exit(73))"
    env={**os.environ,'PYTHONPATH':str(Path(__file__).resolve().parents[1]/'src')}
    process=subprocess.run([sys.executable,'-c',script,str(tmp_path)],env=env,capture_output=True)
    assert process.returncode==73 and current_bytes(tmp_path)==before


def test_valid_in_memory_reselection_during_staging_refuses_old_snapshot(tmp_path,monkeypatch):
    from translation import atomic_bundle
    data,review=fixture(tmp_path);export_accepted_revision(tmp_path,data,review);before=current_bytes(tmp_path/'output_cn')
    original=atomic_bundle._snapshot
    def stage(root,files):
        revision=original(root,files)
        for row in data['segments']:
            row['draft']='another accepted target'
            identity=approval_identity(project_id=data['project_id'],language_direction='JP_TO_CN',segment=selected_segment(row,'draft'))
            review[row['id']]={'status':'approved','approval_identity':identity,'decision_provenance':decision_provenance(identity,'approved',DecisionActor('agent','synthetic-new-review'))}
        data['accepted_revision']=build_accepted_revision(data,review,{r['id']:'draft' for r in data['segments']})
        return revision
    monkeypatch.setattr(atomic_bundle,'_snapshot',stage)
    with pytest.raises(RuntimeError,match='accepted selection changed'):export_accepted_revision(tmp_path,data,review)
    assert current_bytes(tmp_path/'output_cn')==before


def test_legacy_bilingual_final_copy_refuses_before_switch(tmp_path):
    data,review=fixture(tmp_path);export_accepted_revision(tmp_path,data,review);output=tmp_path/'output_cn';before=current_bytes(output)
    path=output/'bilingual/full_volume_bilingual.md';path.parent.mkdir();path.write_bytes(b'preserved legacy final copy')
    with pytest.raises(ValueError,match='bilingual final'):export_accepted_revision(tmp_path,data,review)
    assert current_bytes(output)==before and path.read_bytes()==b'preserved legacy final copy'


@pytest.mark.parametrize('direction',['JP_TO_CN','CN_TO_JP'])
def test_existing_placeholder_and_singleton_consumer(tmp_path,monkeypatch,direction):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
    import check_final_translation_singleton as checker
    data,review=fixture(tmp_path,direction);suffix='cn' if direction=='JP_TO_CN' else 'jp'
    output=tmp_path/('output_'+suffix);(output/'translated').mkdir(parents=True);(output/'translated/.gitkeep').write_bytes(b'')
    export_accepted_revision(tmp_path,data,review);monkeypatch.setattr(checker,'REPO_ROOT',tmp_path)
    assert checker.check_singleton(output)['status']=='passed'
    assert (output/'translated/.gitkeep').read_bytes()==b''
