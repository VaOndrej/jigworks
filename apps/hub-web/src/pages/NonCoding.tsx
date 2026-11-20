export function NonCodingPage() {
  return (
    <main className="page page-narrow">
      <h1 className="h1">Non-coding teams</h1>
      <p className="lead">
        Not built in the prototype. This tab describes the direction: the same versioned, audited workflows, used by teams
        that do not write code.
      </p>

      <section className="card prose">
        <h2>The idea</h2>
        <p>
          A workflow in Jigworks is a LangGraph graph with human approvals, published as an immutable release and run by
          everyone in the same pinned version. Nothing in that model is specific to code. HR, legal and operations teams
          have the same need: a repeatable way of working with agents, a person who approves, and a record of what
          happened.
        </p>

        <h2>Examples</h2>
        <ul>
          <li>
            <b>HR: CV screening.</b> An agent reads each application against the role's must-haves and writes a short,
            cited assessment; a recruiter approves or overrides every decision; nobody is rejected without a human.
          </li>
          <li>
            <b>Legal: contract review.</b> An agent compares a supplier contract with the company's standard clauses and
            lists the deviations; counsel approves the redline before it goes out.
          </li>
          <li>
            <b>Operations: incident write-ups.</b> An agent drafts the post-incident report from the timeline and the
            chat log; the incident owner edits and approves it.
          </li>
        </ul>

        <h2>Base workflow + department variant</h2>
        <p>
          A central team publishes a base workflow. A department publishes a variant that adds its own check and approval
          nodes (LangGraph subgraphs and <code>interrupt</code>), for example a works-council approval in one country.
          Both are versioned releases, so analytics compare the variant with the base, release by release.
        </p>

        <h2>Running outside the IDE</h2>
        <p>
          Engineers run workflows from VS Code next to their repository. Non-coding teams need a runner without an IDE: a
          web form for the input, approvals in the hub or in chat, and documents instead of a git worktree. The audit
          trail, the price table and the human-delta loop stay the same.
        </p>

        <h2>Why it is not in the prototype</h2>
        <p>
          The prototype proves the loop on code, where the result can be checked by tests and invariants. Documents need
          different gates (citations, policy checks) and a different runner. Both are designed, not built.
        </p>
      </section>
    </main>
  );
}
