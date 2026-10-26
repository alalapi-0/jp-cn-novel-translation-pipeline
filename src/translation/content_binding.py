"""Resolve content operations to exact full-source versions, never fragment keys."""
from contextlib import contextmanager, ExitStack
import hashlib
import json
from pathlib import Path
import re
import math
import time

from providers.content_unit_budget import ContentUnitBudget
from providers.cost_guard import CostGuard
from translation.chapter_parser import chapter_id_from_path
from translation.source_alignment import SourceDocument


def _chapter_key(value):
    match = re.fullmatch(r'(?:ch-)?([0-9]+)', str(value))
    return ('number', int(match[1])) if match else ('label', str(value))


def validate_round(checkpoint):
    used = checkpoint.get('content_unit_ids_used')
    started = checkpoint.get('content_round_started_at')
    if (not isinstance(used, list) or any(not isinstance(x, str) or len(x) != 64 for x in used)
            or len(set(used)) != len(used) or len(used) > 10
            or isinstance(started, bool) or not isinstance(started, (int, float))
            or not math.isfinite(started) or started <= 0):
        raise ValueError('unverified cumulative content round identity')


def reserve_round(checkpoint, bindings):
    validate_round(checkpoint)
    elapsed = time.time() - checkpoint['content_round_started_at']
    if elapsed < 0 or elapsed >= 2400:
        raise RuntimeError('content round duration exhausted or clock moved backwards')
    used = set(checkpoint['content_unit_ids_used']) | {b['unit'].identity['source_revision'] for b in bindings}
    if len(used) > 10:
        raise RuntimeError('content round unit limit exhausted')
    checkpoint['content_unit_ids_used'] = sorted(used)


class SourceBindings:
    """Input-folder lineage only; other project import roots need registration."""

    def __init__(self, repo_root):
        self.root = Path(repo_root).resolve()
        self.cache = {}
        self.dispatched = set()

    def chapter(self, chapter_id, *, direction='JP_TO_CN', source_path=None, fragments=()):
        if direction == 'JP_TO_CN':
            folders = [self.root/'input_jp']
        elif direction == 'CN_TO_JP':
            folders = [self.root/'input_cn', self.root/'input_zh']
        else:
            raise ValueError('unknown source language direction')
        if source_path:
            path = Path(source_path)
            path = path if path.is_absolute() else self.root/path
            candidates = [path]
        else:
            candidates = [p for folder in folders if folder.is_dir() and not folder.is_symlink()
                for p in folder.iterdir() if p.suffix.lower() in {'.txt', '.md'}
                and _chapter_key(chapter_id_from_path(p)) == _chapter_key(chapter_id)]
        if len(candidates) != 1:
            raise ValueError('unknown or ambiguous full-source chapter identity')
        path = candidates[0]
        if (not any(path.resolve().is_relative_to(folder.resolve()) for folder in folders) or path.is_symlink()
                or not path.is_file() or any(parent.is_symlink() for parent in path.parents)
                or _chapter_key(chapter_id_from_path(path)) != _chapter_key(chapter_id)):
            raise ValueError('unregistered or mismatched full-source path')
        path = path.resolve()
        if path not in self.cache:
            raw = path.read_bytes()
            text = raw.decode('utf-8')
            digest = hashlib.sha256(raw).hexdigest()
            unit = ContentUnitBudget(self.root/'workspace/checkpoints', text)
            self.cache[path] = {'path': path, 'sha256': digest, 'unit': unit,
                'document': SourceDocument(text, revision=hashlib.sha256(text.encode()).hexdigest(),
                                           chapter_id=str(chapter_id))}
        binding = self.cache[path]
        for fragment in fragments:
            if not fragment or binding['document'].locate(fragment)['status'] != 'unique_exact_source':
                raise ValueError('fragment has unknown or ambiguous full-source lineage')
        self.verify([binding])
        return binding

    def segment(self, doc, chapter, segment):
        return self.chapter(chapter.get('chapter_id'),
            direction=doc.get('language_direction', 'JP_TO_CN'), source_path=chapter.get('source_path'),
            fragments=[segment.get('source_text')])

    @staticmethod
    def identities(bindings):
        return sorted([{'path': str(b['path']), 'sha256': b['sha256'],
                        'unit': b['unit'].identity} for b in {str(x['path']): x for x in bindings}.values()],
                      key=lambda x: x['path'])

    @staticmethod
    def verify(bindings):
        for binding in bindings:
            path = binding['path']
            if (path.is_symlink() or not path.is_file() or any(p.is_symlink() for p in path.parents)
                    or hashlib.sha256(path.read_bytes()).hexdigest() != binding['sha256']):
                raise ValueError('full source changed during controlled operation')

    @contextmanager
    def operation(self, bindings, messages, provider, *, role, run_id, correction_key=None, deadline=None):
        unique = {str(b['unit'].path): b for b in bindings}
        if not unique:
            raise ValueError('content operation has no full-source identity')
        if len(self.dispatched | set(unique)) > 10:
            raise RuntimeError('controlled round content unit limit exhausted')
        self.verify(unique.values())
        with ExitStack() as stack:
            leases = [stack.enter_context(unique[key]['unit'].operation(messages,
                role=role, run_id=run_id, correction_key=correction_key)) for key in sorted(unique)]
            combined = _CombinedLease(leases, deadline)
            guard = getattr(provider, 'cost_guard', None)
            previous = None
            if isinstance(guard, CostGuard):
                previous = guard.content_unit_lease
                guard.content_unit_lease = combined
            try:
                self.verify(unique.values())
                combined.remaining()
                self.dispatched.update(unique)
                yield
                self.verify(unique.values())
                combined.remaining()
            finally:
                if isinstance(guard, CostGuard):
                    guard.content_unit_lease = previous


class _CombinedLease:
    def __init__(self, leases, deadline):
        self.leases = leases
        self.deadline = deadline

    def remaining(self):
        remaining = min(lease.remaining() for lease in self.leases)
        if self.deadline is not None:
            remaining = min(remaining, self.deadline - time.time())
        if remaining <= 0:
            raise RuntimeError('content round duration exhausted')
        return remaining

    @contextmanager
    def physical_attempt(self, messages):
        with ExitStack() as stack:
            remaining = [stack.enter_context(lease.physical_attempt(messages)) for lease in self.leases]
            yield min(*remaining, self.remaining())
