"""Runner → hub sync (T14) against the fake hub: live sync, a network cut mid-run, the queued
events arriving afterwards, and a wrong key."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import jigworks_contracts as contracts
import pytest

from jigworks_runner.testing.fakehub import FakeHub

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / "workflows" / "feature-development"
SAMPLE = ROOT / "sample-repo"
FEATURE = 'def describe(order):\n    return f"{order.side.value} {order.quantity} {order.instrument}"\n'


def sh(cwd: Path, *args: str) -> str:
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=True).stdout


@pytest.fixture
def hub():
    h = FakeHub(key="test-key")
    h.start()
    yield h
    h.stop()


@pytest.fixture
def env(tmp_path: Path, hub: FakeHub):
    repo = tmp_path / "repo"
    shutil.copytree(SAMPLE, repo / "sample-repo", ignore=shutil.ignore_patterns("__pycache__", ".hypothesis", "scripts"))
    (repo / ".gitignore").write_text("__pycache__/\n.hypothesis/\n.pytest_cache/\n")
    for args in (("init", "-q", "-b", "main"), ("config", "user.email", "dev@example.com"), ("config", "user.name", "Dev"),
                 ("add", "-A"), ("commit", "-q", "-m", "base")):
        sh(repo, "git", *args)
    remote = tmp_path / "remote.git"
    sh(tmp_path, "git", "clone", "-q", "--bare", str(repo), str(remote))
    script = tmp_path / "script.json"
    script.write_text(json.dumps({
        "plan": [{"text": "1. Add describe(order)."}],
        "implement": [{"text": "working", "sleep": 1.0, "files": {"sample-repo/sample_repo/notes.py": FEATURE}}],
        "review": [{"text": "VERDICT: PASS"}],
    }))
    environ = {**os.environ, "JIGWORKS_HUB_URL": hub.url, "HUB_PASSWORD": "test-key"}
    return {"repo": repo, "remote": remote, "home": tmp_path / "home", "script": script, "env": environ}


def jw(env, *args: str, extra_env: dict | None = None) -> subprocess.CompletedProcess:
    cmd = [sys.executable, "-m", "jigworks_runner.cli", *args]
    if args[0] != "run":
        cmd += ["--home", str(env["home"])]
    return subprocess.run(cmd, cwd=env["repo"], capture_output=True, text=True, env={**env["env"], **(extra_env or {})})


def start(env, run_id: str):
    return jw(env, "run", "--workflow", str(WORKFLOW), "--repo", str(env["repo"] / "sample-repo"),
              "--prompt", "Add describe(order)", "--adapter", "fake", "--fake-script", str(env["script"]),
              "--run-id", run_id, "--home", str(env["home"]), "--pr-remote", str(env["remote"]))


def local_seqs(env, run_id: str) -> list[int]:
    lines = (env["home"] / "runs" / run_id / "events.jsonl").read_text().splitlines()
    return [json.loads(x)["seq"] for x in lines if x.strip()]


def test_hub_sync_registers_the_run_and_streams_events(env, hub):
    p = start(env, "run_hub_live")
    assert p.returncode == 0, p.stderr
    assert "hub synced" in p.stderr
    assert hub.runs["run_hub_live"]["release"] == "feature-development@1.6.0"
    assert contracts.validate("RunCreate", hub.runs["run_hub_live"]) == []
    assert hub.seqs("run_hub_live") == local_seqs(env, "run_hub_live")
    assert ("POST", "/api/runs", 201) in hub.requests
    state = json.loads((env["home"] / "runs" / "run_hub_live" / "hub.json").read_text())
    assert state["registered"] and state["ackedSeq"] == local_seqs(env, "run_hub_live")[-1]
    assert "test-key" not in (env["home"] / "runs" / "run_hub_live" / "run.json").read_text(), "the key is never stored"


def test_network_cut_mid_run_queues_events_and_they_arrive_afterwards(env, hub):
    assert start(env, "run_hub_cut").returncode == 0
    before_cut = len(hub.seqs("run_hub_cut"))
    # the hub goes down as soon as it has seen `implement` start: everything after is queued locally
    hub.down_after = ("implement", "running")
    approve = jw(env, "approve", "run_hub_cut")
    assert approve.returncode == 0, approve.stderr  # the run itself is not affected by the outage
    assert "hub sync failed" in approve.stderr and "events queued" in approve.stderr
    local = local_seqs(env, "run_hub_cut")
    on_hub = hub.seqs("run_hub_cut")
    assert before_cut < len(on_hub) < len(local), (before_cut, len(on_hub), len(local))
    assert any(e.get("node") == "implement" and e.get("status") == "running" for e in hub.events["run_hub_cut"].values())
    assert on_hub == list(range(len(on_hub))), "what reached the hub before the cut is a gap-free prefix"
    queued = len(local) - len(on_hub)
    print(f"\nlocal events: {len(local)}, on the hub after the cut: {len(on_hub)}, queued: {queued}")

    # still down: an explicit sync keeps them queued and says so
    still = jw(env, "sync", "run_hub_cut")
    assert still.returncode == 1 and "queued" in still.stderr

    # back up: the queued events arrive, in order, without gaps, nothing stored twice
    hub.down = False
    synced = jw(env, "sync", "run_hub_cut")
    assert synced.returncode == 0, synced.stderr
    print(synced.stderr.strip())
    assert hub.seqs("run_hub_cut") == local
    assert hub.seqs("run_hub_cut") == list(range(len(local)))
    again = jw(env, "sync", "run_hub_cut")
    assert "up to date" in again.stderr

    # the rest of the run streams normally again
    done = jw(env, "approve", "run_hub_cut")
    assert done.returncode == 0 and "hub synced" in done.stderr
    assert hub.seqs("run_hub_cut") == local_seqs(env, "run_hub_cut")
    last = hub.events["run_hub_cut"][max(hub.seqs("run_hub_cut"))]
    assert last["kind"] == "run_finished" and last["summary"]["status"] == "succeeded"


def test_replay_of_already_sent_events_counts_duplicates(env, hub):
    assert start(env, "run_hub_dup").returncode == 0
    state_file = env["home"] / "runs" / "run_hub_dup" / "hub.json"
    state = json.loads(state_file.read_text())
    state["ackedSeq"] = -1  # pretend the acknowledgement was lost
    state_file.write_text(json.dumps(state))
    again = jw(env, "sync", "run_hub_dup")
    assert again.returncode == 0
    assert "0 new" in again.stderr and "already there" in again.stderr
    assert hub.seqs("run_hub_dup") == local_seqs(env, "run_hub_dup")


def test_wrong_key_is_a_clear_error_and_events_stay_queued(env, hub):
    p = jw(env, "run", "--workflow", str(WORKFLOW), "--repo", str(env["repo"] / "sample-repo"), "--prompt", "x",
           "--adapter", "fake", "--fake-script", str(env["script"]), "--run-id", "run_hub_key",
           "--home", str(env["home"]), extra_env={"HUB_PASSWORD": "wrong"})
    assert p.returncode == 0, "the run works without the hub"
    assert "refused the key" in p.stderr and "check HUB_PASSWORD" in p.stderr
    assert "run_hub_key" not in hub.runs
    fixed = jw(env, "sync", "run_hub_key")
    assert fixed.returncode == 0 and hub.seqs("run_hub_key") == local_seqs(env, "run_hub_key")
