"""Tests for translation-memory asset deposition and consumption."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from assets.translation_memory import (  # noqa: E402
    ExternalAssetExtractionUnavailable,
    build_translation_memory_assets,
    render_translation_asset_context,
)
from translation.draft_runner import run_draft_stage_a  # noqa: E402
from translation.prompt_builder import build_batch_messages  # noqa: E402
from translation.chapter_parser import Segment  # noqa: E402
from workbench.export_service import run_export  # noqa: E402
from workbench.project_registry import (  # noqa: E402
    create_project_manifest,
    patch_project_review_state_cas,
    save_project_manifest,
)
from workbench.review_state import DecisionActor, approval_identity, patch_project_review_state  # noqa: E402


def test_memory_context_caps_terms_names_and_pairs_independently(monkeypatch):
    from assets import translation_memory as memory
    data = {
        "term_candidates": [{"source": "term-one", "target": "one"}],
        "proper_noun_candidates": [{"source": f"name-{n}"} for n in range(4)],
        "translation_pairs": [{"source_text": "phrase-one", "target_text": "target"}],
    }
    monkeypatch.setattr(memory, "_current_asset_context", lambda *_args, **_kwargs: data)
    result = memory.select_batch_context_hits(
        Path("synthetic.json"), ["term-one name-0 name-1 name-2 name-3 phrase-one"],
        max_terms=8, max_character_notes=1, max_pairs=0,
    )
    assert result.count("- Term:") == 1
    assert result.count("- Name:") == 1
    assert "- Phrase:" not in result
    no_terms = memory.select_batch_context_hits(
        Path("synthetic.json"), ["term-one name-0"], max_terms=0, max_character_notes=1, max_pairs=0,
    )
    assert "- Term:" not in no_terms and no_terms.count("- Name:") == 1


def test_zero_memory_caps_avoid_reading_context(monkeypatch):
    from assets import translation_memory as memory
    def unexpected_read(*_args, **_kwargs):
        raise AssertionError("zero-cap request must not read a context")
    monkeypatch.setattr(memory, "_current_asset_context", unexpected_read)
    assert memory.select_batch_context_hits(
        Path("synthetic.json"), ["source"], max_terms=0, max_character_notes=0, max_pairs=0,
    ) == ""


@pytest.mark.parametrize("field, value", [
    ("max_terms", -1), ("max_character_notes", -1), ("max_pairs", -1), ("max_terms", True),
])
def test_memory_context_rejects_invalid_caps(monkeypatch, field, value):
    from assets import translation_memory as memory
    monkeypatch.setattr(memory, "_current_asset_context", lambda *_args, **_kwargs: {})
    with pytest.raises(ValueError, match="nonnegative integer"):
        memory.select_batch_context_hits(Path("synthetic.json"), ["source"], **{field: value})


def _seed_workbench_project(repo: Path) -> str:
    project_id = "asset-memory-test"
    approved_segment = {
        "id": "seg-001",
        "segment_id": "seg-001",
        "chapter": 1,
        "source": "アルファの森へ向かう。",
        "draft": "前往阿尔法之森。",
        "status": "pending",
    }
    rejected_segment = {
        "id": "seg-002",
        "segment_id": "seg-002",
        "chapter": 1,
        "source": "【レア】称号を獲得した。",
        "draft": "【稀有】获得了称号。",
        "status": "pending",
    }
    create_project_manifest(
        repo,
        project_id=project_id,
        name="Asset Memory",
        language_direction="JP_TO_CN",
        segments=[
            approved_segment,
            rejected_segment,
        ],
    )
    identity = approval_identity(
        project_id=project_id,
        language_direction="JP_TO_CN",
        segment=approved_segment,
    )
    rejected_identity = approval_identity(
        project_id=project_id,
        language_direction="JP_TO_CN",
        segment=rejected_segment,
    )
    patch_project_review_state_cas(
        repo,
        project_id,
        decision_actor=DecisionActor("agent", "synthetic-test-agent"),
        segments={
            "seg-001": {"status": "approved", "expected_identity": identity},
            "seg-002": {
                "status": "rejected",
                "expected_identity": rejected_identity,
            },
        },
    )
    return project_id


def test_agent_mode_builds_approved_translation_memory_without_api(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "must-not-be-used")
    project_id = _seed_workbench_project(tmp_path)

    doc = build_translation_memory_assets(repo_root=tmp_path, project_id=project_id)

    assert doc["mode"] == "agent"
    assert doc["stats"]["api_calls"] == 0
    assert doc["stats"]["pairs"] == 1
    assert doc["approved_pairs"][0]["segment_id"] == "seg-001"
    assert "seg-002" not in doc["segment_map"]
    assert Path(doc["asset_path"]).is_file()
    assert "アルファ" in doc["context_prompt"]


def test_manifest_memory_rejects_legacy_unbound_approval(tmp_path):
    project_id = "asset-memory-legacy"
    create_project_manifest(
        tmp_path,
        project_id=project_id,
        name="Legacy",
        language_direction="JP_TO_CN",
        segments=[
            {
                "id": "seg-001",
                "source": "原文",
                "draft": "译文",
                "status": "approved",
            }
        ],
    )
    patch_project_review_state(
        tmp_path,
        project_id,
        segments={"seg-001": {"status": "approved", "note": "keep"}},
    )

    with pytest.raises(ValueError, match="no approved translation pairs"):
        build_translation_memory_assets(repo_root=tmp_path, project_id=project_id)


@pytest.mark.parametrize(
    "project_id,segment",
    [
        (
            "asset-memory-blank-source",
            {"id": "seg-001", "source": "", "draft": "译文"},
        ),
        (
            "asset-memory-blank-target",
            {"id": "seg-001", "source": "原文", "draft": "   "},
        ),
    ],
)
def test_approved_consumers_share_blank_content_eligibility(
    tmp_path,
    project_id,
    segment,
):
    # Legacy malformed manifests remain readable; new imports reject blank sources.
    save_project_manifest(
        tmp_path,
        {
            "project_id": project_id,
            "name": "Blank",
            "language_direction": "JP_TO_CN",
            "segments": [segment],
        },
    )
    identity = approval_identity(
        project_id=project_id,
        language_direction="JP_TO_CN",
        segment=segment,
    )
    patch_project_review_state(
        tmp_path,
        project_id,
        segments={
            "seg-001": {"status": "approved", "approval_identity": identity},
        },
    )

    with pytest.raises(ValueError, match="no approved segments"):
        run_export(
            tmp_path,
            source="manifest",
            project_id=project_id,
            status_mode="approved",
        )
    with pytest.raises(ValueError, match="no approved translation pairs"):
        build_translation_memory_assets(repo_root=tmp_path, project_id=project_id)


def test_run_source_translated_mode_can_deposit_completed_pairs(tmp_path):
    run_id = "run-memory-source"
    run_root = tmp_path / "workspace" / "runs" / run_id
    run_root.mkdir(parents=True)
    (run_root / "segments.json").write_text(
        json.dumps(
            {
                "language_direction": "JP_TO_CN",
                "chapters": [
                    {
                        "chapter_id": "ch-001",
                        "segments": [
                            {
                                "segment_id": "ch-001-seg-001",
                                "source_text": "主人公はレベル1だった。",
                                "draft_text": "主角是等级1。",
                                "status": "machine_translated",
                            }
                        ],
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    doc = build_translation_memory_assets(
        repo_root=tmp_path,
        source_run=run_id,
        status_mode="translated",
    )

    assert doc["stats"]["pairs"] == 1
    assert doc["segment_map"]["ch-001-seg-001"] == "主角是等级1。"


def test_external_api_mode_requires_explicit_enablement(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    project_id = _seed_workbench_project(tmp_path)

    with pytest.raises(ExternalAssetExtractionUnavailable):
        build_translation_memory_assets(
            repo_root=tmp_path,
            project_id=project_id,
            mode="external_api",
        )


def test_prompt_builder_withholds_unscoped_asset_context():
    messages = build_batch_messages(
        [Segment(segment_id="seg-003", source_text="テスト")],
        chapter_label="章",
        asset_context="Term: アルファ => 阿尔法",
    )

    assert "withheld_unscoped" in messages[1].content
    assert "アルファ => 阿尔法" not in messages[1].content


def test_draft_run_rejects_unscoped_asset_and_preserves_it(tmp_path, monkeypatch):
    monkeypatch.setenv("CONTROLLED_RUN_ENABLED", "true")
    monkeypatch.setenv("REAL_API_TESTS_ENABLED", "false")
    asset_path = tmp_path / "workspace" / "assets" / "translation_memory" / "ctx.json"
    asset_path.parent.mkdir(parents=True)
    asset_path.write_text(
        json.dumps(
            {
                "asset_kind": "translation_memory",
                "context_prompt": "Term: アルファ => 阿尔法",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    input_dir = tmp_path / "input_jp"
    input_dir.mkdir()
    (input_dir / "001-test.md").write_text("# 测试\n\n## 节\n\nアルファです。\n", encoding="utf-8")

    seen_messages: list[str] = []

    class StubProvider:
        provider_id = "stub"
        model_name = "stub-model"

        def __init__(self, cost_guard=None):
            self.cost_guard = cost_guard

        def generate(self, messages, options=None):  # noqa: ARG002
            from providers.types import ModelResult

            seen_messages.append(messages[1].content)
            fixed = {"items": [{"segment_id": "ch-001-seg-001", "translation": "这是阿尔法。"}]}
            result = ModelResult(
                provider_id=self.provider_id,
                model_name=self.model_name,
                raw_output=json.dumps(fixed, ensure_ascii=False),
                parsed_output=fixed,
            )
            result.mark_finished("ok")
            return result

    before = asset_path.read_bytes()
    with pytest.raises(ValueError, match="unscoped asset"):
        run_draft_stage_a(
            repo_root=tmp_path, input_dir=input_dir, limit_chapters=1,
            run_id="asset-context-run", provider_factory=lambda g: StubProvider(cost_guard=g),
            asset_context_path=asset_path,
        )
    assert seen_messages == [] and asset_path.read_bytes() == before
    assert not (tmp_path / "workspace/runs/asset-context-run").exists()
    from assets.translation_memory import load_translation_asset_context
    assert load_translation_asset_context(asset_path)["context_prompt"] == "Term: アルファ => 阿尔法"
    assert render_translation_asset_context(asset_path) == ""  # audit-readable, unproven consumption withheld


def test_r42_baseline_same_size_same_second_prompt_edit_is_fresh(tmp_path):
    import os
    from translation.configs_asset_context import build_configs_asset_context, _DOC_CACHE
    path=tmp_path/'glossary.yaml';chars=tmp_path/'absent.yaml'
    path.write_text('entries:\n- source_term: Alpha\n  target_term: Old\n')
    _DOC_CACHE.clear()
    first=build_configs_asset_context(['Alpha'],glossary_path=path,character_path=chars)
    stamp=path.stat();raw=path.read_bytes();path.write_bytes(raw.replace(b'Old',b'New'))
    os.utime(path,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
    second=build_configs_asset_context(['Alpha'],glossary_path=path,character_path=chars)
    assert 'Old' in first.text and 'New' in second.text and 'Old' not in second.text


def test_r42_baseline_changed_target_invalidates_only_affected_memory(tmp_path):
    from workbench.project_registry import get_project_manifest
    pid='machine-memory'
    rows=[{'id':'one','source':'First source sentence.','draft':'OLD first target.','status':'machine_translated'},
          {'id':'two','source':'Second source sentence.','draft':'Stable second target.','status':'machine_translated'}]
    create_project_manifest(tmp_path,project_id=pid,name='Synthetic',language_direction='JP_TO_CN',segments=rows)
    doc=build_translation_memory_assets(repo_root=tmp_path,project_id=pid,status_mode='translated')
    path=Path(doc['asset_path']);before=path.read_bytes()
    manifest=get_project_manifest(tmp_path,pid);payload=json.loads(manifest.path.read_text());payload['segments'][0]['draft']='NEW first target.'
    save_project_manifest(tmp_path,payload)
    rendered=render_translation_asset_context(path)
    assert 'OLD first target.' not in rendered and 'Stable second target.' in rendered
    assert path.read_bytes()==before


def test_r42_baseline_revoked_acceptance_withholds_old_memory(tmp_path):
    pid=_seed_workbench_project(tmp_path);doc=build_translation_memory_assets(repo_root=tmp_path,project_id=pid)
    patch_project_review_state(tmp_path,pid,segments={'seg-001':{'status':'rejected'}})
    assert render_translation_asset_context(Path(doc['asset_path']))==''


def test_r42_baseline_machine_pairs_are_not_called_approved(tmp_path):
    pid='unreviewed'
    create_project_manifest(tmp_path,project_id=pid,name='Synthetic',language_direction='JP_TO_CN',
        segments=[{'id':'one','source':'Synthetic source.','draft':'Synthetic target.','status':'machine_translated'}])
    doc=build_translation_memory_assets(repo_root=tmp_path,project_id=pid,status_mode='translated')
    assert doc.get('approved_pairs')==[] and len(doc.get('machine_pairs',[]))==1


def _r42_machine_project(repo):
    pid='dependency-memory'
    create_project_manifest(repo,project_id=pid,name='Synthetic',language_direction='JP_TO_CN',segments=[
        {'id':'one','source':'First source sentence.','draft':'First target.','status':'machine_translated'},
        {'id':'two','source':'Second source sentence.','draft':'Second target.','status':'machine_translated'}])
    return pid


@pytest.mark.parametrize('field,new',[('source','Other source sentence.'),('draft','Other target.'),('status','rejected')])
def test_r42_source_target_or_eligibility_change_is_scoped(tmp_path,field,new):
    from workbench.project_registry import get_project_manifest
    from assets.translation_memory import select_batch_context_hits
    pid=_r42_machine_project(tmp_path)
    doc=build_translation_memory_assets(repo_root=tmp_path,project_id=pid,status_mode='translated');path=Path(doc['asset_path'])
    manifest=get_project_manifest(tmp_path,pid);payload=json.loads(manifest.path.read_text())
    payload['segments'][0][field]=new;save_project_manifest(tmp_path,payload)
    # Source changes invalidate necessary context through the existing scope revision.
    rendered=render_translation_asset_context(path)
    assert 'First target.' not in rendered
    if field!='source': assert 'Second target.' in rendered
    hits=select_batch_context_hits(path,['First source sentence.','Second source sentence.'])
    assert 'First target.' not in hits


def test_r42_explicit_tm_withdrawal_is_scoped_and_auditable(tmp_path):
    pid=_r42_machine_project(tmp_path);doc=build_translation_memory_assets(repo_root=tmp_path,project_id=pid,status_mode='translated')
    path=Path(doc['asset_path']);saved=json.loads(path.read_text())
    saved['withdrawn_pair_ids']=[saved['translation_pairs'][0]['pair_id']]
    path.write_text(json.dumps(saved));before=path.read_bytes()
    result=render_translation_asset_context(path)
    assert 'First target.' not in result and 'Second target.' in result and path.read_bytes()==before
    saved['withdrawn']=True;path.write_text(json.dumps(saved));assert render_translation_asset_context(path)==''


@pytest.mark.parametrize('tamper',['payload','digest','duplicate','missing_source','legacy','direction'])
def test_r42_unknown_or_forged_tm_is_withheld(tmp_path,tamper):
    pid=_r42_machine_project(tmp_path);doc=build_translation_memory_assets(repo_root=tmp_path,project_id=pid,status_mode='translated')
    path=Path(doc['asset_path']);saved=json.loads(path.read_text());row=saved['translation_pairs'][0]
    if tamper=='payload': row['target_text']='FORGED target.'
    elif tamper=='digest': row['version_sha256']='0'*64
    elif tamper=='duplicate': saved['translation_pairs'].append(dict(row))
    elif tamper=='missing_source': saved['source_refs']=['manifest:unknown-project']
    elif tamper=='legacy': saved['schema_version']=1
    else:saved['language_direction']='CN_TO_JP'
    saved['context_prompt']='FORGED prompt';saved['term_candidates']=[{'source':'FORGED','target':'FORGED'}]
    path.write_text(json.dumps(saved));before=path.read_bytes();result=render_translation_asset_context(path)
    assert 'First target.' not in result and 'FORGED' not in result and path.read_bytes()==before


def _r42_run(repo, *, project_id=None, source='アルファの森へ向かう。', target='前往阿尔法之森。'):
    run=repo/'workspace/runs/run_synthetic_tm';run.mkdir(parents=True,exist_ok=True)
    payload={'language_direction':'JP_TO_CN','chapters':[{'chapter_id':'ch-001','segments':[
        {'segment_id':'seg-001','source_text':source,'draft_text':target,
         'refined_text':'STALE refined text must not win.','status':'machine_translated'}]}]}
    if project_id:payload['project_id']=project_id
    path=run/'segments.json';path.write_text(json.dumps(payload,ensure_ascii=False));return path


def test_r42_run_and_manifest_share_current_acceptance_eligibility(tmp_path):
    pid=_seed_workbench_project(tmp_path);run=_r42_run(tmp_path,project_id=pid)
    doc=build_translation_memory_assets(repo_root=tmp_path,source_run=run.parent.name)
    assert doc['approved_pairs'][0]['qualification']=='nonhuman_candidate'
    assert doc['approved_pairs'][0]['acceptance_provenance']['actor_type']=='agent'
    assert 'STALE' not in doc['context_prompt']
    path=Path(doc['asset_path']);assert '前往阿尔法之森' in render_translation_asset_context(path)
    patch_project_review_state(tmp_path,pid,segments={'seg-001':{'status':'rejected'}})
    assert render_translation_asset_context(path)==''


@pytest.mark.parametrize('mismatch',['source','target','direction','project','label_only','revoked_run'])
def test_r42_run_labels_or_mismatched_content_cannot_supply_acceptance(tmp_path,mismatch):
    pid=_seed_workbench_project(tmp_path);run=_r42_run(tmp_path,project_id=pid)
    data=json.loads(run.read_text());row=data['chapters'][0]['segments'][0]
    if mismatch=='source':row['source_text']='Other source.'
    elif mismatch=='target':row['draft_text']='Other target.'
    elif mismatch=='direction':data['language_direction']='CN_TO_JP'
    elif mismatch=='project':data['project_id']='unknown-project'
    elif mismatch=='revoked_run':row['status']='rejected'
    else:data.pop('project_id');row['status']='approved'
    run.write_text(json.dumps(data))
    with pytest.raises((ValueError,KeyError)):
        build_translation_memory_assets(repo_root=tmp_path,source_run=run.parent.name)


def test_r42_run_machine_mode_uses_draft_and_revalidates_content(tmp_path):
    run=_r42_run(tmp_path)
    doc=build_translation_memory_assets(repo_root=tmp_path,source_run=run.parent.name,status_mode='translated')
    assert doc['approved_pairs']==[] and doc['machine_pairs'][0]['qualification']=='unreviewed_translation'
    path=Path(doc['asset_path']);assert 'STALE' not in render_translation_asset_context(path)
    data=json.loads(run.read_text());data['chapters'][0]['segments'][0]['draft_text']='Changed target.'
    run.write_text(json.dumps(data));assert render_translation_asset_context(path)==''


def test_r42_external_asset_requires_explicit_repo_context(tmp_path):
    pid=_r42_machine_project(tmp_path);path=tmp_path/'chosen-local-output.json'
    build_translation_memory_assets(repo_root=tmp_path,project_id=pid,status_mode='translated',output_path=path)
    assert render_translation_asset_context(path)==''
    assert 'First target.' in render_translation_asset_context(path,repo_root=tmp_path)


def test_r42_prompt_dependencies_track_only_emitted_entries_and_withdrawal(tmp_path):
    from translation.configs_asset_context import build_configs_asset_context
    import yaml
    path=tmp_path/'glossary.yaml';chars=tmp_path/'characters.yaml'
    data={'entries':[{'source_term':'Alpha','target_term':'One','knowledge_claims':[{'claim_id':'c1','withdrawn':False}]},
                     {'source_term':'Beta','target_term':'Two'}]}
    chars.write_text('characters: []');path.write_text(yaml.safe_dump(data))
    def build():return build_configs_asset_context(['Alpha'],glossary_path=path,character_path=chars)
    first=build();data['entries'][1]['target_term']='Unrelated';path.write_text(yaml.safe_dump(data));other=build()
    assert first.dependency_versions==other.dependency_versions
    data['entries'][0]['knowledge_claims'][0]['withdrawn']=True;path.write_text(yaml.safe_dump(data));withdraw=build()
    assert first.text==withdraw.text and first.dependency_sha256!=withdraw.dependency_sha256
    data['entries'][0]['withdrawn']=True;path.write_text(yaml.safe_dump(data));assert build().empty


def test_r42_memory_reads_only_explicit_manifest_and_keeps_unrelated_data_unopened(tmp_path,monkeypatch):
    pid=_r42_machine_project(tmp_path)
    other=tmp_path/'workspace/manifests/unrelated.json';other.write_text('UNREADABLE UNRELATED DATA')
    original=Path.read_bytes;original_text=Path.read_text
    def checked(self,*args,**kwargs):
        assert self!=other
        return original(self,*args,**kwargs)
    def checked_text(self,*args,**kwargs):
        assert self!=other
        return original_text(self,*args,**kwargs)
    monkeypatch.setattr(Path,'read_bytes',checked);monkeypatch.setattr(Path,'read_text',checked_text)
    doc=build_translation_memory_assets(repo_root=tmp_path,project_id=pid,status_mode='translated')
    assert 'First target.' in render_translation_asset_context(Path(doc['asset_path']))


def test_r42_serialized_run_reference_cannot_open_outside_registered_roots(tmp_path,monkeypatch):
    pid=_r42_machine_project(tmp_path);doc=build_translation_memory_assets(repo_root=tmp_path,project_id=pid,status_mode='translated')
    path=Path(doc['asset_path']);outside=tmp_path/'unregistered';outside.mkdir();secret=outside/'segments.json'
    secret.write_text('MUST NOT BE READ')
    data=json.loads(path.read_text());data['source_refs']=['run:'+str(outside)];path.write_text(json.dumps(data))
    original=Path.read_text
    def checked(self,*args,**kwargs):
        assert self!=secret
        return original(self,*args,**kwargs)
    monkeypatch.setattr(Path,'read_text',checked)
    assert render_translation_asset_context(path)==''


def test_r42_malformed_tm_identity_withholds_instead_of_resurrecting_saved_prompt(tmp_path):
    pid=_r42_machine_project(tmp_path);doc=build_translation_memory_assets(repo_root=tmp_path,project_id=pid,status_mode='translated')
    path=Path(doc['asset_path']);data=json.loads(path.read_text())
    data['translation_pairs'][0]['pair_id']={'invalid':'identity'};data['context_prompt']='FORGED'
    path.write_text(json.dumps(data));text=render_translation_asset_context(path)
    assert 'First target.' not in text and 'Second target.' in text and 'FORGED' not in text


@pytest.mark.parametrize('kind,mutation',[('glossary','term'),('glossary','knowledge'),('glossary','withdraw'),
    ('character','term'),('character','missing'),('glossary','malformed')])
def test_r42_live_config_edits_invalidate_scoped_memory_without_manifest_rewrite(tmp_path,kind,mutation):
    import yaml
    from translation.source_versions import text_sha
    from workbench.project_registry import get_project_manifest
    from workbench.review_state import approval_identity
    pid=_r42_machine_project(tmp_path);manifest=get_project_manifest(tmp_path,pid)
    data=json.loads(manifest.path.read_text());data['dependency_versions']={'config:one':text_sha('placeholder')}
    data['dependency_sources']={'config:one':{'kind':kind,'entry':'Alpha'}}
    data['segments'][0]['dependency_keys']=['config:one'];data['segments'][1]['dependency_keys']=[]
    cfg=tmp_path/'workspace/configs';cfg.mkdir();path=cfg/('glossary.yaml' if kind=='glossary' else 'character_profile.yaml')
    field='entries' if kind=='glossary' else 'characters';idfield='source_term' if kind=='glossary' else 'name'
    entry={idfield:'Alpha','target_term':'One','knowledge_claims':[{'claim_id':'c','withdrawn':False}]}
    path.write_text(yaml.safe_dump({field:[entry]}));save_project_manifest(tmp_path,data)
    original=get_project_manifest(tmp_path,pid).segments[0]
    doc=build_translation_memory_assets(repo_root=tmp_path,project_id=pid,status_mode='translated');asset=Path(doc['asset_path'])
    before=manifest.path.read_bytes()
    if mutation=='term':entry['target_term']='New'
    elif mutation=='knowledge':entry['knowledge_claims'][0]['withdrawn']=True
    elif mutation=='withdraw':entry['withdrawn']=True
    if mutation=='missing':path.unlink()
    elif mutation=='malformed':path.write_text('entries: [unterminated')
    else:path.write_text(yaml.safe_dump({field:[entry]}))
    current=get_project_manifest(tmp_path,pid).segments[0]
    def identity(row):return approval_identity(project_id=pid,language_direction='JP_TO_CN',segment=row)
    assert identity(original)!=identity(current)
    text=render_translation_asset_context(asset)
    assert 'First target.' not in text and 'Second target.' in text
    assert manifest.path.read_bytes()==before


@pytest.mark.parametrize('mutation',['withdraw','source_changed','cycle'])
def test_r42_live_tm_dependency_is_validated_through_its_source(tmp_path,mutation):
    from translation.source_versions import text_sha
    from workbench.project_registry import get_project_manifest
    parent=_r42_machine_project(tmp_path);parentdoc=build_translation_memory_assets(repo_root=tmp_path,project_id=parent,status_mode='translated')
    parentpath=Path(parentdoc['asset_path']);pair=parentdoc['translation_pairs'][0]
    consumer=parent if mutation=='cycle' else 'tm-consumer'
    if consumer!=parent:
        create_project_manifest(tmp_path,project_id=consumer,name='Synthetic',language_direction='JP_TO_CN',segments=[
            {'id':'one','source':'Consumer source.','draft':'Consumer target.','status':'machine_translated'},
            {'id':'two','source':'Unrelated source.','draft':'Unrelated target.','status':'machine_translated'}])
    manifest=get_project_manifest(tmp_path,consumer);data=json.loads(manifest.path.read_text())
    data['dependency_versions']={'tm:one':text_sha('placeholder')}
    data['dependency_sources']={'tm:one':{'kind':'tm_pair','asset':parentpath.name,'pair_id':pair['pair_id']}}
    data['segments'][0]['dependency_keys']=['tm:one'];data['segments'][1]['dependency_keys']=[]
    save_project_manifest(tmp_path,data)
    if mutation=='cycle':
        current=get_project_manifest(tmp_path,parent)
        assert current.segments[0]['dependency_resolution_errors']==['tm:one']
        assert render_translation_asset_context(parentpath)=='' or 'First target.' not in render_translation_asset_context(parentpath)
        return
    child=build_translation_memory_assets(repo_root=tmp_path,project_id=consumer,status_mode='translated');childpath=Path(child['asset_path'])
    if mutation=='withdraw':
        saved=json.loads(parentpath.read_text());saved['withdrawn_pair_ids']=[pair['pair_id']];parentpath.write_text(json.dumps(saved))
    else:
        p=get_project_manifest(tmp_path,parent);changed=json.loads(p.path.read_text());changed['segments'][0]['draft']='Changed parent target.'
        save_project_manifest(tmp_path,changed)
    text=render_translation_asset_context(childpath)
    assert 'Consumer target.' not in text and 'Unrelated target.' in text


def test_r42_run_memory_revalidates_same_live_dependency_contract(tmp_path):
    from translation.source_versions import text_sha
    run=_r42_run(tmp_path);data=json.loads(run.read_text())
    data['dependency_sources']={'glossary:one':{'kind':'glossary','entry':'Alpha'}}
    data['dependency_versions']={'glossary:one':text_sha('placeholder')}
    data['chapters'][0]['segments'][0]['dependency_keys']=['glossary:one'];run.write_text(json.dumps(data))
    cfg=tmp_path/'workspace/configs';cfg.mkdir();path=cfg/'glossary.yaml'
    path.write_text('entries:\n- source_term: Alpha\n  target_term: One\n')
    doc=build_translation_memory_assets(repo_root=tmp_path,source_run=run.parent.name,status_mode='translated');asset=Path(doc['asset_path'])
    assert render_translation_asset_context(asset)
    before=run.read_bytes();path.write_text('entries:\n- source_term: Alpha\n  target_term: New\n')
    assert render_translation_asset_context(asset)=='' and run.read_bytes()==before


@pytest.mark.parametrize('route',['manifest','run'])
@pytest.mark.parametrize('mutation',['catalog','direct','unknown','bad_selection'])
def test_r42_malformed_runtime_dependency_does_not_discard_independent_rows(tmp_path,route,mutation):
    from translation.source_versions import text_sha
    from workbench.project_registry import get_project_manifest
    pid=_r42_machine_project(tmp_path)
    if route=='manifest':
        manifest=get_project_manifest(tmp_path,pid);source=manifest.path;data=json.loads(source.read_text());rows=data['segments']
    else:
        source=_r42_run(tmp_path);data=json.loads(source.read_text());rows=data['chapters'][0]['segments']
        rows[0].update(source_text='First source sentence.',draft_text='First target.',segment_id='one')
        rows.append({'segment_id':'two','source_text':'Second source sentence.','draft_text':'Second target.','status':'machine_translated'})
    data['dependency_versions']={'term:a':text_sha('v1'),'term:b':text_sha('v1')}
    rows[0]['dependency_keys']=['term:a'];rows[1]['dependency_keys']=['term:b'];source.write_text(json.dumps(data))
    kwargs={'project_id':pid} if route=='manifest' else {'source_run':source.parent.name}
    asset=Path(build_translation_memory_assets(repo_root=tmp_path,status_mode='translated',**kwargs)['asset_path'])
    if mutation=='catalog':data['dependency_versions']['term:a']='bad'
    elif mutation=='direct':rows[0].pop('dependency_keys');rows[0]['dependency_versions']={'term:a':'bad'}
    elif mutation=='unknown':rows[0]['dependency_keys']=['unknown:key']
    else:rows[0]['dependency_keys']=['term:a','term:a']
    source.write_text(json.dumps(data));before=source.read_bytes()
    text=render_translation_asset_context(asset)
    assert 'First target.' not in text and 'Second target.' in text
    assert source.read_bytes()==before
