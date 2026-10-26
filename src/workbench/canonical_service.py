"""Versioned Workbench import/selection, sharing canonical export domain checks.

Import is untrusted and never issues a reviewer identity. Existing trusted local
Agent/PSH decisions are required separately before a version can be selected.
"""
from __future__ import annotations
import hashlib
import json
import os
import re
from pathlib import Path
import tempfile
from difflib import unified_diff

from translation.chapter_parser import parse_chapter_file
from translation.canonical_export import build_accepted_revision, validate_accepted_revision
from workbench.project_id import validate_project_id
from workbench.project_registry import (build_source_inventory, get_project_manifest, manifests_dir,
    _project_write_lock, _save_project_manifest_unlocked, ManifestWriteInProgressError, parse_project_manifest)
from workbench.review_state import (DecisionActor, get_project_review_state, approval_identity,
    review_decision_summary, review_state_path)


class CanonicalVersionConflict(ValueError):
    pass


def _ordinary(path):
    if path.is_symlink() or any(p.is_symlink() for p in path.parents):
        raise ValueError('unmanaged project path preserved')
    return path


def _path(root, project):
    return _ordinary(manifests_dir(root)/f'{validate_project_id(project)}.json')


def _read(root, project, expected=None):
    path=_path(root,project)
    if not path.is_file():raise ValueError('unknown project_id')
    raw=path.read_bytes();digest=hashlib.sha256(raw).hexdigest()
    if expected is not None and digest != expected:raise CanonicalVersionConflict('版本已变化，请刷新后重试；原文件已保留。')
    data=json.loads(raw)
    if not isinstance(data,dict) or data.get("project_id")!=project: raise ValueError("project identity differs from selected manifest")
    from workbench.project_registry import _resolve_manifest_dependencies
    data=_resolve_manifest_dependencies(Path(root),data)
    return path,raw,data,digest


def _archive(root,project,raw):
    digest=hashlib.sha256(raw).hexdigest()
    path=_ordinary(manifests_dir(root)/'.versions'/project/(digest+'.json'));path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():
        if path.read_bytes()!=raw:raise ValueError('saved candidate recovery version changed')
    else:
        with path.open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
    return digest


def import_sources(root, *, project_id, name, language_direction, chapters):
    root=Path(root);project_id=validate_project_id(project_id)
    if language_direction not in {'JP_TO_CN','CN_TO_JP'}:raise ValueError('invalid language direction')
    if not isinstance(chapters,list) or not chapters:raise ValueError('请选择至少一个完整源章节文件。')
    prepared=[];rows=[];documents=[];ids=set();names=set()
    prefix='input_jp' if language_direction=='JP_TO_CN' else 'input_cn'
    source_root=_ordinary(root/prefix/project_id)
    for chapter in chapters:
        if not isinstance(chapter,dict) or set(chapter)!={'filename','text'}:raise ValueError('source chapter requires filename/text only')
        filename=chapter['filename'];text=chapter['text']
        if (not isinstance(filename,str) or Path(filename).name!=filename or filename in names
                or Path(filename).suffix.lower() not in {'.md','.txt'}
                or not isinstance(text,str) or not text.strip()):raise ValueError('章节文件必须非空且名称唯一（.md/.txt）。')
        names.add(filename);raw=text.encode();path=source_root/filename
        parsed=parse_chapter_file(path,source_bytes=raw)
        if parsed.chapter_id in ids or not parsed.segments:raise ValueError('空章或重复章节编号；未导入任何内容。')
        ids.add(parsed.chapter_id);prepared.append((path,raw))
        documents.append({'chapter_id':parsed.chapter_id,'path':str(path.relative_to(root)),'source_revision':parsed.source_revision})
        rows.extend({'id':s.segment_id,'source':s.source_text,'source_binding':s.source_binding,'draft':'','status':'pending','generated_by':'imported_source'} for s in parsed.segments)
    data={'project_id':project_id,'name':str(name or project_id),'language_direction':language_direction,'status':'source_imported','chapters':len(chapters),
          'segments':rows,'source_inventory':build_source_inventory(rows,language_direction=language_direction,origin='workbench_source_import'),
          'source_documents':documents,'generation_mode':'agent_quota_translation','generation_state':'awaiting_bound_candidate_import'}
    lock=_project_write_lock(project_id)
    if not lock.acquire(blocking=False):raise ManifestWriteInProgressError('project import in progress')
    try:
        if get_project_manifest(root,project_id) is not None:raise ValueError('项目已存在；导入不会覆盖原文或已有项目。')
        if source_root.exists():
            # Recover only an exactly matching completed source copy; never overwrite it.
            if set(p.name for p in source_root.iterdir())!=names or any(not p.is_file() or p.is_symlink() or p.read_bytes()!=raw for p,raw in prepared):
                raise ValueError('existing source directory differs; preserved for recovery')
        else:
            source_root.parent.mkdir(parents=True,exist_ok=True)
            with tempfile.TemporaryDirectory(prefix='.source-import-',dir=source_root.parent) as directory:
                stage=Path(directory)
                for path,raw in prepared:
                    with (stage/path.name).open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
                os.rename(stage,source_root)
        _save_project_manifest_unlocked(root,data)
    finally:lock.release()
    return selection_status(root,project_id)


def import_candidates(root, project_id, *, expected_manifest_sha256, source_inventory_sha256, candidates,
                      _native_request_id=None, _native_metadata=None):
    root=Path(root);project_id=validate_project_id(project_id);lock=_project_write_lock(project_id)
    if not lock.acquire(blocking=False):raise ManifestWriteInProgressError('project write in progress')
    try:
        _,raw,data,_=_read(root,project_id,expected_manifest_sha256)
        from workbench.generation_jobs import get_project_generation_job, ACTIVE_JOB_STATUSES
        job = get_project_generation_job(root,project_id) or {}
        if _native_metadata is not None and not (_native_request_id and job.get('request_id') == _native_request_id
                and job.get('mode') == 'agent_quota_translation' and job.get('status') == 'running'):
            raise ValueError('native producer requires current internal job context')
        if job.get('status') in ACTIVE_JOB_STATUSES:
            if not (_native_request_id and job.get('request_id') == _native_request_id
                    and job.get('mode') == 'agent_quota_translation'):
                raise ValueError('生成仍在运行，请等待或使用既有恢复入口；未替换候选。')
        inventory=data.get('source_inventory') or {}
        if inventory.get('schema')!='workbench-source-inventory/2' or inventory.get('inventory_sha256')!=source_inventory_sha256:
            raise ValueError('候选与当前源清单不匹配。')
        expected=[row['id'] for row in data['segments']]
        if not isinstance(candidates,list) or any(not isinstance(r,dict) or set(r)!={'segment_id','target_text'} for r in candidates):raise ValueError('candidate requires segment_id/target_text only; review identities cannot be imported')
        if [r['segment_id'] for r in candidates]!=expected:raise ValueError('候选必须完整覆盖当前源段，顺序一致且无重复。')
        if any(not isinstance(r['target_text'],str) or not r['target_text'].strip() for r in candidates):raise ValueError('候选含空译文；原候选已保留。')
        if any(old.get('draft')!=new['target_text'] for old,new in zip(data['segments'],candidates)):
            previous=_archive(root,project_id,raw)
            data['segments']=[{**old,'draft':new['target_text'],'status':'pending','generated_by':'imported_candidate'} for old,new in zip(data['segments'],candidates)]
            data.pop('native_generation',None)
            if _native_metadata is not None:
                data['native_generation']=_native_metadata
                data['generation_mode']='agent_quota_translation'
                for row in data['segments']:row['generated_by']='native_agent_quota'
            data.pop('accepted_revision',None);data['previous_manifest_sha256']=previous;data['status']='review_pending';data['generation_state']='imported_unreviewed'
            _save_project_manifest_unlocked(root,data)
    finally:lock.release()
    return selection_status(root,project_id)


def _json_sha(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        allow_nan=False, separators=(',', ':')).encode()).hexdigest()


def _previous_candidate(root, project_id, data):
    """Read only the hash-addressed predecessor; never restore its authority."""
    from translation.source_versions import review_dependencies, validate_source_binding
    from translation.content_binding import SourceBindings
    digest = data.get('previous_manifest_sha256')
    if not isinstance(digest, str) or not re.fullmatch(r'[0-9a-f]{64}', digest):
        raise ValueError('没有可恢复的上一份候选。')
    path = _ordinary(manifests_dir(root)/'.versions'/project_id/(digest+'.json'))
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError('恢复快照已变化；当前候选已保留。')
    previous = json.loads(raw)
    if not isinstance(previous, dict): raise ValueError('invalid recovery snapshot')
    current = parse_project_manifest(data); old = parse_project_manifest(previous)
    for key in ('project_id','language_direction','source_inventory','source_documents'):
        if data.get(key) != previous.get(key):
            raise ValueError('恢复快照的源文或依赖版本不匹配。')
    for key in ('dependency_versions','dependency_sources'):
        if (data.get(key) or {}) != (previous.get(key) or {}):
            raise ValueError('恢复快照的依赖版本不匹配。')
    inventory = data.get('source_inventory') or {}
    if (inventory.get('schema') != 'workbench-source-inventory/2' or
            build_source_inventory(list(current.segments), language_direction=current.language_direction,
                origin=inventory.get('origin')) != inventory or len(current.segments) != len(old.segments)):
        raise ValueError('recovery requires the exact versioned source inventory')
    documents = data.get('source_documents')
    if not isinstance(documents, list) or not documents: raise ValueError('registered source documents required')
    resolver = SourceBindings(root); bindings = []; changes = []
    for row, prior in zip(current.segments, old.segments):
        def dependencies(value):
            result = review_dependencies(value, value.get('source',''))
            result.pop('draft_recovery_revision', None)
            return result
        if (row['id'] != prior['id'] or row.get('source') != prior.get('source') or
                row.get('dependency_keys') != prior.get('dependency_keys') or
                dependencies(row) != dependencies(prior) or row.get('dependency_resolution_errors')):
            raise ValueError('恢复快照的段落、源文或审核依赖已变化。')
        binding = validate_source_binding(row.get('source_binding'), row['source'])
        matches = [d for d in documents if isinstance(d,dict) and
            d.get('chapter_id') == binding['chapter_id'] and d.get('source_revision') == binding['source_revision']]
        if len(matches) != 1 or not isinstance(matches[0].get('path'), str):
            raise ValueError('ambiguous recovery source document')
        full = resolver.chapter(binding['chapter_id'], direction=current.language_direction, source_path=matches[0]['path'])
        validate_source_binding(binding, row['source'], document_text=full['document'].text)
        bindings.append(full)
        if not isinstance(prior.get('draft',''), str): raise ValueError('invalid prior candidate text')
        if row.get('draft','') != prior.get('draft',''): changes.append(row['id'])
    return digest, old, changes, bindings


def candidate_recovery_status(root, project_id, data):
    try:
        _, _, changes, _ = _previous_candidate(root, project_id, data)
        return {'available':bool(changes), 'changed_draft_count':len(changes),
            'reason':'可恢复上一份候选；变动段落需要重新审核。' if changes else '上一份快照没有不同的候选文本。'}
    except (ValueError, KeyError, TypeError, OSError):
        return {'available':False, 'changed_draft_count':0, 'reason':'没有与当前源文及依赖匹配的上一份候选。'}


def restore_previous_candidates(root, project_id, *, expected_manifest_sha256):
    """One reversible draft step; no approval, generation, budget or export effect."""
    from translation.content_binding import SourceBindings
    from workbench.generation_jobs import project_generation_lock, get_project_generation_job, ACTIVE_JOB_STATUSES
    root = Path(root); project_id = validate_project_id(project_id)
    if not isinstance(expected_manifest_sha256,str) or not re.fullmatch(r'[0-9a-f]{64}', expected_manifest_sha256):
        raise ValueError('current manifest SHA-256 required')
    generation_lock = project_generation_lock(project_id); lock = _project_write_lock(project_id)
    if not generation_lock.acquire(blocking=False): raise ManifestWriteInProgressError('project generation in progress')
    try:
        if not lock.acquire(blocking=False): raise ManifestWriteInProgressError('project write in progress')
        try:
            _, raw, data, digest = _read(root, project_id, expected_manifest_sha256)
            if (get_project_generation_job(root, project_id) or {}).get('status') in ACTIVE_JOB_STATUSES:
                raise ValueError('生成仍在运行；当前候选已保留。')
            previous, old, changes, bindings = _previous_candidate(root, project_id, data)
            if changes:
                kept = {'id','source','source_binding','dependency_versions','dependency_keys',
                    'dependency_sha256','source_context_revision'}
                rows = []
                for row, prior in zip(data['segments'], old.segments):
                    if row['id'] not in changes: rows.append(row); continue
                    recovered = {k:v for k,v in row.items() if k in kept}
                    recovered.update(draft=prior.get('draft',''), status='pending', generated_by='recovered_unreviewed_draft',
                        draft_recovery_revision=_json_sha({'schema':'draft-recovery/1','manifest_sha256':digest,
                            'snapshot_sha256':previous,'segment_id':row['id'],
                            'current_identity':approval_identity(project_id=project_id,
                                language_direction=data['language_direction'], segment=row)}))
                    rows.append(recovered)
                SourceBindings.verify(bindings)
                if _read(root, project_id, expected_manifest_sha256)[2] != data:
                    raise CanonicalVersionConflict('审核依赖在恢复期间变化；当前候选已保留。')
                data['previous_manifest_sha256'] = _archive(root, project_id, raw)
                data['segments'] = rows
                for key in ('accepted_revision','native_generation','selected_revision','human_approved_final',
                            'human_reviewed','actor_type','decision_actor','model','model_provider','issuer',
                            'approved','locked','canonical_revision','canonical_export','export_receipt','review_provenance'):
                    data.pop(key,None)
                data['status']='review_pending'; data['generation_state']='recovered_unreviewed'
                _save_project_manifest_unlocked(root, data)
        finally: lock.release()
    finally: generation_lock.release()
    return {'action':'restore_unreviewed_drafts' if changes else 'preserve_original',
        'changed_segment_ids':changes, 'approval_issued':False,'human_approved_final':False,
        'canonical_adoption':False,'selection':selection_status(root,project_id)}


def _revision_case(root, project_id, data, segment_id):
    """Exact selected-row lineage; never serialize the full source document."""
    from translation.content_binding import SourceBindings
    from translation.source_versions import validate_source_binding
    manifest = parse_project_manifest(data)
    inventory = data.get('source_inventory') or {}
    if (inventory.get('schema') != 'workbench-source-inventory/2' or
            build_source_inventory(list(manifest.segments), language_direction=manifest.language_direction,
                origin=inventory.get('origin')) != inventory):
        raise ValueError('revision requires the exact versioned source inventory')
    rows = [row for row in manifest.segments if row['id'] == segment_id]
    if len(rows) != 1 or not isinstance(rows[0].get('draft'), str) or not rows[0]['draft'].strip():
        raise ValueError('revision requires one existing nonempty draft')
    row = rows[0]
    binding = validate_source_binding(row.get('source_binding'), row['source'])
    documents = [d for d in data.get('source_documents', []) if isinstance(d, dict)
        and d.get('chapter_id') == binding['chapter_id']
        and d.get('source_revision') == binding['source_revision']]
    if len(documents) != 1 or not isinstance(documents[0].get('path'), str):
        raise ValueError('revision requires one registered full source document')
    full = SourceBindings(root).chapter(binding['chapter_id'], direction=manifest.language_direction,
        source_path=documents[0]['path'])
    text = full['document'].text
    validate_source_binding(binding, row['source'], document_text=text)
    end = binding['source_spans'][0][0]; start = max(0, end - 512)
    context = text[start:end]
    _ordinary(review_state_path(Path(root)))
    review = get_project_review_state(Path(root), project_id)['segments'].get(segment_id)
    case = {'schema':'workbench-revision-case/1', 'project_id':project_id, 'segment_id':segment_id,
        'source_inventory_sha256':inventory['inventory_sha256'], 'source_binding':binding,
        'candidate_identity':approval_identity(project_id=project_id,
            language_direction=manifest.language_direction, segment=row),
        'review_entry_sha256':_json_sha(review), 'context_span':[start,end],
        'context_sha256':hashlib.sha256(context.encode()).hexdigest(),
        'content_unit':full['unit'].identity}
    return row, context, case, full


def _old_revision_origin(row, case):
    return {'target_revision':hashlib.sha256(row['draft'].encode()).hexdigest(),
        'provenance':{'kind':'managed_unreviewed_or_reviewed_draft', 'condition':'B_old',
            'source_revision':case['source_binding']['source_revision'],
            'candidate_identity':case['candidate_identity']}}


def prepare_revision_comparison(root, project_id, *, expected_manifest_sha256, segment_id,
                                candidates, origins):
    """Read-only private plan. Supplied method origins remain unverified claims."""
    from translation.revision_comparison import plan_method_comparison
    _, _, data, _ = _read(Path(root), project_id, expected_manifest_sha256)
    row, context, case, _ = _revision_case(Path(root), project_id, data, segment_id)
    if type(candidates) is not dict or set(candidates) != {'simple','problem_driven'}:
        raise ValueError('provide simple/problem_driven only; old draft is read from the project')
    if type(origins) is not dict or set(origins) != set(candidates):
        raise ValueError('revision method origins required')
    for name, origin in origins.items():
        provenance = origin.get('provenance') if isinstance(origin, dict) else None
        if (not isinstance(provenance, dict) or provenance.get('condition') != name or
                provenance.get('source_revision') != case['source_binding']['source_revision']):
            raise ValueError('revision method origin differs from selected source/condition')
    return plan_method_comparison(row['source'], context, {'B_old':row['draft'], **candidates},
        binding=case, origins={'B_old':_old_revision_origin(row, case), **origins})


def apply_revision_comparison(root, project_id, *, expected_manifest_sha256, segment_id,
                              plan, view1, view2, chosen_target_revision, decision_actor):
    """Explicit local draft selection, never reviewer approval or canonical adoption.

    Comparison claims are structurally validated, not authenticated evaluator receipts.
    The changed draft must pass the existing independent review CAS before selection.
    """
    from translation.content_binding import SourceBindings
    from translation.revision_comparison import aggregate_method_comparison
    from workbench.generation_jobs import (project_generation_lock, get_project_generation_job,
        ACTIVE_JOB_STATUSES)
    if (not isinstance(decision_actor, DecisionActor) or
            decision_actor.actor_type not in {'agent','psh_proxy'}):
        raise ValueError('draft selection requires explicit trusted local Agent/PSH context')
    root = Path(root); project_id = validate_project_id(project_id)
    generation_lock = project_generation_lock(project_id); lock = _project_write_lock(project_id)
    if not generation_lock.acquire(blocking=False):
        raise ManifestWriteInProgressError('project generation in progress')
    try:
        if not lock.acquire(blocking=False):
            raise ManifestWriteInProgressError('project write in progress')
        try:
            _, raw, data, _ = _read(root, project_id, expected_manifest_sha256)
            if (get_project_generation_job(root, project_id) or {}).get('status') in ACTIVE_JOB_STATUSES:
                raise ValueError('generation still active; original draft preserved')
            row, context, case, full = _revision_case(root, project_id, data, segment_id)
            inputs = plan.get('input') if isinstance(plan, dict) else None
            if (not isinstance(inputs, dict) or inputs.get('binding') != case or
                    inputs.get('source') != row['source'] or inputs.get('context') != context or
                    not isinstance(inputs.get('candidates'), dict) or
                    inputs['candidates'].get('B_old') != row['draft'] or
                    not isinstance(inputs.get('origins'), dict) or
                    inputs['origins'].get('B_old') != _old_revision_origin(row, case)):
                raise CanonicalVersionConflict('comparison input or selected review changed; original preserved')
            decision = aggregate_method_comparison(plan, view1, view2)
            winner = decision['experimental_winner_target_revision']
            receipt = {'schema':'workbench-revision-application/1', 'project_id':project_id,
                'segment_id':segment_id, 'action':'preserve_original', 'changed_segment_ids':[],
                'decision':decision, 'auto_acceptance_enabled':False, 'human_approved_final':False,
                'canonical_adoption':False, 'comparison_evidence':'structurally_validated_unverified_claims'}
            if (not decision['complete'] or not decision['all_method_targets_evaluated'] or
                    winner is None):
                return receipt
            if chosen_target_revision != winner:
                raise ValueError('explicit target choice differs from the complete comparison winner')
            target = next(t for t in inputs['candidates'].values()
                if hashlib.sha256(t.encode()).hexdigest() == winner)
            if target == row['draft']:
                return {**receipt, 'reason':'no_benefit_original_wins'}
            # A budget snapshot is read-only: applying existing text is no model operation.
            unit = full['unit']; _ordinary(unit.path)
            budget = {'scope':'cumulative_whole_source', 'identity':unit.identity,
                'status':'not_recorded', 'observable_operations':None, 'revision':None,
                'native_internal_usage':'unknown', 'model_operations_in_application':0}
            if unit.path.exists():
                _, state = unit._load()
                budget.update(status='recorded', observable_operations=len(state['operations']),
                    revision=state['revision'], ledger_sha256=hashlib.sha256(unit.path.read_bytes()).hexdigest())
            trace = {'schema':'workbench-unreviewed-revision/1', 'case':case,
                'plan_sha256':_json_sha(plan), 'views_sha256':_json_sha([view1,view2]),
                'old_target_revision':hashlib.sha256(row['draft'].encode()).hexdigest(),
                'new_target_revision':winner, 'origin_verification':'unverified_claim',
                'actor':{'actor_type':decision_actor.actor_type, 'actor_ref':decision_actor.actor_ref},
                'approval_issued':False, 'cost':budget, 'comparison':decision,
                'diff':'\n'.join(unified_diff(row['draft'].splitlines(), target.splitlines(),
                    fromfile='previous-draft', tofile='unreviewed-draft', lineterm=''))+'\n'}
            # Keep unrelated raw rows exactly; resolved dependency projections are read-only.
            output = json.loads(raw)
            for selected in output['segments']:
                if selected['id'] == segment_id:
                    selected.update(draft=target, status='pending', generated_by='compared_unreviewed_revision',
                        revision_application=trace)
            SourceBindings.verify([full])
            _, _, current, _ = _read(root, project_id, expected_manifest_sha256)
            if _revision_case(root, project_id, current, segment_id)[2] != case:
                raise CanonicalVersionConflict('selected revision dependencies changed; original preserved')
            output['previous_manifest_sha256'] = _archive(root, project_id, raw)
            output.pop('accepted_revision', None); output.pop('native_generation', None)
            output['status'] = 'review_pending'; output['generation_state'] = 'bounded_revision_unreviewed'
            _save_project_manifest_unlocked(root, output)
            return {**receipt, 'action':'import_unreviewed_draft', 'changed_segment_ids':[segment_id],
                'trace':trace, 'selection':selection_status(root, project_id)}
        finally:
            lock.release()
    finally:
        generation_lock.release()


def selection_status(root,project_id):
    root=Path(root);_,_,data,digest=_read(root,project_id)
    manifest=parse_project_manifest(data)
    review=get_project_review_state(root,project_id)['segments'];accepted=0;actors={};complete=0
    for row in manifest.segments:
        identity=approval_identity(project_id=project_id,language_direction=manifest.language_direction,segment=row)
        decision=review_decision_summary(review.get(row['id']),identity,segment=row)
        accepted+=decision['candidate_accepted'];actors[decision['actor_type']]=actors.get(decision['actor_type'],0)+1
        complete+=bool(str(row.get('draft') or '').strip())
    inventory=data.get('source_inventory') or {};versioned=inventory.get('schema')=='workbench-source-inventory/2'
    selected=False
    if data.get('accepted_revision'):
        try:validate_accepted_revision(data,review);selected=True
        except ValueError:pass
    return {'project_id':project_id,'manifest_sha256':digest,'source_inventory_sha256':inventory.get('inventory_sha256'),
            'source_versioned':versioned,'chapters':manifest.chapters,'segments_total':len(manifest.segments),'segments_with_target':complete,
            'recovery':candidate_recovery_status(root,project_id,data),
            'current_agent_accepted':accepted,'actor_counts':actors,'can_select':bool(versioned and manifest.segments and accepted==len(manifest.segments)),
            'selected_current':selected,'accepted_revision_sha256':(data.get('accepted_revision') or {}).get('revision_sha256'),
            'generation_mode':data.get('generation_mode','legacy_sample'),'generation_state':data.get('generation_state','legacy_unknown'),
            'human_approved_final':False,'segments':[{'segment_id':r['id'],'source':r.get('source',''),'target_text':r.get('draft','')} for r in manifest.segments]}


def native_generation_provenance(root, project_id, *, expected_segments=None):
    """Read-only receipt binding for labels; returns no private native identifiers."""
    unknown = {'status':'unverified', 'execution_mode':None}
    try:
        _, _, data, _ = _read(root, project_id)
        manifest = parse_project_manifest(data)
        if expected_segments is not None and manifest.segments != expected_segments: return unknown
        meta = data.get('native_generation')
        if data.get('generation_mode') != 'agent_quota_translation' or not isinstance(meta, dict): return unknown
        request = meta.get('request_id')
        if not isinstance(request, str) or not 1 <= len(request) <= 96 or not all(c.isalnum() or c in '-_' for c in request): return unknown
        directory = _ordinary(Path(root)/'workspace/runs/workbench-native'/request)
        receipt_path = _ordinary(directory/'native-receipt.json'); answer_path = _ordinary(directory/'answer.json')
        if not receipt_path.is_file() or not answer_path.is_file(): return unknown
        if receipt_path.stat().st_size > 65536 or answer_path.stat().st_size > 4*1024*1024: return unknown
        receipt = json.loads(receipt_path.read_text()); answer_raw = answer_path.read_bytes()
        if receipt != {k:v for k,v in meta.items() if k != 'request_id'}: return unknown
        if (receipt.get('execution_mode') != 'agent_quota_translation' or receipt.get('model_provider') != 'openai'
                or receipt.get('model_override') is not False or receipt.get('human_approved_final') is not False
                or receipt.get('model_identity_status') != 'same_app_server_thread_start'
                or not isinstance(receipt.get('model'), str) or not receipt['model']
                or receipt.get('configured_model') not in (None, receipt['model'])
                or any(not isinstance(receipt.get(k), str) or not receipt[k] for k in ['thread_id','turn_id'])
                or hashlib.sha256(answer_raw).hexdigest() != receipt.get('answer_sha256')): return unknown
        answer = json.loads(answer_raw)
        if not isinstance(answer, dict): return unknown
        expected = [{'segment_id':s['id'], 'target_text':s.get('draft','')} for s in manifest.segments]
        if answer.get('candidates') != expected or any(s.get('generated_by') != 'native_agent_quota' for s in manifest.segments): return unknown
        from workbench.generation_jobs import find_generation_job
        job = find_generation_job(root, project_id, request) or {}; result = job.get('response_payload') or {}
        if not isinstance(result, dict): return unknown
        selected = result.get('selection') or {}
        if not isinstance(selected, dict): return unknown
        rows = [{'segment_id':s['id'], 'source':s.get('source',''), 'target_text':s.get('draft','')} for s in manifest.segments]
        if (job.get('status') != 'succeeded' or result.get('action') != 'generate' or result.get('project_id') != project_id
                or result.get('native') != receipt or selected.get('segments') != rows
                or selected.get('source_inventory_sha256') != data['source_inventory']['inventory_sha256']): return unknown
        return {'status':'verified', 'execution_mode':'agent_quota_translation'}
    except (OSError, ValueError, TypeError, KeyError):
        return unknown


def select_revision(root,project_id,*,expected_manifest_sha256,target_fields):
    root=Path(root);project_id=validate_project_id(project_id);lock=_project_write_lock(project_id)
    if not lock.acquire(blocking=False):raise ManifestWriteInProgressError('project write in progress')
    try:
        _,raw,data,_=_read(root,project_id,expected_manifest_sha256)
        reviews=get_project_review_state(root,project_id)['segments']
        accepted=build_accepted_revision(data,reviews,target_fields)
        if data.get('accepted_revision')!=accepted:
            _archive(root,project_id,raw);data['accepted_revision']=accepted;_save_project_manifest_unlocked(root,data)
    finally:lock.release()
    return selection_status(root,project_id)


def export_selected(root,project_id,*,expected_manifest_sha256):
    from translation.canonical_export import export_accepted_revision
    from workbench.review_state import review_state_path
    root=Path(root);path,raw,data,_=_read(root,project_id,expected_manifest_sha256)
    review_path=_ordinary(review_state_path(root));review_raw=review_path.read_bytes() if review_path.is_file() else None
    reviews=get_project_review_state(root,project_id)['segments']
    def recheck():
        _read(root,project_id,expected_manifest_sha256)
        now=review_path.read_bytes() if review_path.is_file() else None
        if now!=review_raw:raise CanonicalVersionConflict('审查在导出期间变化；请刷新。')
    return export_accepted_revision(root,data,reviews,before_commit=recheck)
