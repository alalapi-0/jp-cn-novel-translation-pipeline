"""Version-bound, source-grounded calibration evidence; never an approval issuer.

Confidence is reported by the evaluator, not established as calibrated probability.
Toy contrast labels and agreement cannot enable automatic semantic acceptance.
"""
from copy import deepcopy
import hashlib
import math
import json

LABELS={'A','B'}
PREFERENCES=LABELS|{'tie','abstain'}
SEVERITIES={'low','medium','high','critical'}


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def packet_identity(packet):
    return sha(json.dumps(packet,ensure_ascii=False,sort_keys=True,separators=(',',':')))


def unique_span(text,quote):
    if not isinstance(quote,str) or not quote or text.count(quote)!=1:
        raise ValueError('evidence quote must occur exactly once in its bound text')
    start=text.index(quote)
    return [start,start+len(quote)]


def evidence_span(text, quote, supplied=None, *, gap=False):
    """Verify codepoint coordinates, including explicit zero-width omission gaps.

    A matching gap locates the evaluator's claim; it cannot prove missing meaning.
    Repeated quotes require an explicit span rather than choosing the first match.
    """
    if supplied is None:
        if gap:
            raise ValueError('omission gap requires explicit coordinates')
        return unique_span(text, quote)
    if (not isinstance(supplied, list) or len(supplied) != 2
            or any(type(n) is not int for n in supplied)):
        raise ValueError('invalid evidence coordinates')
    a, b = supplied
    if (not 0 <= a <= b <= len(text) or not isinstance(quote, str)
            or (gap and (a != b or quote != ''))
            or (not gap and (a == b or not quote or text[a:b] != quote))):
        raise ValueError('evidence coordinates do not match bound text')
    return [a, b]


def packet_cases(packet):
    if not isinstance(packet,dict) or not isinstance(packet.get('schema'),str) or packet['schema'] not in {'synthetic-blind-evaluation/1','source-blind-evaluation/1'} or type(packet.get('order')) is not int or packet['order'] not in {1,2} or not isinstance(packet.get('cases'),list):
        raise ValueError('unknown calibration packet')
    cases={}
    for case in packet.get('cases',[]):
        if not isinstance(case,dict):raise ValueError('invalid calibration case')
        cid=case.get('case_id')
        if not isinstance(cid,str) or not cid or cid in cases:raise ValueError('ambiguous calibration case')
        if not isinstance(case.get('source'),str) or not case['source'] or sha(case['source'])!=case.get('source_revision'):
            raise ValueError('source calibration version mismatch')
        if (not isinstance(case.get('source_context',''),str) or not isinstance(case.get('candidates'),dict)
                or not isinstance(case.get('target_versions'),dict) or set(case['candidates'])!=LABELS or set(case['target_versions'])!=LABELS):
            raise ValueError('missing calibration candidate')
        for label,text in case['candidates'].items():
            if not isinstance(text,str) or not text or sha(text)!=case['target_versions'][label]:raise ValueError('candidate version mismatch')
        cases[cid]=case
    if not cases:raise ValueError('empty calibration denominator')
    return cases


def validate_view(packet,view):
    cases=packet_cases(packet)
    located = packet['schema'] == 'source-blind-evaluation/1'
    view_schema = 'source-calibration-view/1' if located else 'calibration-view/1'
    if (not isinstance(view,dict) or set(view)!={'schema','order','cases','input_packet_sha256'}
            or view.get('schema')!=view_schema or type(view.get('order')) is not int
            or view['order']!=packet['order'] or view.get('input_packet_sha256')!=packet_identity(packet)
            or not isinstance(view.get('cases'),list)):
        raise ValueError('view does not match blinded packet')
    seen=set();rows=[]
    for supplied in view['cases']:
        if not isinstance(supplied,dict) or set(supplied)!={'case_id','preferred','blocked','issues','literary_preference','note'}:
            raise ValueError('unsupported calibration judgment fields')
        cid=supplied.get('case_id')
        if not isinstance(cid,str) or cid not in cases or cid in seen:raise ValueError('foreign or duplicate view case')
        seen.add(cid);case=cases[cid];row=deepcopy(supplied)
        if not isinstance(row['note'],str):raise ValueError('judgment note must be text')
        if any(not isinstance(row.get(key),str) or row[key] not in PREFERENCES for key in ('preferred','literary_preference')):
            raise ValueError('unknown evaluation choice')
        blocked=row.get('blocked');issues=row.get('issues')
        if (not isinstance(blocked,list) or any(not isinstance(x,str) or x not in LABELS for x in blocked) or len(set(blocked))!=len(blocked)
                or not isinstance(issues,list)):raise ValueError('invalid blocked candidates or issues')
        severe=set()
        for issue in issues:
            required={'candidate','issue_type','severity','confidence','source_quote','target_quote','reason'}
            optional={'source_span','target_span','target_evidence_kind'} if located else set()
            if (not isinstance(issue,dict) or not required<=set(issue) or set(issue)-required-optional
                    or not isinstance(issue.get('candidate'),str) or issue['candidate'] not in LABELS
                    or not isinstance(issue.get('severity'),str) or issue['severity'] not in SEVERITIES):
                raise ValueError('invalid located issue')
            confidence=issue.get('confidence')
            if type(confidence) not in {int,float} or not math.isfinite(confidence) or not 0<=confidence<=1:
                raise ValueError('invalid stated confidence')
            if not isinstance(issue.get('reason'),str) or not issue['reason'] or not isinstance(issue.get('issue_type'),str) or not issue['issue_type']:
                raise ValueError('unexplained semantic issue')
            if located:
                kind=issue.get('target_evidence_kind','text_span')
                if not isinstance(kind,str) or kind not in {'text_span','omission_gap'} or kind=='omission_gap' and issue['issue_type']!='OMISSION':
                    raise ValueError('unsupported target evidence kind')
                issue['source_span']=evidence_span(case['source'],issue['source_quote'],issue.get('source_span'))
                issue['target_span']=evidence_span(case['candidates'][issue['candidate']],issue['target_quote'],issue.get('target_span'),gap=kind=='omission_gap')
                issue['target_evidence_kind']=kind
            else:
                issue['source_span']=unique_span(case['source'],issue.get('source_quote'))
                issue['target_span']=unique_span(case['candidates'][issue['candidate']],issue.get('target_quote'))
            if issue['severity'] in {'high','critical'}:severe.add(issue['candidate'])
        if set(blocked)!=severe:raise ValueError('severe issues and candidate veto disagree')
        if row['preferred'] in blocked or row['preferred']=='tie' and blocked:
            raise ValueError('literary preference cannot override a severe source conflict')
        row.update(source_revision=case['source_revision'],target_versions=dict(case['target_versions']))
        rows.append(row)
    if seen!=set(cases):raise ValueError('missing calibration judgments')
    return {'schema':'validated-source-calibration-view/1' if located else 'validated-calibration-view/1','order':packet['order'],'cases':rows,
        'input_packet_sha256':view['input_packet_sha256'],
        'review_actor_type':'agent_proxy','approval_state':'not_granted','auto_acceptance_enabled':False,
        'validated_scope':'identity/shape/quote spans only;semantic truth remains evaluator judgment'}


def summarize(packet1,packet2,labels,view1,view2):
    first=packet_cases(packet1);second=packet_cases(packet2)
    gold={row['case_id']:row for row in labels.get('cases',[])}
    if len(gold)!=len(labels.get('cases',[])) or set(first)!=set(second) or set(first)!=set(gold):
        raise ValueError('calibration denominator mismatch')
    one=validate_view(packet1,view1);two=validate_view(packet2,view2)
    index2={row['case_id']:row for row in two['cases']};by_view=[]
    for order,validated in enumerate((one,two),1):
        counts={key:0 for key in ('tp','fp','tn','fn','unknown','preference_matches_author_expectation')}
        for row in validated['cases']:
            cid=row['case_id'];g=gold[cid]
            if g['source_revision']!=first[cid]['source_revision'] or g.get('target_versions')!=first[cid]['target_versions']:
                raise ValueError('controlled label source or target version changed')
            if g.get('case_identity_sha256')!=packet_identity(first[cid]):
                raise ValueError('controlled label semantic context changed')
            expected=set(g['expected_blocked'])
            if not expected<=LABELS or g['expected_preference'] not in PREFERENCES:raise ValueError('invalid contrast expectation')
            normalize=lambda label:({'A':'B','B':'A'}.get(label,label) if order==2 else label)
            predicted={normalize(x) for x in row['blocked']}
            counts['preference_matches_author_expectation']+=normalize(row['preferred'])==g['expected_preference']
            for label in LABELS:
                if row['preferred']=='abstain' and label not in predicted:counts['unknown']+=1
                else:counts['tp' if label in expected and label in predicted else 'fn' if label in expected else 'fp' if label in predicted else 'tn']+=1
        by_view.append({'order':order,**counts})
    agreement=0
    for row in one['cases']:
        cid=row['case_id'];a,b=first[cid],second[cid]
        if a['source']!=b['source'] or a.get('source_context')!=b.get('source_context') or a['candidates']['A']!=b['candidates']['B'] or a['candidates']['B']!=b['candidates']['A']:
            raise ValueError('second packet is not the same pair in reversed order')
        swapped={'A':'B','B':'A'}.get(index2[cid]['preferred'],index2[cid]['preferred'])
        agreement+=row['preferred']==swapped
    return {'schema':'synthetic-calibration-summary/1','source_units':len(first),'candidate_judgments_per_view':2*len(first),
        'by_view':by_view,'order_normalized_preference_agreement':agreement,
        'auto_acceptance_enabled':False,'human_approval':False,
        'coverage':'tiny author-designed synthetic contrasts only;not corpus/literary/probability calibration',
        'limitations':['Views share model capabilities;separate histories are not independent model validation.',
            'Easy compound degradations;9riskclusters are not exhaustive subtype coverage.',
            'Author-intended tie can still receive a legitimate literary preference;report mismatch without relabeling gold.',
            'No development or holdout evaluation;unmeasured dimensions remain uncalibrated.']}


def summarize_source(packet1, packet2, labels, view1, view2):
    """Keep detection, severe veto, unknown references and order effects separate.

    Author labels are provisional controls, never certified references. Abstention
    retains its reference denominator; recall does not improve by dropping it.
    """
    if (not isinstance(packet1, dict) or not isinstance(packet2, dict)
            or packet1.get('schema') != 'source-blind-evaluation/1' or packet1.get('order') != 1
            or packet2.get('schema') != 'source-blind-evaluation/1' or packet2.get('order') != 2):
        raise ValueError('source packets require original and reversed orders')
    first, second = packet_cases(packet1), packet_cases(packet2)
    if (not isinstance(labels, dict) or set(labels) != {'schema', 'cases'}
            or labels['schema'] != 'source-control-labels/1' or not isinstance(labels['cases'], list)):
        raise ValueError('unsupported control labels')
    required = {'case_id', 'source_revision', 'target_versions', 'case_identity_sha256',
                'expected_status', 'expected_preference', 'probe_class', 'label_authority', 'reason'}
    gold = {}
    for row in labels['cases']:
        if (not isinstance(row, dict) or set(row) != required
                or not isinstance(row['case_id'], str) or row['case_id'] in gold
                or not isinstance(row['expected_status'], dict) or set(row['expected_status']) != LABELS
                or any(not isinstance(v, str) or v not in {'severe', 'not_severe', 'unknown'}
                       for v in row['expected_status'].values())
                or row['expected_preference'] is not None and
                   (not isinstance(row['expected_preference'], str) or row['expected_preference'] not in PREFERENCES)
                or any(not isinstance(row[k], str) or not row[k] for k in ('probe_class', 'label_authority', 'reason'))):
            raise ValueError('invalid control label')
        gold[row['case_id']] = row
    if set(first) != set(second) or set(first) != set(gold):
        raise ValueError('calibration denominator mismatch')
    for cid, case in first.items():
        g = gold[cid]
        if (g['source_revision'] != case['source_revision'] or g['target_versions'] != case['target_versions']
                or g['case_identity_sha256'] != packet_identity(case)):
            raise ValueError('control case version or context changed')
        reversed_case = deepcopy(case)
        for field in ('candidates', 'target_versions'):
            reversed_case[field] = {'A': case[field]['B'], 'B': case[field]['A']}
        if reversed_case != second[cid]:
            raise ValueError('second packet is not the identical reversed case')
    views = [validate_view(packet1, view1), validate_view(packet2, view2)]

    def new_counts():
        return {k: 0 for k in ('tp', 'fp', 'tn', 'fn', 'unknown_reference', 'unknown_prediction_positive',
                               'unknown_prediction_negative', 'reference_positive', 'reference_negative')}

    def finish(counts):
        counts['precision'] = counts['tp'] / (counts['tp'] + counts['fp']) if counts['tp'] + counts['fp'] else None
        counts['recall'] = counts['tp'] / counts['reference_positive'] if counts['reference_positive'] else None
        return counts

    by_view = []
    for order, view in enumerate(views, 1):
        normalize = lambda label: {'A': 'B', 'B': 'A'}.get(label, label) if order == 2 else label
        stats = {mode: new_counts() for mode in ('issue_detection', 'severe_veto')}
        classes = {}; confidence = {'below_0.5': 0, '0.5_to_below_0.9': 0, '0.9_to_1': 0}
        preference_labeled = preference_matches = 0
        for row in view['cases']:
            g = gold[row['case_id']]; group = classes.setdefault(g['probe_class'], {m: new_counts() for m in stats})
            if g['expected_preference'] is not None:
                preference_labeled += 1
                preference_matches += normalize(row['preferred']) == g['expected_preference']
            for issue in row['issues']:
                value = issue['confidence']; confidence['below_0.5' if value < .5 else '0.5_to_below_0.9' if value < .9 else '0.9_to_1'] += 1
            predicted = {'issue_detection': {normalize(x['candidate']) for x in row['issues']},
                         'severe_veto': {normalize(x) for x in row['blocked']}}
            for mode in stats:
                for label, truth in g['expected_status'].items():
                    for counts in (stats[mode], group[mode]):
                        if truth == 'unknown':
                            counts['unknown_reference'] += 1
                            continue
                        positive = truth == 'severe'
                        counts['reference_positive' if positive else 'reference_negative'] += 1
                        if label in predicted[mode]:
                            counts['tp' if positive else 'fp'] += 1
                        elif row['preferred'] == 'abstain':
                            counts['unknown_prediction_positive' if positive else 'unknown_prediction_negative'] += 1
                        else:
                            counts['fn' if positive else 'tn'] += 1
            # Every original candidate remains in the denominator, including unknown references.
        for counts in stats.values():
            assert counts['reference_positive'] + counts['reference_negative'] + counts['unknown_reference'] == 2 * len(first)
        by_view.append({'order': order, **{m: finish(c) for m, c in stats.items()},
                        'by_probe_class': {k: {m: finish(c) for m, c in v.items()} for k, v in classes.items()},
                        'stated_confidence_bins': confidence,
                        'author_preference_labeled_cases': preference_labeled,
                        'preference_matches_author_expectation': preference_matches})
    second_rows = {r['case_id']: r for r in views[1]['cases']}
    agreement = literary_agreement = 0; severe_disagreements = []; preference_disagreements = []; literary_disagreements = []; lengths = []
    for row in views[0]['cases']:
        cid = row['case_id']; two = second_rows[cid]
        normalize = lambda label: {'A': 'B', 'B': 'A'}.get(label, label)
        agreement += row['preferred'] == normalize(two['preferred'])
        literary_agreement += row['literary_preference'] == normalize(two['literary_preference'])
        if row['preferred'] != normalize(two['preferred']):preference_disagreements.append(cid)
        if row['literary_preference'] != normalize(two['literary_preference']):literary_disagreements.append(cid)
        if set(row['blocked']) != {normalize(x) for x in two['blocked']}:
            severe_disagreements.append(cid)
        lengths.append({'case_id': cid, 'candidate_codepoints': {k: len(v) for k, v in first[cid]['candidates'].items()},
                        'preferred_order1': row['preferred'], 'preferred_order2_normalized': normalize(two['preferred']),
                        'literary_order1': row['literary_preference'], 'literary_order2_normalized': normalize(two['literary_preference'])})
    return {'schema': 'source-calibration-summary/1', 'source_units': len(first),
            'candidate_judgments_per_view': 2 * len(first), 'by_view': by_view,
            'order_normalized_preference_agreement': agreement,
            'order_normalized_literary_preference_agreement': literary_agreement,
            'preference_disagreement_cases': preference_disagreements,
            'literary_preference_disagreement_cases': literary_disagreements,
            'severe_veto_disagreement_cases': severe_disagreements, 'preference_length_observations': lengths,
            'reference_authority': 'provisional source-grounded author controls;not human/corpus gold',
            'auto_acceptance_enabled': False, 'human_approval': False, 'default_action': 'preserve_original',
            'limitations': ['Small selected excerpts and synthetic controls;not whole-work or holdout quality.',
                           'Two histories share model capabilities;no strong model independence.',
                           'Evaluator history and presentation order vary together;agreement is diagnostic,not a causal order-bias estimate.',
                           'Unknown references are excluded from truth metrics but retained in the original denominator.',
                           'Near-one stated confidence is not calibrated probability;severity and order disagreement remain failures.',
                           'Per-class cells are too small for population precision/recall or bias claims;report counts,not spurious significance.']}
