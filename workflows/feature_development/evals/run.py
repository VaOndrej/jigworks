"""Evals for feature-development: measure the workflow, not just the code (T07).

    uv run python -m workflows.feature_development.evals.run                    # scripted agents (default)
    uv run python -m workflows.feature_development.evals.run --adapter claude   # live, release models
    uv run python -m workflows.feature_development.evals.run --tasks 02,03      # a subset

Each task in `workflows/feature-development/evals/tasks/` runs through the real engine, the real
gate and git on a fresh copy of sample-repo; every human interrupt is approved. Per task the report
has: outcome, whether the final gate passed, whether the invariants hold on the final tree (checked
again here, independently of the gate), what the review and the gate caught, fix iterations,
tokens and API-equivalent cost.

`--adapter fake` replays each task's scripted agent. Several are adversarial on purpose (they break
an invariant, leak a credential), so the report shows whether the workflow's guardrails catch
them. It measures the workflow, not the model. `--adapter claude` measures both and costs real
usage (about $3–5 API-equivalent per task with the release's models, see T06).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import jigworks_contracts as contracts

from jigworks_runner.adapters.claude import ClaudeAdapter
from jigworks_runner.adapters.fake import FakeAdapter, FakeStep
from jigworks_runner.engine import WorkflowRun, default_pr_opener
from jigworks_runner.package import load_package
from jigworks_runner.pricing import PriceTable

ROOT = Path(__file__).resolve().parents[3]
PACKAGE_DIR = ROOT / "workflows" / "feature-development"
TASKS_DIR = PACKAGE_DIR / "evals" / "tasks"
RESULTS_DIR = PACKAGE_DIR / "evals" / "results"
SAMPLE = ROOT / "sample-repo"
PRICES = Path(contracts.__file__).resolve().parent.parent / "fixtures" / "prices.json"
FAKE_KEY = "QQQQ7777ZXCVBNML"  # completes an AKIA… key in task 04; built here so the repo holds no key


def sh(cwd: Path, *args: str) -> str:
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=True).stdout


def fresh_repo(tmp: Path) -> tuple[Path, Path]:
    repo = tmp / "repo"
    shutil.copytree(SAMPLE, repo / "sample-repo", ignore=shutil.ignore_patterns("__pycache__", ".hypothesis", "scripts"))
    (repo / ".gitignore").write_text("__pycache__/\n.hypothesis/\n.pytest_cache/\n")
    for args in (("init", "-q", "-b", "main"), ("config", "user.email", "evals@example.com"),
                 ("config", "user.name", "Evals"), ("add", "-A"), ("commit", "-q", "-m", "base")):
        sh(repo, "git", *args)
    remote = tmp / "remote.git"
    sh(tmp, "git", "init", "-q", "--bare", str(remote))
    return repo, remote


def script_of(task: dict[str, Any]) -> dict[str, list[FakeStep]]:
    raw = json.loads(json.dumps(task["fake"]["script"]).replace("@@FAKEKEY@@", FAKE_KEY))
    return {node: [FakeStep.from_json(s) for s in steps] for node, steps in raw.items()}


def invariants_hold(repo: Path) -> tuple[bool, str]:
    """Run the property tests on the final tree, independently of the workflow's gate."""
    env = {**os.environ, "PYTHONPATH": str(repo / "sample-repo")}
    proc = subprocess.run([sys.executable, "-m", "pytest", "sample-repo/tests/test_invariants.py", "-q", "-p", "no:cacheprovider"],
                          cwd=repo, env=env, capture_output=True, text=True)
    last = [ln for ln in proc.stdout.splitlines() if ln.strip()][-1:] or ["no output"]
    return proc.returncode == 0, last[0]


def run_task(task: dict[str, Any], adapter: str, prices: PriceTable) -> dict[str, Any]:
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix=f"jigworks-eval-{task['id']}-") as tmp:
        repo, remote = fresh_repo(Path(tmp))
        agent = FakeAdapter(script_of(task)) if adapter == "fake" else ClaudeAdapter()
        run = WorkflowRun(
            load_package(PACKAGE_DIR), run_id=f"eval_{task['id'].replace('-', '_')}", cwd=repo, agent=agent,
            author_email="evals@example.com", pr_opener=default_pr_opener(remote=str(remote), base="main"),
        )
        outcome = run.start(task["prompt"], title=task["title"])
        decisions = 0
        while outcome.status == "waiting_human" and decisions < 6:
            outcome = run.decide("approve", "evals@example.com")
            decisions += 1
        events = run.sink.events
        gates = [e["gateResult"] for e in events if e["kind"] == "gate_result"]
        reviews = [e for e in events if e["kind"] == "node_status" and e["node"] == "review" and e["status"] in ("succeeded", "failed")]
        held, detail = invariants_hold(repo)
        # Control: the same check on the implementer's first commit, i.e. what would have shipped
        # without the review, the gate and the fix loop.
        impl = next((s for s in run.ledger.steps if s["node"] == "implement" and s.get("commit")), None)
        broken_after_implement = None
        if impl:
            snap = Path(tmp) / "after-implement"
            sh(repo, "git", "worktree", "add", "-q", "--detach", str(snap), impl["commit"])
            ok, _ = invariants_hold(snap)
            broken_after_implement = not ok
            sh(repo, "git", "worktree", "remove", "--force", str(snap))
        summary = run.ledger.summary()
        usage = summary["usage"]
        cost = float(prices.total(run.ledger.usage)) if run.ledger.usage else 0.0
        caught = [c["name"] for g in gates for c in g["checks"] if not c["passed"]]
        return {
            "id": task["id"],
            "title": task["title"],
            "tempts": task.get("tempts", ""),
            "behaviour": task["fake"]["behaviour"] if adapter == "fake" else "live agent",
            "outcome": outcome.status,
            "gatePassed": bool(gates and gates[-1]["passed"]),
            "invariantsHold": held,
            "brokenAfterImplement": broken_after_implement,
            "invariantDetail": detail,
            "reviewFailures": sum(1 for r in reviews if r["status"] == "failed"),
            "gateFailures": sum(1 for g in gates if not g["passed"]),
            "caughtBy": sorted(set(caught)),
            "fixIterations": summary.get("fixLoops", 0),
            "tokens": {k: usage[k] for k in ("input", "output", "cache_write", "cache_read")},
            "costUsd": round(cost, 4),
            "seconds": round(time.monotonic() - started, 1),
            "changedFiles": summary.get("changedFiles", []),
        }


def report(rows: list[dict[str, Any]], adapter: str, release: str, digest: str) -> str:
    now = datetime.now(UTC)
    lines = [
        f"# Evals · feature-development · {now:%Y-%m-%d}",
        "",
        f"- Release: `{release}` (`{digest}`)",
        f"- Adapter: `{adapter}`" + (" (scripted agents; several adversarial on purpose: this measures the workflow's guardrails, not the model)" if adapter == "fake" else " (live, the release's models)"),
        f"- Run: `uv run python -m workflows.feature_development.evals.run --adapter {adapter}` at {now:%H:%M} UTC",
        "- \"Invariants hold\" is checked again after the run on the final tree, independently of the gate.",
        "",
        "| Task | Tempts | Invariants broken after `implement` (control) | Caught by | Fix iterations | Outcome | Gate passed | Invariants hold at the end | Tokens in / out / cache | Cost (API eq.) |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        t = r["tokens"]
        caught = ", ".join(([f"review ×{r['reviewFailures']}"] if r["reviewFailures"] else []) + r["caughtBy"]) or "—"
        control = {True: "**yes**", False: "no", None: "—"}[r["brokenAfterImplement"]]
        lines.append(
            f"| {r['id']} {r['title']} | {r['tempts']} | {control} | {caught} | {r['fixIterations']} | {r['outcome']} | "
            f"{'yes' if r['gatePassed'] else 'NO'} | {'yes' if r['invariantsHold'] else 'NO'} | "
            f"{t['input']} / {t['output']} / {t['cache_write'] + t['cache_read']} | ${r['costUsd']:.4f} |"
        )
    held = sum(r["invariantsHold"] for r in rows)
    broken = sum(1 for r in rows if r["brokenAfterImplement"])
    lines += [
        "",
        f"**Summary:** after `implement`, {broken}/{len(rows)} runs had broken an invariant; at the end "
        f"{held}/{len(rows)} runs have every invariant intact; "
        f"{sum(r['gateFailures'] for r in rows)} gate failures and {sum(r['reviewFailures'] for r in rows)} review failures "
        f"were caught and fixed inside the workflow; {sum(r['fixIterations'] for r in rows)} fix iterations in total.",
        "",
        "## Per task",
        "",
    ]
    for r in rows:
        lines += [f"- **{r['id']}** — {r['behaviour']}. Final property tests: `{r['invariantDetail']}`. "
                  f"Files touched during the run: {', '.join(r['changedFiles']) or '—'}. {r['seconds']} s."]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--adapter", choices=["fake", "claude"], default="fake")
    p.add_argument("--tasks", help="comma-separated task id prefixes, e.g. 02,03")
    p.add_argument("--no-write", action="store_true", help="print the report, do not write results/")
    args = p.parse_args(argv)
    tasks = [json.loads(f.read_text()) for f in sorted(TASKS_DIR.glob("*.json"))]
    if args.tasks:
        wanted = args.tasks.split(",")
        tasks = [t for t in tasks if any(t["id"].startswith(w) for w in wanted)]
    pkg = load_package(PACKAGE_DIR)
    prices = PriceTable.from_file(PRICES)
    rows = []
    for t in tasks:
        print(f"· {t['id']} …", file=sys.stderr, flush=True)
        rows.append(run_task(t, args.adapter, prices))
    md = report(rows, args.adapter, pkg.release, pkg.digest)
    print(md)
    if not args.no_write:
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        out = RESULTS_DIR / f"{datetime.now(UTC):%Y-%m-%d}-{args.adapter}.md"
        out.write_text(md)
        print(f"written: {out.relative_to(ROOT)}", file=sys.stderr)
    return 0 if all(r["invariantsHold"] for r in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
