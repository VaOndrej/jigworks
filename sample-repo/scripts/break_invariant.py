"""Apply a plausible-looking bug to the order service and show that the property tests catch it.

Default: work on a temporary copy of sample-repo, so the tree stays clean, and exit 0 only if
the property tests FAIL while the plain example tests still PASS (the demo point: the agent's
own example tests do not see the bug). ``--apply`` writes the bug into the real tree instead
(for a live demo; undo with ``git checkout sample-repo/sample_repo``).
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

SAMPLE_REPO = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Bug:
    name: str
    invariant: str
    story: str
    file: str
    old: str
    new: str


BUGS = [
    Bug(
        name="overfill",
        invariant="I1",
        story="'simplify' the overfill guard to compare against the order size",
        file="sample_repo/orders.py",
        old="if quantity > self.remaining:",
        new="if quantity > self.quantity:",
    ),
    Bug(
        name="cancel-terminal",
        invariant="I3",
        story="'inline' cancel and skip the transition table",
        file="sample_repo/orders.py",
        old="    def cancel(self) -> None:\n        self._transition(OrderStatus.CANCELLED)",
        new="    def cancel(self) -> None:\n        self.status = OrderStatus.CANCELLED",
    ),
    Bug(
        name="position-cumulative",
        invariant="I2",
        story="book the order's filled quantity instead of the fill's quantity",
        file="sample_repo/service.py",
        old="order.side.sign * fill.quantity",
        new="order.side.sign * order.filled_quantity",
    ),
    Bug(
        name="limit-one-sided",
        invariant="I6",
        story="'simplify' the limit check to one comparison for both sides",
        file="sample_repo/orders.py",
        old="worse = price > self.limit_price if self.side is Side.BUY else price < self.limit_price",
        new="worse = price > self.limit_price",
    ),
]
BY_NAME = {b.name: b for b in BUGS}


def apply(root: Path, bug: Bug) -> None:
    path = root / bug.file
    text = path.read_text()
    if text.count(bug.old) != 1:
        raise SystemExit(f"break-invariant: cannot apply '{bug.name}': anchor not found exactly once in {bug.file}")
    path.write_text(text.replace(bug.old, bug.new))


def run_pytest(root: Path, test_file: str) -> tuple[int, str]:
    env = {**os.environ, "PYTHONPATH": str(root)}
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", str(root / "tests" / test_file), "-q", "-p", "no:cacheprovider",
         "--rootdir", str(root), "-x", "--no-header", "-r", "f"],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stdout + proc.stderr


def check_one(bug: Bug) -> bool:
    print(f"== bug '{bug.name}' ({bug.invariant}): {bug.story}")
    print(f"   {bug.file}: {bug.old.strip().splitlines()[-1].strip()}")
    print(f"   -> {bug.new.strip().splitlines()[-1].strip()}")
    with tempfile.TemporaryDirectory(prefix="jigworks-break-") as tmp:
        root = Path(tmp) / "sample-repo"
        shutil.copytree(SAMPLE_REPO, root, ignore=shutil.ignore_patterns("__pycache__", ".hypothesis"))
        apply(root, bug)
        ex_code, _ = run_pytest(root, "test_examples.py")
        prop_code, prop_out = run_pytest(root, "test_invariants.py")
    failed_lines = [
        "FAILED tests/test_invariants.py::" + ln.split("::", 1)[-1]
        for ln in prop_out.splitlines()
        if ln.startswith("FAILED")
    ]
    print(f"   example tests:  {'pass' if ex_code == 0 else 'FAIL'}")
    print(f"   property tests: {'pass' if prop_code == 0 else 'FAIL'}")
    for ln in failed_lines:
        print(f"     {ln}")
    caught = prop_code != 0
    print(f"   => {'CAUGHT by the property tests' if caught else 'NOT CAUGHT'}"
          + ("" if ex_code == 0 else " (example tests also failed)"))
    return caught


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("bug", nargs="?", default="overfill", help="bug name, or 'all' (default: overfill)")
    parser.add_argument("--list", action="store_true", help="list the bugs")
    parser.add_argument("--apply", action="store_true", help="write the bug into the real tree")
    args = parser.parse_args()

    if args.list:
        for b in BUGS:
            print(f"{b.name:22} {b.invariant}  {b.story}")
        return 0
    if args.apply:
        bug = BY_NAME[args.bug]
        apply(SAMPLE_REPO, bug)
        print(f"applied '{bug.name}' to {SAMPLE_REPO / bug.file}; undo: git checkout sample-repo/sample_repo")
        return 0

    bugs = BUGS if args.bug == "all" else [BY_NAME[args.bug]]
    results = [check_one(b) for b in bugs]
    print(f"\n{sum(results)}/{len(results)} bugs caught by the property tests")
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
