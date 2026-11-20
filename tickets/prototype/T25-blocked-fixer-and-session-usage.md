# T25 · Blocked fixer, gate deadlocks, usage of resumed sessions (`feature-development` 1.7.0)

| Field | Value |
|---|---|
| Status | review |
| Owner | local |
| Label | `milestone-1` |
| Size | M |
| Demo critical path | no |
| Depends on | T22, T24 |
| Human time | 5 min |

## Goal

The real run `run_20261120122836_6ab988` (1.6.0, continued with `resume --more-fixes`) went round
after round without progress and showed $168–195:

1. The fixer could not download a chart library (denied) and said so in prose; each round it
   changed nothing, and a new reviewer found 3 to 14 different problems. Nothing stopped it.
2. Then the gate failed on two things the fixer may not touch: `INVARIANTS.md` (created by the
   implementer as the plan said, required by a test from write_tests, but "protected") and bandit
   B108 in a test from write_tests (read-only for implement and fix).
3. Claude CLI 2.1.329 reports `modelUsage` of a `--resume` call as the session's running total; the
   runner recorded it per call, so the fixer session (22 resumes) was counted 22 times. Real cost
   ~$25, shown $195.

## Acceptance criteria

- [x] A fix that changed nothing (untracked new files count as changes) goes straight to `approve_fix` ("no_changes"), without another review.
- [x] The fixer writes `NEEDS HUMAN: …` lines for what only the human can do; they go straight to `approve_fix` ("needs_human"), listed under "What the fixer needs from you" with the fixer's last reply.
- [x] Gate: a new `INVARIANTS.md` belongs to the implementer; an existing one stays read-only.
- [x] Gate: bandit findings in the tests from write_tests are reported ("not counted, in the read-only tests") but do not fail the gate.
- [x] Runner: a resumed call records only its own usage (`jigworks_contracts.usage.this_call`), also after a run recorded running totals.
- [x] Hub and extension read runs recorded with running totals per call (`per_call`, same rule in Python and TypeScript); the hub rebuilds a run's usage rows on every ingest.
- [x] The real run's events: extension and Python rule both give $24.98 (was $195.50).
- [ ] Published to the hub as 1.7.0 (human).
- [ ] Production hub shows the real run's corrected cost after its next ingest (human).

## Notes

- The running-total rule is a heuristic, because a UsageRecord has no field that says which kind it is (`additionalProperties: false`, frozen contract): the leading records of a session and model where no field shrinks and the output grows are running totals; after the first record that breaks this they are per call. A per-call series is misread only if a later call is at least as large as the first one in every field (the first call writes the whole prompt cache, so this does not happen in practice). Old CLIs that report per call are kept as they are.
- Haiku background calls of the old run (identical records, $0.0019 each) are read as separate calls; whether they were running totals cannot be told. $0.04 in total.
- The hub fixes an already stored run only when that run ingests new events (`reproject`); runs that never sync again keep their old usage rows.
- Bandit findings in tests from write_tests are no longer blocking; the reviewer and the human must read them in the gate summary. Catching them at write_tests time would be better (not built).
- The run on 1.6.0 cannot use any of this: its release is pinned.

## Evidence

```
$ claude --version   # 2.1.329; 4 calls of one Haiku session, the 4th with stream-json
assistant msg usage {'input_tokens': 2, 'cache_creation_input_tokens': 73, 'cache_read_input_tokens': 281468, 'output_tokens': 6}
modelUsage {'claude-haiku-5-5': {'inputTokens': 1188, 'outputTokens': 39, 'cacheReadInputTokens': 431236, 'cacheCreationInputTokens': 494061, 'costUSD': 0.4511451, ...}}

# before the fixes (red):
test_adapter_resumed_session_with_cumulative_usage_records_only_this_call   assert (1188, 39, 494061, 431236) == (2, 6, 73, 281468)
test_a_blocked_fixer_asks_the_human_at_once                                 FAILED
test_a_fix_that_changes_nothing_asks_the_human                              FAILED
test_implement_may_create_an_invariants_file_but_not_change_one             assert 'waiting_human' == 'succeeded'
test_security_findings_in_the_read_only_tests_do_not_block_the_fixer        assert 'waiting_human' == 'succeeded'

$ uv run pytest workflows/feature-development/tests -q -p no:cacheprovider
59 passed, 17 warnings in 223.90s (0:03:43)
$ uv run pytest runner packages/contracts -q -p no:cacheprovider
114 passed, 1 skipped, 17 warnings in 71.47s
$ uv run pytest apps/hub-api packages/contracts/tests/test_usage.py runner/tests/test_adapter_claude.py -q
120 passed, 1 skipped
$ pnpm --filter vscode test:unit      # 23 passing
$ pnpm --filter vscode test           # 31 passing, 1 pending

# the real run, folded by the compiled extension code and by the Python rule
events 1394 | before (sum of records): $195.50 | extension now: API equivalent $24.98 / CLI $24.98
python per_call: CLI $24.98
```
