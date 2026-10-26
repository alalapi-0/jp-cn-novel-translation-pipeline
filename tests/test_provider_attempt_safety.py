"""Fault-injection checks at registered real-adapter physical attempt boundaries."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'model-router/src')]
from providers.cost_guard import CostGuard, CostGuardConfig, CostGuardError
from providers.router_provider import RouterProvider
from providers.openrouter_provider import OpenRouterProvider
from providers.types import Message, GenerateOptions
from model_router.chat_types import ChatResult, UsageInfo
from model_router.config_loader import RouterConfig, ProfileConfig, ProviderConfig, ProfileFallback
from model_router.modelRouter import ModelRouter
from model_router.errors import RateLimitError

MESSAGES = [Message('user', '合成入力')]


def guard_at(tmp_path, **changes):
    cfg = CostGuardConfig(real_api_tests_enabled=True, max_test_cost_usd=1,
                          max_tokens_per_run=10000, log_dir=tmp_path)
    cfg.max_calls_per_run = 2
    cfg.max_duration_sec = 1200
    for key, value in changes.items():
        setattr(cfg, key, value)
    return CostGuard(cfg)


def result():
    return ChatResult('synthetic', 'synthetic', 'p', UsageInfo(2, 1, 3), {})


def routed(guard, monkeypatch, effect, max_tokens=20):
    cfg = RouterConfig('draft_translation', {'draft_translation': ProfileConfig(
        'draft_translation', 'p', 'synthetic', max_tokens=max_tokens,
        fallback=[ProfileFallback('q', 'synthetic')])},
        {p: ProviderConfig(p, 'openai', max_retries=3) for p in ['p', 'q']}, Path('synthetic'))
    router = ModelRouter(cfg)
    inner = Mock(); inner.chat.side_effect = effect
    monkeypatch.setattr(router, '_get_provider', lambda _: inner)
    monkeypatch.setattr('model_router.modelRouter.time.sleep', lambda _: None)
    adapter = RouterProvider(cost_guard=guard, profile='draft_translation', max_tokens=max_tokens)
    adapter._chat = router.chat
    return adapter, inner


def ledger(guard):
    return json.loads((guard.config.log_dir / 'attempt_budget.json').read_text())


def test_zero_dollars_even_with_zero_estimated_price_denies_network(tmp_path, monkeypatch):
    guard = guard_at(tmp_path, max_test_cost_usd=0, cost_per_million_tokens=0)
    adapter, inner = routed(guard, monkeypatch, lambda *a, **k: result())
    with pytest.raises(CostGuardError): adapter.generate(MESSAGES, GenerateOptions(pipeline_stage="real_api_smoke"))
    assert inner.chat.call_count == 0


def test_router_retry_and_fallback_share_pre_dispatch_cap(tmp_path, monkeypatch):
    guard = guard_at(tmp_path)
    def fail(*a, **k):
        state = ledger(guard)
        assert state['call_count'] == inner.chat.call_count
        assert state['attempts'][-1]['status'] == 'reserved'
        raise RateLimitError('synthetic transient', 'p', 429)
    adapter, inner = routed(guard, monkeypatch, fail)
    with pytest.raises(CostGuardError): adapter.generate(MESSAGES, GenerateOptions(pipeline_stage="real_api_smoke"))
    assert inner.chat.call_count == adapter.network_calls == guard.call_count == 2
    assert [a['status'] for a in ledger(guard)['attempts']] == ['failed', 'failed']


def test_failed_attempt_survives_new_guard_and_adapter(tmp_path, monkeypatch):
    one = guard_at(tmp_path, max_calls_per_run=1)
    adapter, inner = routed(one, monkeypatch, RuntimeError('synthetic failure'))
    with pytest.raises(RuntimeError): adapter.generate(MESSAGES, GenerateOptions(pipeline_stage="real_api_smoke"))
    assert inner.chat.call_count == 1
    two = guard_at(tmp_path, max_calls_per_run=1)
    adapter2, inner2 = routed(two, monkeypatch, lambda *a, **k: result())
    with pytest.raises(CostGuardError): adapter2.generate(MESSAGES, GenerateOptions(pipeline_stage="real_api_smoke"))
    assert inner2.chat.call_count == 0
    assert two.call_count == 1


def test_output_allowance_is_reserved_before_provider_entry(tmp_path, monkeypatch):
    guard = guard_at(tmp_path, max_tokens_per_run=10)
    adapter, inner = routed(guard, monkeypatch, lambda *a, **k: result(), max_tokens=20)
    with pytest.raises(CostGuardError): adapter.generate([Message('user', 'x')], GenerateOptions(pipeline_stage='real_api_smoke'))
    assert inner.chat.call_count == 0


@pytest.mark.parametrize('limit', [None, 0, -1])
def test_unbounded_output_denied(tmp_path, monkeypatch, limit):
    guard = guard_at(tmp_path)
    adapter, inner = routed(guard, monkeypatch, lambda *a, **k: result(), max_tokens=limit)
    with pytest.raises(CostGuardError): adapter.generate(MESSAGES, GenerateOptions(pipeline_stage="real_api_smoke"))
    assert inner.chat.call_count == 0


def test_disabled_real_permission_denies_direct_adapter(tmp_path, monkeypatch):
    guard = guard_at(tmp_path, real_api_tests_enabled=False)
    adapter, inner = routed(guard, monkeypatch, lambda *a, **k: result())
    with pytest.raises(CostGuardError): adapter.generate(MESSAGES, GenerateOptions(pipeline_stage="real_api_smoke"))
    assert inner.chat.call_count == 0


def test_openrouter_failed_network_attempt_charged(tmp_path, monkeypatch):
    monkeypatch.setenv('OPENROUTER_API_KEY', 'synthetic-not-a-credential')
    guard = guard_at(tmp_path, max_calls_per_run=1)
    adapter = OpenRouterProvider(cost_guard=guard, max_tokens=20)
    inner = Mock(side_effect=RuntimeError('synthetic transport failure'))
    adapter._inner = SimpleNamespace(chat=inner)
    with pytest.raises(RuntimeError): adapter.generate(MESSAGES, GenerateOptions(pipeline_stage="real_api_smoke"))
    with pytest.raises(CostGuardError): adapter.generate(MESSAGES, GenerateOptions(pipeline_stage="real_api_smoke"))
    assert inner.call_count == adapter.network_calls == guard.call_count == 1


def test_restart_cannot_raise_existing_budget(tmp_path, monkeypatch):
    one = guard_at(tmp_path, max_calls_per_run=1)
    adapter, _ = routed(one, monkeypatch, lambda *a, **k: result())
    adapter.generate(MESSAGES, GenerateOptions(pipeline_stage="real_api_smoke"))
    before = (tmp_path/'attempt_budget.json').read_bytes()
    two = guard_at(tmp_path, max_calls_per_run=2)
    adapter2, inner2 = routed(two, monkeypatch, lambda *a, **k: result())
    with pytest.raises(CostGuardError): adapter2.generate(MESSAGES, GenerateOptions(pipeline_stage="real_api_smoke"))
    assert inner2.chat.call_count == 0
    assert (tmp_path/'attempt_budget.json').read_bytes() == before


def test_reservation_persistence_failure_never_dispatches(tmp_path, monkeypatch):
    guard = guard_at(tmp_path)
    adapter, inner = routed(guard, monkeypatch, lambda *a, **k: result())
    monkeypatch.setattr(guard, '_save_attempts', Mock(side_effect=OSError('synthetic full disk')))
    with pytest.raises(OSError): adapter.generate(MESSAGES, GenerateOptions(pipeline_stage="real_api_smoke"))
    assert inner.chat.call_count == 0
    assert guard.call_count == 0


def test_interruption_keeps_spent_reservation_and_disallows_ambiguous_replay(tmp_path, monkeypatch):
    guard = guard_at(tmp_path)
    adapter, inner = routed(guard, monkeypatch, KeyboardInterrupt())
    with pytest.raises(KeyboardInterrupt): adapter.generate(MESSAGES, GenerateOptions(pipeline_stage="real_api_smoke"))
    assert ledger(guard)['attempts'][0]['status'] == 'interrupted'
    newer = guard_at(tmp_path)
    adapter2, inner2 = routed(newer, monkeypatch, lambda *a, **k: result())
    with pytest.raises(CostGuardError): adapter2.generate(MESSAGES, GenerateOptions(pipeline_stage="real_api_smoke"))
    assert inner.chat.call_count == 1 and inner2.chat.call_count == 0


def test_post_dispatch_save_failure_retains_pre_dispatch_reservation(tmp_path, monkeypatch):
    guard = guard_at(tmp_path)
    original = guard._save_attempts
    def save(path, state):
        if state['attempts'][-1]['status'] != 'reserved':
            raise OSError('synthetic post-call crash')
        return original(path, state)
    monkeypatch.setattr(guard, '_save_attempts', save)
    adapter, inner = routed(guard, monkeypatch, lambda *a, **k: result())
    with pytest.raises(OSError): adapter.generate(MESSAGES, GenerateOptions(pipeline_stage="real_api_smoke"))
    assert ledger(guard)['attempts'][0]['status'] == 'reserved'
    newer = guard_at(tmp_path)
    adapter2, inner2 = routed(newer, monkeypatch, lambda *a, **k: result())
    with pytest.raises(CostGuardError): adapter2.generate(MESSAGES, GenerateOptions(pipeline_stage="real_api_smoke"))
    assert inner.chat.call_count == 1 and inner2.chat.call_count == 0


def test_nontransient_failure_does_not_retry_or_fallback(tmp_path, monkeypatch):
    guard = guard_at(tmp_path)
    adapter, inner = routed(guard, monkeypatch, RuntimeError('unknown delivery'))
    with pytest.raises(RuntimeError): adapter.generate(MESSAGES, GenerateOptions(pipeline_stage="real_api_smoke"))
    assert inner.chat.call_count == 1
    adapter2, inner2 = routed(guard_at(tmp_path), monkeypatch, lambda *a, **k: result())
    with pytest.raises(CostGuardError): adapter2.generate(MESSAGES, GenerateOptions(pipeline_stage="real_api_smoke"))
    assert inner2.chat.call_count == 0


def test_only_one_extra_transient_attempt_across_restart(tmp_path, monkeypatch):
    guard = guard_at(tmp_path, max_calls_per_run=8)
    adapter, inner = routed(guard, monkeypatch, RateLimitError('synthetic transient', 'p', 429))
    with pytest.raises(CostGuardError): adapter.generate(MESSAGES, GenerateOptions(pipeline_stage="real_api_smoke"))
    assert inner.chat.call_count == 2
    next_adapter, next_inner = routed(guard_at(tmp_path, max_calls_per_run=8), monkeypatch, lambda *a, **k: result())
    with pytest.raises(CostGuardError): next_adapter.generate(MESSAGES, GenerateOptions(pipeline_stage="real_api_smoke"))
    assert next_inner.chat.call_count == 0


def test_expired_ledger_cannot_restart_duration(tmp_path, monkeypatch):
    guard = guard_at(tmp_path)
    adapter, _ = routed(guard, monkeypatch, lambda *a, **k: result())
    adapter.generate(MESSAGES, GenerateOptions(pipeline_stage="real_api_smoke"))
    path = tmp_path/'attempt_budget.json'; state = ledger(guard)
    state['started_at_unix'] -= 1300
    path.write_text(json.dumps(state)); before = path.read_bytes()
    adapter2, inner2 = routed(guard_at(tmp_path), monkeypatch, lambda *a, **k: result())
    with pytest.raises(CostGuardError, match='duration'): adapter2.generate([Message('user', 'different input')], GenerateOptions(pipeline_stage='real_api_smoke'))
    assert inner2.chat.call_count == 0 and path.read_bytes() == before


def test_separate_process_cannot_reserve_while_attempt_in_flight(tmp_path):
    import subprocess
    guard = guard_at(tmp_path)
    program = '''from pathlib import Path
import sys
sys.path.insert(0,sys.argv[2])
from providers.cost_guard import CostGuard,CostGuardConfig,CostGuardError
from providers.types import Message, GenerateOptions
cfg=CostGuardConfig(real_api_tests_enabled=True,max_test_cost_usd=1,max_tokens_per_run=10000,log_dir=Path(sys.argv[1]),max_calls_per_run=2)
try:
 with CostGuard(cfg).attempt([Message("user","other")],20):
  raise AssertionError("concurrent reservation accepted")
except CostGuardError:
 pass
'''
    with guard.attempt(MESSAGES, 20):
        proc = subprocess.run([sys.executable, '-c', program, str(tmp_path), str(ROOT/'src')], capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr
    assert ledger(guard)['call_count'] == 1


def test_corrupt_ledger_is_preserved_and_denied(tmp_path, monkeypatch):
    guard = guard_at(tmp_path); path = tmp_path/'attempt_budget.json'
    path.write_bytes(b'{broken')
    adapter, inner = routed(guard, monkeypatch, lambda *a, **k: result())
    with pytest.raises(CostGuardError): adapter.generate(MESSAGES, GenerateOptions(pipeline_stage="real_api_smoke"))
    assert inner.chat.call_count == 0 and path.read_bytes() == b'{broken'


def test_reported_usage_overrun_rejected_and_charged(tmp_path, monkeypatch):
    guard = guard_at(tmp_path)
    response = result(); response.usage = UsageInfo(10000, 10000, 20000)
    adapter, inner = routed(guard, monkeypatch, lambda *a, **k: response)
    with pytest.raises(CostGuardError, match='exceeded'): adapter.generate(MESSAGES, GenerateOptions(pipeline_stage="real_api_smoke"))
    assert inner.chat.call_count == 1 and ledger(guard)['attempts'][0]['status'] == 'failed'


def test_actual_http_entry_observes_each_retry_reservation(tmp_path, monkeypatch):
    import urllib.error
    from unittest.mock import MagicMock
    monkeypatch.setenv('SYNTHETIC_PROVIDER_KEY', 'synthetic-not-a-credential')
    config = RouterConfig('draft_translation', {'draft_translation': ProfileConfig(
        'draft_translation', 'p', 'synthetic', max_tokens=20)},
        {'p': ProviderConfig('p', 'openai', base_url='https://synthetic.invalid',
                             api_key_env='SYNTHETIC_PROVIDER_KEY', max_retries=3)}, Path('synthetic'))
    router = ModelRouter(config)
    monkeypatch.setattr('model_router.modelRouter.time.sleep', lambda _: None)
    guard = guard_at(tmp_path)
    adapter = RouterProvider(cost_guard=guard, max_tokens=20)
    adapter._chat = router.chat
    calls = []
    response = MagicMock()
    response.__enter__.return_value = response
    response.read.return_value = json.dumps({'choices':[{'message':{'content':'synthetic'}}],
                                            'usage':{'total_tokens':3}}).encode()
    def http(request, timeout):
        state = ledger(guard)
        assert state['call_count'] == len(calls) + 1
        assert state['attempts'][-1]['status'] == 'reserved'
        assert json.loads(request.data)['max_tokens'] == 20
        assert 0 < timeout <= 1200
        calls.append(request)
        if len(calls) == 1:
            raise urllib.error.HTTPError(request.full_url, 429, 'synthetic transient', None, None)
        return response
    monkeypatch.setattr('urllib.request.urlopen', http)
    output = adapter.generate(MESSAGES, GenerateOptions(pipeline_stage="real_api_smoke"))
    assert output.raw_output == 'synthetic'
    assert len(calls) == adapter.network_calls == ledger(guard)['call_count'] == 2
    assert [a['status'] for a in ledger(guard)['attempts']] == ['failed', 'succeeded']


def test_process_death_keeps_unknown_attempt_spent(tmp_path, monkeypatch):
    import subprocess
    program = """import os,sys
from pathlib import Path
sys.path.insert(0,sys.argv[2])
from providers.cost_guard import CostGuard,CostGuardConfig
from providers.types import Message, GenerateOptions
cfg=CostGuardConfig(real_api_tests_enabled=True,max_test_cost_usd=1,max_tokens_per_run=10000,log_dir=Path(sys.argv[1]),max_calls_per_run=2)
with CostGuard(cfg).attempt([Message('user','合成入力')],20):
 os._exit(23)
"""
    proc = subprocess.run([sys.executable, '-c', program, str(tmp_path), str(ROOT/'src')])
    assert proc.returncode == 23
    guard = guard_at(tmp_path)
    assert ledger(guard)['attempts'][0]['status'] == 'reserved'
    adapter, inner = routed(guard, monkeypatch, lambda *a, **k: result())
    with pytest.raises(CostGuardError): adapter.generate(MESSAGES, GenerateOptions(pipeline_stage="real_api_smoke"))
    assert inner.chat.call_count == 0 and guard.call_count == 1


@pytest.mark.parametrize('changes', [
    {'max_calls_per_run': 0}, {'max_tokens_per_run': 0}, {'max_duration_sec': 0},
    {'max_test_cost_usd': float('nan')}, {'cost_per_million_tokens': float('inf')},
])
def test_invalid_or_zero_attempt_limits_never_enter_provider(tmp_path, monkeypatch, changes):
    guard = guard_at(tmp_path, **changes)
    adapter, inner = routed(guard, monkeypatch, lambda *a, **k: result())
    with pytest.raises(CostGuardError): adapter.generate(MESSAGES, GenerateOptions(pipeline_stage="real_api_smoke"))
    assert inner.chat.call_count == 0


def test_output_cost_reserved_even_when_input_alone_fits(tmp_path, monkeypatch):
    guard = guard_at(tmp_path, max_test_cost_usd=0.00006, cost_per_million_tokens=1)
    adapter, inner = routed(guard, monkeypatch, lambda *a, **k: result(), max_tokens=100)
    with pytest.raises(CostGuardError): adapter.generate([Message('user', 'x')], GenerateOptions(pipeline_stage='real_api_smoke'))
    assert inner.chat.call_count == 0


def test_fallback_has_its_own_reservation_and_same_budget(tmp_path, monkeypatch):
    from model_router.errors import ServerError
    guard = guard_at(tmp_path)
    adapter, inner = routed(guard, monkeypatch, [ServerError('synthetic 503', 'p', 503), result()])
    # Exhaust primary route after its first classified failure, then use fallback.
    router = adapter._chat.__self__
    for cfg in router.config.providers.values(): cfg.max_retries = 0
    output = adapter.generate(MESSAGES, GenerateOptions(pipeline_stage="real_api_smoke"))
    assert output.raw_output == 'synthetic'
    assert inner.chat.call_count == adapter.network_calls == guard.call_count == 2
    assert ledger(guard)['spent_tokens'] == sum(a['reserved_tokens'] for a in ledger(guard)['attempts'])
    assert [a['provider_id'] for a in ledger(guard)['attempts']] == ['p', 'q']


def test_exhaustion_before_fallback_never_enters_second_provider(tmp_path, monkeypatch):
    from model_router.errors import ServerError
    guard = guard_at(tmp_path, max_calls_per_run=1)
    adapter, inner = routed(guard, monkeypatch, [ServerError('synthetic 503', 'p', 503), result()])
    for cfg in adapter._chat.__self__.config.providers.values(): cfg.max_retries = 0
    with pytest.raises(CostGuardError): adapter.generate(MESSAGES, GenerateOptions(pipeline_stage="real_api_smoke"))
    assert inner.chat.call_count == 1


def test_usage_overrun_durably_stops_other_inputs(tmp_path, monkeypatch):
    guard = guard_at(tmp_path)
    response = result(); response.usage = UsageInfo(1, 100, 101)
    adapter, _ = routed(guard, monkeypatch, lambda *a, **k: response)
    with pytest.raises(CostGuardError): adapter.generate(MESSAGES, GenerateOptions(pipeline_stage="real_api_smoke"))
    assert ledger(guard)['aborted'] is True
    assert ledger(guard)['spent_tokens'] >= 101
    newer = guard_at(tmp_path)
    adapter2, inner2 = routed(newer, monkeypatch, lambda *a, **k: result())
    with pytest.raises(CostGuardError, match='aborted'):
        adapter2.generate([Message('user', 'different')], GenerateOptions(pipeline_stage='real_api_smoke'))
    assert inner2.chat.call_count == 0
