import { defineConfig } from "@playwright/test";

const port = process.env.ACCOUNTANT_FLOW_PORT || "8014";

export default defineConfig({
  testDir: "./e2e",
  testMatch: "accountant-advance-coverage.spec.ts",
  outputDir: process.env.PLAYWRIGHT_OUTPUT_DIR || "./test-results-accountant-flow",
  timeout: 420_000,
  expect: { timeout: 60_000 },
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
