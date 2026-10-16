// Flow A2: digital self-expense, NO recorded advance -> POLICY -> accountant
// accept (simulated grant) -> PAY -> partial + full recordActual -> SETTLED.
import { chromium } from "playwright";
import { writeFileSync } from "node:fs";
import { join } from "node:path";
import {
  PDFS, flowDir, newSummary, step, saveSummary, openIssuesTab, openLatestCase, switchPersona, fillDigitalLines,
} from "./s6-helpers.mjs";

const BASE = process.env.BROWSER_BASE_URL || "http://127.0.0.1:65134";
const DIR = flowDir("flow-a2-self-clean");
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
  await step(summary, "fill-form", () => fillDigitalLines(page, true, true, [2700000, 1000000]));
  await step(summary, "read", async () => {
    await page.getByRole("button", { name: "Đọc & lập bản nháp" }).click();
    await page.getByRole("button", { name: "Xác nhận và nộp hồ sơ" }).waitFor({ timeout: 120000 });
  });
  await step(summary, "submit", async () => {
    await page.getByRole("button", { name: "Xác nhận và nộp hồ sơ" }).click();
    await page.getByRole("tab", { name: /Vấn đề cần xử lý/ }).waitFor({ timeout: 120000 });
  });
  await step(summary, "issues-tab", () => openIssuesTab(page));
  await step(summary, "policy-visible", async () => {
    const body = await page.locator("main").innerText();
    if (!body.includes("ngoại lệ")) throw new Error("POLICY missing_evidence not visible");
  });
  await page.screenshot({ path: join(DIR, "policy.png"), fullPage: true });

  // Accountant accepts the exception (simulated grant covers 1.5m).
  await step(summary, "switch-accountant", () => switchPersona(page, "accountant"));
  await step(summary, "reopen-case", () => openLatestCase(page, BASE));
  await step(summary, "issues-tab-accountant", () => openIssuesTab(page));
  await step(summary, "accept-exception", async () => {
    const tabs = page.locator('section[aria-labelledby="questions-title"] [role="tab"]');
    const count = await tabs.count();
    for (let i = 0; i < count; i++) {
      await tabs.nth(i).click().catch(() => {});
      if ((await page.locator('[data-testid="exception-review"]').count()) > 0) break;
    }
    await page.getByLabel(/Lý do quyết định/).fill("Nghiệm thu + chuyển khoản đủ căn cứ thay hóa đơn");
    await page.getByRole("button", { name: "Chấp nhận ngoại lệ" }).click();
    await page.waitForFunction(
      () => !document.querySelector('[data-testid="exception-review"]'),
      { timeout: 30000 },
    );
  });
  await page.screenshot({ path: join(DIR, "accepted.png"), fullPage: true });

  // PAY instruction -> partial then full actuals -> SETTLED.
  await step(summary, "pay-instruction", async () => {
    await page.getByRole("tab", { name: /Đối soát chi phí/ }).click({ timeout: 10000 });
    const body = await page.locator("main").innerText();
    if (!body.includes("3.700.000")) throw new Error("expected PAY 3.700.000 nowhere visible");
  });
  async function recordActual(amount, reference, filename) {
    await page.getByRole("tab", { name: /Sổ cái|Dòng tiền/ }).click({ timeout: 10000 });
    await page.getByLabel("Tải chứng từ chi bổ sung").setInputFiles(join(PDFS, filename));
    const attached=page.waitForResponse(r=>r.url().endsWith("/sources") && r.request().method()==="POST");
    await page.getByRole("button",{name:"Lưu chứng từ chi bổ sung"}).click();
    const upload=await attached;if(!upload.ok())throw new Error(`proof upload ${upload.status()}: ${await upload.text()}`);
    await page.getByLabel("Lệnh chi",{exact:true}).selectOption({ index: 1 });
    await page.getByLabel("Chứng từ chi bổ sung",{exact:true}).selectOption({ label: filename });
    await page.getByLabel("Số tiền thực chi").fill(String(amount));
    await page.getByLabel("Mã giao dịch chi").fill(reference);
    await page.getByLabel("Ngày giao dịch chi").fill("2026-10-12");
    await page.getByLabel("Trang chứng từ chi").fill("1");
    await page.getByLabel("Căn cứ chứng từ chi").fill(`Số tiền: ${amount}`);
    const posted=page.waitForResponse(r=>r.url().endsWith("/actuals") && r.request().method()==="POST",{timeout:10000});
    await page.getByRole("button", { name: "Xác nhận khoản chi đã nhận" }).click();
    const response=await posted;
    if(!response.ok())throw new Error(`actual ${response.status()}: ${await response.text()}`);
    const result=await response.json();
    writeFileSync(join(DIR,`${reference}.json`),JSON.stringify(result,null,2));
    const instruction=result.case_view.instructions.find(i=>i.direction==="PAY");
    const expected=amount===1000000?{fulfilled:1000000,remaining:2700000,status:"PARTIAL"}:{fulfilled:3700000,remaining:0,status:"FULFILLED"};
    if(instruction.fulfilled_amount!==expected.fulfilled || instruction.remaining!==expected.remaining || instruction.status!==expected.status)throw new Error(JSON.stringify(instruction));
    return {status:response.status(),instruction};
  }
  await step(summary, "record-partial", () => recordActual(1000000, "FT-PAY-PARTIAL-01", "payout-partial.pdf"));
  await step(summary, "record-full", () => recordActual(2700000, "FT-PAY-FINAL-02", "payout-final.pdf"));
  await step(summary, "coverage-recheck-if-stale", async()=>{
    const checkbox=page.getByLabel(/Tôi đã kiểm tra các giao dịch/);
    if(await checkbox.count()){
      await checkbox.check();
      const response=page.waitForResponse(r=>r.url().endsWith("/money-history/recheck") && r.request().method()==="POST");
      await page.getByRole("button",{name:"Xác nhận đã đối chiếu lại"}).click();
      const r=await response;if(!r.ok())throw new Error(await r.text());
      return {status:r.status()};
    }
    return "not stale";
  });
  await step(summary,"close-execution",async()=>{
    await page.getByLabel("Lệnh xác nhận thực hiện").selectOption({index:1});
    await page.getByLabel("Chứng từ xác nhận thực hiện").selectOption({label:"payout-final.pdf"});
    await page.getByLabel("Căn cứ xác nhận thực hiện").fill("Mã giao dịch: FT-PAY-FINAL-02");
    await page.getByLabel("Lý do xác nhận thực hiện").fill("Đã đối chiếu hai lần chi 1 triệu và 2,7 triệu; đợt thực hiện kết thúc, không còn giao dịch đang chuyển.");
    const response=page.waitForResponse(r=>r.url().endsWith("/mark-execution") && r.request().method()==="POST");
    await page.getByRole("button",{name:"Xác nhận đã hoàn tất thực hiện"}).click();
    const r=await response;if(!r.ok())throw new Error(await r.text());
    return {status:r.status()};
  });
  await step(summary, "settled-reload-api", async () => {
    await page.reload({waitUntil:"networkidle"});
    const detail=await page.evaluate(async()=>{const {cases}=await(await fetch("/api/cases")).json();return await(await fetch(`/api/cases/${cases[0].id}`)).json();});
    writeFileSync(join(DIR,"final-case.json"),JSON.stringify(detail,null,2));
    const i=detail.instructions.find(i=>i.direction==="PAY");
    if(detail.state!=="SETTLED" || detail.actual_money.P.value!==3700000 || detail.actual_money.S.value!==0 || i.remaining!==0 || i.execution_state!=="CLOSED_CONFIRMED" || detail.issues.some(i=>i.status==="OPEN")) throw new Error(JSON.stringify({state:detail.state,money:detail.actual_money,instruction:i,issues:detail.issues}));
    return {state:detail.state,P:detail.actual_money.P.value,S:detail.actual_money.S.value,instruction:i};
  });
  await page.screenshot({ path: join(DIR, "settled.png"), fullPage: true });
} catch (error) {
  summary.fatal = String(error).slice(0, 500);
  writeFileSync(join(DIR,"failure-body.txt"),await page.locator("body").innerText());
  await page.screenshot({ path: join(DIR, "failure.png"), fullPage: true }).catch(() => {});
} finally {
  await browser.close();
}
process.exit(saveSummary(DIR, summary) ? 0 : 1);
