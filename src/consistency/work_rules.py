"""Explicit, version-pinned work policies for read-only legacy review.

No default file, active-work selector, approval issuer or mutable global policy.
Selecting a policy does not validate its literary claims or permit target writes.
"""
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
import hashlib
import json
import os
import re


def _digest(value):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value) is not None


def _strings(value):
    if not isinstance(value, list) or any(not isinstance(s, str) or not s for s in value):
        raise ValueError('work rule requires a list of nonempty strings')


def _freeze(value):
    if isinstance(value, dict):
        return MappingProxyType({k: _freeze(v) for k, v in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(v) for v in value)
    return value


@dataclass(frozen=True)
class WorkRules:
    work_id: str
    source_revision: str
    language_direction: str
    sha256: str
    rules: object
    target_files: tuple = ()

    def get(self, key, default=()):
        return self.rules.get(key, default)

    def require_document(self, document):
        if not isinstance(document, dict):
            raise ValueError('explicit work/source/direction document required')
        binding = (document.get('work_id', document.get('project_id')),
                   document.get('source_revision'), document.get('language_direction'))
        if binding != (self.work_id, self.source_revision, self.language_direction):
            raise ValueError('work/source/direction does not match selected policy')
        return self


def load_work_rules(repo_root, path=None, sha256=None, *, document=None):
    if path is None:
        if sha256 is not None:
            raise ValueError('policy hash without explicit policy file')
        return None
    if not _digest(sha256) or not isinstance(document, dict):
        raise ValueError('explicit policy hash and work/source/direction binding required')
    work = document.get('work_id', document.get('project_id'))
    revision, direction = document.get('source_revision'), document.get('language_direction')
    if (not isinstance(work, str) or not work.strip() or not _digest(revision)
            or direction not in {'JP_TO_CN', 'CN_TO_JP'}):
        raise ValueError('unknown work/source/direction binding')
    root = Path(repo_root).resolve()
    selected = Path(path)
    selected = selected if selected.is_absolute() else root/selected
    if (not any(selected.resolve().is_relative_to(root/folder) for folder in ('configs', 'workspace/configs'))
            or selected.is_symlink() or any(p.is_symlink() for p in selected.parents)
            or any(p.startswith('.env') for p in selected.parts) or not selected.is_file()):
        raise ValueError('policy must be an ordinary file inside selected repository configs')
    with os.fdopen(os.open(selected, os.O_RDONLY | os.O_NOFOLLOW), 'rb') as stream:
        raw = stream.read(1024*1024+1)
    if len(raw) > 1024*1024 or hashlib.sha256(raw).hexdigest() != sha256:
        raise ValueError('work policy version mismatch or size limit')
    value = json.loads(raw)
    if (not isinstance(value, dict) or value.get('schema') != 'work-rules/1'
            or value.get('activation') != 'review_only'
            or set(value) != {'schema', 'activation', 'work_id', 'source_revision', 'language_direction', 'rules', 'target_files'}
            or not isinstance(value.get('rules'), dict)):
        raise ValueError('unverified legacy policy or unsupported activation/schema')
    rules = value['rules']
    allowed = {'auto_fix_denylist', 'source_rules', 'protected_variant_prefixes',
               'protected_variant_suffixes', 'source_prefix_exclusions', 'chapter_range',
               'legacy_refinement_targets', 'normalize_punctuation', 'term_registry', 'contextual_variants', 'audit'}
    if set(rules)-allowed:
        raise ValueError('unsupported work rule fields')
    for key in ('auto_fix_denylist', 'legacy_refinement_targets'):
        _strings(rules.get(key, []))
    for key in ('protected_variant_prefixes', 'protected_variant_suffixes', 'source_prefix_exclusions'):
        mapping = rules.get(key, {})
        if not isinstance(mapping, dict) or any(not isinstance(k, str) or not k for k in mapping):
            raise ValueError('invalid work-specific prefix/suffix mapping')
        for values in mapping.values():
            _strings(values)
    if 'normalize_punctuation' in rules and type(rules['normalize_punctuation']) is not bool:
        raise ValueError('invalid punctuation policy')
    if 'chapter_range' in rules:
        _range(rules['chapter_range'])
    rows = rules.get('source_rules', [])
    if not isinstance(rows, list):
        raise ValueError('invalid source-conditioned work rules')
    for row in rows:
        if (not isinstance(row, dict) or set(row)-{'variant','target','source','blocker_sources','segment_ids','preserve_if_present'}
                or any(not isinstance(row.get(k), str) or not row[k] for k in ('variant','target'))
                or not isinstance(row.get('source', ''), str)):
            raise ValueError('invalid source-conditioned rule')
        for key in ('blocker_sources','segment_ids','preserve_if_present'):
            _strings(row.get(key, []))
        if not row.get('source') and not row.get('segment_ids'):
            raise ValueError('unanchored work-specific replacement')
    registry = rules.get('term_registry', [])
    contexts = rules.get('contextual_variants', [])
    if not isinstance(registry, list) or not isinstance(contexts, list):
        raise ValueError('invalid work-scoped term/context rules')
    ids = set()
    for row in registry:
        if (not isinstance(row, dict) or set(row) != {'term_id','source','canonical','aliases','kind'}
                or any(not isinstance(row.get(k),str) or not row[k] for k in ('term_id','source','canonical','kind'))
                or row['term_id'] in ids):
            raise ValueError('invalid or duplicate selected term registry')
        _strings(row['aliases']);ids.add(row['term_id'])
    for row in contexts:
        if (not isinstance(row,dict) or set(row) != {'source','source_contains','target_contains_any'}
                or any(not isinstance(row[k],str) or not row[k] for k in ('source','source_contains'))):
            raise ValueError('invalid selected contextual variant')
        _strings(row['target_contains_any'])
        if not row['target_contains_any']:raise ValueError('empty contextual target evidence')
    audit=rules.get('audit',{})
    if not isinstance(audit,dict) or set(audit)-{'target_field','english_terms','protected_literals','punctuation_rules','characters','previous_issues'}:
        raise ValueError('invalid selected audit policy')
    if not isinstance(audit.get('target_field','draft_text'),str) or audit.get('target_field','draft_text') not in {'draft_text','target_text','refined_text'}:
        raise ValueError('invalid explicit audit target field')
    for key in ('english_terms','protected_literals','punctuation_rules'):
        _strings(audit.get(key,[]))
    characters=audit.get('characters',[])
    if not isinstance(characters,list):raise ValueError('invalid selected character hints')
    character_ids=set()
    for row in characters:
        if (not isinstance(row,dict) or set(row)!={'character_id','source_names','target_names','voice_markers'}
                or not isinstance(row['character_id'],str) or not row['character_id'] or row['character_id'] in character_ids):
            raise ValueError('invalid or duplicate selected character hint')
        character_ids.add(row['character_id'])
        for key in ('source_names','target_names'):_strings(row[key])
        if not row['source_names'] or not isinstance(row['voice_markers'],list):raise ValueError('unanchored character hint')
        for marker in row['voice_markers']:
            if (not isinstance(marker,dict) or set(marker)!={'source','targets'}
                    or not isinstance(marker['source'],str) or not marker['source']):raise ValueError('invalid voice marker')
            _strings(marker['targets'])
            if not marker['targets']:raise ValueError('empty target voice evidence')
    previous=audit.get('previous_issues',[])
    if not isinstance(previous,list):raise ValueError('invalid previous evidence manifest')
    evidence_paths=set()
    for row in previous:
        if (not isinstance(row,dict) or set(row)!={'path','sha256'} or not isinstance(row['path'],str)
                or not _digest(row['sha256'])):raise ValueError('invalid previous evidence version')
        selected_evidence=str(_review_path(root,row['path']).resolve())
        if selected_evidence in evidence_paths:raise ValueError('duplicate previous evidence path')
        evidence_paths.add(selected_evidence)
    targets = value['target_files']
    if not isinstance(targets,list):raise ValueError('invalid selected target manifest')
    paths=set()
    for row in targets:
        if (not isinstance(row,dict) or set(row) != {'path','sha256'} or not isinstance(row['path'],str)
                or not _digest(row['sha256']) or row['path'] in paths):
            raise ValueError('invalid selected target version')
        _target_path(root,row['path']);paths.add(row['path'])
    policy = WorkRules(value['work_id'], value['source_revision'], value['language_direction'], sha256, _freeze(rules), _freeze(targets))
    return policy.require_document(document)


def _target_path(repo_root, path):
    root=Path(repo_root).resolve();target=Path(path)
    target=target if target.is_absolute() else root/target
    if (not any(target.resolve().is_relative_to(root/'workspace'/folder) for folder in ('runs','archived_runs','candidates'))
            or target.name != 'segments.json' or target.is_symlink() or any(p.is_symlink() for p in target.parents)
            or '..' in target.parts):
        raise ValueError('unregistered or nonordinary candidate target path')
    return target


def selected_target_paths(repo_root, policy):
    if not isinstance(policy,WorkRules) or not policy.target_files:
        raise ValueError('explicit hash-bound target manifest required; no ambient run discovery')
    return [_target_path(repo_root,row['path']) for row in policy.target_files]


def read_target_document(repo_root, policy, path):
    target=_target_path(repo_root,path)
    selected={str(_target_path(repo_root,row['path']).resolve()):row['sha256'] for row in policy.target_files}
    if str(target.resolve()) not in selected or not target.is_file():
        raise ValueError('target not in selected work/version manifest')
    with os.fdopen(os.open(target,os.O_RDONLY|os.O_NOFOLLOW),'rb') as stream:
        raw=stream.read(16*1024*1024+1)
    if len(raw)>16*1024*1024 or hashlib.sha256(raw).hexdigest()!=selected[str(target.resolve())]:
        raise ValueError('selected target version mismatch or preview size limit')
    document=json.loads(raw)
    policy.require_document(document)
    return document


def _review_path(repo_root,path):
    root=Path(repo_root).resolve();selected=Path(path)
    selected=selected if selected.is_absolute() else root/selected
    if (not any(selected.resolve().is_relative_to(root/'workspace'/folder) for folder in ('review','candidates','tooling/actual_chapter_audits'))
            or selected.suffix!='.json' or '..' in selected.parts or any(p.startswith('.env') for p in selected.parts)
            or selected.is_symlink() or any(p.is_symlink() for p in selected.parents)):
        raise ValueError('unregistered or nonordinary previous evidence path')
    return selected


def read_previous_review(repo_root,policy,path):
    if not isinstance(policy,WorkRules):raise ValueError('explicit work policy required before evidence read')
    selected=_review_path(repo_root,path)
    manifest={str(_review_path(repo_root,row['path']).resolve()):row['sha256']
              for row in policy.get('audit',{}).get('previous_issues',())}
    if str(selected.resolve()) not in manifest or not selected.is_file():raise ValueError('previous report not selected')
    with os.fdopen(os.open(selected,os.O_RDONLY|os.O_NOFOLLOW),'rb') as stream:raw=stream.read(4*1024*1024+1)
    if len(raw)>4*1024*1024 or hashlib.sha256(raw).hexdigest()!=manifest[str(selected.resolve())]:
        raise ValueError('previous evidence version mismatch or size limit')
    value=json.loads(raw);policy.require_document(value)
    if value.get('schema')!='work-review-input/1' or not isinstance(value.get('issues'),list):
        raise ValueError('unversioned previous issue report')
    versions=value.get('target_files');allowed={str(_target_path(repo_root,row['path']).resolve()) for row in policy.target_files}
    if not isinstance(versions,list) or not versions:raise ValueError('missing previous target versions')
    seen=set()
    for row in versions:
        if not isinstance(row,dict) or set(row)!={'path','sha256'} or not isinstance(row['path'],str) or not _digest(row['sha256']):
            raise ValueError('invalid previous target version')
        target=str(_target_path(repo_root,row['path']).resolve())
        if target not in allowed or target in seen:raise ValueError('foreign or duplicate previous target scope')
        seen.add(target)
    for issue in value['issues']:
        if not isinstance(issue,dict) or not isinstance(issue.get('segment_id'),str) or not issue['segment_id']:
            raise ValueError('invalid previous issue identity')
        for key in ('description','suggested_fix'):
            if key in issue and not isinstance(issue[key],str):raise ValueError('invalid previous issue text')
    return value


def add_work_rule_arguments(parser):
    parser.add_argument('--work-rules', type=Path, default=None)
    parser.add_argument('--work-rules-sha256', default=None)
    parser.add_argument('--work-id', default=None)
    parser.add_argument('--source-revision', default=None)
    parser.add_argument('--language-direction', choices=('JP_TO_CN','CN_TO_JP'), default=None)


def policy_from_arguments(args, repo_root, *, document=None):
    hinted = {'work_id':args.work_id, 'source_revision':args.source_revision,
              'language_direction':args.language_direction}
    if document is not None:
        for key, value in hinted.items():
            actual = document.get(key, document.get('project_id') if key == 'work_id' else None)
            if value is not None and value != actual:
                raise ValueError('explicit policy binding conflicts with target document')
    return load_work_rules(repo_root, args.work_rules, args.work_rules_sha256,
                           document=document if document is not None else hinted)


def _range(value):
    if (not isinstance(value, (list,tuple)) or len(value) != 2
            or any(type(n) is not int or n < 0 for n in value) or value[0] > value[1]):
        raise ValueError('invalid explicitly selected chapter range')
    return tuple(value)


def selected_chapter_range(args, policy):
    configured = policy.get('chapter_range', None) if policy else None
    if args.chapters is None and configured is None:
        raise ValueError('explicit chapter range or selected work policy required')
    if args.chapters is not None and configured is not None and _range(args.chapters) != _range(configured):
        raise ValueError('chapter range conflicts with selected work policy')
    return _range(configured if configured is not None else args.chapters)
