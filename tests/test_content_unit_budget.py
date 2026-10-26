"""Synthetic observable entry counts, including cross-run and process recovery."""
import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from providers.types import Message, ModelResult
from translation.draft_runner import run_draft_stage_b, RunBudget


def test_changed_run_id_cannot_repeat_successful_source_operation(tmp_path, monkeypatch):
    monkeypatch.setenv('CONTROLLED_RUN_ENABLED', 'true')
    monkeypatch.setenv('REAL_API_TESTS_ENABLED', 'false')
    source = tmp_path / 'input_jp'; source.mkdir()
    (source / '001.md').write_text('# Synthetic\n\n## Unit\n\n合成原文。\n')
    entries = []
    class Provider:
        provider_id = model_name = 'synthetic'
        def generate(self, messages, options):
            entries.append(1)
            return ModelResult(provider_id='synthetic', model_name='synthetic',
                raw_output=json.dumps({'items':[{'segment_id':'ch-001-seg-001','translation':'合成译文。'}]}))
    for name in ('first', 'renamed'):
        run_draft_stage_b(repo_root=tmp_path, input_dir=source, limit_chapters=1,
            run_id=name, provider_factory=lambda guard: Provider(), run_budget=RunBudget(max_api_calls=8))
    assert len(entries) == 1


def unit(tmp_path, text='synthetic source'):
    from providers.content_unit_budget import ContentUnitBudget
    return ContentUnitBudget(tmp_path / 'checkpoints', text)


def messages(number):
    return [Message(role='user', content=f'synthetic request {number}')]


def state(budget):
    return json.loads(budget.path.read_text())['metadata']['content_unit_budget']


def test_eight_entries_are_shared_by_runs_models_and_all_operation_roles(tmp_path):
    entries = []
    for i in range(9):
        current = unit(tmp_path)
        if i == 8:
            with pytest.raises(RuntimeError, match='limit exhausted'):
                with current.operation(messages(i), role='generation', run_id='another'):
                    entries.append(i)
        else:
            with current.operation(messages(i), role=('generation', 'review', 'style')[i % 3], run_id=str(i)):
                entries.append(i)
    assert entries == list(range(8))
    assert len(state(current)['operations']) == 8


def test_two_revisions_cannot_reset_skip_or_raise(tmp_path):
    current = unit(tmp_path)
    for i in range(3):
        with current.operation(messages(i), role='generation', revision=i): pass
    for revision in (0, 1, 3, True):
        with pytest.raises((RuntimeError, ValueError)):
            with current.operation(messages(10), role='generation', revision=revision):
                pytest.fail('invalid revision entered')
    assert state(current)['revision'] == 2


def test_expired_unit_does_not_restart_when_run_changes(tmp_path, monkeypatch):
    with unit(tmp_path).operation(messages(0), role='review'): pass
    started = state(unit(tmp_path))['started_at_unix']
    monkeypatch.setattr('providers.content_unit_budget.time.time', lambda: started + 1201)
    with pytest.raises(RuntimeError, match='duration'):
        with unit(tmp_path).operation(messages(1), role='style', run_id='renamed'):
            pytest.fail('expired unit entered')


def test_reservation_write_failure_prevents_callback(tmp_path, monkeypatch):
    def fail(*_): raise OSError('synthetic disk error')
    monkeypatch.setattr('providers.controlled_run.atomic_write_json', fail)
    with pytest.raises(OSError):
        with unit(tmp_path).operation(messages(0), role='review'):
            pytest.fail('unreserved callback entered')


def test_unknown_failure_is_charged_and_cannot_replay_across_roles(tmp_path):
    with pytest.raises(RuntimeError, match='unknown delivery'):
        with unit(tmp_path).operation(messages(0), role='generation'):
            raise RuntimeError('unknown delivery')
    with pytest.raises(RuntimeError, match='replay'):
        with unit(tmp_path).operation(messages(0), role='review', run_id='new-agent'):
            pytest.fail('unknown request replayed')
    assert len(state(unit(tmp_path))['operations']) == 1


def test_classified_retry_has_only_one_extra_entry(tmp_path):
    class Transient(RuntimeError): status_code = 429
    entries = []
    for i in range(2):
        with pytest.raises(Transient):
            with unit(tmp_path).operation(messages(0), role='generation', run_id=str(i)):
                entries.append(i)
                raise Transient()
    with pytest.raises(RuntimeError, match='replay'):
        with unit(tmp_path).operation(messages(0), role='generation'):
            pytest.fail('third transient retry entered')
    assert entries == [0, 1]


def test_physical_retries_reuse_first_reservation_and_charge_each_entry(tmp_path):
    from providers.cost_guard import CostGuard, CostGuardConfig
    guard = CostGuard(CostGuardConfig(real_api_tests_enabled=True,
        max_test_cost_usd=1, max_tokens_per_run=10000, log_dir=tmp_path/'provider'))
    class Transient(RuntimeError): status_code = 503
    entered = []
    with unit(tmp_path).operation(messages(0), role='generation') as lease:
        guard.content_unit_lease = lease
        for i in range(2):
            with pytest.raises(Transient):
                with guard.attempt(messages(0), 20):
                    entered.append(i)
                    raise Transient()
        with pytest.raises(RuntimeError, match='replay'):
            with guard.attempt(messages(0), 20):
                pytest.fail('third physical retry entered')
    assert entered == [0, 1]
    assert guard.call_count == len(state(unit(tmp_path))['operations']) == 2


def test_eighth_operation_denies_second_physical_retry(tmp_path):
    from providers.cost_guard import CostGuard, CostGuardConfig
    for i in range(7):
        with unit(tmp_path).operation(messages(i), role='style'): pass
    guard = CostGuard(CostGuardConfig(real_api_tests_enabled=True,
        max_test_cost_usd=1, max_tokens_per_run=10000, log_dir=tmp_path/'provider'))
    class Transient(RuntimeError): status_code = 503
    with unit(tmp_path).operation(messages(7), role='generation') as lease:
        guard.content_unit_lease = lease
        with pytest.raises(Transient):
            with guard.attempt(messages(7), 20): raise Transient()
        with pytest.raises(RuntimeError, match='limit exhausted'):
            with guard.attempt(messages(7), 20): pytest.fail('ninth physical entry')
    assert guard.call_count == 1 and len(state(unit(tmp_path))['operations']) == 8


def test_process_death_preserves_reservation_and_releases_kernel_lock(tmp_path):
    import os, subprocess
    code = '''
import os,sys
from pathlib import Path
from providers.content_unit_budget import ContentUnitBudget
from providers.types import Message
budget=ContentUnitBudget(Path(sys.argv[1])/'checkpoints','synthetic source')
with budget.operation([Message(role='user',content='synthetic request 0')],role='generation'):
    os._exit(23)
'''
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1]/'src'))
    process = subprocess.run([sys.executable, '-c', code, str(tmp_path)], env=env)
    assert process.returncode == 23
    with pytest.raises(RuntimeError, match='replay'):
        with unit(tmp_path).operation(messages(0), role='review'): pytest.fail('ambiguous replay')
    with unit(tmp_path).operation(messages(1), role='review'): pass
    assert len(state(unit(tmp_path))['operations']) == 2


def test_concurrent_role_cannot_enter_shared_unit(tmp_path):
    with unit(tmp_path).operation(messages(0), role='generation'):
        with pytest.raises(RuntimeError, match='in use'):
            with unit(tmp_path).operation(messages(1), role='review'):
                pytest.fail('parallel content writer')


def test_changed_version_is_new_unit_and_old_budget_is_retained(tmp_path):
    before = unit(tmp_path)
    with before.operation(messages(0), role='review'): pass
    saved = before.path.read_bytes()
    after = unit(tmp_path, 'new synthetic version')
    with after.operation(messages(0), role='review'): pass
    assert after.path != before.path and before.path.read_bytes() == saved


def test_corrupt_budget_is_preserved_without_entry(tmp_path):
    current = unit(tmp_path)
    with current.operation(messages(0), role='review'): pass
    current.path.write_text('{"bad":true}')
    saved = current.path.read_bytes()
    with pytest.raises((RuntimeError, TypeError)):
        with unit(tmp_path).operation(messages(1), role='style'):
            pytest.fail('corrupt budget entered')
    assert current.path.read_bytes() == saved


def test_retained_lease_cannot_dispatch_after_releasing_unit_lock(tmp_path):
    from providers.cost_guard import CostGuard, CostGuardConfig
    guard = CostGuard(CostGuardConfig(real_api_tests_enabled=True,
        max_test_cost_usd=1, max_tokens_per_run=10000, log_dir=tmp_path/'provider'))
    with unit(tmp_path).operation(messages(0), role='review') as lease: pass
    guard.content_unit_lease = lease
    with pytest.raises(RuntimeError, match='closed'):
        with guard.attempt(messages(0), 20): pytest.fail('expired lease dispatched')
    assert guard.call_count == 0


def test_callback_overrun_is_rejected_and_retains_charge(tmp_path, monkeypatch):
    current = unit(tmp_path)
    with pytest.raises(RuntimeError, match='duration'):
        with current.operation(messages(0), role='style'):
            started = state(current)['started_at_unix']
            monkeypatch.setattr('providers.content_unit_budget.time.time', lambda: started + 1201)
    assert state(current)['operations'][0]['status'] == 'failed'
    assert len(state(current)['operations']) == 1


def test_correction_key_is_cumulative_and_cannot_relabel_old_revision(tmp_path):
    current=unit(tmp_path)
    for i in range(2):
        with current.operation(messages(i),role='generation',correction_key=str(i)*64):pass
        with current.operation(messages(i+10),role='review'):pass
    with pytest.raises(RuntimeError,match='revision limit'):
        with current.operation(messages(2),role='generation',correction_key='2'*64):pytest.fail('third revision')
    with pytest.raises(RuntimeError,match='sequence'):
        with current.operation(messages(3),role='generation',correction_key='0'*64):pytest.fail('revision reset')
    assert state(current)['revision']==2 and len(state(current)['operations'])==4
