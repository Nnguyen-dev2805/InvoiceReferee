// Flow B: paper advance dossier (mismatch) — read -> draft -> submit -> FACTs + OCR region.
import { chromium } from "playwright";
import { join } from "node:path";
import { flowDir, newSummary, step, saveSummary, openIssuesTab, PDFS } from "./s6-helpers.mjs";

const BASE = process.env.BROWSER_BASE_URL || "http://127.0.0.1:65136";
const DIR = flowDir("flow-d-self-paper");
const summary = newSummary();

const browser = await chromium.launch();
const page = await browser.newPage();
try {
  await step(summary, "goto", () => page.goto(BASE, { waitUntil: "networkidle" }));
  await step(summary, "new-intake", async () => {
    await page.getByRole("button", { name: "+ Tạo hồ sơ mới" }).click({ timeout: 15000 });
  });
  await step(summary, "choose-paper-advance", async () => {
    await page.getByText("Nhân viên tự chi").click({ timeout: 10000 });
    await page.getByText("Tải đơn giấy").click({ timeout: 10000 });
  });
  await step(summary, "upload", async () => {
    await page.getByLabel("Lý do không nhận tạm ứng").fill("Tự chi, chưa nhận khoản tạm ứng nào");
    await page.locator("#paper-file").setInputFiles(join(PDFS, "paper-self.pdf"));
    await page.locator("#evidence-files").setInputFiles([
      join(PDFS, "invoice-self.pdf"),
      join(PDFS, "acceptance-self.pdf"),
      join(PDFS, "transfer-self.pdf"),
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
  await step(summary, "paper-self-persisted-reload", async () => {
    const detail = await page.evaluate(async()=>{const {cases}=await(await fetch("/api/cases")).json();return await(await fetch(`/api/cases/${cases[0].id}`)).json();});
    if(detail.issues.some(i=>i.field_or_rule==="advance:type_conflict"))throw new Error("unexpected advance conflict");
    if(!detail.issues.some(i=>(i.field_or_rule||"").endsWith(":exception_reason")))throw new Error("paper has no exception reason: expected FACT before POLICY");
    if(detail.instructions.length)throw new Error("money issued with missing facts");
    if(detail.actual_money.A.value!==0)throw new Error("self-expense A not proven zero from seeded context");
    await page.reload({waitUntil:"networkidle"});
    return {id:detail.id,A:detail.actual_money.A,issues:detail.issues.map(i=>i.field_or_rule)};
  });
  await page.screenshot({ path: join(DIR, "issues.png"), fullPage: true });
} catch (error) {
  summary.fatal = String(error).slice(0, 500);
  await page.screenshot({ path: join(DIR, "failure.png"), fullPage: true }).catch(() => {});
} finally {
  await browser.close();
}
process.exit(saveSummary(DIR, summary) ? 0 : 1);
