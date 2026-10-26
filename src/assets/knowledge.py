"""Evidence-bearing knowledge candidates; never fact or approval authority.

Coordinates are half-open Unicode codepoints in an immutable source catalog.
Exact quotes establish location only. Free-standing propositions never enter a
translation prompt: the adapter releases original quotes through the existing
NarrativeContextCatalog and its per-segment textual-time/speaker limits.
"""
from dataclasses import dataclass
from copy import deepcopy
import hashlib
import json


def _text(nullable=False):
    return {'type':['string','null'] if nullable else 'string',**({} if nullable else {'minLength':1})}


_EVIDENCE = {'type':'object','additionalProperties':False,
    'required':['source_catalog_sha256','chapter_id','segment_id','source_sha256','start_char','end_char','quote'],
    'properties':{'source_catalog_sha256':{'type':'string','pattern':'^[0-9a-f]{64}$'},
        'chapter_id':_text(),'segment_id':_text(),'source_sha256':{'type':'string','pattern':'^[0-9a-f]{64}$'},
        'start_char':{'type':'integer','minimum':0},'end_char':{'type':'integer','minimum':1},'quote':_text()}}
_DEFAULTS={'schema':'knowledge-claim/1','epistemic_status':'unknown','confidence':None,'producer':'unknown',
    'evidence':[],'effective_from':None,'effective_until':None,'subject_id':None,'object_id':None,
    'predicate':None,'speaker_id':None,'slot':None,'alternatives':[],'withdrawn':False,'semantic_truth':'not_verified'}
_PROPERTIES={'schema':{'const':'knowledge-claim/1'},'claim_id':_text(),
    'category':{'enum':['glossary','character','world','summary','relationship','address','creative_pattern','unknown']},
    'statement':{'type':'string'},'epistemic_status':{'enum':['assertion','inference','unknown']},
    'confidence':{'type':['number','null'],'minimum':0,'maximum':1},
    'producer':{'enum':['model','rule','import','owner','unknown']},'evidence':{'type':'array','maxItems':8,'items':_EVIDENCE},
    **{k:_text(True) for k in ['effective_from','effective_until','subject_id','object_id','predicate','speaker_id','slot']},
    'alternatives':{'type':'array','maxItems':16,'items':{'type':'object','additionalProperties':False,
        'required':['target','condition'],'properties':{'target':_text(),'condition':_text()}}},
    'withdrawn':{'type':'boolean'},'semantic_truth':{'const':'not_verified'}}


def knowledge_schema():
    """Embedded in existing schemas so validation never needs a remote resolver."""
    return deepcopy({'type':'object','additionalProperties':False,
        'required':['claim_id','category','statement'],'properties':_PROPERTIES})


@dataclass(frozen=True,init=False)
class KnowledgeClaim:
    _serialized:str

    def __init__(self, value):
        import jsonschema
        if type(value) is not dict:raise ValueError('knowledge claim must be an object')
        row={**deepcopy(_DEFAULTS),**deepcopy(value)}
        try:jsonschema.validate(row,knowledge_schema())
        except jsonschema.ValidationError:raise ValueError('invalid knowledge candidate metadata') from None
        object.__setattr__(self,'_serialized',json.dumps(row,ensure_ascii=False,sort_keys=True,allow_nan=False))

    def to_dict(self):return json.loads(self._serialized)

    @property
    def sha256(self):return hashlib.sha256(self._serialized.encode()).hexdigest()


def model_claims(value, *, asset_id):
    """Retain compatible model suggestions without inheriting truth/approval."""
    if type(value) is not list:return []
    result=[]
    for index,item in enumerate(value[:16]):
        if type(item) is not dict:continue
        row={k:v for k,v in item.items() if k in _PROPERTIES}
        row.update(producer='model',semantic_truth='not_verified')
        row.setdefault('claim_id',f'{asset_id}:model:{index}')
        row.setdefault('category','unknown');row.setdefault('statement','')
        try:claim=KnowledgeClaim(row)
        except (ValueError,TypeError):
            # Keep a traceable unknown candidate, never fabricate missing proof.
            claim=KnowledgeClaim({'claim_id':f'{asset_id}:model:{index}','category':'unknown',
                'statement':item.get('statement') if type(item.get('statement')) is str else '',
                'producer':'model','epistemic_status':'unknown'})
        result.append(claim.to_dict())
    return result


def build_knowledge_context(source, claims, *, policy=None):
    """Adapt compatible active assertions to exact source quotes, never claims.

    Inferences, unknowns, withdrawn claims and missing scopes stay withheld.
    Invalid/stale asserted evidence refuses context construction before dispatch.
    This establishes textual provenance, not semantic or human acceptance.
    """
    from translation.context_policy import SourceContextCatalog
    from translation.narrative_context import ContextFact,NarrativeContextCatalog
    if not isinstance(source,SourceContextCatalog):raise ValueError('immutable source catalog required')
    facts=[];seen=set()
    for raw in claims:
        claim=raw if type(raw) is KnowledgeClaim else KnowledgeClaim(raw)
        row=claim.to_dict();cid=row['claim_id']
        if cid in seen:raise ValueError('duplicate knowledge claim identity')
        seen.add(cid)
        if (row['withdrawn'] or row['epistemic_status']!='assertion' or not row['evidence']
                or row['effective_from'] is None):continue
        for index,evidence in enumerate(row['evidence']):
            pos=source._positions.get(evidence['segment_id'])
            if pos is None:raise ValueError('unknown knowledge evidence source')
            chapter,_,text=source._rows[pos]
            start=evidence['start_char'];end=evidence['end_char']
            if (evidence['source_catalog_sha256']!=source.sha256 or chapter!=evidence['chapter_id']
                    or evidence['source_sha256']!=hashlib.sha256(text.encode()).hexdigest()
                    or not 0<=start<end<=len(text) or text[start:end]!=evidence['quote']):
                raise ValueError('knowledge evidence differs from frozen source')
            facts.append(ContextFact(f'{cid}:{index}',evidence['segment_id'],evidence['source_sha256'],
                start,end,evidence['quote'],row['effective_from'],row['effective_until'],
                row['speaker_id'],row['slot']))
    return NarrativeContextCatalog(source,facts=facts,policy=policy)
