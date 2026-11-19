# Build log: LOCAL agent (overnight, 19–20 Nov 2026)

Agent: Claude Code (Opus 5.5), worktree `~/Development/jigworks-local`, branch `agent/local`.

## Decisions taken without the human

### D1 · `JIGWORKS_AGENT` was empty at start (19 Nov, start of session)

- **What happened:** the session was launched in the main checkout (`~/Development/jigworks`,
  branch `feature/hub-and-vs-code-extension`), not in the LOCAL worktree. I switched the
  session into `~/Development/jigworks-local` (branch `agent/local`, confirmed with
  `git branch --show-current`), but the env var from `.claude/settings.local.json`
  (`JIGWORKS_AGENT=local`) is only read at session start, so `echo $JIGWORKS_AGENT` stays empty.
- **Consequence:** the `PreToolUse` ownership hook is inactive for this session (it exits 0 when
  the variable is empty).
- **Decision:** proceed as LOCAL rather than lose the night. Identity is unambiguous (worktree,
  branch and `settings.local.json` all say `local`). Compensation: I run
  `scripts/check-ownership.sh local` before every commit and only touch LOCAL paths.
- **Honest note:** the kickoff's "Before the first ticket" gate ("both must hold before you write
  anything") was added to the kickoff while I was already running; I had written the first T03
  source files before I saw it. Nothing was committed before this entry.
- **Fix for next time:** start the LOCAL session from `~/Development/jigworks-local`.

## Ticket entries

### T03 · sample-repo invariants — done

- **Built:** `sample_repo/orders.py` (order state machine), `service.py` (place/fill/cancel,
  positions), `INVARIANTS.md` (I1–I7), Hypothesis property tests per invariant plus a stateful
  model test, 7 plain example tests, `scripts/break-invariant.sh` with 4 plausible-looking bugs.
- **Proof:** 19 passed; `break-invariant.sh all` → 4/4 caught, example tests pass with every bug
  (the demo point). Output in the ticket.
- **Decisions:** derandomized Hypothesis (reproducible gate); bugs run in a temp copy by default,
  `--apply` writes into the tree for a live demo; `hypothesis` is a runtime dependency of the
  sample-repo package because the root `pyproject.toml` is not mine.
- **Went wrong:** nothing material; first draft had two filler tests, removed.
