"""Per-call usage from records that may hold a resumed session's running totals (T25)."""

from __future__ import annotations

import pytest

from jigworks_contracts.usage import per_call, session_total, this_call


def rec(i, o, cw, cr, cost, session="s1", model="claude-sonnet-5-5"):
    return {"model": model, "sessionId": session, "input": i, "output": o, "cache_write": cw, "cache_read": cr,
            "cliCostUsd": cost}


# The fixer session of run_20261120122836_6ab988 (rounds 18, 19, 21), recorded as running totals.
LEGACY = [rec(228, 207699, 691789, 25527388, 7.3973408), rec(240, 213688, 705496, 27827461, 7.7420901),
          rec(246, 215863, 713785, 29007035, 7.9149655)]


def test_running_totals_become_differences():
    calls = per_call(LEGACY)
    assert [c["output"] for c in calls] == [207699, 5989, 2175]
    assert sum(c["cliCostUsd"] for c in calls) == pytest.approx(7.9149655)


def test_per_call_records_stay_as_they_are():
    first = rec(500, 30000, 600000, 2_000_000, 5.0)
    later = [rec(4, 800, 9000, 700000, 0.3), rec(6, 900, 4000, 710000, 0.3)]
    assert per_call([first, *later]) == [first, *later]


def test_a_mixed_series_switches_once_and_never_back():
    delta = rec(4, 621, 2577, 405961, 0.0571)
    bigger_call = rec(300, 9000, 20000, 900000, 1.2)  # larger than the delta in every field: still per call
    calls = per_call([*LEGACY, delta, bigger_call])
    assert calls[-2:] == [delta, bigger_call]


def test_sessions_and_models_are_separate_series():
    other = rec(1, 2, 3, 4, 0.01, session="s2")
    haiku = rec(18566, 21, 0, 0, 0.0018671, model="claude-haiku-5-5")
    calls = per_call([LEGACY[0], other, haiku, LEGACY[1], haiku])
    assert calls[1] == other and calls[2] == haiku
    assert calls[3]["output"] == 5989
    assert calls[4] == haiku, "two equal records are two calls (a running total grows in output)"


def test_this_call_subtracts_the_session_total_or_keeps_a_per_call_report():
    assert session_total(LEGACY)["output"] == 215863
    reported = rec(250, 218327, 721411, 29806256, 8.0500396)
    assert this_call(reported, LEGACY)["output"] == 218327 - 215863
    per_call_report = rec(4, 621, 2577, 405961, 0.0571)
    assert this_call(per_call_report, LEGACY) == per_call_report
    assert this_call(reported, []) == reported
