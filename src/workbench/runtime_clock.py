"""Finite, source-free checks for an already established runtime window.

The caller owns the original deadline and effects.  This helper neither reads
data nor grants, renews, or extends a runtime window.
"""

from __future__ import annotations

import math
from typing import Literal

ClockFailure = Literal[
    "invalid_time",
    "negative_headroom",
    "invalid_window",
    "clock_reversed",
    "headroom_exhausted",
]
CLOCK_FAILURES = frozenset(
    {"invalid_time", "negative_headroom", "invalid_window", "clock_reversed", "headroom_exhausted"}
)


def _finite_number(value: object) -> bool:
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def clock_failure(first: object, stop: object, current: object, headroom: object = 0) -> ClockFailure | None:
    """Return a fixed refusal reason, or ``None`` if the original window is open."""
    if not all(_finite_number(value) for value in (first, stop, current, headroom)):
        return "invalid_time"
    if headroom < 0:
        return "negative_headroom"
    if stop <= first:
        return "invalid_window"
    if current < first:
        return "clock_reversed"
    if current + headroom >= stop:
        return "headroom_exhausted"
    return None
