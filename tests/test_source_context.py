"""Source-only chronology checked at prompt and synthetic provider boundaries."""
from pathlib import Path
import json
import sys
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))


def test_current_head_is_never_fabricated_as_preceding_context():
    from translation.chapter_parser import Segment
    from translation.prompt_builder import build_batch_messages
    content=build_batch_messages([Segment('s1','CURRENT_HEAD')],chapter_label='synthetic',compact_context=True)[1].content
    assert 'Batch opening context' not in content
    assert content.count('CURRENT_HEAD')==1


def test_real_call_path_receives_preceding_source_not_future_or_draft(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from translation import draft_runner
    from providers.types import ModelResult
    import translation.configs_asset_context as assets
    monkeypatch.setenv('CONTROLLED_RUN_ENABLED','true');monkeypatch.setenv('REAL_API_TESTS_ENABLED','false')
    monkeypatch.setattr(assets,'build_configs_asset_context',lambda *_:SimpleNamespace(empty=True))
    source=tmp_path/'input_jp';source.mkdir()
    (source/'001-synthetic.md').write_text('# synthetic\n\nPREVIOUS_SOURCE\n\nCURRENT_SOURCE\n\nFUTURE_SOURCE')
    captured=[]
    class Provider:
        provider_id='fake';model_name='synthetic';network_calls=0
        def generate(self,messages,options=None):
            text=messages[1].content;captured.append(text)
            value=json.loads(text[text.index('{'):]);items=[{'segment_id':r['segment_id'],'translation':'候选译文足够长度'} for r in value['segments']]
            return ModelResult(raw_output=json.dumps({'items':items}),model_name=self.model_name,provider_id=self.provider_id)
    draft_runner.run_draft_stage_b(repo_root=tmp_path,input_dir=source,limit_chapters=1,run_id='context-case',
        provider_factory=lambda _:Provider(),max_segments_per_call=1,batch_token_budget=200,compact_context=True)
    assert len(captured)==3
    second=json.loads(captured[1][captured[1].index('{'):])
    assert second['source_context']['items'][0]['source_text']=='PREVIOUS_SOURCE'
    assert 'FUTURE_SOURCE' not in captured[1]
    assert second['source_context']['anchor']['segment_id']==second['segments'][0]['segment_id']


def chapters():
    from translation.chapter_parser import ParsedChapter,Segment
    return [ParsedChapter('ch-a','selected-a','chapter-a',[Segment('a1','SOURCE_ALPHA','UNVERIFIED_TARGET'),Segment('a2','SOURCE_BETA')]),
            ParsedChapter('ch-b','selected-b','chapter-b',[Segment('b1','CURRENT_GAMMA'),Segment('b2','FUTURE_DELTA')])]


@pytest.mark.parametrize('compact',[True,False])
def test_cross_chapter_source_context_is_explicit_and_not_writable(compact):
    from translation.context_policy import SourceContextCatalog,SourceContextPolicy
    from translation.prompt_builder import build_batch_messages
    source=chapters();pending=[source[1].segments[0]]
    context=SourceContextCatalog(source).before(pending,SourceContextPolicy(max_segments=2,max_chars=100))
    messages=build_batch_messages(pending,chapter_label='chapter-b',compact_context=compact,source_context=context)
    user=messages[-1].content;contract=json.JSONDecoder().raw_decode(user[user.index('{'):])[0]
    assert [x['segment_id'] for x in contract['source_context']['items']]==['a1','a2']
    assert [x['segment_id'] for x in contract['segments']]==['b1']
    assert 'FUTURE_DELTA' not in user and 'UNVERIFIED_TARGET' not in user
    assert contract['source_context']['anchor']=={'chapter_id':'ch-b','segment_id':'b1'}


def test_bounded_windows_and_character_spans_are_reproducible():
    from translation.context_policy import SourceContextCatalog,SourceContextPolicy
    source=chapters();catalog=SourceContextCatalog(source);pending=[source[1].segments[0]]
    tiny=catalog.before(pending,SourceContextPolicy(2,4)).to_dict()
    assert tiny['items'][0]['source_text']=='BETA'
    assert tiny['items'][0]['source_start_char']==len('SOURCE_')
    assert tiny['items'][0]['source_end_char']==len('SOURCE_BETA')
    assert tiny==catalog.before(pending,SourceContextPolicy(2,4)).to_dict()
    assert catalog.before(pending,SourceContextPolicy(0,100)).to_dict()['items']==[]
    assert catalog.before(pending,SourceContextPolicy(2,0)).to_dict()['items']==[]
    assert tiny['sha256']!=catalog.before(pending,SourceContextPolicy(1,100)).to_dict()['sha256']
    assert catalog.before([source[0].segments[0]]).to_dict()['items']==[]


def test_catalog_is_immutable_and_excludes_later_manual_target_changes():
    from dataclasses import FrozenInstanceError
    from translation.context_policy import SourceContextCatalog
    source=chapters();catalog=SourceContextCatalog(source);pending=[source[1].segments[0]]
    before=catalog.before(pending).to_dict()
    source[0].segments[0].source_text='later source edit'
    source[0].segments[0].draft_text='later manual target edit'
    assert catalog.before(pending).to_dict()==before
    with pytest.raises(FrozenInstanceError):catalog.sha256='changed'
    with pytest.raises(TypeError):catalog._positions['a1']=9
    with pytest.raises(ValueError):catalog.before([source[0].segments[0]])


@pytest.mark.parametrize('kind',['foreign','duplicate','reordered','changed','bad_type'])
def test_ambiguous_current_batch_is_refused(kind):
    from translation.chapter_parser import Segment
    from translation.context_policy import SourceContextCatalog
    source=chapters();catalog=SourceContextCatalog(source);a1,a2=source[0].segments
    cases={'foreign':[Segment('foreign','x')],'duplicate':[a1,a1],'reordered':[a2,a1],
           'changed':[Segment('a1','changed')],'bad_type':[Segment([], 'x')]}
    with pytest.raises(ValueError):catalog.before(cases[kind])


@pytest.mark.parametrize('value',[-1,True,1.5,'2'])
def test_invalid_windows_are_not_silently_coerced(value):
    from translation.context_policy import SourceContextPolicy
    with pytest.raises(ValueError):SourceContextPolicy(max_segments=value)
    with pytest.raises(ValueError):SourceContextPolicy(max_chars=value)


def test_prompt_refuses_context_for_different_current_anchor():
    from translation.context_policy import SourceContextCatalog
    from translation.prompt_builder import build_batch_messages
    source=chapters();context=SourceContextCatalog(source).before([source[1].segments[0]])
    with pytest.raises(ValueError):build_batch_messages([source[1].segments[1]],chapter_label='chapter-b',source_context=context)


def test_fake_provider_reads_only_current_request_ids():
    from translation.context_policy import SourceContextCatalog
    from translation.prompt_builder import build_batch_messages
    from providers.fake_provider import FakeProvider
    source=chapters();pending=[source[1].segments[0]]
    context=SourceContextCatalog(source).before(pending)
    result=FakeProvider().generate(build_batch_messages(pending,chapter_label='chapter-b',source_context=context))
    assert json.loads(result.raw_output)['segment_id']=='b1'
    assert 'a1' not in result.raw_output and 'a2' not in result.raw_output


def test_policy_change_on_resume_preserves_prior_candidate_and_budget(tmp_path,monkeypatch):
    from translation import draft_runner
    from translation.context_policy import SourceContextPolicy
    from providers.fake_provider import FakeProvider
    monkeypatch.setenv('CONTROLLED_RUN_ENABLED','true');monkeypatch.setenv('REAL_API_TESTS_ENABLED','false')
    source=tmp_path/'input_jp';source.mkdir();(source/'001-synthetic.md').write_text('# source\n\n合成源文。')
    def run(policy):return draft_runner.run_draft_stage_b(repo_root=tmp_path,input_dir=source,limit_chapters=1,
        run_id='policy-pin',provider_factory=lambda _:FakeProvider(),source_context_policy=policy)
    _,root=run(SourceContextPolicy(1,100))
    candidate=root/'segments.json';before=candidate.read_bytes()
    checkpoint=tmp_path/'workspace/simulations/checkpoints/policy-pin.json';pinned=checkpoint.read_bytes()
    state=json.loads(pinned)['metadata']['draft_execution']
    assert state['pin']['identity']['source_context']['policy']['max_chars']==100
    with pytest.raises(RuntimeError,match='identity changed'):run(SourceContextPolicy(2,100))
    assert candidate.read_bytes()==before and checkpoint.read_bytes()==pinned
