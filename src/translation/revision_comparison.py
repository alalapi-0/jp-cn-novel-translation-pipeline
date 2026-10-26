"""Anonymous revision experiments; never canonical or approval authority."""
from copy import deepcopy
from itertools import combinations
import unicodedata
import json
from quality_review.calibration import packet_identity, packet_cases, sha, validate_view

_METHODS = ('B_old', 'simple', 'problem_driven')
_CANDIDATE_SETS = ({'B_old', 'simple'}, {'B_old', 'problem_driven'}, set(_METHODS))


class ComparisonTerminated(ValueError):
    """A content-free terminal outcome; callers must not reserve an evaluator."""
    def __init__(self, unique_count, candidate_count):
        super().__init__('insufficient_distinct_candidates')
        self.outcome = {
            'reason':'insufficient_distinct_candidates', 'terminal':True,
            'comparison_required':False, 'complete':False,
            'comparison_scope':'non_three_way', 'unique_target_count':unique_count,
            'candidate_count':candidate_count, 'experimental_winner':None,
            'default_action':'preserve_original', 'auto_acceptance_enabled':False,
            'human_approved_final':False, 'canonical_adoption':False,
        }


def _text_identity(text):
    if type(text) is not str or not text.strip():raise ValueError('invalid candidate text')
    return sha(unicodedata.normalize('NFC', text.replace('\r\n','\n').replace('\r','\n')).strip())


def _require_distinct(texts):
    identities={_text_identity(text) for text in texts}
    if len(identities)!=len(texts):raise ComparisonTerminated(len(identities),len(texts))


def _validate_packet_pairs(packet):
    cases=packet_cases(packet)
    if len(cases) not in {1,3}:raise ValueError('incomplete candidate pair graph')
    identities={};counts={};edges=set()
    for case in cases.values():
        texts=case['candidates']
        _require_distinct(list(texts.values()))
        pair=[]
        for text in texts.values():
            identity=_text_identity(text)
            # Normalization decides distinctness, but one candidate still has
            # exactly one original text/hash throughout the anonymous packet.
            if identity in identities and identities[identity]!=text:
                raise ValueError('incoherent candidate pair graph')
            identities[identity]=text;counts[identity]=counts.get(identity,0)+1
            pair.append(identity)
        edge=frozenset(pair)
        if edge in edges:raise ValueError('duplicate candidate pair graph edge')
        edges.add(edge)
    size=2 if len(cases)==1 else 3
    if (len(identities)!=size or any(count!=size-1 for count in counts.values())
            or edges!={frozenset(pair) for pair in combinations(identities,2)}):
        raise ValueError('incoherent candidate pair graph')


def object_schema(properties):
    return {'type':'object','properties':properties,'required':list(properties),'additionalProperties':False}


def issue_schema(*, candidate=False):
    text=lambda n:{'type':'string','minLength':1,'maxLength':n}
    fields={'issue_type':{'type':'string','enum':['MISTRANSLATION','OMISSION','ADDITION','WRONG_LANGUAGE','REFERENCE','MODALITY','TERMINOLOGY','EXPRESSION']},'severity':{'type':'string','enum':['low','medium','high','critical']},
        'confidence':{'type':'number','minimum':0,'maximum':1},'source_quote':text(1200),
        'target_quote':text(1200),'reason':text(800)}
    if candidate:fields={'candidate':{'type':'string','enum':['A','B']},**fields}
    return object_schema(fields)


def diagnosis_schema(input_sha):
    return object_schema({'input_sha256':{'type':'string','const':input_sha},
        'issues':{'type':'array','maxItems':8,'items':issue_schema()}})


def comparison_packets(source, context, candidates, *, binding):
    if (set(candidates) not in _CANDIDATE_SETS or not source or
            any(not isinstance(t,str) or not t.strip() for t in candidates.values())):
        raise ValueError('two or three complete experimental candidates required')
    _require_distinct(list(candidates.values()))
    names=sorted(candidates,key=lambda n:(sha(candidates[n]),n));cases=[];mapping={}
    for index,(one,two) in enumerate(combinations(names,2),1):
        cid=f'pair_{index}';mapping[cid]={'A':one,'B':two}
        texts={'A':candidates[one],'B':candidates[two]}
        cases.append({'case_id':cid,'source':source,'source_revision':sha(source),
            'source_context':context,'binding':deepcopy(binding),'candidates':texts,
            'target_versions':{k:sha(v) for k,v in texts.items()}})
    first={'schema':'source-blind-evaluation/1','order':1,'cases':cases}
    second=deepcopy(first);second['order']=2
    for case in second['cases']:
        for key in ['candidates','target_versions']:case[key]={'A':case[key]['B'],'B':case[key]['A']}
    return first,second,mapping


def comparison_schema(packet):
    _validate_packet_pairs(packet)
    choice={'type':'string','enum':['A','B','tie','abstain']}
    row=object_schema({'case_id':{'type':'string','enum':[c['case_id'] for c in packet['cases']]},
        'preferred':choice,'blocked':{'type':'array','maxItems':2,
            'items':{'type':'string','enum':['A','B']}},
        'issues':{'type':'array','maxItems':8,'items':issue_schema(candidate=True)},
        'literary_preference':choice,'note':{'type':'string','maxLength':1200}})
    return object_schema({'schema':{'type':'string','const':'source-calibration-view/1'},
        'order':{'type':'integer','const':packet['order']},
        'input_packet_sha256':{'type':'string','const':packet_identity(packet)},
        'cases':{'type':'array','minItems':len(packet['cases']),'maxItems':len(packet['cases']),'items':row}})


def aggregate(first, second, mapping, view1, view2):
    # Keeping the original is the safe action, not evidence that it won.
    result={'experimental_winner':None,'default_action':'preserve_original',
        'auto_acceptance_enabled':False,'human_approved_final':False,'canonical_adoption':False,
        'complete':False,'reason':'invalid_or_incomplete_evidence',
        'same_model_independence':'limited;distinct histories are not independent capabilities'}
    try:
        _validate_packet_pairs(first);_validate_packet_pairs(second)
        one=validate_view(first,view1);two=validate_view(second,view2)
        ids={c['case_id'] for c in first['cases']}
        if first['order']!=1 or second['order']!=2 or set(mapping)!=ids:raise ValueError('pair coverage')
        second_cases={c['case_id']:c for c in second['cases']}
        if set(second_cases)!=ids:raise ValueError('swap coverage')
        pairs=set();condition_texts={}
        for case in first['cases']:
            cid=case['case_id'];other=second_cases[cid];m=mapping[cid]
            if set(m)!={'A','B'} or m['A']==m['B']:raise ValueError('pair identity')
            for label,name in m.items():
                text=case['candidates'][label]
                if name in condition_texts and condition_texts[name]!=text:raise ValueError('incoherent condition text')
                condition_texts[name]=text
            pairs.add(frozenset(m.values()));expected=deepcopy(case)
            for key in ['candidates','target_versions']:expected[key]={'A':case[key]['B'],'B':case[key]['A']}
            if other!=expected:raise ValueError('not an exact swapped pair')
        names=set().union(*(set(m.values()) for m in mapping.values()))
        if names not in _CANDIDATE_SETS:raise ValueError('candidate coverage')
        if pairs!={frozenset(p) for p in combinations(names,2)}:raise ValueError('missing pair')
        if len(ids)!=len(pairs):raise ValueError('duplicate pair')
        _require_distinct(list(condition_texts.values()))
        result.update(candidate_count=len(names),pair_count=len(pairs),
            comparison_scope=('three_way' if len(names)==3 else
                'old_vs_simple_partial' if 'simple' in names else 'old_vs_problem_partial'))
        two_by={c['case_id']:c for c in two['cases']};wins={n:0 for n in names};veto=set()
        for row in one['cases']:
            other=two_by[row['case_id']];m=mapping[row['case_id']]
            def translate(label,reverse=False):
                return m[{'A':'B','B':'A'}[label] if reverse else label] if label in {'A','B'} else label
            blocked1={translate(x) for x in row['blocked']};blocked2={translate(x,True) for x in other['blocked']}
            if blocked1!=blocked2:return {**result,'complete':True,'reason':'severe_fidelity_disagreement'}
            veto|=blocked1|blocked2
            def profile(rr,reverse):
                return sorted((translate(i['candidate'],reverse),i['issue_type'],i['severity'],
                    i['source_quote'],i['target_quote']) for i in rr['issues'])
            if profile(row,False)!=profile(other,True):
                return {**result,'complete':True,'reason':'issue_or_severity_disagreement'}
            choice1=translate(row['preferred']);choice2=translate(other['preferred'],True)
            if choice1!=choice2 or translate(row['literary_preference'])!=translate(other['literary_preference'],True):
                return {**result,'complete':True,'reason':'swapped_view_disagreement'}
            if choice1 in {'tie','abstain'}:return {**result,'complete':True,'reason':'tie_or_uncertainty'}
            if any(i['issue_type'] in {'OMISSION','ADDITION'} for rr in [row,other] for i in rr['issues']):
                return {**result,'complete':True,'reason':'unresolved_semantic_claim'}
            wins[choice1]+=1
        winners=[n for n in names if wins[n]==len(names)-1 and n not in veto]
        if len(winners)!=1:return {**result,'complete':True,'reason':'cycle_or_no_safe_winner'}
        return {**result,'experimental_winner':winners[0],'complete':True,
            'reason':'consistent_source_first_pairwise_winner','wins':wins,'severe_candidate_vetoes':sorted(veto)}
    except ComparisonTerminated as error:return {**result,**error.outcome}
    except (ValueError,KeyError,TypeError):return result


def plan_method_comparison(source, context, candidates, *, binding, origins):
    """Keep all method lineages privately; evaluate only distinct target texts.

    Provenance is preserved as a claim, never promoted to approval authority.
    Representatives choose serialization, not a preferred method or winner.
    """
    if (type(source) is not str or not source or type(context) is not str
            or type(candidates) is not dict or set(candidates) != set(_METHODS)
            or type(origins) is not dict or set(origins) != set(_METHODS)
            or type(binding) is not dict):
        raise ValueError('three complete method lineages required')
    for name in _METHODS:
        _text_identity(candidates[name])
        origin = origins[name]
        if (type(origin) is not dict or set(origin) != {'target_revision', 'provenance'}
                or origin['target_revision'] != sha(candidates[name])
                or type(origin['provenance']) is not dict or not origin['provenance']):
            raise ValueError('stale or missing method provenance')
    original = {'source': source, 'context': context, 'candidates': candidates,
                'binding': binding, 'origins': origins}
    try:
        frozen = json.loads(json.dumps(original, ensure_ascii=False, sort_keys=True, allow_nan=False))
    except (ValueError, TypeError):
        raise ValueError('method inputs must be finite JSON data') from None
    if frozen != original:
        raise ValueError('method inputs must preserve JSON identity')
    fingerprint = packet_identity(frozen)
    buckets = {}
    for name in _METHODS:
        buckets.setdefault(_text_identity(candidates[name]), []).append(name)
    groups = []; lineages = {}; representatives = {}
    for normalized, members in buckets.items():
        representative = members[0]
        versions = {name: sha(candidates[name]) for name in members}
        equivalence = ('single_condition' if len(members) == 1 else
                       'byte_identical' if len(set(versions.values())) == 1 else 'normalized_only')
        groups.append({'representative': representative, 'members': members,
            'normalized_target_revision': normalized, 'target_versions': versions,
            'equivalence': equivalence})
        representatives[representative] = candidates[representative]
        for name in members:
            lineages[name] = {'target_revision': versions[name],
                'normalized_target_revision': normalized, 'representative': representative,
                'origin': deepcopy(origins[name]), 'origin_verification': 'unverified_claim'}
    count = len(groups); packets = []; mapping = {}
    if count > 1:
        first, second, mapping = comparison_packets(source, context, representatives,
            binding={'comparison_input_sha256': fingerprint})
        comparison_schema(first); comparison_schema(second)
        packets = [first, second]
    return {'schema': 'revision-method-comparison-plan/1', 'input': frozen,
        'input_identity': fingerprint, 'lineages': lineages, 'groups': groups,
        'representatives': list(representatives), 'method_condition_count': 3,
        'unique_target_count': count, 'comparison_required': count > 1,
        'comparison_scope': ('three_way' if count == 3 else
            'two_unique_targets_partial' if count == 2 else 'identity_only'),
        'packets': packets, 'private_mapping': mapping}


def _validated_method_plan(plan):
    try:
        if type(plan) is not dict:
            raise ValueError('invalid method plan')
        expected = plan_method_comparison(**plan['input'])
        if expected != plan:
            raise ValueError('method plan changed')
    except (KeyError, TypeError, ValueError):
        raise ValueError('invalid method comparison plan') from None
    return expected


def method_evaluation_packets(plan):
    """Export only validated public packets, without private lineage metadata."""
    return deepcopy(_validated_method_plan(plan)['packets'])


def aggregate_method_comparison(plan, view1=None, view2=None):
    result = {'experimental_winner': None, 'experimental_winner_target_revision': None,
        'byte_identical_winner_conditions': [],
        'default_action': 'preserve_original', 'auto_acceptance_enabled': False,
        'human_approved_final': False, 'canonical_adoption': False, 'complete': False,
        'reason': 'invalid_or_incomplete_method_evidence', 'all_method_targets_evaluated': False,
        'method_advantage': 'not_established_by_text_identity'}
    try:
        bound = _validated_method_plan(plan)
        if not bound['comparison_required'] and (view1 is not None or view2 is not None):
            raise ValueError('identity-only plan cannot have evaluator views')
        facts = {'method_condition_count': 3, 'unique_target_count': bound['unique_target_count'],
            'comparison_scope': bound['comparison_scope'], 'lineage_groups': deepcopy(bound['groups'])}
        if not bound['comparison_required']:
            return {**result, **facts, 'reason': 'all_conditions_normalized_equivalent',
                'comparison_required': False, 'candidate_count': 1, 'pair_count': 0}
        raw = aggregate(*bound['packets'], bound['private_mapping'], view1, view2)
        inexact = any(g['equivalence'] == 'normalized_only' for g in bound['groups'])
        winner = raw['experimental_winner']
        aliases = next((g['members'] for g in bound['groups']
                        if g['representative'] == winner), [])
        return {**result, **raw, **facts, 'comparison_required': True,
            'representative_comparison_scope': raw.get('comparison_scope'),
            'representative_comparison_complete': raw['complete'],
            'representative_reason': raw['reason'],
            'representative_experimental_winner': winner,
            'complete': raw['complete'] and not inexact,
            'experimental_winner': winner if not inexact and len(aliases) == 1 else None,
            'experimental_winner_target_revision': (
                bound['lineages'][winner]['target_revision']
                if not inexact and winner is not None else None),
            'byte_identical_winner_conditions': [] if inexact else aliases,
            'all_method_targets_evaluated': raw['complete'] and not inexact,
            'reason': ('normalized_variants_not_fully_evaluated'
                if inexact and winner is not None else
                'equivalent_conditions_share_winning_target' if len(aliases) > 1 else raw['reason'])}
    except (KeyError, TypeError, ValueError):
        return result
