import { expect, test, type Page } from "@playwright/test";

// T13: the three tabs at 1440 px, against localhost or the preview (HUB_URL).
const password = process.env.HUB_PASSWORD ?? "";
const target = process.env.HUB_TARGET ?? "local";
const shot = (page: Page, name: string, fullPage = true) =>
  page.screenshot({ path: `e2e/hub/screenshots/${target}-${name}-1440.png`, fullPage });

test.describe.configure({ mode: "serial" });

test.beforeAll(() => {
  if (!password) throw new Error("HUB_PASSWORD is not set");
});

async function login(page: Page) {
  await page.goto("/");
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Open the hub" }).click();
  await expect(page.getByRole("heading", { name: "Workflows", level: 1 })).toBeVisible();
}

test("password screen guards the hub and sets an HTTP-only cookie", async ({ page, context }) => {
  await page.goto("/runs");
  await expect(page.getByRole("heading", { name: "Hub password" })).toBeVisible();
  await shot(page, "login", false);
  await page.getByLabel("Password").fill("definitely-wrong");
  await page.getByRole("button", { name: "Open the hub" }).click();
  await expect(page.getByRole("alert")).toHaveText("Wrong password.");
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Open the hub" }).click();
  await expect(page.getByRole("heading", { name: "Runs & analytics" })).toBeVisible();
  const cookie = (await context.cookies()).find((c) => c.name === "jigworks_session");
  expect(cookie?.httpOnly).toBe(true);
  expect(cookie?.value).not.toContain(password);
  expect(await page.evaluate(() => document.cookie)).not.toContain("jigworks_session");
});

test("Workflows: weekly numbers, workflow table with step shape, live sessions, releases", async ({ page }) => {
  await login(page);
  const table = page.locator("table").first();
  await expect(table.getByRole("link", { name: "feature-development", exact: true })).toBeVisible();
  await expect(table.getByText("stable 1.3.0")).toBeVisible();
  await expect(table.getByRole("img", { name: /Agent steps, 2 human reviews, 1 gate/ })).toBeVisible();
  await expect(page.getByRole("region", { name: "Live now" }).getByText("Review required")).toBeVisible();
  const releases = page.getByRole("region", { name: "Recent releases" });
  if (target === "local") {
    await expect(releases.getByText("feature-development 1.3.0")).toBeVisible();
  } else {
    // The shared Preview database also holds the transcript's smoke-check releases
    // (preview-api.sh publishes one per run), which push older releases out of this list.
    await expect(releases.getByText(/\d+\.\d+\.\d+/).first()).toBeVisible();
  }
  await expect(page.getByRole("region", { name: "This week" }).getByText("PLANNED", { exact: true })).toBeVisible();
  await shot(page, "workflows");
});

test("Editor: Python code, files from templates, GitHub source planned, models in workflow.toml", async ({ page }) => {
  await login(page);
  await page.getByRole("link", { name: "feature-development", exact: true }).click();
  await expect(page.getByRole("heading", { name: /Draft 1\.3\.0/ })).toBeVisible();
  await expect(page.getByLabel("Editor: graph.py")).toContainText("StateGraph");
  await expect(page.getByText("Connect GitHub repo")).toBeDisabled();
  await expect(page.locator(".source-bar").getByText("PLANNED", { exact: true })).toBeVisible();
  await expect(page.locator(".toml-pre")).toContainText('default = "claude-sonnet-5"');
  // New file from the node-function template, inside steps/.
  await page.getByText("nodes.py").click();
  await page.getByRole("button", { name: "New file" }).click();
  await expect(page.getByLabel("Template")).toHaveValue("node");
  await page.locator("#tree-name").fill("security_scan");
  await shot(page, "editor-new-file", false);
  await page.getByRole("button", { name: "Create" }).click();
  await expect(page.getByLabel("Editor: steps/security_scan.py")).toContainText("def security_scan(state):");
  await expect(page.locator(".save-state")).toHaveText("Saved", { timeout: 10_000 });
  // Validate reports the checks; no AI edit box anywhere.
  await page.getByRole("button", { name: "Validate" }).click();
  await expect(page.getByRole("region", { name: "Validation" })).toContainText("10 nodes", { timeout: 90_000 });
  await expect(page.getByRole("textbox", { name: /ai|prompt/i })).toHaveCount(0);
  await page.getByText("graph.py").first().click();
  await shot(page, "editor");
  // Clean up: delete the new file again.
  page.on("dialog", (d) => d.accept());
  await page.getByText("security_scan.py").click();
  await page.getByRole("button", { name: "Delete steps/security_scan.py" }).click();
  await expect(page.getByRole("navigation", { name: "Files" }).getByText("security_scan.py")).toHaveCount(0);
  await expect(page.locator(".save-state")).toHaveText("Saved", { timeout: 10_000 });
});

test("Graph: the Code/Graph toggle renders get_graph() from Sandbox with a live overlay", async ({ page }) => {
  await login(page);
  await page.goto("/workflows/feature-development");
  await page.getByRole("tab", { name: "Graph" }).click();
  await expect(page).toHaveURL(/\/workflows\/feature-development\/graph/);
  const graph = page.locator(".graph-canvas");
  await expect(graph.locator(".react-flow__node")).toHaveCount(12, { timeout: 90_000 });
  for (const node of ["plan", "approve_plan", "write_tests", "implement", "review", "fix", "gate", "approve_pr", "open_pr", "summary"]) {
    await expect(graph.locator(`.react-flow__node[data-id="${node}"]`)).toBeVisible();
  }
  await expect(page.getByText("Read-only. Rendered from")).toBeVisible();
  const overlay = page.getByLabel("Overlay");
  const live = await overlay.locator("option", { hasText: "live" }).first().getAttribute("value");
  if (live) {
    await overlay.selectOption(live);
    await expect(graph.locator(".g-running")).toHaveCount(1);
  }
  await page.locator('.react-flow__node[data-id="review"]').click();
  await expect(page.getByRole("complementary", { name: "Selected node" })).toContainText("review");
  await shot(page, "graph");
});

test("Runs & analytics: key numbers, cost per day, planned outcomes, versions, runs, audit trail", async ({ page }) => {
  await login(page);
  await page.getByRole("link", { name: "Runs & analytics" }).first().click();
  await page.getByLabel("Period").selectOption("all");
  const keys = page.getByRole("region", { name: "Key numbers" });
  await expect(keys.getByText("Gate pass, first try")).toBeVisible();
  await expect(keys.getByText("API equivalent", { exact: false })).toBeVisible();
  // Any day with cost: the last bar is today, which has $0 (zero height) once the seed is a day old.
  await expect(page.getByRole("region", { name: "Cost per day" }).locator(".bar:visible").first()).toBeVisible();
  const outcomes = page.getByRole("region", { name: "Outcomes" });
  await expect(outcomes.getByText("PLANNED", { exact: true })).toBeVisible();
  await expect(outcomes).toContainText("Sample data");
  await expect(page.getByRole("region", { name: "Compare versions" })).toContainText("1.2.0");
  await page.getByRole("cell", { name: "run_fd_0002" }).click();
  await expect(page).toHaveURL(/\/runs\/run_fd_0002/);
  const detail = page.getByRole("complementary", { name: "Run detail" });
  await expect(detail).toContainText("run_fd_0002 · audit trail");
  await expect(detail).toContainText("requested changes");
  await expect(detail.locator(".delta-box")).toContainText("PLANNED");
  await shot(page, "runs");
});

test("Non-coding teams: text tab", async ({ page }) => {
  await login(page);
  await page.getByRole("link", { name: "Non-coding teams" }).click();
  await expect(page.getByRole("heading", { name: "Non-coding teams", level: 1 })).toBeVisible();
  await expect(page.getByText("CV screening")).toBeVisible();
  await shot(page, "non-coding");
});
