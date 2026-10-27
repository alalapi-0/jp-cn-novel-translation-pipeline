"""Synthetic boundary tests; the clock helper has no file or model access."""

import math

import pytest

from workbench.runtime_clock import CLOCK_FAILURES, clock_failure


@pytest.mark.parametrize("field", ["first", "stop", "current", "headroom"])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), True, None, "1", 10**1000])
def test_invalid_time_values_are_rejected(field, value):
    values = dict(first=100, stop=998, current=200, headroom=60)
    values[field] = value
    assert clock_failure(**values) == "invalid_time"


def test_invalid_windows_and_headroom_are_rejected():
    assert clock_failure(100, 998, 1100, -200) == "negative_headroom"
    assert clock_failure(100, 100, 100) == "invalid_window"
    assert clock_failure(100, 99, 100) == "invalid_window"
    assert clock_failure(100, 998, 99) == "clock_reversed"


@pytest.mark.parametrize("headroom", [0, 60, 180])
def test_original_strict_headroom_boundary_is_preserved(headroom):
    deadline = 998.0 - headroom
    assert clock_failure(100, 998, math.nextafter(deadline, -math.inf), headroom) is None
    assert clock_failure(100, 998, deadline, headroom) == "headroom_exhausted"
    assert clock_failure(100, 998, deadline + 1, headroom) == "headroom_exhausted"


def test_failure_names_are_fixed_and_contain_no_input_text():
    assert CLOCK_FAILURES == {
        "invalid_time", "negative_headroom", "invalid_window", "clock_reversed", "headroom_exhausted"
    }
    assert clock_failure(100, 998, "private synthetic text") == "invalid_time"
