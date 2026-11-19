"""`jigworks` — the local runner CLI.

    jigworks run --workflow workflows/feature-development --repo sample-repo --prompt "<task>"
    jigworks approve <runId> | request-changes <runId> --comment "…" | reject <runId>
    jigworks resume <runId>          # after a crash, a kill or a usage-limit pause
    jigworks ls [--json]             # runs and their status
    jigworks show <runId>            # RunSummary JSON
    jigworks audit <runId>           # AuditRecord JSON (+ API-equivalent cost)
    jigworks events <runId>          # the run's event log (JSONL)
    jigworks graph <workflow>        # get_graph() as GraphJSON

Every command that drives a run prints the run's new events as JSONL on stdout (one
`RunEvent` per line) and exits when the run finishes or stops at an interrupt or a pause; the
state is on disk (see store.py), so the next command picks it up in a new process.
Exit codes: 0 = ok (including waiting for a human, paused, rejected), 1 = run failed, 2 = usage error.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import jigworks_contracts as contracts

from . import __version__, git
from .adapters.base import Agent
from .adapters.claude import ClaudeAdapter, auth_status
from .adapters.fake import FakeAdapter, load_script
from .engine import Outcome, RunStateError, WorkflowRun, default_pr_opener
from .events import EventSink
from .ledger import Ledger
from .package import bundle_files, load_package
from .pricing import PriceTable
from .progress import weights_from_history
from .store import RunBusy, RunDir, Store, UnknownRun, default_home, new_run_id

PRICES = Path(contracts.__file__).resolve().parent.parent / "fixtures" / "prices.json"


class UsageError(Exception):
    pass


def eprint(*args: Any) -> None:
    print(*args, file=sys.stderr, flush=True)


def repo_root(path: Path) -> Path:
    try:
        return Path(git.git(path, "rev-parse", "--show-toplevel").strip())
    except (git.GitError, FileNotFoundError, NotADirectoryError) as exc:
        raise UsageError(f"{path} is not inside a git repository") from exc


def home_for(args: argparse.Namespace) -> Path:
    if getattr(args, "home", None):
        return Path(args.home).resolve()
    base = Path(getattr(args, "repo", None) or ".").resolve()
    return default_home(repo_root(base if base.is_dir() else base.parent))


def make_agent(meta: dict[str, Any]) -> Agent:
    if meta["adapter"] == "fake":
        return FakeAdapter(load_script(meta["fakeScript"]) if meta.get("fakeScript") else {})
    return ClaudeAdapter(claude_bin=os.environ.get("JIGWORKS_CLAUDE_BIN", "claude"))


def add_worktree(root: Path, path: Path, branch: str) -> str:
    for attempt in range(10):  # parallel `git worktree add` can race on the repo's lock files
        try:
            git.git(root, "worktree", "add", "-q", "-b", branch, str(path), "HEAD")
            return git.head(path)
        except git.GitError as exc:
            if "lock" not in str(exc) or attempt == 9:
                raise
            time.sleep(0.2 * (attempt + 1))
    raise AssertionError("unreachable")


def pr_remote(meta: dict[str, Any]) -> str:
    """A remote name stays a name; a path is resolved against the repo root, never the worktree
    (the push runs inside the worktree, where a relative path would point somewhere else)."""
    remote = meta.get("prRemote", "origin")
    candidate = Path(meta["repoRoot"]) / remote
    if not Path(remote).is_absolute() and ("/" in remote or remote.endswith(".git")) and candidate.exists():
        return str(candidate.resolve())
    return remote


@contextmanager
def open_run(store: Store, run_id: str, echo: bool = True) -> Iterator[tuple[RunDir, WorkflowRun]]:
    rd = store.get(run_id)
    meta = rd.meta()
    with rd.lock(), rd.checkpointer() as checkpointer:
        events = rd.events()
        sink = EventSink(run_id=run_id, events=events, next_seq=len(events))

        def persist(event: dict[str, Any]) -> None:
            rd.append_event(event)
            if echo:
                sys.stdout.write(json.dumps(event, separators=(",", ":")) + "\n")
                sys.stdout.flush()

        sink.subscribe(persist)
        package = load_package(rd.package_dir, digest=meta["digest"])
        run = WorkflowRun(
            package,
            run_id=run_id,
            cwd=Path(meta["worktree"]),
            agent=make_agent(meta),
            author_email=meta["authorEmail"],
            sink=sink,
            checkpointer=checkpointer,
            base_commit=meta["baseCommit"],
            options=meta.get("options", {}),
            pr_opener=default_pr_opener(remote=pr_remote(meta), base=meta.get("prBase", "main")),
            branch=meta["branch"],
            repo=meta.get("repo"),
            node_results=rd.node_results(),
            on_node_result=rd.append_node_result,
            weights=meta.get("weights"),
        )
        try:
            yield rd, run
        finally:
            rd.append_audit(run.audit())


def report(outcome: Outcome, run_id: str) -> int:
    msg = {
        "waiting_human": f"{run_id}: waiting for a human ({(outcome.interrupt or {}).get('stage')} review). "
        f"Next: jigworks approve|request-changes|reject {run_id}",
        "paused_usage_limit": f"{run_id}: paused by the usage limit. Next: jigworks resume {run_id}",
        "succeeded": f"{run_id}: succeeded",
        "rejected": f"{run_id}: rejected",
        "failed": f"{run_id}: failed",
    }.get(outcome.status, f"{run_id}: {outcome.status}")
    eprint(msg)
    return 1 if outcome.status == "failed" else 0


# --- commands ------------------------------------------------------------------------------------


def cmd_run(args: argparse.Namespace) -> int:
    workflow = Path(args.workflow).resolve()
    repo = Path(args.repo).resolve()
    root = repo_root(repo)
    rel = os.path.relpath(repo, root)
    home = Path(args.home).resolve() if args.home else default_home(root)
    store = Store(home)
    author = git.user_email(root) or "unknown@localhost"

    if args.adapter == "claude" and not args.skip_preflight:
        status = auth_status(os.environ.get("JIGWORKS_CLAUDE_BIN", "claude"))
        if not status.logged_in:
            eprint("claude is not logged in (claude auth status). Run `claude` and /login, then try again.")
            return 2

    files = bundle_files(workflow)
    probe = load_package(workflow)  # validates workflow.toml and computes the digest
    run_id = args.run_id or new_run_id()
    rd = store.create(run_id)
    package_dir = store.copy_package(rd, files)
    branch = f"jigworks/{run_id}"
    worktree = store.worktree_path(run_id)
    base = add_worktree(root, worktree, branch)

    history = [a for r in store.all() if r.run_id != run_id and (a := r.last_audit())]
    weights, source = weights_from_history(probe.manifest, probe.digest, history)
    options: dict[str, Any] = {}
    if rel not in (".", ""):
        options["gate"] = {"scope": [rel.rstrip("/") + "/"]}
    if args.max_fix_loops is not None:
        options["max_fix_loops"] = args.max_fix_loops
    meta = {
        "runId": run_id,
        "workflowDir": str(workflow),
        "packageDir": str(package_dir),
        "digest": probe.digest,
        "release": probe.release,
        "repoRoot": str(root),
        "repo": root.name,
        "scope": rel,
        "worktree": str(worktree),
        "branch": branch,
        "baseCommit": base,
        "adapter": args.adapter,
        "fakeScript": str(Path(args.fake_script).resolve()) if args.fake_script else None,
        "authorEmail": author,
        "weights": weights,
        "weightsSource": source,
        "options": options,
        "prRemote": args.pr_remote,
        "prBase": args.pr_base,
        "runnerVersion": __version__,
        "pid": os.getpid(),
    }
    rd.write_meta(meta)
    eprint(f"{run_id}: {probe.release} ({probe.digest[:19]}…) in {worktree}, weights from {source}")
    with open_run(store, run_id) as (_, run):
        outcome = run.start(args.prompt, title=args.title)
    return report(outcome, run_id)


def _decide(args: argparse.Namespace, decision: str) -> int:
    store = Store(home_for(args))
    with open_run(store, args.run_id) as (rd, run):
        approver = args.as_email or git.user_email(Path(rd.meta()["repoRoot"])) or "unknown@localhost"
        outcome = run.decide(decision, approver, getattr(args, "comment", None))
    return report(outcome, args.run_id)


def cmd_resume(args: argparse.Namespace) -> int:
    store = Store(home_for(args))
    with open_run(store, args.run_id) as (_, run):
        outcome = run.resume()
    return report(outcome, args.run_id)


def _ledger(rd: RunDir) -> Ledger:
    meta = rd.meta()
    return Ledger.replay(rd.events(), meta.get("weights") or {})


def run_row(rd: RunDir) -> dict[str, Any]:
    meta = rd.meta()
    led = _ledger(rd)
    status = led.status
    busy = rd.is_busy()
    if status == "running" and not busy:
        status = "interrupted"  # no process is working on it: `jigworks resume`
    return {
        "runId": rd.run_id,
        "release": meta["release"],
        "status": status,
        "node": (led.pending or {}).get("node") or (led.current[0] if led.current else None),
        "progress": led.progress(),
        "startedAt": led.started_at,
        "title": (led.started or {}).get("title"),
        "worktree": meta["worktree"],
        "busy": busy,
    }


def cmd_ls(args: argparse.Namespace) -> int:
    store = Store(home_for(args))
    rows = [run_row(rd) for rd in store.all()]
    if args.json:
        print(json.dumps(rows, indent=2))
        return 0
    if not rows:
        print("no runs")
        return 0
    print(f"{'RUN':32} {'RELEASE':28} {'STATUS':20} {'NODE':12} {'%':>6}  TITLE")
    for r in rows:
        print(f"{r['runId']:32} {r['release']:28} {r['status']:20} {(r['node'] or '-'):12} {r['progress']:>6}  {r['title'] or ''}")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    rd = Store(home_for(args)).get(args.run_id)
    print(json.dumps(_ledger(rd).summary(), indent=2))
    return 0


def cmd_audit(args: argparse.Namespace) -> int:
    rd = Store(home_for(args)).get(args.run_id)
    record = rd.last_audit() or _ledger(rd).audit()
    table = PriceTable.from_file(PRICES)
    try:
        cost = float(round(table.total(record.get("usage", [])), 6))
    except LookupError as exc:
        cost = None
        eprint(f"no price for a model in this run: {exc}")
    print(json.dumps({"audit": record, "apiEquivalentCostUsd": cost}, indent=2))
    return 0


def cmd_events(args: argparse.Namespace) -> int:
    rd = Store(home_for(args)).get(args.run_id)
    for e in rd.events():
        print(json.dumps(e, separators=(",", ":")))
    return 0


def cmd_graph(args: argparse.Namespace) -> int:
    print(json.dumps(load_package(Path(args.workflow)).graph_json(), indent=2))
    return 0


def cmd_inspect(args: argparse.Namespace) -> int:
    """Manifest, digest and graph of a workflow package, for the extension (no TOML parsing in TS)."""
    pkg = load_package(Path(args.workflow))
    print(json.dumps({"path": str(pkg.root), "release": pkg.release, "digest": pkg.digest,
                      "manifest": pkg.manifest, "graph": pkg.graph_json()}, indent=2))
    return 0


def cmd_unpack(args: argparse.Namespace) -> int:
    """Verify a release bundle against its digest and unpack it (T10 import, T15 sync).

    The digest check and the unsafe-path check are the frozen contract's `read_bundle`. Nothing
    is written unless both pass; the package lands in <dest>/package/ with jigworks-source.json."""
    import shutil

    from jigworks_contracts import bundle as cbundle

    data = Path(args.zip).read_bytes()
    expected = args.digest
    if not expected:
        sidecar = Path(args.zip + ".sha256")
        if not sidecar.exists():
            raise UsageError("no --digest and no <zip>.sha256 next to the bundle")
        expected = sidecar.read_text().strip()
    try:
        files = cbundle.read_bundle(data, expected)
    except ValueError as exc:
        eprint(f"jigworks: {exc}")
        return 3
    dest = Path(args.dest)
    staging = dest.with_name(dest.name + ".partial")
    if staging.exists():
        shutil.rmtree(staging)
    for rel, content in files.items():
        p = staging / "package" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content)
    pkg = load_package(staging / "package", digest=expected)
    meta = {"source": args.source, "channel": args.channel, "digest": expected, "release": pkg.release,
            "importedFrom": Path(args.zip).name}
    (staging / "jigworks-source.json").write_text(json.dumps({k: v for k, v in meta.items() if v}, indent=2))
    if dest.exists():
        shutil.rmtree(dest)
    staging.rename(dest)
    print(json.dumps({**meta, "path": str(dest / "package"), "manifest": pkg.manifest}, indent=2))
    return 0


def cmd_preflight(args: argparse.Namespace) -> int:
    """`claude auth status`, reduced to what may be shown (no email, no org)."""
    status = auth_status(os.environ.get("JIGWORKS_CLAUDE_BIN", "claude"))
    print(json.dumps({"loggedIn": status.logged_in, "authMethod": status.auth_method,
                      "subscriptionType": status.subscription_type}))
    return 0 if status.logged_in else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="jigworks", description="Jigworks local runner")
    p.add_argument("--version", action="version", version=f"jigworks {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    def with_home(sp: argparse.ArgumentParser) -> argparse.ArgumentParser:
        sp.add_argument("--home", help="state directory (default: <repo>/.jigworks or $JIGWORKS_HOME)")
        sp.add_argument("--repo", default=".", help=argparse.SUPPRESS)
        return sp

    r = sub.add_parser("run", help="start a run in a fresh git worktree")
    r.add_argument("--workflow", required=True, help="workflow package directory")
    r.add_argument("--repo", required=True, help="path in the target git repo (the agent may only change it)")
    r.add_argument("--prompt", required=True)
    r.add_argument("--title")
    r.add_argument("--adapter", choices=["claude", "fake"], default="claude")
    r.add_argument("--fake-script", help="JSON script for --adapter fake")
    r.add_argument("--run-id")
    r.add_argument("--home")
    r.add_argument("--pr-remote", default="origin", help="remote name or URL/path the PR branch is pushed to")
    r.add_argument("--pr-base", default="main")
    r.add_argument("--max-fix-loops", type=int)
    r.add_argument("--skip-preflight", action="store_true")
    r.set_defaults(fn=cmd_run)

    for name, decision, help_ in (("approve", "approve", "approve the open interrupt"),
                                  ("reject", "reject", "reject the open interrupt")):
        sp = with_home(sub.add_parser(name, help=help_))
        sp.add_argument("run_id")
        sp.add_argument("--as", dest="as_email", help="approver email (default: git config user.email)")
        sp.set_defaults(fn=lambda a, d=decision: _decide(a, d))
    rc = with_home(sub.add_parser("request-changes", help="send a comment back to the agent"))
    rc.add_argument("run_id")
    rc.add_argument("--comment", required=True)
    rc.add_argument("--as", dest="as_email")
    rc.set_defaults(fn=lambda a: _decide(a, "request_changes"))

    for name, fn, help_ in (("resume", cmd_resume, "continue after a crash or a usage-limit pause"),
                            ("show", cmd_show, "print the RunSummary"),
                            ("audit", cmd_audit, "print the AuditRecord and the API-equivalent cost"),
                            ("events", cmd_events, "print the event log")):
        sp = with_home(sub.add_parser(name, help=help_))
        sp.add_argument("run_id")
        sp.set_defaults(fn=fn)
    ls = with_home(sub.add_parser("ls", help="list runs"))
    ls.add_argument("--json", action="store_true")
    ls.set_defaults(fn=cmd_ls)
    g = sub.add_parser("graph", help="print get_graph() as GraphJSON")
    g.add_argument("workflow")
    g.set_defaults(fn=cmd_graph)
    i = sub.add_parser("inspect", help="print manifest, digest and graph of a workflow package")
    i.add_argument("workflow")
    i.set_defaults(fn=cmd_inspect)
    u = sub.add_parser("unpack", help="verify a release .zip against its digest and unpack it")
    u.add_argument("zip")
    u.add_argument("--digest", help="expected sha256:… (default: <zip>.sha256)")
    u.add_argument("--dest", required=True, help="target directory (gets package/ and jigworks-source.json)")
    u.add_argument("--source", choices=["imported", "hub"], default="imported")
    u.add_argument("--channel")
    u.set_defaults(fn=cmd_unpack)
    pf = sub.add_parser("preflight", help="check that claude is installed and logged in")
    pf.set_defaults(fn=cmd_preflight)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.fn(args)
    except (UsageError, UnknownRun, RunBusy, RunStateError) as exc:
        eprint(f"jigworks: {exc}")
        return 2
    except subprocess.CalledProcessError as exc:
        eprint(f"jigworks: {exc}\n{exc.stderr or ''}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
