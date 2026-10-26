#!/usr/bin/env python3
"""Build a content-first audit for a chapter range.

This report intentionally treats glossary/profile data as hints, not truth.
It reads only explicitly selected, hash-pinned candidate inputs. All rules are
work-scoped hints; observations and previous surface relations never imply
semantic acceptance, canonical authority or human approval.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import os
import tempfile

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "src"))

from consistency.work_rules import (WorkRules, add_work_rule_arguments, policy_from_arguments,
    selected_chapter_range, selected_target_paths, read_target_document, read_previous_review)

BRACKETS = "【】"
KANA_RUN_RE = re.compile(r"[\u3041-\u3096\u30a1-\u30fa\u30fc]{1,}")
KATAKANA_TERM_RE = re.compile(r"[\u30a1-\u30fa\u30fc]{2,}(?:[A-Za-z0-9]+)?")
PLACEHOLDER_RE = re.compile(r"[□�]")
CHAPTER_ID_RE = re.compile(r"ch-(\d+)")
KANA_CHARS = set(chr(c) for c in range(0x3040, 0x3100))
ASCII_QUOTE_RE = re.compile(r"[\"“”‘’]")
ASCII_ELLIPSIS_RE = re.compile(r"\.\.\.")
ENGLISH_TOKEN_RE = re.compile(r"\b([A-Za-z]{3,})\b")
DIALOGUE_MARKERS = ("「", "『", "」", "』")


def source_occurs_as_term(source: str, text: str) -> bool:
    """Return true when a source hint occurs as its own kana term.

    Boundary matching is a heuristic observation, not lexical or semantic proof.
    """
    if not source or source not in text:
        return False
    if not any(ch in KANA_CHARS for ch in source):
        return True
    start = 0
    while True:
        idx = text.find(source, start)
        if idx == -1:
            return False
        before = text[idx - 1] if idx > 0 else ""
        after_idx = idx + len(source)
        after = text[after_idx] if after_idx < len(text) else ""
        if before not in KANA_CHARS and after not in KANA_CHARS:
            return True
        start = idx + len(source)


def is_allowed_contextual_hint(source, src, tgt, work_rules=None):
    return bool(work_rules and any(row['source']==source and row['source_contains'] in src
        and any(text in tgt for text in row['target_contains_any'])
        for row in work_rules.get('contextual_variants')))


def is_protected_literal_source_residual(src, tgt, tokens, work_rules=None):
    literals=work_rules.get('audit',{}).get('protected_literals',()) if work_rules else ()
    return any(text in src and text in tgt and all(token in text for token in tokens) for text in literals)


def _collect_english_tokens(text: str) -> set[str]:
    return {token.lower() for token in ENGLISH_TOKEN_RE.findall(text or "")}


def _load_english_term_allowlist(work_rules=None):
    # An explanation hint, never a cache or an instruction to omit an observation.
    return {text.lower() for text in work_rules.get('audit',{}).get('english_terms',())} if work_rules else set()


def _load_style_punctuation_rules(work_rules=None):
    return list(work_rules.get('audit',{}).get('punctuation_rules',())) if work_rules else []


def _contains_dialogue_markup(text: str) -> bool:
    return any(marker in text for marker in DIALOGUE_MARKERS)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def chapter_num(raw: str) -> int | None:
    m = CHAPTER_ID_RE.search(raw or "")
    return int(m.group(1)) if m else None


def cn_text(seg):
    return seg.get(seg.get('_target_field','draft_text')) or ''


def strip_brackets(raw: str) -> str:
    return (raw or "").strip().strip(BRACKETS).strip()


def clip(text: str, needle: str = "", *, width: int = 140) -> str:
    text = " ".join((text or "").split())
    if not text or len(text) <= width:
        return text
    if needle and needle in text:
        pos = text.find(needle)
        start = max(0, pos - width // 2)
        end = min(len(text), start + width)
        start = max(0, end - width)
        prefix = "..." if start else ""
        suffix = "..." if end < len(text) else ""
        return prefix + text[start:end] + suffix
    return text[: width - 3] + "..."


def load_segments(start, end, work_rules=None):
    if not isinstance(work_rules,WorkRules):raise ValueError('explicit selected work policy required before run reads')
    out={};field=work_rules.get('audit',{}).get('target_field','draft_text')
    for path in selected_target_paths(REPO_ROOT,work_rules):
        doc=read_target_document(REPO_ROOT,work_rules,path)
        chapters=doc.get('chapters')
        if not isinstance(chapters,list) or not chapters:raise ValueError('missing selected chapter inventory')
        for chapter in chapters:
            if not isinstance(chapter,dict):raise ValueError('invalid chapter record')
            cid=chapter.get('chapter_id')
            if not isinstance(cid,str) or not re.fullmatch(r'ch-\d+',cid):raise ValueError('invalid chapter identity')
            num=chapter_num(cid)
            if not start<=num<=end:continue
            segments=chapter.get('segments')
            if not isinstance(segments,list) or not segments:raise ValueError('empty selected chapter')
            for seg in segments:
                if not isinstance(seg,dict):raise ValueError('invalid selected segment')
                sid=seg.get('segment_id')
                if not isinstance(sid,str) or not sid or sid in out:raise ValueError('missing or duplicate selected segment identity')
                if not isinstance(seg.get('source_text'),str) or not seg['source_text'].strip():raise ValueError('empty or invalid selected source')
                if field in seg and not isinstance(seg[field],str):raise ValueError('invalid selected target text')
                out[sid]={**seg,'_chapter_id':cid,'_run_file':str(path.relative_to(REPO_ROOT)),
                          '_target_field':field,'_source_revision':work_rules.source_revision}
    if not out:raise ValueError('no segments in explicitly selected scope')
    return out


def target_punctuation_residuals(segments,work_rules=None):
    rows=[]
    for sid,seg in segments.items():
        text=cn_text(seg);surfaces=[]
        if ASCII_QUOTE_RE.search(text):surfaces.append('quote_surface')
        if ASCII_ELLIPSIS_RE.search(text):surfaces.append('three_dot_ellipsis_surface')
        if '《' in text or '》' in text:
            surfaces.append('angle_bracket_surface')
            if text.count('《')!=text.count('》'):surfaces.append('unequal_angle_bracket_counts')
        if surfaces:rows.append({'chapter_id':seg['_chapter_id'],'segment_id':sid,'issues':surfaces,
            'source_ref':clip(seg.get('source_text') or ''),'target_ref':clip(text),
            'policy_hints':_load_style_punctuation_rules(work_rules),'interpretation':'surface_observation_not_style_verdict'})
    return rows


def target_english_residuals(segments,work_rules=None):
    rows=[];explained=_load_english_term_allowlist(work_rules)
    for sid,seg in segments.items():
        src=seg.get('source_text') or '';tgt=cn_text(seg);tokens=sorted(set(ENGLISH_TOKEN_RE.findall(tgt)))
        if not tokens:continue
        source_tokens=_collect_english_tokens(src)
        rows.append({'chapter_id':seg['_chapter_id'],'segment_id':sid,'english_tokens':tokens,
            'present_in_source':[t for t in tokens if t.lower() in source_tokens],
            'policy_explained_tokens':[t for t in tokens if t.lower() in explained],
            'source_ref':clip(src),'target_ref':clip(tgt),'recommended_action':'review_context_before_classification'})
    return rows


def _load_character_voice_profiles(work_rules=None):
    return work_rules.get('audit',{}).get('characters',()) if work_rules else ()


def _character_hit(character,text):
    return any(name in text for name in character['source_names'])


def detect_voice_style_drift(segments,work_rules=None):
    rows=[]
    for sid,seg in segments.items():
        src=seg.get('source_text') or '';tgt=cn_text(seg)
        if not src or not tgt or not _contains_dialogue_markup(src):continue
        for character in _load_character_voice_profiles(work_rules):
            if not _character_hit(character,src):continue
            missing=[marker for marker in character['voice_markers']
                     if marker['source'] in src and not any(text in tgt for text in marker['targets'])]
            if missing:rows.append({'chapter_id':seg['_chapter_id'],'segment_id':sid,
                'character_id':character['character_id'],'source_markers':[m['source'] for m in missing],
                'target_marker_hints':[list(m['targets']) for m in missing],
                'source_ref':clip(src),'target_ref':clip(tgt),'interpretation':'selected_voice_hint_needs_context_review'})
    return rows


def build_registry_hints(work_rules=None):
    if not isinstance(work_rules,WorkRules):raise ValueError('explicit selected registry policy required')
    return [{'term_id':row['term_id'],'kind':row['kind'],'source':row['source'],'target':row['canonical'],
             'known_variants':list(row['aliases'])} for row in work_rules.get('term_registry')]


def actual_kana_candidates(segments: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}
    for sid, seg in segments.items():
        src = seg.get("source_text") or ""
        tgt = cn_text(seg)
        for token in KATAKANA_TERM_RE.findall(src):
            bucket = buckets.setdefault(
                token,
                {
                    "source_token": token,
                    "count": 0,
                    "chapters": set(),
                    "samples": [],
                },
            )
            bucket["count"] += 1
            bucket["chapters"].add(seg["_chapter_id"])
            if len(bucket["samples"]) < 6:
                bucket["samples"].append(
                    {
                        "segment_id": sid,
                        "source_ref": clip(src, token),
                        "target_ref": clip(tgt),
                    }
                )
    out = []
    for bucket in buckets.values():
        row = dict(bucket)
        row["chapters"] = sorted(row["chapters"])
        out.append(row)
    out.sort(key=lambda r: (-r["count"], r["source_token"]))
    return out


def target_kana_residuals(segments,work_rules=None):
    if work_rules and work_rules.language_direction=='CN_TO_JP':return []
    rows=[]
    for sid,seg in segments.items():
        tgt=cn_text(seg);tokens=sorted(set(KANA_RUN_RE.findall(tgt)))
        if tokens:rows.append({'chapter_id':seg['_chapter_id'],'segment_id':sid,'kana_tokens':tokens,
            'source_ref':clip(seg.get('source_text') or ''),'target_ref':clip(tgt,tokens[0]),
            'selected_literal_explanation':is_protected_literal_source_residual(seg.get('source_text') or '',tgt,tokens,work_rules)})
    return rows


def target_placeholder_residuals(segments: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for sid, seg in segments.items():
        tgt = cn_text(seg)
        tokens = sorted(set(PLACEHOLDER_RE.findall(tgt)))
        if not tokens:
            continue
        rows.append(
            {
                "chapter_id": seg["_chapter_id"],
                "segment_id": sid,
                "placeholder_tokens": tokens,
                "source_ref": clip(seg.get("source_text") or ""),
                "target_ref": clip(tgt, tokens[0]),
            }
        )
    return rows


VARIANT_PATTERNS = [
    re.compile(r"forbidden/alias「([^」]+)」"),
    re.compile(r"误译为「([^」]+)」"),
    re.compile(r"仍出现[^「]*「([^」]+)」"),
]
EXPECTED_TARGET_RE = re.compile(r"应译为「([^」]+)」")
RULE_TARGET_RE = re.compile(r"→「([^」]+)」")


def extract_variant(issue: dict[str, Any]) -> str:
    text = issue.get("description") or ""
    for pattern in VARIANT_PATTERNS:
        m = pattern.search(text)
        if m:
            return m.group(1)
    return ""


def revalidate_previous_issues(segments,previous_path,work_rules=None):
    if previous_path is None:return None
    previous=read_previous_review(REPO_ROOT,work_rules,previous_path);rows=[];counts=Counter()
    for issue in previous['issues']:
        sid=issue['segment_id'];seg=segments.get(sid);current=cn_text(seg) if seg else ''
        suggested=issue.get('suggested_fix') or '';variant=extract_variant(issue)
        expected=EXPECTED_TARGET_RE.search(issue.get('description') or '')
        rule=RULE_TARGET_RE.search(issue.get('description') or '')
        hint=expected.group(1) if expected else rule.group(1) if rule else ''
        if not seg:status='outside_current_segment_scope'
        elif suggested and ' '.join(current.split())==' '.join(suggested.split()):status='surface_equals_previous_suggestion'
        elif hint:status='previous_hint_present' if hint in current else 'previous_hint_absent'
        elif variant:status='previous_variant_present' if variant in current else 'previous_variant_absent'
        else:status='unclassified_surface_relation'
        counts[status]+=1
        rows.append({'issue_id':issue.get('issue_id'),'issue_type':issue.get('issue_type'),
            'chapter_id':seg.get('_chapter_id') if seg else issue.get('chapter_id'),'segment_id':sid,
            'current_status':status,'previous_status_is_unverified':True,'variant_checked':variant or None,
            'expected_target_hint':hint or None,'current_target_ref':clip(current,variant or hint),
            'interpretation':'surface_comparison_only_not_semantic_resolution'})
    return {'summary':dict(sorted(counts.items())),'issues':rows,'previous_target_versions':previous['target_files'],
            'source_revision':work_rules.source_revision,'acceptance':'not_evaluated'}


def registry_hint_observations(
    segments: dict[str, dict[str, Any]],
    hints: list[dict[str, Any]],
    work_rules=None,
) -> list[dict[str, Any]]:
    observed: dict[str, dict[str, Any]] = {}
    for hint in hints:
        source = hint["source"]
        target = hint["target"]
        variants = [v for v in hint.get("known_variants", []) if v and v != target]
        for sid, seg in segments.items():
            src = seg.get("source_text") or ""
            if source not in src:
                continue
            tgt = cn_text(seg)
            explained=is_allowed_contextual_hint(source,src,tgt,work_rules)
            surfaces = []
            if target in tgt:
                surfaces.append(target)
            surfaces.extend(v for v in variants if v in tgt)
            if not surfaces:
                surfaces.append("UNOBSERVED_BY_HINTS")
            key = hint.get('term_id') or f"{hint['kind']}:{source}:{target}"
            row = observed.setdefault(
                key,
                {
                    "source": source,
                    "term_id": hint.get('term_id'),
                    "hint_target": target,
                    "hint_kind": hint["kind"],
                    "surface_counts": Counter(),
                    "samples": defaultdict(list),
                    "context_explanations": [],
                },
            )
            if explained:row['context_explanations'].append({'segment_id':sid,'policy_sha256':work_rules.sha256 if work_rules else None})
            for surface in surfaces:
                row["surface_counts"][surface] += 1
                if len(row["samples"][surface]) < 5:
                    row["samples"][surface].append(
                        {
                            "chapter_id": seg["_chapter_id"],
                            "target_file": seg.get("_run_file"),
                            "segment_id": sid,
                            "source_ref": clip(src, source),
                            "target_ref": clip(tgt, surface if surface != "UNOBSERVED_BY_HINTS" else ""),
                            "source_match": "substring_hint_not_semantic_identity",
                            "standalone_heuristic": source_occurs_as_term(source,src),
                        }
                    )

    out = []
    for row in observed.values():
        surfaces = dict(row["surface_counts"])
        out.append(
            {
                "source": row["source"],
                "term_id": row['term_id'],
                "hint_target": row["hint_target"],
                "hint_kind": row["hint_kind"],
                "surface_counts": surfaces,
                "context_explanations": row["context_explanations"],
                "samples": {k: v for k, v in row["samples"].items()},
                "interpretation": "hint_only_not_authoritative",
            }
        )
    out.sort(key=lambda r: (-sum(r["surface_counts"].values()), r["source"]))
    return out


def _report_path(path):
    root=REPO_ROOT.resolve();selected=path if path.is_absolute() else root/path
    if (not any(selected.resolve().is_relative_to(root/'workspace'/folder) for folder in ('tooling/actual_chapter_audits','review/audits'))
            or selected.suffix!='.json' or '..' in selected.parts or selected.is_symlink()
            or any(p.is_symlink() for p in selected.parents) or selected.exists()):
        raise ValueError('audit output must be a new ordinary report in dedicated audit output roots')
    return selected


def _write_report(path,report):
    # Publish a complete new report; never replace an input, prior report or manual edit.
    path=_report_path(path);path.parent.mkdir(parents=True,exist_ok=True)
    raw=(json.dumps(report,ensure_ascii=False,indent=2)+'\n').encode()
    fd,tmp=tempfile.mkstemp(prefix='.audit-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
        os.link(tmp,path)
    finally:
        Path(tmp).unlink(missing_ok=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--chapters',type=int,nargs=2,default=None)
    add_work_rule_arguments(parser)
    parser.add_argument('--previous-issues',type=Path,default=None)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    try:
        policy=policy_from_arguments(args,REPO_ROOT)
        if policy is None:raise ValueError('explicit version-pinned work policy required')
        start,end=selected_chapter_range(args,policy)
        output=_report_path(args.output)
        segments=load_segments(start,end,policy)
        previous=revalidate_previous_issues(segments,args.previous_issues,policy)
    except (ValueError,OSError) as error:parser.error(str(error))
    direction=policy.language_direction
    kana=target_kana_residuals(segments,policy)
    punctuation=target_punctuation_residuals(segments,policy)
    placeholder=target_placeholder_residuals(segments)
    english=target_english_residuals(segments,policy)
    voice=detect_voice_style_drift(segments,policy)
    candidates=actual_kana_candidates(segments) if direction=='JP_TO_CN' else []
    registry=registry_hint_observations(segments,build_registry_hints(policy),policy)
    missing=[{'chapter_id':seg['_chapter_id'],'segment_id':sid,'source_ref':clip(seg['source_text']),
              'target_ref':'','interpretation':'selected_target_field_missing_or_blank'}
             for sid,seg in segments.items() if not cn_text(seg).strip()]
    groups={'target_kana_residuals':kana,'target_placeholder_residuals':placeholder,
            'target_english_residuals':english,'target_punctuation_residuals':punctuation,
            'character_voice_style_residuals':voice,'registry_hint_observations':registry,'target_missing_content':missing}
    for kind,rows in groups.items():
        for row in rows:
            row.update(observation_type=kind,severity='unclassified',confidence='uncalibrated',
                       work_rules_sha256=policy.sha256,source_revision=policy.source_revision)
            sid=row.get('segment_id')
            if sid in segments:row['target_file']=segments[sid]['_run_file']
    report={'schema':'actual_chapter_content_audit.v2','generated_at':utc_now(),'mode':'review_only',
        'work_id':policy.work_id,'source_revision':policy.source_revision,'language_direction':direction,
        'work_rules_sha256':policy.sha256,'target_files':[dict(row) for row in policy.target_files],
        'target_field':policy.get('audit',{}).get('target_field','draft_text'),
        'chapter_range':[start,end],'method':'selected_versioned_candidates_and_hints_only',
        'acceptance':'not_evaluated','segments_total':len(segments),'previous_issue_revalidation':previous,
        **{name:{'count':len(rows),'items':rows} for name,rows in groups.items()},
        'style_profile_snippet':{'items':_load_style_punctuation_rules(policy),'interpretation':'selected_hint_only'},
        'source_katakana_candidates':{'direction_applicable':direction=='JP_TO_CN','unique_terms':len(candidates),'top':candidates[:80]}}
    report['target_kana_residuals']['direction_applicable']=direction=='JP_TO_CN'
    _write_report(output,report)
    print(json.dumps({'mode':'review_only','acceptance':'not_evaluated','segments_total':len(segments),
        'chapter_range':[start,end],**{name:len(rows) for name,rows in groups.items()}},ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
