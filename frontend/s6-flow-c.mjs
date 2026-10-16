// Flow C: digital advance dossier, consistent facts, LOW simulated grant.
// POLICY arises; preview shows uncovered; accept is disabled; the decide API
// stays blocked (over ceiling).
import { chromium } from "playwright";
import { join } from "node:path";
import {
  flowDir, newSummary, step, saveSummary, openIssuesTab, openLatestCase, switchPersona, fillDigitalLines,
} from "./s6-helpers.mjs";

const BASE = process.env.BROWSER_BASE_URL || "http://127.0.0.1:65135";
const DIR = flowDir("flow-c-low-grant");
const summary = newSummary();

const browser = await chromium.launch();
const page = await browser.newPage();
try {
  await step(summary, "goto", () => page.goto(BASE, { waitUntil: "networkidle" }));
  await step(summary, "new-intake", async () => {
    await page.getByRole("button", { name: "+ Tạo hồ sơ mới" }).click({ timeout: 15000 });
  });
  await step(summary, "choose-advance-digital", async () => {
    await page.getByText("Quyết toán tạm ứng").click({ timeout: 10000 });
    await page.getByText("Lập trên web").click({ timeout: 10000 });
  });
  await step(summary, "fill-form", () => fillDigitalLines(page, true, false));
  await step(summary, "read", async () => {
    await page.getByRole("button", { name: "Đọc & lập bản nháp" }).click();
    await page.getByRole("button", { name: "Xác nhận và nộp hồ sơ" }).waitFor({ timeout: 120000 });
  });
  await step(summary, "submit", async () => {
    await page.getByRole("button", { name: "Xác nhận và nộp hồ sơ" }).click();
    await page.getByRole("tab", { name: /Vấn đề cần xử lý/ }).waitFor({ timeout: 120000 });
  });
  await step(summary, "switch-accountant", () => switchPersona(page, "accountant"));
  await step(summary, "reopen-case", () => openLatestCase(page, BASE));
  await step(summary, "issues-tab", () => openIssuesTab(page));
  await step(summary, "accept-disabled", async () => {
    const tabs = page.locator('section[aria-labelledby="questions-title"] [role="tab"]');
    const count = await tabs.count();
    for (let i = 0; i < count; i++) {
      await tabs.nth(i).click().catch(() => {});
      if (await page.locator('[data-testid="exception-review"]').isVisible()) break;
    }
    await page.getByText(/chưa có grant EXCEPT_POLICY/).waitFor({ timeout: 15000 });
    const accept = page.getByRole("button", { name: "Chấp nhận ngoại lệ" });
    if (await accept.isEnabled()) throw new Error("accept should be disabled without grant");
  });
  await step(summary, "api-still-blocked", async () => {
    // The no-advance box is absent on advance dossiers; fill only the reason.
    const blocked = await page.evaluate(async () => {
      const issueTab = document.querySelector('[data-testid="exception-review"]');
      void issueTab;
      const cases = await (await fetch("/api/cases")).json();
      const rootId = cases.cases[0].id;
      const detail = await (await fetch(`/api/cases/${rootId}`)).json();
      const issue = detail.issues.find((i) => (i.field_or_rule || "").endsWith(":missing_evidence"));
      const decide = await fetch(`/api/cases/${rootId}/decisions`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Command-Id": `cmd:${Date.now()}` },
        body: JSON.stringify({
          issue_ids: [issue.id], basis_id: "basis:x", actions: ["EXCEPT_POLICY"],
          effect_scope: detail.activity, amount: 1500000, reason: "Cố tình vượt hạn mức",
        }),
      });
      return { status: decide.status, body: (await decide.text()).slice(0, 200) };
    });
    if (blocked.status < 400) throw new Error(`decide unexpectedly allowed: ${blocked.status}`);
  });
  await page.screenshot({ path: join(DIR, "blocked.png"), fullPage: true });
} catch (error) {
  summary.fatal = String(error).slice(0, 500);
  await page.screenshot({ path: join(DIR, "failure.png"), fullPage: true }).catch(() => {});
} finally {
  await browser.close();
}
process.exit(saveSummary(DIR, summary) ? 0 : 1);
