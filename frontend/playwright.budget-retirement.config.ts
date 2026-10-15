import { defineConfig } from "@playwright/test";

const port = process.env.BUDGET_UI_PORT || "8013";

export default defineConfig({
  testDir: "./e2e",
  testMatch: "budget-retirement.spec.ts",
  outputDir: process.env.PLAYWRIGHT_OUTPUT_DIR || "../.runtime/budget-retirement-ui/playwright",
  timeout: 30_000,
  expect: { timeout: 10_000 },
  retries: 0,
  workers: 1,
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    headless: true,
    trace: "on",
    screenshot: "on",
    video: "on",
  },
});
