// Button labels of the approve_fix card. The decision behind them is always the same three
// (approve / request_changes / reject); what Approve does depends on why the human is asked, and
// the frozen interrupt contract has no field for it, so it is read from the workflow's text
// (feature-development 1.8.0). Pure, so it is unit-tested.

export interface FixButtons {
  approve: string;
  note: string;
  stop: string;
  /** Under the buttons while the comment field is empty. */
  idleHint: string;
  /** Under the buttons while a comment is typed. */
  noteHint: string;
}

const ACCEPT = /^## (Changes to protected files|New suppressions)\s*$/m;
const RECHECK = /^(The last fix changed nothing|The fixer is blocked on something only you can do)/;

export function fixButtons(interrupt: { message?: string; plan?: string }): FixButtons {
  const base = { stop: "Stop the run", noteHint: "Enter sends your note to the fixer and continues · clear the text to continue without one" };
  if (ACCEPT.test(interrupt.plan ?? "")) {
    return {
      ...base,
      approve: "Accept these changes",
      note: "Send my note to the fixer",
      idleHint: "Accept these changes accepts exactly what the report shows and re-runs the gate · a note does not accept them",
      noteHint: "Enter sends your note to the fixer; it does not accept the changes · clear the text to accept them instead",
    };
  }
  if (RECHECK.test(interrupt.message ?? "")) {
    return {
      ...base,
      approve: "Re-run the check",
      note: "Continue with my note",
      idleHint: "Re-run the check on the change as it is, or type what you did or a hint and press Enter",
    };
  }
  return { ...base, approve: "Continue fixing", note: "Continue with my note", idleHint: "Continue as it is, or type a hint or your answers and press Enter" };
}
