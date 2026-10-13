import { defineConfig } from "@playwright/test";

// Executed from T6 onward (browsers are not installed at T2). The webServer
// runs the same scripts/dev.py stub entry the UI checkpoint uses.
export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  use: {
    baseURL: "http://127.0.0.1:8010",
    trace: "retain-on-failure",
  },
  webServer: {
    cwd: "..",
    command: "uv run python scripts/dev.py --mode stub --port 8010",
    url: "http://127.0.0.1:8010/api/demo/session",
    reuseExistingServer: true,
    timeout: 60_000,
  },
});
