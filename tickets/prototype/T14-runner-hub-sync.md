# T14 · Runner → hub event sync

| Field | Value |
|---|---|
| Status | done |
| Owner | local |
| Label | `milestone-3` |
| Size | M |
| Demo critical path | no (below the cut line) |
| Depends on | T06 (T12 for the live check; until then a mock from `openapi.json`) |
| Human time | — |

## Goal

The runner posts events to `POST /api/runs/{id}/events`, queues locally when offline and syncs after recovery.

## Notes

Only the runner side. Requests carry `X-Jigworks-Key`. The hub's ingest endpoint is part of T12.

## Acceptance criteria

- [x] A test that cuts the network mid-run shows the queued events arriving afterwards; output pasted.

## Evidence

Verified 19 Nov 2026 by LOCAL in `agent/local`.

Code: `runner/jigworks_runner/hub.py`. The run's `events.jsonl` is the offline queue. The runner
keeps only the last acknowledged seq in `hub.json`, registers the run (`POST /api/runs`, RunCreate)
and posts batches of up to 200 events. A background thread syncs while a command runs and backs
off while the hub is down; `jigworks sync [runId|--all]` flushes. Config: `JIGWORKS_HUB_URL` or
`--hub-url` (stored in run.json), key from `HUB_PASSWORD` (never stored), optional
`VERCEL_AUTOMATION_BYPASS_SECRET`.

Tested against `jigworks_runner.testing.fakehub`, an in-process fake of the hub endpoints that
validates every body against the frozen contracts (RunCreate, EventBatch, EventBatchResult) and
dedupes on (runId, seq) like the real ingest.

`uv run pytest runner/tests/test_hub_sync.py -v -s`:

```
test_hub_sync_registers_the_run_and_streams_events PASSED
local events: 28, on the hub after the cut: 15, queued: 13
run_hub_cut: hub synced (13 new, 0 already there)
test_network_cut_mid_run_queues_events_and_they_arrive_afterwards PASSED
test_replay_of_already_sent_events_counts_duplicates PASSED
test_wrong_key_is_a_clear_error_and_events_stay_queued PASSED
============================== 4 passed in 11.40s ==============================
```

The cut: the fake hub goes down as soon as it has ingested `implement · running`. The run itself
finishes its command normally ("hub sync failed, 13 events queued … sent with the next command or
`jigworks sync`"). An explicit sync while the hub is still down keeps them queued (exit 1). Once
the hub is up, `jigworks sync` delivers the 13 queued events. The hub then holds seq 0..27 with no
gap, a second sync is a no-op, and the rest of the run streams live again up to `run_finished`.

## Notes

- **Not run against the real hub preview.** `bash e2e/local/hub-live.sh <preview url>` (a
  fake-adapter run synced to a deployment, then read back through the API) needs `HUB_PASSWORD`
  and the bypass secret from `.env.local`. The overnight session's permission check refused to
  load them, and I did not work around it. Human, to run it:
  `bash e2e/local/hub-live.sh https://jigworks-ov8hsrzbd-woncommerce-5172s-projects.vercel.app`
  (the newest Ready preview at 22:20 UTC).
- The fake hub covers the documented API shapes, not every hub behaviour (projection, SSE).
