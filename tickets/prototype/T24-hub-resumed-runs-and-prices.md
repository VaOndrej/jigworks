# T24 · Hub analytics: resumed runs stay live, every model has a price

| Field | Value |
|---|---|
| Status | review |
| Owner | hub |
| Label | `milestone-1` |
| Size | S |
| Demo critical path | no |
| Depends on | T13, T22 |
| Human time | 2 min |

## Goal

Runs & analytics showed the real run `run_20261120122836_6ab988` as "0 running" and "$0.00"
while it was live in the extension (review / fix loop, 64 %). Two bugs:

1. **Status.** The run ended `failed` at the fix loop limit and was continued with
   `jigworks resume --more-fixes` (T22). The later events carry `runStatus: running`, but the
   projection applied the old `run_finished` summary last, so its `status: failed` won.
2. **Cost.** The seed runs only into an empty database (`seed_if_empty`). The production hub was
   seeded on 19 Nov; the Opus 5.5 / Sonnet 5.5 prices were added to the seed on 20 Nov and never
   reached it. `claude-haiku-5-5` had no price at all. An unpriced model counts as $0.

## Acceptance criteria

- [x] An event with a non-terminal `runStatus` after `run_finished` makes the run live again: the stale runner summary is dropped, `currentNode` is set, no `finishedAt`.
- [x] `claude-haiku-5-5` is in the price list (`packages/contracts/fixtures/prices.json`, synced to `seed_data/`).
- [x] Every hub start adds price rows the database does not have yet (`sync_prices`, `ON CONFLICT DO NOTHING`; existing rows are never changed).
- [x] Replaying the real run's events: hub status equals the last `runStatus` in the log; the API-equivalent cost equals the CLI's own cost.
- [ ] After deploy, the production hub lists the 5.5 models in `/api/analytics/usage` → `prices` and shows the run's cost (human: needs the hub key).

## Notes

- Contract fixture change (`prices.json`), approved by the human in the session; the schema is unchanged.
- Haiku 5.5 input/output ($0.10 / $0.50 per MTok) come from the Anthropic price list. The cache rows ($0.20 write, $0.005 read) are derived with the same ratios as the other 5.5 rows in this file and are **not verified**; the >100K-token prompt tier ($0.50 / $2.50) is not modelled. On the real run Haiku is $0.07 of $117, so the error is negligible.
- `pnpm verify:hub` runs Playwright against the Vercel preview (not this change); its Workflows test fails on `stable 1.3.0` because the shared preview database now has newer stable releases. Pre-existing, not fixed here.

## Evidence

```
$ uv run pytest apps/hub-api/tests/test_projection.py -k resumed   # before the fix
E       AssertionError: assert 'rejected' == 'running'
$ uv run pytest apps/hub-api/tests/test_api.py -k prices_added     # before the fix
E         Extra items in the left set: 'claude-sonnet-5-5' 'claude-opus-5-5' 'claude-haiku-5-5'

$ uv run pytest apps/hub-api -q -p no:cacheprovider               # after
83 passed, 17 warnings in 10.92s

# replay of the real run's events.jsonl through hub_api.projection + the new price list
# (while the resumed run was live)
last runStatus in log: running | hub status: running              # was: failed
# after the run hit the limit again
last runStatus in log: failed | hub status: failed
usage models without a price: Counter()                           # was: claude-haiku-5-5 × 36
API-equivalent cost by model: {'claude-haiku-5-5': 0.07, 'claude-opus-5-5': 13.53, 'claude-sonnet-5-5': 103.5} total 117.09
CLI's own cost: 117.09
```
