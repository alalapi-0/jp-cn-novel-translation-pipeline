"""Pinned draft-run admission in the existing controlled checkpoint.

This is run-scoped engineering accounting. Cross-run content-unit accounting
and semantic review remain separate acceptance, never implied by this module.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
import math

from providers.controlled_run import checkpoint_lock
from translation.exporter import export_segments_doc, export_chapter_markdown


def digest(path: Path):
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise RuntimeError('draft artifact must be an ordinary file')
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def atomic_bytes(path: Path, raw: bytes):
    fd, name = tempfile.mkstemp(prefix='.draft-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw);stream.flush();os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):os.unlink(name)


class DraftExecution:
    def __init__(self, controlled, budget, guard, run_root, identity):
        self.controlled, self.budget, self.guard, self.root = controlled, budget, guard, run_root
        self.identity=identity
        if budget.max_api_calls is None:budget.max_api_calls = 8
        if type(budget.max_api_calls) is not int or budget.max_api_calls < 0:
            raise ValueError('invalid draft invocation limit')
        budget.max_api_calls = min(8, budget.max_api_calls)
        if budget.max_wall_seconds < 0:raise ValueError("negative draft wall limit")
        if type(budget.api_calls_used) is not int or budget.api_calls_used < 0:raise ValueError("invalid initial draft spending")
        if not math.isfinite(budget.max_wall_seconds):raise ValueError("invalid draft wall limit")
        if type(budget.max_segments) is not int or budget.max_segments < 0:raise ValueError("invalid draft segment limit")
        if budget.max_wall_seconds <= 0:budget.max_wall_seconds = 1200
        budget.max_wall_seconds = min(1200, budget.max_wall_seconds)
        limits = {'calls':budget.max_api_calls,'segments':budget.max_segments,'seconds':budget.max_wall_seconds}
        pinned = {'identity':identity,'limits':limits}
        prior = self.state
        if prior is not None:
            if prior.get('schema') != 1 or prior.get('pin') != pinned:
                raise RuntimeError('draft checkpoint input or budget identity changed')
        else:
            if controlled.checkpoint_path.exists() or controlled.checkpoint.completed_segments or (run_root/'segments.json').exists() or any((run_root/'draft').glob('*.md')):
                raise RuntimeError('unverified legacy draft resume; preserve candidate and register identity first')
            prior = {'schema':1,'pin':pinned,'api_calls_used':budget.api_calls_used,
                     'segments_used':budget.segments_used,'started_at_unix':time.time()-(time.monotonic()-budget.started_at),
                     'provider_attempts':0,'attempts':[],'baseline_api_calls_used':budget.api_calls_used,'output_sha256':None,'pending_output':None,'md_sha256':{}}
            self.update(prior)
        self.validate_state()
        self.recover_output()
        saved=self.state
        budget.api_calls_used=saved['api_calls_used'];budget.segments_used=saved['segments_used']
        elapsed=time.time()-saved['started_at_unix']
        if elapsed < 0:raise RuntimeError('draft clock moved backwards')
        budget.started_at=time.monotonic()-elapsed
        guard.config.log_dir=run_root/'model_runs'
        guard.config.attempt_ledger_path=run_root/'provider_attempt_budget.json'
        guard.config.max_calls_per_run=min(guard.config.max_calls_per_run,budget.max_api_calls)
        guard.config.deadline_at_unix=saved['started_at_unix']+budget.max_wall_seconds
        self.reconcile_provider_ledger()

    def reconcile_provider_ledger(self):
        # A process can die after the physical reservation but before finish().
        # Read durable evidence even when current permission forbids dispatch;
        # the provider still checks its current limits before any later call.
        path=self.guard.config.attempt_ledger_path
        state=deepcopy(self.state)
        if not path.exists():
            if state.get('provider_attempts',0) and self.identity['mode'].startswith('real'):
                raise RuntimeError('durable provider ledger disappeared; prior calls unknown')
            return
        digest(path)  # ordinary-file check; no source/request bodies in this ledger
        with checkpoint_lock(path):
            try:
                limits=json.loads(path.read_text())['limits']
                if not isinstance(limits,dict):raise ValueError('invalid ledger limits')
                physical=self.guard._load_attempts(path,limits)
            except (ValueError,KeyError,TypeError) as exc:
                raise RuntimeError('invalid durable provider attempt evidence') from exc
        state['provider_attempts']=max(state.get('provider_attempts',0),physical['call_count'])
        cp=deepcopy(self.controlled.checkpoint);cp.metadata['draft_execution']=state
        cp.spent_tokens=max(cp.spent_tokens,physical['spent_tokens'])
        cp.spent_usd=max(cp.spent_usd,physical['spent_usd'])
        self.controlled._commit(cp)
        self.guard.call_count=physical['call_count']
        self.guard.spent_tokens=physical['spent_tokens'];self.guard.spent_usd=physical['spent_usd']

    def verify_sources(self):
        for row in self.identity['sources']:
            if digest(Path(row['path']))!=row['sha256']:
                raise RuntimeError('draft source version changed during execution')

    def validate_state(self):
        state=self.state
        try:
            base=state['baseline_api_calls_used'];rows=state['attempts']
            if type(base) is not int or base<0 or not isinstance(rows,list):raise ValueError()
            if type(state['api_calls_used']) is not int or state['api_calls_used']!=base+len(rows):raise ValueError()
            if type(state['segments_used']) is not int or state['segments_used']<0:raise ValueError()
            if not math.isfinite(state['started_at_unix']):raise ValueError()
            for n,row in enumerate(rows,base+1):
                if row['id']!=n or row['status'] not in {'reserved','succeeded','failed','interrupted'}:raise ValueError()
                if type(row['retry_eligible']) is not bool or len(row['request_sha256'])!=64:raise ValueError()
        except (KeyError,TypeError,ValueError) as exc:
            raise RuntimeError('invalid durable draft accounting; preserve checkpoint') from exc

    def set_status(self, status):
        cp=deepcopy(self.controlled.checkpoint);cp.status=status
        if status=='simulated':cp.completed_segments=[]
        self.controlled._commit(cp)

    def reconcile_done(self, chapters, simulated):
        self.verify_sources()
        cp=deepcopy(self.controlled.checkpoint)
        ids=[s.segment_id for ch in chapters for s in ch.segments if s.draft_text.strip()]
        cp.completed_segments=[] if simulated else ids
        cp.metadata['draft_execution']['segments_used']=len(ids)
        self.budget.segments_used=len(ids)
        self.controlled._commit(cp)

    @property
    def state(self):return self.controlled.checkpoint.metadata.get('draft_execution')

    def update(self, value):
        cp=deepcopy(self.controlled.checkpoint);cp.metadata['draft_execution']=value
        self.controlled._commit(cp)

    def reserve(self, messages, ids):
        self.verify_sources()
        state=deepcopy(self.state)
        key=hashlib.sha256(json.dumps([{'role':m.role,'content':m.content} for m in messages],sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        previous=[a for a in state['attempts'] if a['request_sha256']==key]
        if previous and (len(previous)>=2 or not previous[-1]['retry_eligible']):
            raise RuntimeError('draft same-input retry is unproven or exhausted')
        if self.budget.exhausted():raise RuntimeError('draft invocation budget exhausted')
        state['api_calls_used']+=1
        state['attempts'].append({'id':state['api_calls_used'],'segment_ids':ids,'request_sha256':key,
                                  'status':'reserved','retry_eligible':False})
        self.update(state);self.budget.api_calls_used=state['api_calls_used']

    def finish(self, error=None):
        state=deepcopy(self.state);row=state['attempts'][-1]
        state['provider_attempts']=max(state.get('provider_attempts',0),self.guard.call_count)
        row['status']='succeeded' if error is None else ('failed' if isinstance(error,Exception) else 'interrupted')
        cause=error;seen=set()
        while cause is not None and id(cause) not in seen:
            seen.add(id(cause));status=getattr(cause,'status_code',None)
            if type(status) is int and (status==429 or 500<=status<=599):row['retry_eligible']=True;break
            cause=cause.__cause__
        if error is not None:row['error_class']=type(error).__name__
        cp=deepcopy(self.controlled.checkpoint);cp.metadata['draft_execution']=state
        cp.spent_tokens=max(cp.spent_tokens,self.guard.spent_tokens)
        cp.spent_usd=max(cp.spent_usd,self.guard.spent_usd)
        self.controlled._commit(cp)
        return row['retry_eligible']

    def recover_output(self):
        self.verify_sources()
        state=deepcopy(self.state);path=self.root/'segments.json';pending=self.root/'.segments.pending.json'
        intent=state.get('pending_output');actual=digest(path)
        if intent:
            after=intent['after'];before=intent['before']
            if actual==before and digest(pending)==after:
                os.replace(pending,path);actual=after
            if actual!=after:raise RuntimeError('draft pending output conflicts with owner edit or missing candidate')
            if pending.exists():
                if digest(pending)!=after:raise RuntimeError('unknown pending draft candidate')
                pending.unlink()
            state['output_sha256']=after;state['pending_output']=None;self.update(state)
        elif actual!=state['output_sha256']:
            raise RuntimeError('draft output identity changed; owner edit preserved')
        elif pending.exists():
            raise RuntimeError('unregistered pending draft candidate preserved')

    def save_segments(self, chapters):
        self.recover_output();path=self.root/'segments.json';before=self.state['output_sha256']
        with tempfile.TemporaryDirectory(prefix='.draft-build-',dir=self.root) as name:
            stage=Path(name)/'segments.json';export_segments_doc(chapters,stage)
            raw=stage.read_bytes()
        after=hashlib.sha256(raw).hexdigest()
        if after==before:return
        pending=self.root/'.segments.pending.json';atomic_bytes(pending,raw)
        state=deepcopy(self.state);state['pending_output']={'before':before,'after':after}
        state['segments_used']=sum(bool(s.draft_text.strip()) for ch in chapters for s in ch.segments)
        self.update(state)
        self.recover_output()

    def save_chapter(self, chapter, out_dir):
        self.verify_sources()
        target=out_dir/f'{chapter.chapter_id}_draft_zh.md'
        state=deepcopy(self.state);expected=state['md_sha256'].get(target.name)
        if digest(target)!=expected:raise RuntimeError('draft markdown owner edit preserved')
        with tempfile.TemporaryDirectory(prefix='.draft-md-',dir=self.root) as name:
            raw=export_chapter_markdown(chapter,Path(name)).read_bytes()
        if digest(target)!=expected:raise RuntimeError('draft markdown changed before write')
        atomic_bytes(target,raw);state['md_sha256'][target.name]=hashlib.sha256(raw).hexdigest();self.update(state)
