import { defineConfig } from "@playwright/test";

const LIVE_PORT = process.env.LIVE_PORT || "8095";

export default defineConfig({
  testDir: "./e2e",
  testMatch: "live-tc02-tc03.spec.ts",
  timeout: 300_000,
  expect: {
    timeout: 30_000,
  },
  workers: 1,
  use: {
    baseURL: `http://127.0.0.1:${LIVE_PORT}`,
    headless: true,
    trace: "retain-on-failure",
    screenshot: "on",
    video: "on",
  },
});
