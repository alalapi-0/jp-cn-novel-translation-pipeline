"""Bounded preceding source context from the selected immutable source snapshot.

This describes textual chronology, not semantic facts or translation approval.
No filesystem, target text, asset store, current batch or future source is read.
"""
from dataclasses import dataclass
from types import MappingProxyType
import hashlib
import json


def _hash(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def source_anchor_identity(segment):
    """Identify the current text and its validated source binding, if present."""
    if (not isinstance(segment.segment_id,str) or not segment.segment_id
            or not isinstance(segment.source_text,str) or not segment.source_text.strip()):
        raise ValueError('invalid current source context anchor')
    binding=getattr(segment,'source_binding',None)
    if binding is not None:
        from .source_versions import validate_source_binding
        binding=validate_source_binding(binding,segment.source_text)['binding_sha256']
    return (segment.segment_id,hashlib.sha256(segment.source_text.encode()).hexdigest(),binding)


@dataclass(frozen=True)
class SourceContextPolicy:
    max_segments: int = 3
    max_chars: int = 1200

    def __post_init__(self):
        if any(type(n) is not int or n < 0 for n in (self.max_segments,self.max_chars)):
            raise ValueError('source context window requires nonnegative integer bounds')

    def identity(self):
        return {'schema':'preceding-source-policy/1','max_segments':self.max_segments,'max_chars':self.max_chars}


@dataclass(frozen=True)
class PrecedingSourceContext:
    anchor: tuple
    items: tuple
    policy: SourceContextPolicy
    source_catalog_sha256: str
    current_anchors: tuple

    def to_dict(self):
        value={'schema':'preceding-source-context/1','scope':'selected_source_only',
            'anchor':{'chapter_id':self.anchor[0],'segment_id':self.anchor[1]},
            'policy':self.policy.identity(),'source_catalog_sha256':self.source_catalog_sha256,
            'items':[{'chapter_id':ch,'segment_id':sid,'source_text':text,'source_start_char':start,
                      'source_end_char':end,'source_sha256':sha} for ch,sid,text,start,end,sha in self.items]}
        return {**value,'sha256':_hash(value)}


@dataclass(frozen=True,init=False)
class SourceContextCatalog:
    """A read-only snapshot; translated or manually edited targets never enter it."""
    _rows: tuple
    _positions: object
    _bindings: tuple
    sha256: str
    def __init__(self,chapters):
        rows=[];positions={};chapter_ids=set();versions=[];pins=[]
        for chapter in chapters:
            if not isinstance(chapter.chapter_id,str) or not chapter.chapter_id or chapter.chapter_id in chapter_ids:
                raise ValueError('ambiguous context chapter identity')
            chapter_ids.add(chapter.chapter_id)
            from .source_versions import validate_source_binding
            bindings=[]
            for segment in chapter.segments:
                if (not isinstance(segment.segment_id,str) or not segment.segment_id or segment.segment_id in positions
                        or not isinstance(segment.source_text,str) or not segment.source_text.strip()):
                    raise ValueError('ambiguous or empty source context segment')
                positions[segment.segment_id]=len(rows)
                rows.append((chapter.chapter_id,segment.segment_id,segment.source_text))
                binding=getattr(segment,'source_binding',None)
                if binding is not None:
                    binding=validate_source_binding(binding,segment.source_text)
                    if binding['chapter_id']!=chapter.chapter_id or binding['source_revision']!=chapter.source_revision:
                        raise ValueError('context source binding differs from selected chapter')
                elif getattr(chapter,'source_revision',''):
                    raise ValueError('versioned context chapter has an unbound segment')
                bindings.append(binding['binding_sha256'] if binding else None)
                pins.append(bindings[-1])
            versions.append([chapter.chapter_id,getattr(chapter,'source_revision',''),
                             getattr(chapter,'parser_version',''),bindings])
        object.__setattr__(self,'_rows',tuple(rows))
        object.__setattr__(self,'_positions',MappingProxyType(positions))
        object.__setattr__(self,'_bindings',tuple(pins))
        object.__setattr__(self,'sha256',_hash({'rows':self._rows,'source_versions':versions}))

    def identity(self,policy):
        return {'policy':policy.identity(),'source_catalog_sha256':self.sha256}

    def before(self,segments,policy=None):
        policy=SourceContextPolicy() if policy is None else policy
        if not isinstance(policy,SourceContextPolicy):raise ValueError('explicit source context policy required')
        if not segments:raise ValueError('nonempty current source anchor required')
        indexes=[];anchors=[]
        for segment in segments:
            identity=source_anchor_identity(segment);index=self._positions.get(identity[0])
            if index is None or self._rows[index][2]!=segment.source_text or self._bindings[index]!=identity[2]:
                raise ValueError('current batch differs from selected source context snapshot')
            indexes.append(index);anchors.append(identity)
        if indexes!=sorted(set(indexes)):raise ValueError('current context anchors are duplicate or unordered')
        anchor=indexes[0];remaining=policy.max_chars;items=[]
        if policy.max_segments and remaining:
            for ch,sid,text in reversed(self._rows[max(0,anchor-policy.max_segments):anchor]):
                if not remaining:break
                start=max(0,len(text)-remaining);part=text[start:];remaining-=len(part)
                items.append((ch,sid,part,start,len(text),hashlib.sha256(text.encode()).hexdigest()))
        return PrecedingSourceContext(self._rows[anchor][:2],tuple(reversed(items)),policy,self.sha256,tuple(anchors))
