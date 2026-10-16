// Flow A: digital self-expense WITH a recorded advance -> advance:type_conflict.
import { chromium } from "playwright";
import { join } from "node:path";
import { flowDir, newSummary, step, saveSummary, openIssuesTab, openLatestCase, fillDigitalLines } from "./s6-helpers.mjs";

const BASE = process.env.BROWSER_BASE_URL || "http://127.0.0.1:65133";
const DIR = flowDir("flow-a-self-conflict");
const summary = newSummary();

const browser = await chromium.launch();
const page = await browser.newPage();
try {
  await step(summary, "goto", () => page.goto(BASE, { waitUntil: "networkidle" }));
  await step(summary, "new-intake", async () => {
    await page.getByRole("button", { name: "+ Tạo hồ sơ mới" }).click({ timeout: 15000 });
  });
  await step(summary, "choose-self-digital", async () => {
    await page.getByText("Nhân viên tự chi").click({ timeout: 10000 });
    await page.getByText("Lập trên web").click({ timeout: 10000 });
  });
  await step(summary, "fill-form", () => fillDigitalLines(page, true));
  await step(summary, "read", async () => {
    await page.getByRole("button", { name: "Đọc & lập bản nháp" }).click();
    await page.getByRole("button", { name: "Xác nhận và nộp hồ sơ" }).waitFor({ timeout: 120000 });
  });
  await step(summary, "draft-alternative-visible", async () => {
    const body = await page.locator("body").innerText();
    if (!body.includes("Bằng chứng thay thế")) throw new Error("missing ALTERNATIVE block");
  });
  await page.screenshot({ path: join(DIR, "draft.png"), fullPage: true });
  await step(summary, "submit", async () => {
    await page.getByRole("button", { name: "Xác nhận và nộp hồ sơ" }).click();
    await page.getByRole("tab", { name: /Vấn đề cần xử lý/ }).waitFor({ timeout: 120000 });
  });
  await step(summary, "issues-tab", () => openIssuesTab(page));
  await step(summary, "type-conflict-visible", async () => {
    const tabs = page.locator('section[aria-labelledby="questions-title"] [role="tab"]');
    const count = await tabs.count();
    const scopes = count > 0 ? tabs : page.getByRole("tab", { name: /Vấn đề cần xử lý/ });
    const n = await scopes.count();
    for (let i = 0; i < Math.max(n, 1); i++) {
      if (n > 0) await scopes.nth(i).click().catch(() => {});
      const body = await page.locator("main").innerText();
      if (body.includes("tạm ứng") && (body.includes("5.000.000") || body.includes("5000000"))) {
        const conflict = body.includes("tự chi") || body.includes("không nhận tạm ứng");
        if (conflict) return;
      }
    }
    throw new Error("advance:type_conflict not visible");
  });
  await page.screenshot({ path: join(DIR, "issues.png"), fullPage: true });
  // Reload persistence: the conflict survives a refresh.
  await step(summary, "reload-keeps-conflict", async () => {
    await page.reload({ waitUntil: "networkidle" });
    await openLatestCase(page, BASE);
    await openIssuesTab(page);
    const tabs = page.locator('section[aria-labelledby="questions-title"] [role="tab"]');
    const count = await tabs.count();
    for (let i = 0; i < Math.max(count, 1); i++) {
      if (count > 0) await tabs.nth(i).click().catch(() => {});
      const body = await page.locator("main").innerText();
      if (body.includes("không nhận tạm ứng") || body.includes("tự chi")) return;
    }
    throw new Error("conflict lost after reload");
  });
} catch (error) {
  summary.fatal = String(error).slice(0, 500);
  await page.screenshot({ path: join(DIR, "failure.png"), fullPage: true }).catch(() => {});
} finally {
  await browser.close();
}
process.exit(saveSummary(DIR, summary) ? 0 : 1);
