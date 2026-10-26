"""Bounded, source-bound context with textual as-of scopes.

Quote equality proves provenance, not semantic truth. Temporal slots and speakers
are caller annotations, not extracted facts. This module never opens assets,
target stores or review files, and never issues approval.
"""
from dataclasses import dataclass
import hashlib
import json

from .context_policy import SourceContextCatalog, SourceContextPolicy, _hash


@dataclass(frozen=True)
class NarrativeContextPolicy:
    max_facts: int = 8
    max_prior_translations: int = 3
    max_chars: int = 2400

    def __post_init__(self):
        if any(type(n) is not int or n < 0 for n in
               (self.max_facts, self.max_prior_translations, self.max_chars)):
            raise ValueError('narrative context requires nonnegative integer bounds')

    def identity(self):
        return {'schema': 'narrative-context-policy/1', 'max_facts': self.max_facts,
                'max_prior_translations': self.max_prior_translations, 'max_chars': self.max_chars}


@dataclass(frozen=True)
class ContextFact:
    """An exact source quote; no free-standing inferred proposition is admitted."""
    fact_id: str
    segment_id: str
    source_sha256: str
    start_char: int
    end_char: int
    quote: str
    effective_from: str
    effective_until: str | None = None
    speaker_id: str | None = None
    slot: str | None = None


@dataclass(frozen=True)
class PriorTranslation:
    segment_id: str
    source_sha256: str
    target_text: str
    project_id: str
    review_entry: dict


@dataclass(frozen=True)
class NarrativeContext:
    segment_ids: tuple
    source_sha256s: tuple
    _serialized: str

    def to_dict(self):
        value = json.loads(self._serialized)
        return {**value, 'sha256': _hash(value)}


def _text(value):
    return isinstance(value, str) and bool(value.strip())


@dataclass(frozen=True, init=False)
class NarrativeContextCatalog:
    source: SourceContextCatalog
    policy: NarrativeContextPolicy
    _facts: tuple
    _priors: tuple
    _speakers: str
    sha256: str

    def __init__(self, source, *, facts=(), prior_translations=(), policy=None, speakers=None):
        if not isinstance(source, SourceContextCatalog):
            raise ValueError('selected immutable source catalog required')
        policy = NarrativeContextPolicy() if policy is None else policy
        if not isinstance(policy, NarrativeContextPolicy):
            raise ValueError('explicit narrative context policy required')

        def point(segment_id):
            if not _text(segment_id) or segment_id not in source._positions:
                raise ValueError('unknown narrative source position')
            return source._positions[segment_id]

        rows = []; ids = set()
        for fact in facts:
            if not isinstance(fact, ContextFact) or not _text(fact.fact_id) or fact.fact_id in ids:
                raise ValueError('duplicate or invalid context fact')
            ids.add(fact.fact_id); index = point(fact.segment_id)
            chapter_id, _, text = source._rows[index]
            if (fact.source_sha256 != hashlib.sha256(text.encode()).hexdigest()
                    or type(fact.start_char) is not int or type(fact.end_char) is not int
                    or not 0 <= fact.start_char < fact.end_char <= len(text)
                    or not _text(fact.quote) or fact.quote != text[fact.start_char:fact.end_char]):
                raise ValueError('context fact differs from exact source evidence')
            start = point(fact.effective_from)
            end = point(fact.effective_until) if fact.effective_until is not None else len(source._rows)
            if start < index: raise ValueError('fact cannot become known before evidence')
            if end <= start: raise ValueError('invalid narrative interval')
            if any(v is not None and not _text(v) for v in (fact.speaker_id, fact.slot)):
                raise ValueError('invalid narrative annotation')
            value = {**fact.__dict__, 'chapter_id': chapter_id,
                     'grounding': 'exact_source_quote', 'semantic_truth': 'not_verified',
                     'scope_basis': 'caller_annotation_textual_order', 'writable': False}
            for old in rows:
                prior = json.loads(old[4])
                if (fact.slot is not None and prior['slot'] == fact.slot
                        and (fact.speaker_id is None or prior['speaker_id'] is None
                             or prior['speaker_id'] == fact.speaker_id)
                        and max(start, old[0]) < min(end, old[1])):
                    raise ValueError('overlapping narrative slot; explicit scope required')
            rows.append((start, end, index, fact.speaker_id, json.dumps(value, ensure_ascii=False, sort_keys=True)))

        targets = []; seen = set()
        for item in prior_translations:
            if not isinstance(item, PriorTranslation): raise ValueError('invalid prior translation')
            index = point(item.segment_id); chapter_id, _, text = source._rows[index]
            if (index in seen or item.source_sha256 != hashlib.sha256(text.encode()).hexdigest()
                    or not _text(item.target_text) or not _text(item.project_id)
                    or not isinstance(item.review_entry, dict)):
                raise ValueError('ambiguous or unbound prior translation')
            seen.add(index)
            from workbench.review_state import approval_identity, review_decision_summary
            segment = {'id': item.segment_id, 'source': text, 'draft': item.target_text}
            identity = approval_identity(project_id=item.project_id, language_direction='JP_TO_CN', segment=segment)
            decision = review_decision_summary(item.review_entry, identity, segment=segment)
            value = {'segment_id': item.segment_id, 'chapter_id': chapter_id,
                     'source_sha256': item.source_sha256, 'target_text': item.target_text,
                     'target_sha256': hashlib.sha256(item.target_text.encode()).hexdigest(),
                     'project_id': item.project_id, 'approval_identity': identity,
                     'review_entry_sha256': _hash(item.review_entry), 'review_summary': decision,
                     'trust': 'higher_nonhuman_accepted' if decision['candidate_accepted'] else 'low_unverified',
                     'human_approved_final': False, 'writable': False}
            targets.append((index, json.dumps(value, ensure_ascii=False, sort_keys=True)))
        speakers = dict(speakers or {})
        for sid, speaker in speakers.items():
            point(sid)
            if not _text(speaker): raise ValueError('invalid speaker annotation')
        rows.sort(key=lambda row: (row[2], row[4])); targets.sort()
        speaker_json = json.dumps(speakers, sort_keys=True, ensure_ascii=False)
        for name, value in [('source', source), ('policy', policy), ('_facts', tuple(rows)),
                            ('_priors', tuple(targets)), ('_speakers', speaker_json)]:
            object.__setattr__(self, name, value)
        object.__setattr__(self, 'sha256', _hash({'source': source.sha256, 'policy': policy.identity(),
            'facts': rows, 'priors': targets, 'speakers': speaker_json}))

    def identity(self):
        return {'schema': 'narrative-context-catalog/1', 'sha256': self.sha256,
                'source_catalog_sha256': self.source.sha256, 'policy': self.policy.identity()}

    def for_batch(self, segments, *, speakers=None):
        self.source.before(segments, SourceContextPolicy(0, 0))  # validates every current source anchor
        annotations = json.loads(self._speakers)
        if speakers is not None:
            if not isinstance(speakers, dict) or set(speakers) - {s.segment_id for s in segments}:
                raise ValueError('speaker annotations must bind current source IDs')
            if any(not _text(v) for v in speakers.values()): raise ValueError('invalid speaker annotation')
            annotations.update(speakers)
        head = self.source._positions[segments[0].segment_id]
        chars = self.policy.max_chars; fact_slots = self.policy.max_facts
        prior_slots = self.policy.max_prior_translations; contexts = []
        for segment in segments:
            index = self.source._positions[segment.segment_id]; selected = []; previous = []
            speaker = annotations.get(segment.segment_id)
            for start, end, evidence, owner, serialized in reversed(self._facts):
                if not (evidence < index and start <= index < end and (owner is None or owner == speaker)):
                    continue
                value = json.loads(serialized); size = len(value['quote'])
                if fact_slots and size <= chars:
                    selected.append(value); chars -= size; fact_slots -= 1
            for evidence, serialized in reversed(self._priors):
                if evidence >= head: continue
                value = json.loads(serialized); size = len(value['target_text'])
                if prior_slots and size <= chars:
                    previous.append(value); chars -= size; prior_slots -= 1
            contexts.append({'segment_id': segment.segment_id, 'speaker_id': speaker,
                             'speaker_basis': 'caller_annotation_unverified',
                             'facts': list(reversed(selected)), 'prior_translations': list(reversed(previous))})
        value = {'schema': 'narrative-context/1', 'catalog': self.identity(), 'contexts': contexts,
                 'as_of_basis': 'selected_source_textual_order', 'semantic_verification': 'not_granted',
                 'usage': 'understanding_only_per_segment_never_add_revealed_facts_or_rewrite_context'}
        return NarrativeContext(tuple(s.segment_id for s in segments),
            tuple(hashlib.sha256(s.source_text.encode()).hexdigest() for s in segments),
            json.dumps(value, ensure_ascii=False, sort_keys=True))
