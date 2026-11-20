import type { RunEvent } from "./generated/types.js";

/** design.md §8 example, verbatim. Typed here so `tsc` proves it satisfies RunEvent. */
export const designExampleEvent: RunEvent = {
  runId: "run_123",
  release: "feature-development@1.3.0",
  node: "review",
  status: "running",
  attempt: 2,
  at: "2026-11-19T15:00:00Z",
};
