import { defineConfig } from "@playwright/test";

const livePort = process.env.LIVE_PORT || "8012";

export default defineConfig({
  testDir: "./e2e",
  testMatch: "live-tc01-reference.spec.ts",
  outputDir: process.env.PLAYWRIGHT_OUTPUT_DIR || "./test-results-tc01-live",
  timeout: 420_000,
  expect: { timeout: 35_000 },
  retries: 0,
  workers: 1,
  use: {
    baseURL: `http://127.0.0.1:${livePort}`,
    headless: true,
    trace: "on",
    screenshot: "on",
    video: "on",
  },
});
