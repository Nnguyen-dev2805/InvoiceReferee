// Flow B: paper advance dossier (mismatch) — read -> draft -> submit -> FACTs + OCR region.
import { chromium } from "playwright";
import { join } from "node:path";
import { flowDir, newSummary, step, saveSummary, openIssuesTab, PDFS } from "./s6-helpers.mjs";

const BASE = process.env.BROWSER_BASE_URL || "http://127.0.0.1:65132";
const DIR = flowDir("flow-b-paper");
const summary = newSummary();

const browser = await chromium.launch();
const page = await browser.newPage();
try {
  await step(summary, "goto", () => page.goto(BASE, { waitUntil: "networkidle" }));
  await step(summary, "new-intake", async () => {
    await page.getByRole("button", { name: "+ Tạo hồ sơ mới" }).click({ timeout: 15000 });
  });
  await step(summary, "choose-paper-advance", async () => {
    await page.getByText("Quyết toán tạm ứng").click({ timeout: 10000 });
    await page.getByText("Tải đơn giấy").click({ timeout: 10000 });
  });
  await step(summary, "upload", async () => {
    await page.locator("#paper-file").setInputFiles(join(PDFS, "paper-mismatch.pdf"));
    await page.locator("#evidence-files").setInputFiles([
      join(PDFS, "invoice-mismatch.pdf"),
      join(PDFS, "acceptance-mismatch.pdf"),
      join(PDFS, "transfer-mismatch.pdf"),
    ]);
  });
  await step(summary, "read", async () => {
    await page.getByRole("button", { name: "Đọc chứng từ" }).click();
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
  await step(summary, "party-mismatch-visible", async () => {
    const body = await page.locator("main").innerText();
    for (const token of ["An Thịnh", "Phúc An"]) {
      if (!body.includes(token)) throw new Error(`issues view missing ${token}`);
    }
  });
  await step(summary, "ocr-region-visible", async () => {
    const tabs = page.getByRole("tab");
    const count = await tabs.count();
    for (let i = 0; i < count; i++) {
      const tab = tabs.nth(i);
      const name = (await tab.innerText().catch(() => "")) || "";
      if (!/Vấn đề|Khoản|chi|mismatch|thanh toán|chứng từ/i.test(name) && i > 0) continue;
      await tab.click().catch(() => {});
      const img = page.getByAltText(/Vùng OCR cần kiểm tra/).first();
      try {
        await img.waitFor({ state: "visible", timeout: 3000 });
        const src = await img.getAttribute("src");
        if (!src || !src.includes("ocr-preview")) throw new Error("ocr preview src missing");
        // The image must actually load (not a broken icon).
        const loaded = await img.evaluate((el) => el.naturalWidth > 0);
        if (!loaded) throw new Error("ocr preview image did not load");
        return;
      } catch {
        continue;
      }
    }
    throw new Error("no visible OCR region image on any issue tab");
  });
  await page.screenshot({ path: join(DIR, "issues.png"), fullPage: true });
} catch (error) {
  summary.fatal = String(error).slice(0, 500);
  await page.screenshot({ path: join(DIR, "failure.png"), fullPage: true }).catch(() => {});
} finally {
  await browser.close();
}
process.exit(saveSummary(DIR, summary) ? 0 : 1);
