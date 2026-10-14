import { defineConfig } from "@playwright/test";

const LIVE_PORT = process.env.LINK_LIVE_PORT || "8096";

export default defineConfig({
  testDir: "./e2e",
  testMatch: "live-link.spec.ts",
  timeout: 420_000,
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
