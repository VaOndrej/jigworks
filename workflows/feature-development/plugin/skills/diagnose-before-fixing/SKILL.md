---
name: diagnose-before-fixing
description: Use when a test, the gate or a review shows that the change is broken and the cause is not obvious. Build a failing feedback loop, find the root cause with falsifiable hypotheses, then fix it once with a regression test.
---

# Diagnose before fixing

A fix without a known cause is a guess, and a guess usually moves the symptom. Find the cause
first; it is faster than another fix round.

## 1. Build a feedback loop that goes red

You need one command that shows this exact failure, that you have already run, and that is:

- **on the real path**: it drives the code that fails and checks the reported symptom, not
  merely "does not crash";
- **deterministic**: same verdict every run (pin the clock, seed random values, isolate files);
- **fast**: seconds, not minutes.

In order of preference: the failing test itself (run alone), a new failing test at the
interface that reaches the bug, a small script with a fixture input, a property test that
searches many inputs for the failure. For a flaky failure, loop it until the failure rate is
high enough to debug.

Do not start theorising before this command exists. If you cannot build one, say so in your
reply and list what you tried.

## 2. Read and minimise

Read the whole error and stack trace: file, line, message. Check what changed (`git diff` of the
change). Then cut inputs, steps and setup one at a time while the loop stays red, until every
remaining part is needed for the failure.

## 3. Hypotheses

Write down three to five ranked hypotheses. Each one predicts something checkable: "If X is the
cause, then changing Y makes the failure disappear." A hypothesis without a prediction is a
hunch: sharpen it or drop it. Compare with similar code in the repo that works and list every
difference.

## 4. Probe, one variable at a time

Each probe tests one prediction. Prefer a targeted assertion or a log at the boundary that
separates two hypotheses. Tag temporary logs with a unique prefix (`[DEBUG-fd1]`) so you can
remove them all with one search. Trace a bad value back to where it is created and fix it there,
not where it is noticed.

## 5. Fix once

1. Turn the minimised loop into a regression test at an interface where the bug really occurs,
   and watch it fail.
2. Make one change that addresses the cause. No unrelated improvements in the same change.
3. Watch the regression test pass, then run the gate's whole test command.
4. Remove every tagged debug line and scratch file.

## When fixes keep failing

If a fix did not work, go back to step 3 with what you learned; do not stack another fix on
top. If three fixes in a row each revealed a new problem somewhere else, the design is wrong,
not the last line. Stop fixing and say so in your reply: what you tried, what each attempt
showed, and what you think has to change. The human decides from there.

## In the reply

State the cause you confirmed (one line), the regression test that guards it, and the test
command with its result.
