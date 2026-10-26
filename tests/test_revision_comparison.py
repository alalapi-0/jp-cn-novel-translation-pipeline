from copy import deepcopy
import hashlib
import pytest
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from quality_review.calibration import packet_identity
from translation.revision_comparison import aggregate, comparison_packets, comparison_schema


def experiment(winner='simple'):
    a,b,m=comparison_packets('今日は雨だ。','',{'B_old':'今天下雨。','simple':'今天是雨天。',
        'problem_driven':'今天下着雨。'},binding={'source_revision':'frozen','source_span':[0,6]})
    def view(p,reverse=False):
        rows=[]
        for c in p['cases']:
            names=m[c['case_id']];target=winner if winner in names.values() else next(iter(names.values()))
            label=next(k for k,v in names.items() if v==target)
            if reverse:label={'A':'B','B':'A'}[label]
            rows.append({'case_id':c['case_id'],'preferred':label,'blocked':[],
                'issues':[],'literary_preference':label,'note':'synthetic source comparison'})
        return {'schema':'source-calibration-view/1','order':p['order'],
            'input_packet_sha256':packet_identity(p),'cases':rows}
    return a,b,m,view(a),view(b,True)


def test_consistent_winner_is_experimental_only():
    result=aggregate(*experiment())
    assert result['experimental_winner']=='simple' and result['complete']
    assert result['default_action']=='preserve_original'
    assert not result['auto_acceptance_enabled'] and not result['canonical_adoption']


def test_disagreeing_swapped_view_preserves_original():
    args=list(experiment());r=args[-1]['cases'][0];r['preferred']={'A':'B','B':'A'}[r['preferred']]
    assert aggregate(*args)['experimental_winner'] is None
    assert aggregate(*args)['default_action']=='preserve_original'


def test_tie_and_missing_pair_default_preserve():
    for mode in ['tie','missing']:
        args=list(experiment())
        if mode=='tie':args[-1]['cases'][0]['preferred']='tie'
        else:args[-1]['cases'].pop()
        result=aggregate(*args)
        assert result['experimental_winner'] is None and not result['auto_acceptance_enabled']
        assert result['default_action']=='preserve_original'


def test_changed_context_or_non_swap_is_invalid():
    args=list(experiment());args[1]['cases'][0]['source_context']='different'
    args[-1]['input_packet_sha256']=packet_identity(args[1])
    assert not aggregate(*args)['complete']


def test_severe_fidelity_veto_cannot_be_literary_winner():
    args=list(experiment());a,b,m,v1,v2=args
    for packet,view,reverse in [(a,v1,False),(b,v2,True)]:
        for case,row in zip(packet['cases'],view['cases']):
            original=next((k for k,v in m[case['case_id']].items() if v=='simple'),None)
            if original is None:continue
            label={'A':'B','B':'A'}[original] if reverse else original
            row['blocked']=[label];row['preferred']={'A':'B','B':'A'}[label]
            row['issues']=[{'candidate':label,'issue_type':'MISTRANSLATION','severity':'high',
                'confidence':1,'source_quote':'雨','target_quote':'雨','reason':'synthetic veto control'}]
    result=aggregate(*args)
    assert result['experimental_winner']!='simple' and not result['canonical_adoption']


def test_foreign_or_duplicate_pair_map_is_rejected():
    args=list(experiment());m=args[2];keys=list(m);m[keys[1]]=deepcopy(m[keys[0]])
    assert not aggregate(*args)['complete']


def test_severity_disagreement_preserves_even_with_same_preference():
    args=list(experiment())
    for packet,view,reverse,severity in [(args[0],args[3],False,'low'),(args[1],args[4],True,'medium')]:
        row=view['cases'][0];case=packet['cases'][0]
        label='B' if reverse else 'A'
        row['issues']=[{'candidate':label,'issue_type':'EXPRESSION','severity':severity,
            'confidence':.8,'source_quote':'雨','target_quote':'雨','reason':'synthetic disagreement'}]
    assert aggregate(*args)['reason']=='issue_or_severity_disagreement'


def test_pairwise_cycle_cannot_produce_a_winner():
    args=list(experiment());a,b,m,v1,v2=args
    # Each candidate wins one pair; presentation still agrees perfectly.
    winners={frozenset(['B_old','simple']):'B_old',frozenset(['simple','problem_driven']):'simple',
        frozenset(['B_old','problem_driven']):'problem_driven'}
    for view,reverse in [(v1,False),(v2,True)]:
        for row in view['cases']:
            mapping=m[row['case_id']];winner=winners[frozenset(mapping.values())]
            label=next(k for k,v in mapping.items() if v==winner)
            if reverse:label={'A':'B','B':'A'}[label]
            row['preferred']=label;row['literary_preference']=label
    assert aggregate(*args)['reason']=='cycle_or_no_safe_winner'


@pytest.mark.parametrize('winner', ['B_old', 'simple'])
def test_two_way_partial_comparison_is_explicit_not_a_third_candidate(winner):
    a,b,m=comparison_packets('今日は雨だ。','',{'B_old':'今天下雨。','simple':'今天是雨天。'},binding={})
    views=[]
    for p,reverse in [(a,False),(b,True)]:
        label=next(k for k,v in m['pair_1'].items() if v==winner)
        if reverse:label={'A':'B','B':'A'}[label]
        views.append({'schema':'source-calibration-view/1','order':p['order'],
            'input_packet_sha256':packet_identity(p),'cases':[{'case_id':'pair_1','preferred':label,
                'blocked':[],'issues':[],'literary_preference':'tie','note':'two-way synthetic'}]})
    result=aggregate(a,b,m,*views)
    assert result['complete'] and result['candidate_count']==2 and result['pair_count']==1
    assert result['comparison_scope']=='old_vs_simple_partial' and result['experimental_winner']==winner
    assert not result['canonical_adoption']


def test_duplicate_blocked_labels_still_fail_after_endpoint_keyword_removed():
    args=list(experiment());args[-1]['cases'][0]['blocked']=['A','A']
    assert not aggregate(*args)['complete']


def test_wrong_packet_order_is_not_an_authorized_swap():
    args=list(experiment());args[1]['order']=1;args[-1]['order']=1
    args[-1]['input_packet_sha256']=packet_identity(args[1])
    assert not aggregate(*args)['complete']


@pytest.mark.parametrize('names',[('simple','problem_driven'),('B_old','simple'),('B_old','problem_driven')])
def test_r40_duplicate_text_terminates_before_evaluator_dispatch(names):
    import pytest
    candidates={'B_old':'原稿。','simple':'简单修订。','problem_driven':'问题修订。'}
    candidates[names[1]]=candidates[names[0]];calls=[]
    with pytest.raises(ValueError,match='insufficient_distinct_candidates') as stopped:
        packets=comparison_packets('原文。','',candidates,binding={})
        calls.append(packets)
    out=stopped.value.outcome
    assert not calls and out['terminal'] and not out['comparison_required'] and not out['complete']
    assert out['comparison_scope']=='non_three_way' and out['unique_target_count']==2
    assert out['experimental_winner'] is None and not out['canonical_adoption'] and not out['human_approved_final']
    assert out['default_action']=='preserve_original'


def test_r40_two_way_duplicate_also_has_zero_evaluation():
    import pytest
    with pytest.raises(ValueError,match='insufficient_distinct_candidates') as stopped:
        comparison_packets('原文。','',{'B_old':'同文。','simple':'同文。'},binding={})
    assert stopped.value.outcome['unique_target_count']==1


def test_r40_hand_built_duplicate_and_incoherent_condition_cannot_claim_threeway():
    from translation.revision_comparison import comparison_schema
    import pytest
    for fault in ['duplicate','incoherent']:
        a,b,m,v1,v2=experiment()
        if fault=='duplicate':
            # Force two conditions to have exactly the same text in every pair.
            replacement=next(c['candidates'][k] for c in a['cases'] for k,n in m[c['case_id']].items() if n=='simple')
            for p in [a,b]:
                for c in p['cases']:
                    mapping=m[c['case_id']]
                    if p['order']==2:mapping={'A':mapping['B'],'B':mapping['A']}
                    for label,name in mapping.items():
                        if name=='problem_driven':c['candidates'][label]=replacement
                        c['target_versions'][label]=hashlib.sha256(c['candidates'][label].encode()).hexdigest()
            with pytest.raises(ValueError,match='insufficient_distinct_candidates'):comparison_schema(a)
        else:
            c=a['cases'][0];c['candidates']['A']='不同版本。';c['target_versions']['A']=hashlib.sha256('不同版本。'.encode()).hexdigest()
            b['cases'][0]['candidates']['B']=c['candidates']['A'];b['cases'][0]['target_versions']['B']=c['target_versions']['A']
        if fault=='incoherent':
            with pytest.raises(ValueError,match='pair graph'):comparison_schema(a)
        for p,v in [(a,v1),(b,v2)]:v['input_packet_sha256']=packet_identity(p)
        result=aggregate(a,b,m,v1,v2)
        assert not result['complete'] and result['experimental_winner'] is None


@pytest.mark.parametrize('left,right', [('same\ntext',' same\r\ntext '), ('é','e\u0301')])
def test_r40_normalized_identity_does_not_admit_equivalent_texts(left,right):
    with pytest.raises(ValueError,match='insufficient_distinct_candidates') as failure:
        comparison_packets('Synthetic source','',{'B_old':left,'simple':right},binding={})
    assert failure.value.outcome['unique_target_count']==1


def test_r40_forged_target_hash_is_rejected_independently():
    a,b,m,v,w=experiment()
    a['cases'][0]['target_versions']['A']='0'*64
    with pytest.raises(ValueError,match='candidate version mismatch'):comparison_schema(a)
    assert aggregate(a,b,m,v,w)['complete'] is False


@pytest.mark.parametrize('fault',['extra_identity','duplicate_edge','missing_edge','incoherent_normalized_text','duplicate_case'])
def test_r40_pair_graph_rejects_handmade_packets_before_dispatch(fault):
    packet,*_=experiment();calls=[]
    if fault=='extra_identity':packet['cases'][0]['candidates']['A']='fourth synthetic text'
    elif fault=='duplicate_edge':
        packet['cases'][2]=deepcopy(packet['cases'][0]);packet['cases'][2]['case_id']='pair_3'
    elif fault=='missing_edge':packet['cases'].pop()
    elif fault=='duplicate_case':packet['cases'][2]['case_id']=packet['cases'][0]['case_id']
    else:packet['cases'][0]['candidates']['A']=' '+packet['cases'][0]['candidates']['A']+' '
    for case in packet['cases']:
        case['target_versions']={label:hashlib.sha256(text.encode()).hexdigest() for label,text in case['candidates'].items()}
    with pytest.raises(ValueError):
        schema=comparison_schema(packet)
        calls.append(('reserve_and_evaluate',schema))
    assert calls==[]


@pytest.mark.parametrize('mode,reason,complete', [
    ('missing_judgment', 'invalid_or_incomplete_evidence', False),
    ('changed_context', 'invalid_or_incomplete_evidence', False),
    ('severe_disagreement', 'severe_fidelity_disagreement', True),
    ('issue_disagreement', 'issue_or_severity_disagreement', True),
    ('choice_disagreement', 'swapped_view_disagreement', True),
    ('literary_disagreement', 'swapped_view_disagreement', True),
    ('tie', 'tie_or_uncertainty', True),
    ('abstain', 'tie_or_uncertainty', True),
    ('omission', 'unresolved_semantic_claim', True),
    ('addition', 'unresolved_semantic_claim', True),
    ('cycle', 'cycle_or_no_safe_winner', True),
])
def test_r44_nonconclusive_evidence_has_no_winner(mode, reason, complete):
    a, b, mapping, one, two = experiment()
    if mode == 'missing_judgment':
        two['cases'].pop()
    elif mode == 'changed_context':
        b['cases'][0]['source_context'] = 'Different synthetic context'
        two['input_packet_sha256'] = packet_identity(b)
    elif mode in {'tie', 'abstain'}:
        for view in (one, two):
            view['cases'][0]['preferred'] = mode
            view['cases'][0]['literary_preference'] = mode
    elif mode in {'choice_disagreement', 'literary_disagreement'}:
        key = 'preferred' if mode == 'choice_disagreement' else 'literary_preference'
        row = two['cases'][0]
        row[key] = {'A': 'B', 'B': 'A'}[row[key]]
    elif mode in {'severe_disagreement', 'issue_disagreement', 'omission', 'addition'}:
        label = {'A': 'B', 'B': 'A'}[one['cases'][0]['preferred']]
        severity = 'high' if mode == 'severe_disagreement' else 'medium'
        kind = {'omission': 'OMISSION', 'addition': 'ADDITION'}.get(mode, 'EXPRESSION')
        for view, reverse in ((one, False), (two, True)):
            if reverse and mode.endswith('disagreement'):
                continue
            current = {'A': 'B', 'B': 'A'}[label] if reverse else label
            row = view['cases'][0]
            row['issues'] = [{'candidate': current, 'issue_type': kind,
                'severity': severity, 'confidence': .8, 'source_quote': '雨',
                'target_quote': '雨', 'reason': 'Synthetic unresolved evidence'}]
            if severity == 'high':
                row['blocked'] = [current]
    elif mode == 'cycle':
        wins = {frozenset(('B_old', 'simple')): 'B_old',
                frozenset(('simple', 'problem_driven')): 'simple',
                frozenset(('B_old', 'problem_driven')): 'problem_driven'}
        for view, reverse in ((one, False), (two, True)):
            for row in view['cases']:
                pair = mapping[row['case_id']]
                winner = wins[frozenset(pair.values())]
                label = next(k for k, name in pair.items() if name == winner)
                if reverse:
                    label = {'A': 'B', 'B': 'A'}[label]
                row['preferred'] = row['literary_preference'] = label
    result = aggregate(a, b, mapping, one, two)
    assert result['reason'] == reason and result['complete'] is complete
    assert result['experimental_winner'] is None
    assert result['default_action'] == 'preserve_original'
    assert not result['auto_acceptance_enabled'] and not result['canonical_adoption']
    assert not result['human_approved_final']


@pytest.mark.parametrize('winner', ['B_old', 'simple', 'problem_driven'])
def test_r44_each_legitimate_threeway_winner_remains_experimental(winner):
    result = aggregate(*experiment(winner))
    assert result['reason'] == 'consistent_source_first_pairwise_winner'
    assert result['complete'] and result['experimental_winner'] == winner
    assert result['comparison_scope'] == 'three_way'
    assert result['candidate_count'] == result['pair_count'] == 3
    assert result['default_action'] == 'preserve_original'
    assert not result['auto_acceptance_enabled'] and not result['canonical_adoption']
    assert not result['human_approved_final']


@pytest.mark.parametrize('candidates', [
    {'B_old': '同文。', 'simple': '同文。'},
    {'B_old': '原稿。', 'simple': '同文。', 'problem_driven': '同文。'},
])
def test_r44_terminal_duplicate_is_not_an_original_win(candidates):
    with pytest.raises(ValueError, match='insufficient_distinct_candidates') as stopped:
        comparison_packets('合成原文。', '', candidates, binding={})
    result = stopped.value.outcome
    assert result['experimental_winner'] is None
    assert result['default_action'] == 'preserve_original'
    assert not result['complete'] and not result['comparison_required']
    assert not result['auto_acceptance_enabled'] and not result['canonical_adoption']
    assert not result['human_approved_final']


def method_origins(candidates):
    return {name: {'target_revision': hashlib.sha256(text.encode()).hexdigest(),
                   'provenance': {'kind': 'synthetic_fixture', 'condition': name}}
            for name, text in candidates.items()}


def method_plan(candidates, **kwargs):
    from translation import revision_comparison as m
    return m.plan_method_comparison('雨が降った。', '昨日は晴れ。', candidates,
        binding={'source_span': [0, 6], 'private_note': 'ORIGIN_SECRET'},
        origins=kwargs.get('origins', method_origins(candidates)))


def method_views(plan, winner):
    from translation import revision_comparison as m
    target = plan['lineages'][winner]['representative']
    views = []
    for packet, reverse in zip(m.method_evaluation_packets(plan), (False, True)):
        rows = []
        for case in packet['cases']:
            names = plan['private_mapping'][case['case_id']]
            chosen = target if target in names.values() else next(iter(names.values()))
            label = next(k for k, value in names.items() if value == chosen)
            if reverse:
                label = {'A': 'B', 'B': 'A'}[label]
            rows.append({'case_id': case['case_id'], 'preferred': label, 'blocked': [],
                'issues': [], 'literary_preference': label, 'note': 'Synthetic comparison'})
        views.append({'schema': 'source-calibration-view/1', 'order': packet['order'],
            'input_packet_sha256': packet_identity(packet), 'cases': rows})
    return views


@pytest.mark.parametrize('targets,scope,reps,group', [
    (('旧雨文。', '简单雨文。', '问题雨文。'), 'three_way', ('B_old', 'simple', 'problem_driven'), ()),
    (('旧雨文。', '共同雨文。', '共同雨文。'), 'two_unique_targets_partial', ('B_old', 'simple'), ('simple', 'problem_driven')),
    (('旧雨文。', '旧雨文。', '问题雨文。'), 'two_unique_targets_partial', ('B_old', 'problem_driven'), ('B_old', 'simple')),
    (('旧雨文。', '简单雨文。', '旧雨文。'), 'two_unique_targets_partial', ('B_old', 'simple'), ('B_old', 'problem_driven')),
])
def test_r46_method_origins_survive_unique_text_planning(targets, scope, reps, group):
    from translation import revision_comparison as m
    candidates = dict(zip(('B_old', 'simple', 'problem_driven'), targets))
    plan = method_plan(candidates)
    assert plan['comparison_scope'] == scope and plan['method_condition_count'] == 3
    assert tuple(plan['representatives']) == reps
    assert plan['unique_target_count'] == len(reps)
    assert set(plan['lineages']) == set(candidates)
    for name, text in candidates.items():
        row = plan['lineages'][name]
        assert row['target_revision'] == hashlib.sha256(text.encode()).hexdigest()
        assert row['origin'] == method_origins(candidates)[name]
        assert row['origin_verification'] == 'unverified_claim'
    if group:
        assert any(tuple(g['members']) == group and g['equivalence'] == 'byte_identical' for g in plan['groups'])
    packets = m.method_evaluation_packets(plan)
    assert len(packets) == 2 and len(packets[0]['cases']) == (3 if len(reps) == 3 else 1)
    assert all(m.comparison_schema(p)['properties']['cases']['minItems'] == len(p['cases']) for p in packets)
    assert not any(name in str(packets) for name in ['B_old', 'simple', 'problem_driven', 'ORIGIN_SECRET', 'provenance'])
    for one, two in zip(*[p['cases'] for p in packets]):
        assert one['candidates']['A'] == two['candidates']['B']
        assert one['candidates']['B'] == two['candidates']['A']


@pytest.mark.parametrize('winner', ['B_old', 'simple', 'problem_driven'])
def test_r46_collapsed_methods_do_not_get_relabelled_or_individual_advantage(winner):
    from translation import revision_comparison as m
    plan = method_plan({'B_old': '旧雨文。', 'simple': '共同雨文。', 'problem_driven': '共同雨文。'})
    result = m.aggregate_method_comparison(plan, *method_views(plan, winner))
    expected = ['B_old'] if winner == 'B_old' else ['simple', 'problem_driven']
    assert result['byte_identical_winner_conditions'] == expected
    assert result['experimental_winner'] == ('B_old' if winner == 'B_old' else None)
    assert result['comparison_scope'] == 'two_unique_targets_partial'
    assert result['candidate_count'] == 2 and result['pair_count'] == 1 and result['method_condition_count'] == 3
    assert result['default_action'] == 'preserve_original' and not result['auto_acceptance_enabled']
    assert not result['canonical_adoption'] and not result['human_approved_final']
    assert result['method_advantage'] == 'not_established_by_text_identity'


def test_r46_old_equals_simple_retains_problem_method_identity():
    from translation import revision_comparison as m
    plan = method_plan({'B_old': '旧雨文。', 'simple': '旧雨文。', 'problem_driven': '问题雨文。'})
    result = m.aggregate_method_comparison(plan, *method_views(plan, 'problem_driven'))
    assert result['experimental_winner'] == 'problem_driven'
    assert result['byte_identical_winner_conditions'] == ['problem_driven']
    assert result['representative_comparison_scope'] == 'old_vs_problem_partial'


@pytest.mark.parametrize('variants', [('同文。', '同文。', '同文。'), ('é', 'e\u0301', ' é\r\n')])
def test_r46_all_equivalent_is_identity_only_without_evaluator_or_winner(variants):
    from translation import revision_comparison as m
    plan = method_plan(dict(zip(('B_old', 'simple', 'problem_driven'), variants)))
    assert m.method_evaluation_packets(plan) == [] and not plan['comparison_required']
    result = m.aggregate_method_comparison(plan)
    assert result['comparison_scope'] == 'identity_only' and result['unique_target_count'] == 1
    assert result['experimental_winner'] is None and not result['complete']
    assert result['default_action'] == 'preserve_original' and not result['all_method_targets_evaluated']
    assert not result['canonical_adoption'] and not result['human_approved_final']
    assert m.aggregate_method_comparison(plan, {}, {})['reason'] == 'invalid_or_incomplete_method_evidence'


def test_r46_normalization_equivalence_is_not_raw_text_or_quality_acceptance():
    from translation import revision_comparison as m
    plan = method_plan({'B_old': '旧雨文。', 'simple': 'é', 'problem_driven': ' e\u0301\r\n'})
    group = next(g for g in plan['groups'] if len(g['members']) == 2)
    assert group['equivalence'] == 'normalized_only'
    assert plan['lineages']['simple']['target_revision'] != plan['lineages']['problem_driven']['target_revision']
    result = m.aggregate_method_comparison(plan, *method_views(plan, 'simple'))
    assert result['experimental_winner'] is None and result['byte_identical_winner_conditions'] == []
    assert result['reason'] == 'normalized_variants_not_fully_evaluated'
    assert not result['complete'] and result['representative_comparison_complete']
    assert not result['all_method_targets_evaluated'] and result['default_action'] == 'preserve_original'


@pytest.mark.parametrize('fault', ['target', 'origin', 'group', 'map', 'packet', 'count', 'extra'])
def test_r46_tampered_plan_fails_before_evaluator_and_aggregation(fault):
    from translation import revision_comparison as m
    plan = method_plan({'B_old': '旧雨文。', 'simple': '共同雨文。', 'problem_driven': '共同雨文。'})
    views = method_views(plan, 'simple')
    if fault == 'target': plan['input']['candidates']['simple'] = '篡改雨文。'
    elif fault == 'origin': plan['lineages']['simple']['origin']['provenance']['condition'] = 'problem_driven'
    elif fault == 'group': plan['groups'][1]['members'].pop()
    elif fault == 'map': plan['private_mapping']['pair_1']['A'] = 'problem_driven'
    elif fault == 'packet': plan['packets'][0]['cases'][0]['source_context'] = 'changed'
    elif fault == 'count': plan['unique_target_count'] = 3
    else: plan['human_approved_final'] = True
    calls = []
    with pytest.raises(ValueError):
        calls.append(m.method_evaluation_packets(plan))
    assert not calls
    result = m.aggregate_method_comparison(plan, *views)
    assert result['reason'] == 'invalid_or_incomplete_method_evidence' and result['experimental_winner'] is None
    assert not result['complete'] and not result['human_approved_final']


@pytest.mark.parametrize('fault', ['missing_condition', 'stale_origin', 'missing_origin', 'empty_text', 'non_json_origin'])
def test_r46_incomplete_or_stale_lineage_is_not_a_comparison_plan(fault):
    from translation import revision_comparison as m
    candidates = {'B_old': '旧雨文。', 'simple': '共同雨文。', 'problem_driven': '共同雨文。'}
    origins = method_origins(candidates)
    if fault == 'missing_condition': candidates.pop('problem_driven')
    elif fault == 'stale_origin': origins['simple']['target_revision'] = '0' * 64
    elif fault == 'missing_origin': origins.pop('simple')
    elif fault == 'empty_text': candidates['simple'] = ' '
    else: origins['simple']['provenance']['bad'] = float('nan')
    with pytest.raises(ValueError): method_plan(candidates, origins=origins)


def test_r46_origin_approval_tags_remain_unverified_claims():
    from translation import revision_comparison as m
    candidates = {'B_old': '旧雨文。', 'simple': '共同雨文。', 'problem_driven': '共同雨文。'}
    origins = method_origins(candidates)
    origins['simple']['provenance'].update(approved=True, human_approved_final=True)
    plan = method_plan(candidates, origins=origins)
    result = m.aggregate_method_comparison(plan, *method_views(plan, 'simple'))
    assert plan['lineages']['simple']['origin_verification'] == 'unverified_claim'
    assert not result['human_approved_final'] and not result['canonical_adoption']


@pytest.mark.parametrize('mode', ['tie', 'abstain', 'disagree', 'missing', 'bad_quote',
                                 'severe_disagreement', 'unresolved_semantics', 'wrong_order'])
def test_r46_collapsed_route_keeps_evaluator_failure_and_fidelity_guards(mode):
    from translation import revision_comparison as m
    plan = method_plan({'B_old': '旧雨文。', 'simple': '共同雨文。', 'problem_driven': '共同雨文。'})
    one, two = method_views(plan, 'simple')
    if mode in {'tie', 'abstain'}:
        for view in (one, two):
            view['cases'][0]['preferred'] = view['cases'][0]['literary_preference'] = mode
    elif mode == 'disagree':
        two['cases'][0]['preferred'] = {'A': 'B', 'B': 'A'}[two['cases'][0]['preferred']]
    elif mode == 'missing': two['cases'].pop()
    elif mode == 'wrong_order': two['order'] = 1
    else:
        label = {'A': 'B', 'B': 'A'}[one['cases'][0]['preferred']]
        for view, reverse in ((one, False), (two, True)):
            if reverse and mode != 'unresolved_semantics': continue
            current = {'A': 'B', 'B': 'A'}[label] if reverse else label
            row = view['cases'][0]
            row['issues'] = [{'candidate': current,
                'issue_type': 'OMISSION' if mode == 'unresolved_semantics' else 'EXPRESSION',
                'severity': 'high' if mode == 'severe_disagreement' else 'medium',
                'confidence': .8, 'source_quote': 'not present' if mode == 'bad_quote' else '雨',
                'target_quote': '雨', 'reason': 'Synthetic unresolved evidence'}]
            if mode == 'severe_disagreement': row['blocked'] = [current]
    result = m.aggregate_method_comparison(plan, one, two)
    assert result['experimental_winner'] is None and result['byte_identical_winner_conditions'] == []
    assert result['default_action'] == 'preserve_original'
    assert not result['auto_acceptance_enabled'] and not result['canonical_adoption']
    assert not result['human_approved_final']


def test_r46_normalized_variant_does_not_hide_invalid_evaluator_evidence():
    from translation import revision_comparison as m
    plan = method_plan({'B_old': '旧雨文。', 'simple': 'é', 'problem_driven': 'e\u0301'})
    one, two = method_views(plan, 'simple'); two['cases'].pop()
    result = m.aggregate_method_comparison(plan, one, two)
    assert not result['complete'] and result['reason'] == 'invalid_or_incomplete_evidence'
    assert result['representative_reason'] == 'invalid_or_incomplete_evidence'
    assert result['experimental_winner'] is None


@pytest.mark.parametrize('winner', ['B_old', 'simple', 'problem_driven'])
def test_r46_distinct_method_plan_retains_complete_threeway_evaluation(winner):
    from translation import revision_comparison as m
    plan = method_plan({'B_old': '旧雨文。', 'simple': '简单雨文。', 'problem_driven': '问题雨文。'})
    result = m.aggregate_method_comparison(plan, *method_views(plan, winner))
    assert result['complete'] and result['all_method_targets_evaluated']
    assert result['comparison_scope'] == 'three_way' and result['unique_target_count'] == 3
    assert result['candidate_count'] == result['pair_count'] == 3
    assert result['experimental_winner'] == winner and result['byte_identical_winner_conditions'] == [winner]
    assert result['default_action'] == 'preserve_original' and not result['canonical_adoption']


@pytest.mark.parametrize('alias', ['simple', 'problem_driven'])
def test_r46_original_winner_preserves_byte_identical_method_alias(alias):
    from translation import revision_comparison as m
    candidates = {'B_old': '旧雨文。', 'simple': '简单雨文。', 'problem_driven': '问题雨文。'}
    candidates[alias] = candidates['B_old'];plan = method_plan(candidates)
    result = m.aggregate_method_comparison(plan, *method_views(plan, 'B_old'))
    assert result['experimental_winner'] is None
    assert result['byte_identical_winner_conditions'] == ['B_old', alias]
    assert result['comparison_scope'] == 'two_unique_targets_partial'
    assert not result['human_approved_final'] and not result['canonical_adoption']


def test_r46_normalized_variant_keeps_disagreement_as_the_primary_reason():
    from translation import revision_comparison as m
    plan = method_plan({'B_old': '旧雨文。', 'simple': 'é', 'problem_driven': 'e\u0301'})
    one, two = method_views(plan, 'simple')
    two['cases'][0]['preferred'] = {'A': 'B', 'B': 'A'}[two['cases'][0]['preferred']]
    result = m.aggregate_method_comparison(plan, one, two)
    assert result['reason'] == result['representative_reason'] == 'swapped_view_disagreement'
    assert not result['complete'] and result['experimental_winner'] is None


@pytest.mark.parametrize('targets,winner,aliases', [
    (('旧雨文。', '共同雨文。', '共同雨文。'), 'simple', ['simple', 'problem_driven']),
    (('旧雨文。', '旧雨文。', '问题雨文。'), 'B_old', ['B_old', 'simple']),
    (('旧雨文。', '简单雨文。', '旧雨文。'), 'B_old', ['B_old', 'problem_driven']),
])
def test_r46_repair_joint_target_has_no_arbitrary_method_winner(targets, winner, aliases):
    from translation import revision_comparison as m
    candidates = dict(zip(('B_old', 'simple', 'problem_driven'), targets))
    plan = method_plan(candidates)
    result = m.aggregate_method_comparison(plan, *method_views(plan, winner))
    assert result['experimental_winner'] is None
    assert result['experimental_winner_target_revision'] == hashlib.sha256(candidates[winner].encode()).hexdigest()
    assert result['byte_identical_winner_conditions'] == aliases
    assert result['reason'] == 'equivalent_conditions_share_winning_target'
    assert result['representative_experimental_winner'] == winner
    assert result['representative_reason'] == 'consistent_source_first_pairwise_winner'
    assert result['complete'] and result['all_method_targets_evaluated']
    assert result['method_advantage'] == 'not_established_by_text_identity'
    assert result['default_action'] == 'preserve_original' and not result['canonical_adoption']


@pytest.mark.parametrize('mode', ['missing', 'disagree', 'normalized'])
def test_r46_repair_nonconclusive_or_inexact_has_no_target_winner(mode):
    from translation import revision_comparison as m
    candidates = {'B_old': '旧雨文。', 'simple': '共同雨文。', 'problem_driven': '共同雨文。'}
    if mode == 'normalized':
        candidates.update(simple='é', problem_driven='e\u0301')
    plan = method_plan(candidates); one, two = method_views(plan, 'simple')
    if mode == 'missing': two['cases'].pop()
    elif mode == 'disagree':
        two['cases'][0]['preferred'] = {'A': 'B', 'B': 'A'}[two['cases'][0]['preferred']]
    result = m.aggregate_method_comparison(plan, one, two)
    assert result['experimental_winner'] is None
    assert result.get('experimental_winner_target_revision') is None
    assert result['byte_identical_winner_conditions'] == []
    assert result['default_action'] == 'preserve_original' and not result['canonical_adoption']
