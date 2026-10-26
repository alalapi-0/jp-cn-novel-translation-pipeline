"""Observable content operations shared across runs in controlled checkpoints.

The initial partition is one entire source version. Source text is never saved
here. Copying/renaming a source or changing an Agent/run/model cannot reset it.
Finer partitions require a later explicit, immutable alignment protocol.
"""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import time

from .controlled_run import ControlledRunConfig, ControlledRunManager, checkpoint_lock


def request_digest(messages):
    return hashlib.sha256(json.dumps(
        [{'role': m.role, 'content': m.content} for m in messages],
        ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()


def transient(error):
    seen = set()
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        code = getattr(error, 'status_code', None)
        if type(code) is int and (code == 429 or 500 <= code <= 599):
            return True
        error = error.__cause__
    return False


class ContentUnitBudget:
    """Fixed 8 operations, 2 revisions and 1200 seconds, including all roles."""

    def __init__(self, checkpoint_dir: Path, source_text: str):
        if not isinstance(source_text, str) or not source_text.strip():
            raise ValueError('content unit requires a nonempty exact source version')
        revision = hashlib.sha256(source_text.encode('utf-8')).hexdigest()
        self.identity = {'source_revision': revision, 'document_span': [0, len(source_text)],
                         'coordinate': 'unicode_codepoint_half_open', 'partition': 'whole_source/1'}
        self.config = ControlledRunConfig(enabled=True,
            checkpoint_dir=Path(checkpoint_dir) / 'content_units', run_id=revision)
        self.path = self.config.checkpoint_dir / f'{revision}.json'

    def _load(self):
        if self.path.is_symlink() or (self.path.exists() and not self.path.is_file()):
            raise RuntimeError('content checkpoint must be an ordinary file')
        manager = ControlledRunManager(self.config)
        state = manager.checkpoint.metadata.get('content_unit_budget')
        if state is None:
            if self.path.exists():
                raise RuntimeError('unverified legacy content checkpoint preserved')
            state = {'schema': 1, 'identity': self.identity, 'started_at_unix': time.time(),
                     'revision': 0, 'operations': []}
        try:
            if state['schema'] != 1 or state['identity'] != self.identity:
                raise ValueError('identity changed')
            start = state['started_at_unix']
            if isinstance(start, bool) or not isinstance(start, (int, float)) or not math.isfinite(start):
                raise ValueError('invalid start')
            rows = state['operations']
            if not isinstance(rows, list) or len(rows) > 8 or type(state['revision']) is not int:
                raise ValueError('invalid count')
            revision = 0
            correction_keys = {}
            for i, row in enumerate(rows, 1):
                if (type(row['id']) is not int or row['id'] != i or type(row['revision']) is not int
                    or (i == 1 and row['revision'] != 0 and not
                        (row['revision'] == 1 and row.get('correction_key')))
                    or row['revision'] not in {revision, revision + 1} or not 0 <= row['revision'] <= 2
                    or row['role'] not in {'generation', 'review', 'style'}
                    or row['status'] not in {'reserved', 'succeeded', 'failed', 'interrupted'}
                    or type(row['retry_eligible']) is not bool
                    or not isinstance(row['request_sha256'], str) or len(row['request_sha256']) != 64):
                    raise ValueError('invalid operation')
                revision = row['revision']
                correction = row.get('correction_key')
                if correction is not None:
                    if (not isinstance(correction, str) or len(correction) != 64
                            or row['role'] != 'generation' or not 1 <= revision <= 2
                            or correction_keys.get(correction, revision) != revision):
                        raise ValueError('invalid correction identity')
                    correction_keys[correction] = revision
            if state['revision'] != revision:
                raise ValueError('revision count changed')
            if state.get('correction_keys', {}) != correction_keys:
                raise ValueError('correction count changed')
        except (KeyError, ValueError, TypeError) as exc:
            raise RuntimeError('invalid content budget; preserve checkpoint') from exc
        return manager, deepcopy(state)

    @contextmanager
    def operation(self, messages, *, role, revision=None, run_id='unknown', correction_key=None):
        """Reserve before entering an observable callback; lock spans its lifetime."""
        if (role not in {'generation', 'review', 'style'} or
                (revision is not None and (type(revision) is not int or not 0 <= revision <= 2))):
            raise ValueError('invalid content operation or revision')
        if correction_key is not None and (role != 'generation' or revision is not None
                or not isinstance(correction_key, str) or len(correction_key) != 64
                or any(c not in '0123456789abcdef' for c in correction_key)):
            raise ValueError('invalid controlled correction identity')
        with checkpoint_lock(self.path):
            manager, state = self._load()
            if correction_key is not None:
                revision = state.get('correction_keys', {}).get(correction_key, state['revision'] + 1)
                if revision > 2:
                    raise RuntimeError('content unit correction revision limit exhausted')
            elif revision is None:
                revision = state['revision']
            lease = _Operation(manager, state, request_digest(messages), role, revision,
                               str(run_id)[:256], correction_key)
            lease.reserve()
            try:
                yield lease
                lease.remaining()
            except BaseException as error:
                lease.finish(error)
                raise
            else:
                if not lease.physical_calls:
                    lease.finish()
            finally:
                lease.active = False


class _Operation:
    def __init__(self, manager, state, request, role, revision, run_id, correction_key=None):
        self.manager, self.state = manager, state
        self.request, self.role, self.revision, self.run_id = request, role, revision, run_id
        self.physical_calls = 0
        self.row = None
        self.active = True
        self.correction_key = correction_key

    def remaining(self):
        if not self.active:
            raise RuntimeError('content operation lease is closed')
        elapsed = time.time() - self.state['started_at_unix']
        if elapsed < 0 or elapsed >= 1200:
            raise RuntimeError('content unit duration exhausted or clock moved backwards')
        return 1200 - elapsed

    def save(self):
        cp = deepcopy(self.manager.checkpoint)
        cp.metadata['content_unit_budget'] = deepcopy(self.state)
        self.manager._commit(cp)
        directory = os.open(self.manager.checkpoint_path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)

    def reserve(self):
        self.remaining()
        rows = self.state['operations']
        if len(rows) >= 8:
            raise RuntimeError('content unit observable operation limit exhausted')
        previous = [r for r in rows if r['request_sha256'] == self.request]
        if previous and (len(previous) >= 2 or not previous[-1]['retry_eligible']):
            raise RuntimeError('content unit same-input replay is unproven or exhausted')
        current = self.state['revision']
        if (self.revision < current or self.revision > current + 1
                or (not rows and self.revision != 0 and not (self.correction_key and self.revision == 1))):
            raise RuntimeError('content unit revision sequence cannot reset or skip')
        self.row = {'id': len(rows) + 1, 'role': self.role, 'revision': self.revision,
                    'run_id': self.run_id, 'request_sha256': self.request,
                    'status': 'reserved', 'retry_eligible': False}
        rows.append(self.row)
        if self.correction_key is not None:
            self.row['correction_key'] = self.correction_key
            self.state.setdefault('correction_keys', {})[self.correction_key] = self.revision
        self.state['revision'] = self.revision
        self.save()

    def finish(self, error=None):
        self.row['status'] = ('succeeded' if error is None else
                              'failed' if isinstance(error, Exception) else 'interrupted')
        self.row['retry_eligible'] = transient(error)
        self.save()

    @contextmanager
    def physical_attempt(self, messages):
        if request_digest(messages) != self.request:
            raise RuntimeError('physical content request differs from registered invocation')
        if self.physical_calls:
            self.reserve()
        self.physical_calls += 1
        remaining = self.remaining()
        try:
            yield remaining
        except BaseException as error:
            self.finish(error)
            raise
        else:
            self.finish()
