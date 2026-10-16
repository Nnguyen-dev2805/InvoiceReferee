import { defineConfig } from "@playwright/test";

// Executed from T6 onward. The webServer runs the same scripts/dev.py stub
// entry the UI checkpoint uses, but against an ISOLATED db/uploads dir so a
// run never inherits state from a previous run (the default .runtime DB is
// persistent and would otherwise leak versions/roots across specs). Specs run
// serially (workers: 1) so they share one deterministic DB.
const E2E_DIR = "../.runtime/e2e";

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  workers: 1,
  use: {
    baseURL: "http://127.0.0.1:8010",
    trace: "retain-on-failure",
  },
  webServer: {
    cwd: "..",
    command:
      `rm -rf ${E2E_DIR} && ` +
      `uv run python scripts/dev.py --mode stub --port 8010 ` +
      `--context tests/fixtures/legacy-company-context.json ` +
      `--db ${E2E_DIR}/app.sqlite --uploads ${E2E_DIR}/uploads`,
    url: "http://127.0.0.1:8010/api/demo/session",
    reuseExistingServer: false,
    timeout: 60_000,
  },
});
