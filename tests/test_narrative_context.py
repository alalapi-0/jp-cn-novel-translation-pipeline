"""Textual chronology and target provenance, without a semantic truth claim."""
from dataclasses import replace, FrozenInstanceError
import hashlib
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))


def material():
    from translation.chapter_parser import ParsedChapter, Segment
    from translation.context_policy import SourceContextCatalog
    chapters = [ParsedChapter('a', '', 'a', [Segment('a1', '私はまだ彼を敵と思っていた。'),
                                           Segment('a2', '彼女はそう言った。')]),
                ParsedChapter('b', '', 'b', [Segment('b1', '今は彼を仲間と呼ぶ。'),
                                           Segment('b2', '彼はうなずいた。'),
                                           Segment('b3', '実は彼は王子だった。')])]
    return chapters, SourceContextCatalog(chapters)


def fact(sid='a1', **extra):
    from translation.narrative_context import ContextFact
    chapters, _ = material()
    row = next(s for c in chapters for s in c.segments if s.segment_id == sid)
    return ContextFact(fact_id=sid, segment_id=sid,
        source_sha256=hashlib.sha256(row.source_text.encode()).hexdigest(),
        start_char=0, end_char=len(row.source_text), quote=row.source_text,
        effective_from=sid, **extra)


def test_future_knowledge_cannot_enter_earlier_request_even_with_backdated_scope():
    from translation.narrative_context import NarrativeContextCatalog
    chapters, source = material()
    with pytest.raises(ValueError, match='before evidence'):
        NarrativeContextCatalog(source, facts=[replace(fact('b3'), effective_from='a1')])
    catalog = NarrativeContextCatalog(source, facts=[fact('b3')])
    request = catalog.for_batch([chapters[0].segments[1]]).to_dict()
    assert request['contexts'][0]['facts'] == []
    assert '王子' not in json.dumps(request, ensure_ascii=False)


def test_relationship_intervals_and_speakers_do_not_become_global_rules():
    from translation.narrative_context import NarrativeContextCatalog
    chapters, source = material()
    old = fact('a1', effective_until='b1', speaker_id='narrator', slot='attitude')
    new = fact('b1', speaker_id='narrator', slot='attitude')
    catalog = NarrativeContextCatalog(source, facts=[old, new])
    early = catalog.for_batch([chapters[0].segments[1]], speakers={'a2': 'narrator'}).to_dict()
    late = catalog.for_batch([chapters[1].segments[1]], speakers={'b2': 'narrator'}).to_dict()
    other = catalog.for_batch([chapters[1].segments[1]], speakers={'b2': 'other'}).to_dict()
    unknown = catalog.for_batch([chapters[1].segments[1]]).to_dict()
    assert [f['fact_id'] for f in early['contexts'][0]['facts']] == ['a1']
    assert [f['fact_id'] for f in late['contexts'][0]['facts']] == ['b1']
    assert other['contexts'][0]['facts'] == unknown['contexts'][0]['facts'] == []
    with pytest.raises(ValueError, match='overlapping'):
        NarrativeContextCatalog(source, facts=[replace(old, effective_until=None), new])


@pytest.mark.parametrize('change', [dict(quote='虚构事实'), dict(source_sha256='0'*64),
    dict(start_char=True), dict(end_char=999), dict(segment_id='foreign'),
    dict(effective_until='a1')])
def test_unbound_or_ambiguous_fact_is_refused(change):
    from translation.narrative_context import NarrativeContextCatalog
    _, source = material()
    with pytest.raises(ValueError): NarrativeContextCatalog(source, facts=[replace(fact(), **change)])


def prior(*, approved=False, changed=False):
    from translation.narrative_context import PriorTranslation
    from workbench.review_state import approval_identity, decision_provenance, DecisionActor
    chapters, _ = material(); source = chapters[0].segments[0].source_text
    segment = {'id': 'a1', 'source': source, 'draft': '那时我仍把他当成敌人。'}
    identity = approval_identity(project_id='p', language_direction='JP_TO_CN', segment=segment)
    entry = {'status': 'approved', 'approval_identity': identity}
    if approved: entry['decision_provenance'] = decision_provenance(identity, 'approved', DecisionActor('agent', 'reviewer'))
    return PriorTranslation('a1', hashlib.sha256(source.encode()).hexdigest(),
        '等长改稿仍不能借用旧批准。' if changed else segment['draft'], 'p', entry)


@pytest.mark.parametrize('approved,changed,trust', [(False, False, 'low_unverified'),
    (True, False, 'higher_nonhuman_accepted'), (True, True, 'low_unverified')])
def test_previous_target_trust_uses_existing_exact_review_identity(approved, changed, trust):
    from translation.narrative_context import NarrativeContextCatalog
    chapters, source = material()
    item = prior(approved=approved, changed=changed)
    context = NarrativeContextCatalog(source, prior_translations=[item]).for_batch([chapters[1].segments[0]]).to_dict()
    value = context['contexts'][0]['prior_translations'][0]
    assert value['trust'] == trust
    assert value['human_approved_final'] is False
    assert value['target_sha256'] == hashlib.sha256(item.target_text.encode()).hexdigest()
    # The current batch and later targets never become preceding translation.
    assert NarrativeContextCatalog(source, prior_translations=[item]).for_batch([chapters[0].segments[0]]).to_dict()['contexts'][0]['prior_translations'] == []


def test_batch_contains_per_segment_scopes_and_bounded_complete_quotes():
    from translation.narrative_context import NarrativeContextCatalog, NarrativeContextPolicy
    chapters, source = material()
    catalog = NarrativeContextCatalog(source, facts=[fact('a1'), fact('b1')])
    value = catalog.for_batch(chapters[1].segments[:2]).to_dict()
    assert [len(c['facts']) for c in value['contexts']] == [1, 2]
    small = NarrativeContextCatalog(source, facts=[fact('a1')], policy=NarrativeContextPolicy(max_chars=1))
    assert small.for_batch([chapters[1].segments[0]]).to_dict()['contexts'][0]['facts'] == []
    assert small.identity() != catalog.identity()


def test_catalog_freezes_review_input_and_prompt_has_matching_identity():
    from translation.narrative_context import NarrativeContextCatalog
    from translation.prompt_builder import build_batch_messages
    chapters, source = material(); item = prior(approved=True)
    catalog = NarrativeContextCatalog(source, facts=[fact()], prior_translations=[item])
    frozen = catalog.identity(); item.review_entry.clear()
    context = catalog.for_batch([chapters[1].segments[0]])
    assert catalog.identity() == frozen
    for compact in (False, True):
        text = build_batch_messages([chapters[1].segments[0]], chapter_label='b',
            compact_context=compact, narrative_context=context,source_catalog_sha256=source.sha256)[1].content
        contract = json.JSONDecoder().raw_decode(text[text.index('{'):])[0]
        assert contract['narrative_context'] == context.to_dict()
        assert contract['narrative_context']['contexts'][0]['prior_translations'][0]['trust'] == 'higher_nonhuman_accepted'
    with pytest.raises(ValueError):
        build_batch_messages([chapters[1].segments[1]], chapter_label='b', narrative_context=context,
            source_catalog_sha256=source.sha256)
    altered = replace(chapters[1].segments[0], source_text='同じIDでも違う原文。')
    with pytest.raises(ValueError):
        build_batch_messages([altered], chapter_label='b', narrative_context=context,source_catalog_sha256=source.sha256)
    with pytest.raises(FrozenInstanceError): catalog.sha256 = 'changed'


def test_narrative_context_cannot_cross_changed_source_revision():
    from translation.chapter_parser import parse_chapter_file
    from translation.context_policy import SourceContextCatalog
    from translation.narrative_context import ContextFact, NarrativeContextCatalog
    from translation.prompt_builder import build_batch_messages
    path=Path('/synthetic/001-narrative.md')
    old=parse_chapter_file(path,source_bytes=b'# synthetic\n\nEARLIER_OLD\n\nSAME_ANCHOR')
    new=parse_chapter_file(path,source_bytes=b'# synthetic\n\nEARLIER_NEW\n\nSAME_ANCHOR')
    previous=old.segments[0]
    known=ContextFact('f1',previous.segment_id,hashlib.sha256(previous.source_text.encode()).hexdigest(),
        0,len(previous.source_text),previous.source_text,previous.segment_id)
    old_source=SourceContextCatalog([old]);catalog=NarrativeContextCatalog(old_source,facts=[known])
    context=catalog.for_batch([old.segments[1]])
    assert context.to_dict()['contexts'][0]['facts'][0]['quote']=='EARLIER_OLD'
    with pytest.raises(ValueError):
        build_batch_messages([new.segments[1]],chapter_label='synthetic',narrative_context=context,
            source_catalog_sha256=old_source.sha256)


def test_narrative_context_rejects_changed_preceding_chapter():
    from translation.context_policy import SourceContextCatalog
    from translation.narrative_context import NarrativeContextCatalog
    from translation.prompt_builder import build_batch_messages
    old,old_source=material();new,_=material()
    new[0].segments[0].source_text='前一章已修订。'
    selected=SourceContextCatalog(new)
    context=NarrativeContextCatalog(old_source,facts=[fact()]).for_batch([old[1].segments[0]])
    with pytest.raises(ValueError):
        build_batch_messages([new[1].segments[0]],chapter_label='b',narrative_context=context,
            source_catalog_sha256=selected.sha256)


@pytest.mark.parametrize('compact', [True, False])
def test_unscoped_legacy_hints_are_withheld_even_when_labeled_unverified(compact):
    from translation.prompt_builder import build_batch_messages
    chapters, _ = material()
    text = build_batch_messages([chapters[0].segments[1]], chapter_label='a', compact_context=compact,
        asset_context='FUTURE_ASSET_SECRET', glossary_hits='FUTURE_GLOSSARY_SECRET',
        prev_tail_summary='FUTURE_SUMMARY_SECRET')[1].content
    assert all(v not in text for v in ['FUTURE_ASSET_SECRET', 'FUTURE_GLOSSARY_SECRET', 'FUTURE_SUMMARY_SECRET'])
    value = json.loads(text[text.index('{'):])
    assert value['legacy_context']['status'] == 'withheld_unscoped'


@pytest.mark.parametrize('field', ['asset_context_path', 'asset_context_path_resolved'])
def test_runtime_rejects_unscoped_asset_before_provider_or_asset_read(tmp_path, field):
    from translation.draft_runner import run_draft_stage_b
    calls = []
    with pytest.raises(ValueError, match='unscoped asset'):
        run_draft_stage_b(repo_root=tmp_path, input_dir=tmp_path/'missing', limit_chapters=1,
            provider_factory=lambda _: calls.append('provider'), **{field: tmp_path/'unread-private.json'})
    assert calls == []


def test_runtime_receives_temporal_context_and_refuses_changed_resume(tmp_path, monkeypatch):
    from translation import draft_runner
    from translation.chapter_parser import parse_chapter_file
    from translation.context_policy import SourceContextCatalog
    from translation.narrative_context import NarrativeContextCatalog, ContextFact
    from providers.fake_provider import FakeProvider
    import translation.configs_asset_context as assets
    from types import SimpleNamespace
    monkeypatch.setenv('CONTROLLED_RUN_ENABLED', 'true'); monkeypatch.setenv('REAL_API_TESTS_ENABLED', 'false')
    monkeypatch.setattr(assets, 'build_configs_asset_context', lambda *_: SimpleNamespace(empty=True))
    directory = tmp_path/'input_jp'; directory.mkdir(); path = directory/'001-synthetic.md'
    path.write_text('# source\n\n彼は敵だった。\n\n彼は仲間になった。\n\n彼は王子だった。')
    chapter = parse_chapter_file(path); source = SourceContextCatalog([chapter]); first = chapter.segments[0]
    row = ContextFact('first', first.segment_id, hashlib.sha256(first.source_text.encode()).hexdigest(),
        0, len(first.source_text), first.source_text, first.segment_id)
    contexts = NarrativeContextCatalog(source, facts=[row]); captured = []
    class Observer(FakeProvider):
        def generate(self, messages, options=None):
            text = messages[1].content; contract = json.loads(text[text.index('{'):]); captured.append((contract, options.metadata))
            return super().generate(messages, options)
    def run(context):
        return draft_runner.run_draft_stage_b(repo_root=tmp_path, input_dir=directory, limit_chapters=1,
            run_id='temporal-context', provider_factory=lambda _: Observer(), max_segments_per_call=1,
            batch_token_budget=200, narrative_catalog=context)
    _, root = run(contexts)
    assert len(captured) == 3
    second, metadata = captured[1]
    assert second['narrative_context']['contexts'][0]['facts'][0]['quote'] == first.source_text
    assert '王子' not in json.dumps(second, ensure_ascii=False)
    assert metadata['narrative_context_sha256'] == second['narrative_context']['sha256']
    candidate = root/'segments.json'; before = candidate.read_bytes()
    with pytest.raises(RuntimeError, match='identity changed'): run(NarrativeContextCatalog(source))
    assert candidate.read_bytes() == before and len(captured) == 3


@pytest.mark.parametrize('value', [-1, True, 1.5, '2'])
def test_policy_rejects_non_integer_and_negative_budgets(value):
    from translation.narrative_context import NarrativeContextPolicy
    for name in ('max_facts', 'max_prior_translations', 'max_chars'):
        with pytest.raises(ValueError): NarrativeContextPolicy(**{name: value})


def test_duplicate_or_stale_prior_and_foreign_speaker_annotation_are_rejected():
    from translation.narrative_context import NarrativeContextCatalog
    chapters, source = material(); item = prior()
    with pytest.raises(ValueError): NarrativeContextCatalog(source, prior_translations=[item, item])
    with pytest.raises(ValueError): NarrativeContextCatalog(source, prior_translations=[replace(item, source_sha256='0'*64)])
    with pytest.raises(ValueError): NarrativeContextCatalog(source, speakers={'foreign': 'narrator'})
    with pytest.raises(ValueError): NarrativeContextCatalog(source).for_batch([chapters[1].segments[0]], speakers={'a1': 'narrator'})


def test_total_quote_and_target_window_is_bounded_across_batch():
    from translation.narrative_context import NarrativeContextCatalog, NarrativeContextPolicy
    chapters, source = material()
    policy = NarrativeContextPolicy(max_facts=1, max_prior_translations=1, max_chars=30)
    catalog = NarrativeContextCatalog(source, facts=[fact('a1'), fact('b1')],
        prior_translations=[prior()], policy=policy)
    contexts = catalog.for_batch(chapters[1].segments[:2]).to_dict()['contexts']
    facts = [f for c in contexts for f in c['facts']]
    priors = [t for c in contexts for t in c['prior_translations']]
    assert len(facts) <= 1 and len(priors) <= 1
    assert sum(len(f['quote']) for f in facts) + sum(len(t['target_text']) for t in priors) <= 30
