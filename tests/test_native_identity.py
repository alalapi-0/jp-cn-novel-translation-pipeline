"""Identity release tests use synthetic callbacks and never open a native client."""
from copy import deepcopy
from pathlib import Path
from threading import Event
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from workbench.native_identity import (IdentityDenied, IdentityPreflight,
    IDENTITY_FIELDS, freeze_identity_policy, require_identity)


@pytest.fixture
def rig(tmp_path):
    policy = dict(version="synthetic-cli", binary_sha256="a" * 64,
                  configured_model="synthetic-model", effective_model="synthetic-model",
                  model_provider="synthetic-provider", model_override=False)
    state = dict(candidate="b" * 64, configuration="c" * 64, now=1.0,
                 active=True, metadata_calls=0, inputs=0, admission=deepcopy(policy))
    cancel = Event()

    def preflight(directory, cancel=None):
        state["metadata_calls"] += 1
        return state["admission"]

    gate = IdentityPreflight(preflight=preflight, expected=policy,
        directory=tmp_path / "admission", cancel=cancel, now=lambda: state["now"],
        deadline=100.0, candidate_snapshot=lambda: state["candidate"],
        configuration_snapshot=lambda: state["configuration"], active=lambda: state["active"])

    def inputs():
        state["inputs"] += 1
        return "synthetic-inputs"

    return gate, state, policy, cancel, tmp_path / "admission", inputs


@pytest.mark.parametrize("field", sorted(IDENTITY_FIELDS))
@pytest.mark.parametrize("fault", ["missing", "different", "wrong_type"])
def test_identity_denial_precedes_every_input_callback(rig, field, fault):
    gate, state, _, _, _, inputs = rig
    if fault == "missing":
        del state["admission"][field]
    else:
        state["admission"][field] = (True if field == "model_override" else "private-other") if fault == "different" else 1
    with pytest.raises(IdentityDenied, match="different_or_unknown") as error:
        gate.prepare()
    assert "private-other" not in str(error.value)
    with pytest.raises(IdentityDenied):
        gate.release_inputs(inputs)
    assert state["metadata_calls"] == 1 and state["inputs"] == 0


def test_preflight_is_reused_once_without_confinement_or_probe_credit(rig):
    gate, state, policy, cancel, directory, inputs = rig
    gate.prepare()
    assert gate.release_inputs(inputs) == "synthetic-inputs"
    admission = gate.admission_preflight(directory, cancel)
    assert admission == policy
    assert "model_confinement_verified" not in admission
    assert state["metadata_calls"] == 1 and state["inputs"] == 1
    for operation in (gate.prepare, lambda: gate.release_inputs(inputs),
                      lambda: gate.admission_preflight(directory, cancel)):
        with pytest.raises(IdentityDenied):
            operation()
    assert state["metadata_calls"] == 1 and state["inputs"] == 1


@pytest.mark.parametrize("field", ["candidate", "configuration", "active", "cancel", "now"])
def test_intervening_change_never_releases_inputs(rig, field):
    gate, state, _, cancel, _, inputs = rig
    gate.prepare()
    if field == "cancel":
        cancel.set()
    else:
        state[field] = {"candidate": "d" * 64, "configuration": "e" * 64,
                        "active": False, "now": 100.0}[field]
    with pytest.raises(IdentityDenied):
        gate.release_inputs(inputs)
    assert state["metadata_calls"] == 1 and state["inputs"] == 0


@pytest.mark.parametrize("phase", ["candidate", "configuration", "active", "preflight"])
def test_slow_gate_cannot_pass_the_original_deadline(rig, phase):
    gate, state, _, _, _, inputs = rig
    attribute = {"candidate": "_candidate", "configuration": "_configuration",
                 "active": "_active", "preflight": "_preflight"}[phase]
    original = getattr(gate, attribute)

    def slow(*args, **kwargs):
        result = original(*args, **kwargs)
        state["now"] = 100.0
        return result

    setattr(gate, attribute, slow)
    with pytest.raises(IdentityDenied):
        gate.prepare()
    assert state["inputs"] == 0
    assert state["metadata_calls"] == (1 if phase == "preflight" else 0)
    with pytest.raises(IdentityDenied):
        gate.release_inputs(inputs)


@pytest.mark.parametrize("field", ["candidate", "configuration"])
def test_binding_changes_during_preflight_are_denied(rig, field):
    gate, state, _, _, _, inputs = rig
    original = gate._preflight

    def changing(*args, **kwargs):
        result = original(*args, **kwargs)
        state[field] = "d" * 64
        return result

    gate._preflight = changing
    with pytest.raises(IdentityDenied, match="binding_changed"):
        gate.prepare()
    assert state["metadata_calls"] == 1 and state["inputs"] == 0


def test_returned_metadata_cannot_mutate_the_private_snapshot(rig):
    gate, state, policy, cancel, directory, inputs = rig
    gate.prepare()
    state["admission"]["effective_model"] = "mutated-after-preflight"
    gate.release_inputs(inputs)
    assert gate.admission_preflight(directory, cancel) == policy


@pytest.mark.parametrize("fault", ["directory", "cancel", "observer", "config", "candidate", "expired"])
def test_admission_reuse_is_bound_and_never_runs_another_preflight(rig, fault):
    gate, state, _, cancel, directory, inputs = rig
    gate.prepare()
    gate.release_inputs(inputs)
    observer = None
    if fault == "directory": directory = directory / "different"
    if fault == "cancel": cancel = Event()
    if fault == "observer": observer = lambda value: value
    if fault == "config": state["configuration"] = "d" * 64
    if fault == "candidate": state["candidate"] = "e" * 64
    if fault == "expired": state["now"] = 100.0
    with pytest.raises(IdentityDenied):
        gate.admission_preflight(directory, cancel, observer)
    assert state["metadata_calls"] == 1


def test_input_failure_or_reentry_revokes_the_grant(rig):
    gate, state, _, cancel, directory, _ = rig
    gate.prepare()

    def inputs():
        state["inputs"] += 1
        gate.admission_preflight(directory, cancel)

    with pytest.raises(IdentityDenied):
        gate.release_inputs(inputs)
    with pytest.raises(IdentityDenied):
        gate.admission_preflight(directory, cancel)
    assert state["inputs"] == 1 and state["metadata_calls"] == 1


def test_input_exception_does_not_create_a_reusable_positive_grant(rig):
    gate, state, _, cancel, directory, _ = rig
    gate.prepare()

    def failed():
        raise ValueError("synthetic failure")

    with pytest.raises(ValueError):
        gate.release_inputs(failed)
    with pytest.raises(IdentityDenied):
        gate.admission_preflight(directory, cancel)
    assert state["metadata_calls"] == 1


def test_preexisting_probe_credit_is_never_accepted(rig):
    gate, state, _, _, _, _ = rig
    state["admission"]["model_confinement_verified"] = True
    with pytest.raises(IdentityDenied):
        gate.prepare()


@pytest.mark.parametrize("value", [None, True, 1, "", "x" * 64, "a" * 63])
def test_invalid_binding_never_opens_native_or_inputs(rig, value):
    gate, state, _, _, _, _ = rig
    state["candidate"] = value
    with pytest.raises(IdentityDenied):
        gate.prepare()
    assert state["metadata_calls"] == 0 and state["inputs"] == 0


def test_close_revokes_a_prepared_guard(rig):
    gate, state, _, _, _, inputs = rig
    gate.prepare()
    gate.close()
    with pytest.raises(IdentityDenied):
        gate.release_inputs(inputs)
    assert state["inputs"] == 0


def test_explicit_policy_is_detached_and_immutable(rig):
    _, _, supplied, _, _, _ = rig
    original = dict(supplied)
    frozen = freeze_identity_policy(supplied)
    supplied["effective_model"] = "synthetic-changed"
    require_identity(original, frozen)
    with pytest.raises(TypeError):
        frozen["effective_model"] = "synthetic-changed"
    with pytest.raises(IdentityDenied):
        require_identity(supplied, frozen)


def test_different_explicit_policy_has_no_alias_equivalence_or_default(rig):
    _, _, old, _, _, _ = rig
    current = dict(old, configured_model="synthetic-current", effective_model="synthetic-current")
    frozen = freeze_identity_policy(current)
    require_identity(current, frozen)
    for observed in (old, dict(current, effective_model="SYNTHETIC-CURRENT"),
                     dict(current, configured_model="synthetic-current ")):
        with pytest.raises(IdentityDenied, match="different_or_unknown"):
            require_identity(observed, frozen)


@pytest.mark.parametrize("field", sorted(IDENTITY_FIELDS))
@pytest.mark.parametrize("fault", ["missing", "wrong_type"])
def test_invalid_policy_is_rejected_before_matching(rig, field, fault):
    _, _, policy, _, _, _ = rig
    if fault == "missing":
        del policy[field]
    else:
        policy[field] = 0 if field == "model_override" else True
    with pytest.raises(IdentityDenied, match="frozen_identity_policy_required"):
        freeze_identity_policy(policy)


def test_unfrozen_or_forged_policy_cannot_bypass_comparison(rig):
    from types import MappingProxyType
    _, _, policy, _, _, _ = rig
    for expected in (policy, MappingProxyType({}), None):
        with pytest.raises(IdentityDenied, match="frozen_identity_policy_required"):
            require_identity(policy, expected)
