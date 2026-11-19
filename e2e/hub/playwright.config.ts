import { defineConfig } from "@playwright/test";

// HUB_URL: http://localhost:5173 (vite + uvicorn) or a preview URL. HUB_PASSWORD from the environment.
const bypass = process.env.VERCEL_AUTOMATION_BYPASS_SECRET;

export default defineConfig({
  testDir: ".",
  testMatch: "*.spec.ts",
  reporter: "list",
  timeout: 120_000,
  workers: 1,
  use: {
    baseURL: process.env.HUB_URL ?? "http://localhost:5173",
    headless: true,
    viewport: { width: 1440, height: 900 },
    extraHTTPHeaders: bypass ? { "x-vercel-protection-bypass": bypass, "x-vercel-set-bypass-cookie": "true" } : {},
  },
});
