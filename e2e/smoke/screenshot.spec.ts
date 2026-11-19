import { test, expect } from "@playwright/test";

// Toolchain smoke test (T01): headless Chromium renders a page and saves a screenshot.
for (const width of [390, 1440]) {
  test(`headless screenshot at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 800 });
    await page.setContent("<h1 style='font-family:sans-serif'>Jigworks smoke test</h1>");
    await expect(page.locator("h1")).toHaveText("Jigworks smoke test");
    await page.screenshot({ path: `e2e/screenshots/smoke-${width}.png` });
  });
}
