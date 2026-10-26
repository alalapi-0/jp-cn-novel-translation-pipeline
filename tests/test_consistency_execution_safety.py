"""Synthetic faults at consistency-operation budget and recovery entrypoints."""
import json
import hashlib
import os
import sys
import subprocess
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from consistency.arbitration import arbitration_summary, run_arbitration
from consistency.retranslate import pending_segment_ids, run_consistency_retranslate
from providers.controlled_run import ControlledRunConfig, ControlledRunManager
from providers.types import ModelResult

CANDIDATE = {"kind": "shared_target", "source_term": "synthetic", "target_term": "示例", 'chapters':['ch-001']}
_ARBITRATION_SOURCE='# Synthetic\n\n風が吹く。\n'
CANDIDATE['source_evidence']=[{'chapter_id':'ch-001','source_revision':hashlib.sha256(_ARBITRATION_SOURCE.encode()).hexdigest(),
    'start_char':0,'end_char':len(_ARBITRATION_SOURCE),'quote':_ARBITRATION_SOURCE}]



class Spy:
    def __init__(self, mode="ok"):
        self.calls = 0
        self.mode = mode

    def generate(self, messages, options=None):
        self.calls += 1
        if self.mode == "raise": raise RuntimeError("synthetic provider failure")
        raw = "not JSON" if self.mode == "bad" else json.dumps({
            "canonical_target": "示例", "items": [{"segment_id": "seg-1", "translation": "候选译文。"}]})
        return ModelResult(provider_id="synthetic", model_name="synthetic", raw_output=raw)


@pytest.fixture()
def fixture(tmp_path):
    source = tmp_path/'input_jp/001-synthetic.md';source.parent.mkdir()
    source.write_text('# Synthetic\n\n風が吹く。\n')
    root = tmp_path / "workspace/runs/run_safe_draft_stage_b_50ch"; root.mkdir(parents=True)
    (root / "run_metadata.json").write_text(json.dumps({"run_id": root.name, "phase": "draft"}))
    (root / "run_progress.json").write_text(json.dumps({"status": "completed", "total_segments": 1, "completed_segments": 1}))
    path = root / "segments.json"
    path.write_text(json.dumps({"language_direction": "JP_TO_CN", "chapters": [{"chapter_id": "ch-001", 'source_path':str(source), "segments": [
        {"segment_id": "seg-1", "source_text": "風が吹く。", "draft_text": "旧候选。", "status": "machine_translated"}]}]}))
    plan = {"retranslate_tasks": [{"segment_ids": ["seg-1"]}], "stats": {"retranslate_segment_count": 1}}
    return tmp_path, plan, path


def test_arbitration_zero_budget_means_no_provider_call():
    provider = Spy()
    result = run_arbitration([CANDIDATE], provider=provider, max_api_calls=0)
    assert provider.calls == result["api_calls"] == 0
    assert result["budget_exhausted"] is True


def test_retranslate_zero_budget_means_no_provider_call_or_draft_write(fixture):
    root, plan, path = fixture; before = path.read_bytes(); provider = Spy()
    result = run_consistency_retranslate(plan, root, provider=provider, max_api_calls=0)
    assert provider.calls == result["api_calls"] == 0
    assert path.read_bytes() == before and result["completed_segments"] == 0


def test_simulation_cannot_mark_real_completion_or_skip_real_work(fixture):
    root, plan, path = fixture; provider = Spy(); before = path.read_bytes()
    simulated = run_consistency_retranslate(plan, root, provider=provider, max_api_calls=2, dry_run=True)
    assert simulated["completed_segments"] == simulated["batch_completed"] == 0
    assert provider.calls == 0 and path.read_bytes() == before
    assert not (root / "workspace/consistency_audit/retranslate_progress.json").exists()
    real = run_consistency_retranslate(plan, root, provider=provider, max_api_calls=2)
    assert provider.calls == 1 and real["completed_segments"] == 1


def test_failed_ids_remain_pending_for_explicit_budgeted_resume():
    plan = {"retranslate_tasks": [{"segment_ids": ["a", "b"]}]}
    assert pending_segment_ids(plan, {"completed_segment_ids": ["a"], "failed_segment_ids": ["b"]}) == ["b"]


def test_failed_provider_attempt_is_durable_before_retry(fixture):
    root, plan, _ = fixture; provider = Spy("raise")
    try: run_consistency_retranslate(plan, root, provider=provider, max_api_calls=1)
    except RuntimeError: pass
    cp = root / "workspace/consistency_audit/retranslate_progress.json"
    assert cp.is_file()
    state = json.loads(cp.read_text())
    assert state["provider_invocations_used"] == 1 and state["completed_segment_ids"] == []
    assert "seg-1" in state["failed_segment_ids"]


def test_all_parse_failures_cannot_be_pass():
    summary = arbitration_summary({"candidate_count": 1, "decisions": [{"parse_status": "failed"}]})
    assert summary["status"] == "FAIL" and summary["successful_decisions"] == 0


def test_stale_zero_stats_cannot_close_nonempty_retranslation_plan():
    from consistency.retranslate import build_fix_plan_status
    plan = {"retranslate_tasks": [{"segment_ids": ["seg-1"]}],
            "stats": {"retranslate_segment_count": 0, "term_fix_count": 0, "deferred_count": 0}}
    result = build_fix_plan_status(plan, {"dry_run": False, "status": "budget_exhausted",
        "completed_segments": 0, "remaining_segments": 1})
    assert result["retranslate_tasks"]["total_segments"] == 1 and result["all_closed"] is False


def test_simulated_arbitration_does_not_count_as_success_or_api_call():
    result = run_arbitration([CANDIDATE], provider=Spy(), max_api_calls=1, dry_run=True)
    assert result["api_calls"] == 0
    assert arbitration_summary(result)["status"] == "SIMULATED"


def test_controlled_checkpoint_replace_failure_preserves_previous_bytes(tmp_path, monkeypatch):
    manager = ControlledRunManager(ControlledRunConfig(enabled=True, checkpoint_dir=tmp_path, run_id="atomic"))
    manager.save(); before = manager.checkpoint_path.read_bytes()
    def fail_replace(*args): raise OSError("synthetic replace failure")
    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(OSError): manager.mark_segment_done("seg-1")
    assert manager.checkpoint_path.read_bytes() == before
    assert not manager.is_segment_done("seg-1")
    assert not list(tmp_path.glob("*.tmp"))


def test_failed_budget_is_cumulative_and_cannot_be_raised(fixture):
    root, plan, _ = fixture
    failed = run_consistency_retranslate(plan, root, provider=Spy("raise"), max_api_calls=1)
    assert failed["provider_invocations_used"] == 1
    provider = Spy()
    resumed = run_consistency_retranslate(plan, root, provider=provider, max_api_calls=1)
    assert provider.calls == resumed["api_calls"] == 0 and resumed["status"] == "budget_exhausted"
    with pytest.raises(ValueError, match="budget increase"):
        run_consistency_retranslate(plan, root, provider=provider, max_api_calls=2)
    assert provider.calls == 0


def test_rebuilt_plan_timestamp_does_not_restart_or_discard_budget(fixture):
    root, plan, _ = fixture
    run_consistency_retranslate({**plan, "generated_at": "previous"}, root, provider=Spy("bad"), max_api_calls=1)
    provider = Spy()
    result = run_consistency_retranslate({**plan, "generated_at": "rebuilt"}, root, provider=provider, max_api_calls=1)
    assert provider.calls == 0 and result["provider_invocations_used"] == 1 and result["budget_exhausted"] is True


def test_failed_parse_cannot_blindly_replay_despite_unspent_budget(fixture):
    root, plan, _ = fixture
    run_consistency_retranslate(plan, root, provider=Spy("bad"), max_api_calls=2)
    good = Spy()
    result = run_consistency_retranslate(plan, root, provider=good, max_api_calls=2)
    assert good.calls == 0 and result["provider_invocations_used"] == 2
    assert result["completed_segments"] == 0
    cp = json.loads(Path(result["checkpoint_path"]).read_text())
    assert cp["failed_segment_ids"] == ['seg-1']


def test_interrupt_reserves_attempt_and_keeps_failed_id(fixture):
    root, plan, _ = fixture
    class Interrupt(Spy):
        def generate(self, *args): self.calls += 1; raise KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt):
        run_consistency_retranslate(plan, root, provider=Interrupt(), max_api_calls=2)
    good = Spy()
    result = run_consistency_retranslate(plan, root, provider=good, max_api_calls=2)
    assert good.calls == 0 and result["provider_invocations_used"] == 2 and result["completed_segments"] == 0


def test_committed_output_recovers_after_checkpoint_interruption_without_new_call(fixture, monkeypatch):
    import consistency.retranslate as module
    root, plan, draft = fixture; original = module.atomic_write_json
    def interrupted(path, value):
        original(path, value)
        if path == draft: raise KeyboardInterrupt()
    monkeypatch.setattr(module, "atomic_write_json", interrupted)
    with pytest.raises(KeyboardInterrupt):
        run_consistency_retranslate(plan, root, provider=Spy(), max_api_calls=1)
    monkeypatch.setattr(module, "atomic_write_json", original)
    unused = Spy()
    recovered = run_consistency_retranslate(plan, root, provider=unused, max_api_calls=1)
    assert unused.calls == 0 and recovered["recovered_segments"] == recovered["completed_segments"] == 1
    assert recovered["status"] == "closed"


def test_changed_source_or_legacy_checkpoint_is_not_silently_resumed(fixture):
    root, plan, draft = fixture
    run_consistency_retranslate(plan, root, provider=Spy("bad"), max_api_calls=2)
    cp = root / "workspace/consistency_audit/retranslate_progress.json"; before = cp.read_bytes()
    doc = json.loads(draft.read_text()); doc["chapters"][0]["segments"][0]["source_text"] = "雨が降る。"
    draft.write_text(json.dumps(doc)); provider = Spy()
    with pytest.raises(ValueError, match="changed-input|lineage"):
        run_consistency_retranslate(plan, root, provider=provider, max_api_calls=2)
    assert cp.read_bytes() == before and provider.calls == 0
    doc['chapters'][0]['segments'][0]['source_text'] = '風が吹く。'
    draft.write_text(json.dumps(doc))
    cp.write_text(json.dumps({"completed_segment_ids": ["seg-1"], "last_batch": {"dry_run": True}}))
    legacy = cp.read_bytes()
    with pytest.raises(ValueError, match="legacy"):
        run_consistency_retranslate(plan, root, provider=provider, max_api_calls=2)
    assert cp.read_bytes() == legacy and provider.calls == 0


def test_dry_run_leaves_existing_real_checkpoint_and_drafts_unchanged(fixture):
    root, plan, draft = fixture
    real = run_consistency_retranslate(plan, root, provider=Spy(), max_api_calls=1)
    cp = Path(real["checkpoint_path"]); before = cp.read_bytes(); text = draft.read_bytes(); provider = Spy()
    run_consistency_retranslate(plan, root, provider=provider, max_api_calls=1, dry_run=True)
    assert cp.read_bytes() == before and draft.read_bytes() == text and provider.calls == 0


def test_target_edits_between_attempts_are_preserved(fixture):
    root, plan, draft = fixture
    run_consistency_retranslate(plan, root, provider=Spy("bad"), max_api_calls=2)
    doc = json.loads(draft.read_text()); doc["chapters"][0]["segments"][0]["draft_text"] = "用户改稿。"
    draft.write_text(json.dumps(doc)); before = draft.read_bytes(); provider = Spy()
    with pytest.raises(ValueError, match="changed-target"):
        run_consistency_retranslate(plan, root, provider=provider, max_api_calls=2)
    assert provider.calls == 0 and draft.read_bytes() == before


def test_target_edits_during_attempt_are_preserved(fixture):
    root, plan, draft = fixture
    class EditDuringCall(Spy):
        def generate(self, *args):
            doc = json.loads(draft.read_text()); doc["chapters"][0]["segments"][0]["draft_text"] = "用户改稿。"
            draft.write_text(json.dumps(doc)); return super().generate(*args)
    result = run_consistency_retranslate(plan, root, provider=EditDuringCall(), max_api_calls=2)
    assert result["completed_segments"] == 0 and result["batch_failed"] == 1
    assert json.loads(draft.read_text())["chapters"][0]["segments"][0]["draft_text"] == "用户改稿。"


def test_edit_between_outer_validation_and_apply_read_is_preserved(fixture, monkeypatch):
    import consistency.retranslate as module
    root, plan, draft = fixture; original = module._apply_batch_translations
    def race(*args, **kwargs):
        doc = json.loads(draft.read_text())
        doc["chapters"][0]["segments"][0]["draft_text"] = "校验后用户改稿。"
        draft.write_text(json.dumps(doc))
        return original(*args, **kwargs)
    monkeypatch.setattr(module, "_apply_batch_translations", race)
    result = run_consistency_retranslate(plan, root, provider=Spy(), max_api_calls=1)
    assert result["completed_segments"] == 0 and result["batch_failed"] == 1
    assert json.loads(draft.read_text())["chapters"][0]["segments"][0]["draft_text"] == "校验后用户改稿。"


def test_arbitration_failure_resume_and_parse_status_are_durable(tmp_path):
    source = tmp_path/'input_jp/001-synthetic.md';source.parent.mkdir();source.write_text('# Synthetic\n\n風が吹く。\n')
    cp = tmp_path / "arbitration.json"
    result = run_arbitration([CANDIDATE], provider=Spy("bad"), max_api_calls=2, checkpoint_path=cp,repo_root=tmp_path)
    assert result["status"] == "FAIL" and result["provider_invocations_used"] == 1
    result = run_arbitration([CANDIDATE], provider=Spy(), max_api_calls=2, checkpoint_path=cp,repo_root=tmp_path)
    assert result["status"] == "FAIL" and result["provider_invocations_used"] == 2
    assert len(result["decisions"]) == 2
    unused = Spy()
    result = run_arbitration([CANDIDATE], provider=unused, max_api_calls=2, checkpoint_path=cp,repo_root=tmp_path)
    assert result["api_calls"] == unused.calls == 0
    with pytest.raises(ValueError, match="budget increase"):
        run_arbitration([CANDIDATE], provider=unused, max_api_calls=3, checkpoint_path=cp,repo_root=tmp_path)


def test_cross_process_checkpoint_exclusion_prevents_dispatch(fixture):
    from providers.controlled_run import checkpoint_lock
    root, plan, _ = fixture; cp = root / "workspace/consistency_audit/retranslate_progress.json"
    code = """import sys,json
sys.path.insert(0,sys.argv[1])
from consistency.retranslate import run_consistency_retranslate
from pathlib import Path
class Provider:
 def generate(self,*args): raise AssertionError('provider must not be called')
try: run_consistency_retranslate(json.loads(sys.argv[3]),Path(sys.argv[2]),provider=Provider(),max_api_calls=1)
except RuntimeError as error:
 assert 'already in use' in str(error)
else: raise AssertionError('checkpoint lock was bypassed')
"""
    with checkpoint_lock(cp):
        child = subprocess.run([sys.executable, "-c", code, str(Path(__file__).resolve().parents[1] / "src"),
                                str(root), json.dumps(plan)], capture_output=True, text=True, timeout=5)
    assert child.returncode == 0, child.stderr


def test_cli_simulation_outputs_stay_inside_selected_root(fixture):
    import importlib.util
    root, plan, _ = fixture; audit = root / "workspace/consistency_audit"; audit.mkdir(parents=True)
    (audit / "local_fix_plan.json").write_text(json.dumps(plan))
    real_status = audit / "fix_plan_status.json"; real_status.write_text('owner prior status')
    spec = importlib.util.spec_from_file_location("test_retranslate_cli", Path(__file__).resolve().parents[1] / "scripts/run_consistency_retranslate.py")
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    assert module.main(["--repo-root", str(root), "--dry-run", "--json"]) == 0
    assert real_status.read_text() == 'owner prior status'
    assert (audit / "fix_plan_status.simulation.json").exists()
    assert not (audit / "retranslate_progress.json").exists()
