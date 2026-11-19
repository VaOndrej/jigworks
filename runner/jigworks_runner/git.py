"""Small git helpers for the run's worktree (one commit per node, design.md §9)."""

from __future__ import annotations

import subprocess
from pathlib import Path

RUNNER_NAME = "Jigworks runner"


class GitError(RuntimeError):
    pass


def git(cwd: Path, *args: str, check: bool = True) -> str:
    proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise GitError(f"git {' '.join(args)} failed in {cwd}: {proc.stderr.strip()}")
    return proc.stdout


def head(cwd: Path) -> str:
    return git(cwd, "rev-parse", "HEAD").strip()


def user_email(cwd: Path) -> str | None:
    out = git(cwd, "config", "user.email", check=False).strip()
    return out or None


def commit_all(cwd: Path, message: str, author_email: str) -> tuple[str, list[str]]:
    """Commit everything in the worktree (empty commits allowed), return (hash, changed files)."""
    git(cwd, "add", "-A")
    git(
        cwd,
        "-c", f"user.name={RUNNER_NAME}",
        "-c", f"user.email={author_email}",
        "commit", "--allow-empty", "--no-verify", "-q", "-m", message,
    )
    sha = head(cwd)
    files = [f for f in git(cwd, "show", "--name-only", "--format=", sha).splitlines() if f]
    return sha, files


def changed_since(cwd: Path, base: str) -> list[str]:
    return [f for f in git(cwd, "diff", "--name-only", base, "HEAD").splitlines() if f]


def diffstat(cwd: Path, base: str, rev: str = "HEAD") -> dict[str, int]:
    files = added = removed = 0
    for line in git(cwd, "diff", "--numstat", base, rev).splitlines():
        a, r, _ = line.split("\t", 2)
        files += 1
        added += int(a) if a.isdigit() else 0
        removed += int(r) if r.isdigit() else 0
    return {"files": files, "linesAdded": added, "linesRemoved": removed}
