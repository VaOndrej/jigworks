"""The eval harness itself (T07): one adversarial task end to end, so `evals.run` keeps working."""

from __future__ import annotations

import importlib


def test_eval_overfill_bait_is_caught_and_invariants_hold():
    run = importlib.import_module("workflows.feature_development.evals.run")
    task = next(t for t in (run.json.loads(f.read_text()) for f in sorted(run.TASKS_DIR.glob("*.json")))
                if t["id"] == "02-amend-quantity")
    row = run.run_task(task, "fake", run.PriceTable.from_file(run.PRICES))
    assert row["brokenAfterImplement"] is True, "the scripted implementer breaks I1 (control)"
    assert "hypothesis invariants" in row["caughtBy"]
    assert row["outcome"] == "succeeded" and row["gatePassed"] and row["invariantsHold"]
    assert row["fixIterations"] == 1
    md = run.report([row], "fake", "feature-development@1.4.0", "sha256:x")
    assert "| **yes** |" in md and "1/1 runs have every invariant intact" in md
