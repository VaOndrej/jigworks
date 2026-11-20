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
