"""Synthetic epistemic/source-time and abstaining-arbitration regressions."""
import hashlib
import json
from pathlib import Path
import sys
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))


def test_r41_preexisting_model_metadata_cannot_promote_truth():
    from assets.model_assisted_extractor import _dict_to_base_asset
    asset=_dict_to_base_asset({'asset_id':'synthetic-pattern','pattern_description':'abstract pattern',
        'knowledge_claims':[{'claim_id':'claim-1','category':'relationship','statement':'unverified claim',
            'epistemic_status':'assertion','semantic_truth':'verified','approved_by_user':True}]})
    assert asset.to_dict()['knowledge_claims'][0]['semantic_truth']=='not_verified'
    assert asset.to_dict()['knowledge_claims'][0]['producer']=='model'


def test_r41_preexisting_glossary_roundtrip_keeps_epistemic_metadata():
    from glossary.models import GlossaryEntry
    record={'source_term':'合成','target_term':'合成','locked':True,'approved_by_user':True,
        'knowledge_claims':[{'claim_id':'claim-1','category':'glossary','statement':'candidate'}]}
    item=GlossaryEntry.from_dict(record).to_dict()
    assert item['knowledge_claims'][0]['epistemic_status']=='unknown'
    assert item['knowledge_claims'][0]['semantic_truth']=='not_verified'


def test_r41_preexisting_arbitration_without_source_evidence_abstains_before_budget(tmp_path):
    from consistency.arbitration import run_arbitration
    from providers.types import ModelResult
    folder=tmp_path/'input_jp';folder.mkdir();(folder/'001-synthetic.md').write_text('# Synthetic\n\n風が吹く。\n')
    class Spy:
        calls=0
        def generate(self,*a,**k):
            self.calls+=1
            return ModelResult(provider_id='synthetic',model_name='synthetic',raw_output='{"canonical_target":"unfounded"}')
    provider=Spy();report=run_arbitration([{'kind':'shared_target','chapters':['ch-001'],
        'alternate_targets':{'popular':999}}],provider=provider,max_api_calls=1,
        checkpoint_path=tmp_path/'arbitration.json',repo_root=tmp_path)
    assert provider.calls==report['api_calls']==0 and report['status']=='ABSTAIN'
    assert report['decisions'][0]['parse_status']=='abstain'
    assert not list((tmp_path/'workspace/checkpoints/content_units').glob('*.json'))


def catalog():
    from types import SimpleNamespace
    from translation.context_policy import SourceContextCatalog
    source=['合成の前半。','秘密の関係が変わった。','合成の後半。','さらに後。']
    segments=[SimpleNamespace(segment_id=f's{i}',source_text=text) for i,text in enumerate(source)]
    return SourceContextCatalog([SimpleNamespace(chapter_id='ch-001',segments=segments)]),segments


def claim(source,segments,**changes):
    from assets.knowledge import KnowledgeClaim
    text=segments[1].source_text
    value={'claim_id':'relationship-1','category':'relationship','statement':'FALSE_MODEL_PROPOSITION',
        'epistemic_status':'assertion','producer':'model','effective_from':'s1','subject_id':'person-a',
        'object_id':'person-b','predicate':'related','alternatives':[{'target':'別称','condition':'後半のみ'}],
        'evidence':[{'source_catalog_sha256':source.sha256,'chapter_id':'ch-001','segment_id':'s1',
            'source_sha256':hashlib.sha256(text.encode()).hexdigest(),'start_char':0,'end_char':len(text),'quote':text}]}
    value.update(changes)
    return KnowledgeClaim(value)


def test_temporal_quotes_reach_real_prompt_boundary_without_model_proposition():
    from assets.knowledge import build_knowledge_context
    from translation.prompt_builder import build_batch_messages
    source,segments=catalog();knowledge=build_knowledge_context(source,[claim(source,segments)])
    before=knowledge.for_batch(segments[:1]).to_dict();after=knowledge.for_batch(segments[2:3])
    assert before['contexts'][0]['facts']==[]
    # Actual prompt builder validates the same selected source segments.
    for s in segments:s.source_binding=None
    payload=build_batch_messages(segments[2:3],chapter_label='synthetic',narrative_context=after)[-1].content
    assert segments[1].source_text in payload and 'FALSE_MODEL_PROPOSITION' not in payload
    assert 'not_verified' in payload


@pytest.mark.parametrize('change',[{'epistemic_status':'unknown'},{'epistemic_status':'inference'},
    {'withdrawn':True},{'evidence':[]},{'effective_from':None}])
def test_inferred_unknown_withdrawn_unscoped_knowledge_stays_withheld(change):
    from assets.knowledge import build_knowledge_context
    source,segments=catalog();value=build_knowledge_context(source,[claim(source,segments,**change)])
    assert value.for_batch(segments[2:3]).to_dict()['contexts'][0]['facts']==[]


def test_withdrawal_changes_effective_context_identity_and_preserves_input():
    from assets.knowledge import build_knowledge_context,KnowledgeClaim
    source,segments=catalog();original=claim(source,segments);before=original.to_dict()
    active=build_knowledge_context(source,[original]);withdrawn=build_knowledge_context(source,[KnowledgeClaim({**before,'withdrawn':True})])
    assert active.sha256!=withdrawn.sha256 and original.to_dict()==before


@pytest.mark.parametrize('field,value',[('source_catalog_sha256','0'*64),('source_sha256','0'*64),
    ('chapter_id','another'),('segment_id','missing'),('quote','fabricated'),('start_char',1)])
def test_stale_or_false_source_evidence_refuses_context(field,value):
    from assets.knowledge import build_knowledge_context,KnowledgeClaim
    source,segments=catalog();raw=claim(source,segments).to_dict();raw['evidence'][0][field]=value
    with pytest.raises(ValueError):build_knowledge_context(source,[KnowledgeClaim(raw)])


def test_future_start_and_exclusive_until_use_existing_scope_rules():
    from assets.knowledge import build_knowledge_context
    source,segments=catalog()
    with pytest.raises(ValueError,match='before evidence'):
        build_knowledge_context(source,[claim(source,segments,effective_from='s0')])
    context=build_knowledge_context(source,[claim(source,segments,effective_from='s2',effective_until='s3')])
    assert context.for_batch(segments[2:3]).to_dict()['contexts'][0]['facts']
    assert context.for_batch(segments[3:]).to_dict()['contexts'][0]['facts']==[]


@pytest.mark.parametrize('category',['glossary','character','world','summary','relationship','address','creative_pattern'])
def test_all_knowledge_categories_preserve_uncertainty_and_conditional_variants(category):
    from assets.knowledge import KnowledgeClaim
    row=KnowledgeClaim({'claim_id':'k','category':category,'statement':'candidate','confidence':0.25,
        'epistemic_status':'inference','alternatives':[{'target':'A','condition':'speaker one'},{'target':'B','condition':'speaker two'}]})
    assert row.to_dict()['confidence']==0.25 and len(row.to_dict()['alternatives'])==2
    assert row.to_dict()['semantic_truth']=='not_verified'


@pytest.mark.parametrize('name,entry',[('glossary','glossary_entry'),('character_profile','character'),('world_bible','world_entry')])
def test_knowledge_schema_extensions_validate_candidates_but_preserve_legacy(name,entry):
    import jsonschema
    from assets.knowledge import KnowledgeClaim
    schema=json.loads((Path(__file__).resolve().parents[1]/'schemas'/f'{name}.schema.json').read_text())
    extension={'definitions':schema['definitions'],'$ref':'#/definitions/knowledge_claim'}
    valid=KnowledgeClaim({'claim_id':'synthetic','category':'world','statement':'candidate'}).to_dict()
    jsonschema.validate(valid,extension)
    with pytest.raises(jsonschema.ValidationError):jsonschema.validate({**valid,'semantic_truth':'verified'},extension)
    assert 'knowledge_claims' not in schema['definitions'][entry]['required']


def bound_arbitration(tmp_path):
    from consistency.arbitration import run_arbitration
    from providers.types import ModelResult
    text='# Synthetic\n\n風が吹く。\n';folder=tmp_path/'input_jp';folder.mkdir();(folder/'001-synthetic.md').write_text(text)
    candidate={'kind':'shared_target','chapters':['ch-001'],'source_evidence':[{'chapter_id':'ch-001',
        'source_revision':hashlib.sha256(text.encode()).hexdigest(),'start_char':0,'end_char':len(text),'quote':text}]}
    class Spy:
        calls=0
        raw='{"resolution":"alternatives","alternatives":[{"target":"甲","condition":"speaker one"},{"target":"乙","condition":"speaker two"}]}'
        def generate(self,messages,*a,**k):
            self.calls+=1
            assert json.loads(messages[-1].content)['source_evidence'][0]['quote']==text
            assert 'not_verified' in messages[-1].content
            return ModelResult(provider_id='synthetic',model_name='synthetic',raw_output=self.raw)
    return candidate,Spy(),run_arbitration


def test_arbitration_conditional_alternatives_are_not_global_canonical(tmp_path):
    candidate,provider,run=bound_arbitration(tmp_path)
    report=run([candidate],provider=provider,max_api_calls=1,checkpoint_path=tmp_path/'arb.json',repo_root=tmp_path)
    row=report['decisions'][0]
    assert report['status']=='PASS' and row['resolution']=='alternatives' and len(row['alternatives'])==2
    assert 'canonical_target' not in row and row['canonical_adoption'] is False


def test_arbitration_abstention_is_terminal_and_resume_does_not_call_again(tmp_path):
    candidate,provider,run=bound_arbitration(tmp_path);provider.raw='{"resolution":"abstain"}'
    kwargs={'provider':provider,'max_api_calls':2,'checkpoint_path':tmp_path/'arb.json','repo_root':tmp_path}
    first=run([candidate],**kwargs);second=run([candidate],**kwargs)
    assert first['status']==second['status']=='ABSTAIN' and provider.calls==1 and second['api_calls']==0
    assert first['arbitrated_count']==0 and first['resolved_count']==1


def test_invalid_arbitration_evidence_is_rejected_before_checkpoint_or_provider_charge(tmp_path):
    candidate,provider,run=bound_arbitration(tmp_path);candidate['source_evidence'][0]['quote']='forged'
    with pytest.raises(ValueError,match='evidence differs'):
        run([candidate],provider=provider,max_api_calls=1,checkpoint_path=tmp_path/'arb.json',repo_root=tmp_path)
    assert provider.calls==0 and not list((tmp_path/'workspace/checkpoints/content_units').glob('*.json'))


def test_address_annotations_remain_speaker_scoped():
    from assets.knowledge import build_knowledge_context
    source,segments=catalog();context=build_knowledge_context(source,[claim(source,segments,
        category='address',speaker_id='speaker-a',slot='address-to-person-b')])
    assert context.for_batch(segments[2:3],speakers={'s2':'speaker-a'}).to_dict()['contexts'][0]['facts']
    assert context.for_batch(segments[2:3],speakers={'s2':'speaker-b'}).to_dict()['contexts'][0]['facts']==[]


@pytest.mark.parametrize('bad',[{'epistemic_status':'verified'},{'evidence':[{'quote':'unbound'}]},
    {'confidence':99},{'effective_until':False}])
def test_incompatible_model_metadata_degrades_to_unknown_without_invented_evidence(bad):
    from assets.model_assisted_extractor import _dict_to_base_asset
    asset=_dict_to_base_asset({'asset_id':'example','knowledge_claims':[{'claim_id':'k',
        'category':'world','statement':'candidate',**bad,'approved_by_user':True}]})
    row=asset.to_dict()['knowledge_claims'][0]
    assert row['epistemic_status']=='unknown' and row['evidence']==[]
    assert row['semantic_truth']=='not_verified' and 'approved_by_user' not in row


def test_legacy_locked_glossary_without_evidence_is_not_promoted():
    from glossary.models import GlossaryEntry
    original=GlossaryEntry(source_term='旧資料',locked=True,approved_by_user=True)
    assert 'knowledge_claims' not in original.to_dict()
    assert GlossaryEntry.from_dict(original.to_dict()).to_dict()==original.to_dict()


def test_rejected_legacy_arbitration_checkpoint_cannot_resume_as_grounded(tmp_path):
    from translation.content_binding import SourceBindings
    candidate,provider,run=bound_arbitration(tmp_path)
    resolver=SourceBindings(tmp_path);rows=[resolver.chapter('ch-001')]
    old_identity=hashlib.sha256(json.dumps({'candidates':[candidate],
        'full_sources':[resolver.identities(rows)]},ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    checkpoint=tmp_path/'arb.json';checkpoint.write_text(json.dumps({'schema':'arbitration-progress/1','input_sha256':old_identity,
        'provider_invocations_used':1,'completed_item_ids':['0'],'decisions':[{'item_id':'0','parse_status':'ok','canonical_target':'unsupported'}],
        'max_api_calls':1}));before=checkpoint.read_bytes()
    with pytest.raises(ValueError,match='changed arbitration checkpoint'):
        run([candidate],provider=provider,max_api_calls=1,checkpoint_path=checkpoint,repo_root=tmp_path)
    assert provider.calls==0 and checkpoint.read_bytes()==before


@pytest.mark.parametrize('same_id',[False,True])
def test_private_knowledge_evidence_never_copies_to_abstract_public_library(tmp_path,monkeypatch,same_id):
    from assets import runner
    from assets.config import AssetExtractionConfig
    from assets.types import BaseAsset
    run=tmp_path/'workspace/runs/synthetic';run.mkdir(parents=True)
    (run/'segments.json').write_text(json.dumps({'chapters':[{'chapter_id':'ch-001','chapter_label':'synthetic',
        'segments':[{'segment_id':'s0','source_text':'合成の原文。'}]}]}))
    safe=BaseAsset(asset_id='safe',asset_type='narrative',abstraction_level='high',copyright_safety_level='safe',
        reuse_guidance='Use abstractly',pattern_description='A contrast in pacing',
        knowledge_claims=[{'statement':'PRIVATE_EVIDENCE_MARKER'}])
    blocked=BaseAsset(asset_id='blocked',asset_type='narrative',abstraction_level='low',copyright_safety_level='unsafe',
        reuse_guidance='private only',pattern_description='PRIVATE_BLOCKED_MARKER')
    if same_id:blocked.asset_id='safe'
    monkeypatch.setattr(runner,'extract_all_rule_based',lambda _: {'narrative':[safe,blocked]})
    result=runner.run_asset_extraction(repo_root=tmp_path,source_run='synthetic',mode='rule-based',
        config=AssetExtractionConfig(write_to_public_asset_library=True),run_id='public-fixture')
    assert result['stats']['assets_safe']==1 and result['stats']['assets_blocked']==1
    private=(Path(result['output_dir'])/'narrative_assets.jsonl').read_text()
    exported=''.join(p.read_text() for p in (tmp_path/'assets_extracted').glob('*.jsonl'))
    assert 'PRIVATE_EVIDENCE_MARKER' in private and 'PRIVATE_BLOCKED_MARKER' in private
    assert 'PRIVATE_EVIDENCE_MARKER' not in exported and 'PRIVATE_BLOCKED_MARKER' not in exported
    assert '"asset_id": "safe"' in exported


def test_selector_missing_chapter_and_evidence_is_terminal_abstain(tmp_path):
    from consistency.arbitration import select_arbitration_candidates,run_arbitration
    from providers.types import ModelResult
    rows=select_arbitration_candidates({'findings':[{'kind':'shared_target','target_term':'popular'}]})
    assert rows[0]['chapters']==rows[0]['source_evidence']==[]
    class Never:
        calls=0
        def generate(self,*a,**k):self.calls+=1;raise AssertionError('no evidence must never dispatch')
    provider=Never();options={'provider':provider,'max_api_calls':1,'checkpoint_path':tmp_path/'arb.json'}
    a=run_arbitration(rows,**options);b=run_arbitration(rows,**options)
    assert a['status']==b['status']=='ABSTAIN' and a['arbitrated_count']==0
    assert provider.calls==a['api_calls']==b['api_calls']==0
    assert len(json.loads((tmp_path/'arb.json').read_text())['completed_item_ids'])==1


@pytest.mark.parametrize('missing_first',[True,False])
def test_missing_evidence_in_mixed_batch_never_blocks_grounded_or_uses_budget(tmp_path,missing_first):
    from consistency.arbitration import select_arbitration_candidates
    grounded,provider,run=bound_arbitration(tmp_path)
    missing=select_arbitration_candidates({'findings':[{'kind':'shared_target'}]})[0]
    rows=[missing,grounded] if missing_first else [grounded,missing]
    report=run(rows,provider=provider,max_api_calls=1,checkpoint_path=tmp_path/'arb.json',repo_root=tmp_path)
    assert provider.calls==report['api_calls']==1 and report['resolved_count']==2
    assert {r['parse_status'] for r in report['decisions']}=={'ok','abstain'} and report['status']=='ABSTAIN'
    assert len(json.loads((tmp_path/'arb.json').read_text())['content_unit_ids_used'])==1
