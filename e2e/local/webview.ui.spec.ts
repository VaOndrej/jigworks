// The extension's webviews, standalone, replaying the recorded runs (no VS Code, no tokens).
// Screenshots at 1440 px go to e2e/local/screenshots/.
import { expect, test, type Page } from "@playwright/test";
import * as path from "node:path";
import { pathToFileURL } from "node:url";

const page = pathToFileURL(path.join(__dirname, "../../clients/vscode/out/standalone/index.html")).href;
const shots = path.join(__dirname, "screenshots");

async function open(p: Page, query: string) {
  await p.goto(`${page}?${query}`);
  await expect(p.locator(".vs[data-ready='1']")).toBeVisible();
}

test("new session: prompt in the middle, workflow from the sidebar, models from the release", async ({ page: p }) => {
  await open(p, "screen=new&runs=run_fd_0007,run_fd_0005,run_fd_0002");
  await expect(p.getByRole("heading", { name: "What should the agents work on?" })).toBeVisible();
  await expect(p.locator(".chip-wf")).toHaveText("feature-development@1.3.0 · stable");
  await expect(p.getByText("Models are set by the workflow release")).toContainText("Sonnet 5");
  await expect(p.locator(".step.human")).toHaveCount(2);
  await expect(p.locator(".attachment")).toHaveCount(2);
  await expect(p.getByRole("button", { name: "+ Attach" })).toBeVisible();
  await expect(p.getByText(/typical run \$\d+\.\d\d \(median of 1/)).toBeVisible();
  await expect(p.getByRole("button", { name: "Start session" })).toBeEnabled();
  await expect(p.locator(".session")).toHaveCount(3);
  await p.screenshot({ path: path.join(shots, "vscode-new-session-1440.png") });
});

test("running session: NOW on implement, % of plan, live agent output", async ({ page: p }) => {
  await open(p, "screen=session&run=run_fd_0007&runs=run_fd_0007,run_fd_0005,run_fd_0002&tab=output");
  await expect(p.locator(".gnode.now")).toHaveAttribute("data-node", "implement");
  await expect(p.locator(".now-pill")).toHaveText("NOW");
  await expect(p.locator(".gnode[data-node='plan']")).toHaveClass(/done/);
  await expect(p.locator(".gnode[data-node='approve_plan']")).toContainText("✓");
  await expect(p.locator(".big")).toHaveText("30 %");
  await expect(p.locator(".log")).toContainText("▸");
  await expect(p.getByText("NEXT FOR YOU")).toBeVisible();
  await p.screenshot({ path: path.join(shots, "vscode-running-session-1440.png") });
});

test("review: Review badge instead of %, Approve / Request changes / Reject", async ({ page: p }) => {
  await open(p, "screen=session&run=run_fd_0005&runs=run_fd_0007,run_fd_0005,run_fd_0002");
  await expect(p.locator(".session.active .badge-review")).toBeVisible();
  await expect(p.locator(".gnode.needs")).toHaveAttribute("data-node", "approve_pr");
  await expect(p.getByRole("tab", { name: "Activity" }).or(p.locator(".tab.on"))).toHaveText("Activity");
  await expect(p.getByText(/Test report: gate PASS/)).toBeVisible();
  await expect(p.getByRole("button", { name: "Audit log" })).toBeVisible();
  await expect(p.getByRole("button", { name: "Diff (worktree)" })).toBeVisible();
  await expect(p.getByRole("button", { name: "Approve" })).toBeEnabled();
  await expect(p.getByRole("button", { name: "Request changes" })).toBeDisabled();
  await p.getByLabel("Comment for the agent").fill("Use Decimal for amounts.");
  await expect(p.getByRole("button", { name: "Request changes" })).toBeEnabled();
  await expect(p.getByRole("button", { name: "Reject" })).toBeEnabled();
  await p.screenshot({ path: path.join(shots, "vscode-review-1440.png") });
});

test("agent questions render as Markdown: headings, bold, tables, code", async ({ page: p }) => {
  await p.addInitScript(() => localStorage.removeItem("jigworks.liveView"));
  await open(p, "screen=session&run=run_md_0001&runs=run_md_0001,run_fd_0007&tab=output");
  const plan = p.locator(".next .plan");
  await expect(plan.locator("h3", { hasText: "Discount model" })).toBeVisible();
  await expect(plan.locator("strong", { hasText: "I'd pick (a)." })).toBeVisible();
  await expect(plan.locator("table th")).toHaveText(["Rule", "Proposal", "Why"]);
  await expect(plan.locator("table tbody tr")).toHaveCount(3);
  await expect(plan.locator("code", { hasText: "ROUND_HALF_EVEN" })).toBeVisible();
  await expect(plan.locator("del")).toHaveText("loyalty points");
  await expect(plan).not.toContainText("###");
  await expect(p.locator(".next .md-message strong").first()).toHaveText("Request changes");
  await expect(p.locator(".log .l-text table")).toBeVisible();
  await p.screenshot({ path: path.join(shots, "vscode-markdown-questions-1440.png") });
});

test("live view collapses to one line so the questions get the whole page, and stays collapsed", async ({ page: p }) => {
  await p.addInitScript(() => {
    if (!sessionStorage.getItem("seeded")) {
      localStorage.removeItem("jigworks.liveView");
      sessionStorage.setItem("seeded", "1");
    }
  });
  await open(p, "screen=session&run=run_md_0001&runs=run_md_0001,run_fd_0007");
  await expect(p.locator(".graph-card")).toBeVisible();
  await p.getByRole("button", { name: "Hide live view" }).click();
  await expect(p.locator(".graph-card")).toHaveCount(0);
  await expect(p.locator(".progress-card")).toHaveCount(0);
  await expect(p.locator(".output")).toHaveCount(0);
  await expect(p.locator(".live-strip")).toContainText("11 %");
  await expect(p.getByRole("button", { name: "Approve" })).toBeVisible();
  const before = await p.locator(".next").boundingBox();
  expect(before!.width).toBeGreaterThan(900);
  await p.screenshot({ path: path.join(shots, "vscode-live-view-collapsed-1440.png") });

  await p.reload();
  await expect(p.locator(".vs[data-ready='1']")).toBeVisible();
  await expect(p.locator(".graph-card")).toHaveCount(0);
  await p.locator(".live-strip").click();
  await expect(p.locator(".graph-card")).toBeVisible();
  await expect(p.getByRole("button", { name: "Hide live view" })).toBeVisible();
});

type Decide = { type: string; decision?: string; comment?: string };
const decides = (p: Page) => p.evaluate(() => (window as unknown as { __decides: Decide[] }).__decides);

test("gate: typed text never approves; Enter sends it as Request changes", async ({ page: p }) => {
  await open(p, "screen=session&run=run_md_0004&runs=run_md_0004,run_fd_0007");
  const box = p.getByLabel("Comment for the agent");
  const approve = p.getByRole("button", { name: "Approve" });
  const changes = p.getByRole("button", { name: "Request changes" });
  await expect(box).toHaveAttribute("placeholder", /Enter to send, Shift\+Enter for a new line/);
  await expect(approve).toBeEnabled();
  await expect(approve).toHaveClass(/primary/);

  await box.focus();
  await p.keyboard.press("Enter");
  expect(await decides(p)).toHaveLength(0);

  await box.fill("1. spot first");
  await expect(approve).toBeDisabled();
  await expect(changes).toBeEnabled();
  await expect(changes).toHaveClass(/primary/);
  await expect(p.locator(".gate-hint")).toHaveText("Enter sends your text as Request changes · clear the text to approve");
  await expect(p.getByRole("button", { name: "Reject" })).toBeEnabled();
  await p.locator(".gate-hint").scrollIntoViewIfNeeded();
  await p.screenshot({ path: path.join(shots, "vscode-gate-text-typed-1440.png") });

  await p.keyboard.press("Shift+Enter");
  await p.keyboard.type("2. agree");
  expect(await decides(p)).toHaveLength(0);
  await expect(box).toHaveValue("1. spot first\n2. agree");

  await box.fill("");
  await expect(approve).toBeEnabled();
  await box.fill("1. spot first");
  await p.keyboard.press("Enter");
  expect(await decides(p)).toEqual([{ type: "decide", runId: "run_md_0004", decision: "request_changes", comment: "1. spot first" }]);
  await expect(box).toHaveValue("");
  await expect(box).toBeDisabled();
  await expect(approve).toBeDisabled();
  await expect(p.getByRole("button", { name: "Reject" })).toBeDisabled();
});

test("gate: the next brainstorming round starts with an empty, enabled field", async ({ page: p }) => {
  await open(p, "screen=session&run=run_md_0004&runs=run_md_0004,run_fd_0007&replay=round2");
  const box = p.getByLabel("Comment for the agent");
  await box.fill("1. spot first");
  await box.press("Enter");
  await expect(p.locator(".next.waiting .md-message")).toContainText("round 2");
  await expect(box).toHaveValue("");
  await expect(box).toBeEnabled();
  await expect(p.getByRole("button", { name: "Approve" })).toBeEnabled();
  await expect(p.getByRole("button", { name: "Reject" })).toBeEnabled();
  await expect(p.locator(".vs-tab.on")).toContainText("· brainstorm");
});

test("graph: a gate sent back with Request changes is not shown as approved", async ({ page: p }) => {
  await open(p, "screen=session&run=run_md_0002&runs=run_md_0002,run_md_0003,run_fd_0005&now=2026-11-20T12:45:43Z");
  const gate = p.locator(".gnode[data-node='approve_plan']");
  await expect(gate).toHaveClass(/changes/);
  await expect(gate).not.toHaveClass(/done/);
  await expect(gate).toContainText("↺ changes · va.ondrej, 12:43");
  await expect(gate).not.toContainText("✓");
  await expect(p.locator(".gnode[data-node='plan']")).toHaveClass(/now/);
  await expect(p.locator(".gnode[data-node='plan']")).toContainText("running · 2:15 · try 2");
  await expect(p.locator(".legend", { hasText: "changes requested" })).toBeVisible();
  await expect(p.locator(".progress-card")).toContainText("your plan approval ≈ 11 %");
  await p.screenshot({ path: path.join(shots, "vscode-gate-changes-requested-1440.png") });
});

test("running step looks alive: Now card, heartbeat, plain-language actions, tabs", async ({ page: p }) => {
  await open(p, "screen=session&run=run_md_0003&runs=run_md_0003,run_md_0004,run_md_0002&tab=output&now=2026-11-20T13:49:45Z");
  const now = p.getByRole("region", { name: "Now" });
  await expect(now.locator(".eyebrow")).toHaveText("NOW · WRITE TESTS");
  await expect(now.locator(".live-line")).toHaveText("Working · 2:15");
  await expect(p.getByRole("button", { name: "Stop" })).toBeVisible();
  await expect(now.locator(".now-action")).toHaveText("Running tests · 4 s ago");
  await expect(now.locator(".now-list li")).toHaveCount(4);
  await expect(now.locator(".now-list li").first()).toContainText("Editing test_discounts.py");
  await expect(now.locator(".now-counters")).toContainText("3 files touched");
  await expect(now.locator(".now-counters")).toContainText("5 tool calls");
  await expect(now.locator(".now-counters")).toContainText("3k output tokens");
  await expect(now).toContainText("Next for you ≈");
  await expect(p.locator(".gnode[data-node='write_tests']")).toContainText("running · 2:15");
  await expect(p.locator(".gnode.now.alive .live-dot")).toBeVisible();
  await expect(p.locator(".pbar-now.working")).toBeVisible();
  await expect(p.locator(".vs-tab[data-run='run_md_0003']")).toHaveText("Přidej účtování slev pro… · running tests · 12 %");
  await expect(p.locator(".vs-tab[data-run='run_md_0004']")).toHaveText("Brainstorm a paper… · brainstorm");
  // Finish the one-off fade-in of the action list; the infinite pulse is frozen for the shot.
  await p.screenshot({ path: path.join(shots, "vscode-running-now-card-1440.png"), animations: "disabled" });
});

test("runner gone while the run is unfinished: a neutral 'Agent stopped' with Resume", async ({ page: p }) => {
  await open(p, "screen=session&run=run_md_0003&runs=run_md_0003&alive=0&now=2026-11-20T14:10:00Z");
  const now = p.getByRole("region", { name: "Now" });
  await expect(now.locator(".live-line")).toHaveText("Agent stopped · last activity 13:49 · Resume");
  await expect(p.locator(".gnode[data-node='write_tests']")).toContainText("stopped");
  await now.getByRole("button", { name: "Resume" }).click();
  expect(await p.evaluate(() => (window as unknown as { __messages: string[] }).__messages)).toContain("resume");
});

test("finished run with fix loops: fix node done, progress at 100 %", async ({ page: p }) => {
  await open(p, "screen=session&run=run_fd_0002&runs=run_fd_0007,run_fd_0005,run_fd_0002");
  await expect(p.locator(".big")).toHaveText("100 %");
  await expect(p.locator(".gnode[data-node='fix']")).toContainText("3 loops");
  await p.getByRole("button", { name: "Activity" }).click();
  await expect(p.locator(".log")).toContainText("requested changes");
  await p.screenshot({ path: path.join(shots, "vscode-fix-loops-activity-1440.png") });
});

test("hub status in the sidebar: connect when not set up, a clear error when the sync fails", async ({ page: p }) => {
  await open(p, "screen=new&hub=none");
  await expect(p.locator(".hub-line")).toContainText("Not connected to a hub.");
  await p.locator(".hub-line").getByRole("button", { name: "Connect" }).click();
  expect(await p.evaluate(() => (window as unknown as { __messages: string[] }).__messages)).toContain("hubSettings");
  await p.screenshot({ path: path.join(shots, "vscode-hub-not-connected-1440.png") });

  await open(p, "screen=new&hub=error");
  await expect(p.locator(".hub-line.error")).toContainText("sync failed");
  await expect(p.locator(".hub-line.error")).toContainText("Deployment Protection");
  await p.screenshot({ path: path.join(shots, "vscode-hub-error-1440.png") });

  await open(p, "screen=new");
  await expect(p.locator(".hub-line")).toContainText("Hub jigworks.vercel.app · connected");
  await p.screenshot({ path: path.join(shots, "vscode-hub-connected-1440.png") });
});

test("a workspace workflow that differs from the hub's release is tagged local (changed)", async ({ page: p }) => {
  await open(p, "screen=new&local=changed");
  await expect(p.locator(".wf")).toHaveCount(3);
  await expect(p.locator(".wf").nth(2)).toContainText("1.3.0 · local (changed)");
  await p.screenshot({ path: path.join(shots, "vscode-local-changed-1440.png") });
});
