"""Release inputs only after a fresh, single-use source-free identity check.

This is a composition helper, not model confinement or runtime authorization.
The caller supplies the frozen policy and exact candidate/configuration readers.
The existing invocation must still compare its fresh native admission before a
turn. Reusing this preflight replaces that admission's metadata check; it never
adds a native open or skips the source-budgeted confinement probe.
"""
from copy import deepcopy
import math
from pathlib import Path


IDENTITY_FIELDS = frozenset({"version", "binary_sha256", "configured_model",
                             "effective_model", "model_provider", "model_override"})


class IdentityDenied(RuntimeError):
    """A finite reason without model, configuration or candidate values."""


class IdentityPreflight:
    def __init__(self, *, preflight, expected, directory, cancel, now, deadline,
                 candidate_snapshot, configuration_snapshot, active):
        if (type(expected) is not dict or set(expected) != IDENTITY_FIELDS
                or any(type(expected[k]) is not str or not expected[k]
                       for k in IDENTITY_FIELDS - {"model_override"})
                or expected["model_override"] is not False):
            raise IdentityDenied("frozen_identity_policy_required")
        if type(deadline) not in (int, float) or not math.isfinite(deadline):
            raise IdentityDenied("finite_deadline_required")
        self._preflight = preflight
        self._expected = deepcopy(expected)
        self._directory = Path(directory).absolute()
        self._cancel = cancel
        self._now = now
        self._deadline = deadline
        self._candidate = candidate_snapshot
        self._configuration = configuration_snapshot
        self._active = active
        self._state = "new"
        self._binding = None
        self._admission = None

    def _check_active(self):
        if self._cancel.is_set() or self._active() is not True:
            raise IdentityDenied("identity_preflight_inactive")
        # Recheck after the caller's potentially expensive candidate gate.
        stamp = self._now()
        if (type(stamp) not in (int, float) or not math.isfinite(stamp)
                or stamp >= self._deadline or self._cancel.is_set()):
            raise IdentityDenied("identity_preflight_expired_or_cancelled")

    def _snapshot(self):
        self._check_active()
        values = (self._candidate(), self._configuration())
        self._check_active()
        if any(type(v) is not str or len(v) != 64
               or any(c not in "0123456789abcdef" for c in v) for v in values):
            raise IdentityDenied("exact_identity_binding_required")
        return values

    def _fresh(self):
        if self._snapshot() != self._binding:
            raise IdentityDenied("identity_preflight_binding_changed")

    def prepare(self):
        if self._state != "new":
            raise IdentityDenied("identity_preflight_not_new")
        self._state = "preparing"
        try:
            self._binding = self._snapshot()
            admission = self._preflight(self._directory, cancel=self._cancel)
            self._fresh()
            if (type(admission) is not dict
                    or any(type(admission.get(k)) is not type(v) or admission[k] != v
                           for k, v in self._expected.items())
                    or admission.get("model_confinement_verified") is True):
                raise IdentityDenied("native_identity_different_or_unknown")
            self._admission = deepcopy(admission)
            self._state = "prepared"
        except BaseException:
            self.close()
            raise

    def release_inputs(self, prepare_inputs):
        if self._state != "prepared":
            raise IdentityDenied("identity_input_release_not_prepared")
        # Consume before callbacks, including failures and reentrant calls.
        self._state = "releasing"
        try:
            self._fresh()
            result = prepare_inputs()
            self._fresh()
            self._state = "released"
            return result
        except BaseException:
            self.close()
            raise

    def admission_preflight(self, directory, cancel=None, observer=None):
        if self._state != "released":
            raise IdentityDenied("identity_admission_not_released")
        self._state = "consuming"
        try:
            if (Path(directory).absolute() != self._directory
                    or cancel is not self._cancel or observer is not None):
                raise IdentityDenied("identity_admission_scope_changed")
            self._fresh()
            value = deepcopy(self._admission)
            self._admission = None
            self._state = "consumed"
            return value
        except BaseException:
            self.close()
            raise

    def close(self):
        self._state = "closed"
        self._admission = None
