import { explainAdvanceIfNeeded } from "./advance_helpers";
import { expect, test, type Page, type TestInfo } from "@playwright/test";
import { mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const PROJECT_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const SETTLEMENT_DIR = path.join(
  PROJECT_ROOT,
  "data/tham-khao/uc-03/tc01-hop-le-nhan-vien-hoan-tra-tien-thua",
);
const ADVANCE_DIR = path.join(PROJECT_ROOT, "data/demo/tc01-chung-tu-ung");
const SETTLEMENT_FILES = [
  path.join(SETTLEMENT_DIR, "report_hoan_ung.pdf"),
  path.join(SETTLEMENT_DIR, "hoa_don_dien_tu.pdf"),
];

type Captured = {
  consoleErrors: string[];
  requestFailures: Array<{ method: string; path: string; error: string | null }>;
  settlementDraft?: Record<string, unknown>;
  advanceDraft?: Record<string, unknown>;
  before?: Record<string, unknown>;
  after?: Record<string, unknown>;
  uiBefore?: Record<string, string>;
  expected?: Record<string, unknown>;
  health?: Record<string, unknown>;
};

let captured: Captured;

function scrub(value: string): string {
  return value
    .replace(/(api[_-]?key|authorization|bearer|token)\s*[:=]\s*[^\s,;]+/gi, "$1=[REDACTED]")
    .replace(/\b(?:sk|mrl|xk)_[A-Za-z0-9_-]{12,}\b/g, "[REDACTED]");
}

function routePath(url: string): string {
  try {
    return new URL(url).pathname;
  } catch {
    return "[invalid-url]";
  }
}

function viewSnapshot(view: any) {
  const money = view.actual_money ?? {};
  return {
    id: view.id,
    activity: view.activity,
    state: view.state,
    T: money.T?.value ?? null,
    E: money.E?.value ?? null,
    A: money.A?.value ?? null,
    P: money.P?.value ?? null,
    R: money.R?.value ?? null,
    S: money.S?.value ?? null,
    instructions: (view.instructions ?? []).map((instruction: any) => ({
      id: instruction.id,
      direction: instruction.direction,
      amount: instruction.amount,
      status: instruction.status,
    })),
    trace_refs: view.trace_refs ?? [],
    issues: (view.issues ?? []).map((issue: any) => ({
      kind: issue.kind,
      field_or_rule: issue.field_or_rule,
      owner: issue.owner,
      status: issue.status,
    })),
  };
}

async function recordBrowserEvidence(testInfo: TestInfo) {
  const dir = process.env.TC01_EVIDENCE_DIR;
  const body = JSON.stringify(captured, null, 2);
  await testInfo.attach("tc01-browser-evidence.json", {
    body,
    contentType: "application/json",
  });
  if (dir) {
    mkdirSync(dir, { recursive: true });
    writeFileSync(path.join(dir, "playwright-evidence.json"), body, "utf8");
    writeFileSync(path.join(dir, "live-api-summary.json"), body, "utf8");
  }
}

test.beforeEach(async ({ page }) => {
  captured = { consoleErrors: [], requestFailures: [] };
  page.on("console", (message) => {
    if (message.type() === "error") captured.consoleErrors.push(scrub(message.text()));
  });
  page.on("requestfailed", (request) => {
    captured.requestFailures.push({
      method: request.method(),
      path: routePath(request.url()),
      error: request.failure()?.errorText ? scrub(request.failure()!.errorText) : null,
    });
  });
});

test.afterEach(async ({}, testInfo) => {
  await recordBrowserEvidence(testInfo);
});

async function runTc01(page: Page, testInfo: TestInfo, method: "TRANSFER" | "CASH") {
  const receipt = path.join(
    ADVANCE_DIR,
    method === "TRANSFER" ? "03-bien-nhan-chuyen-khoan.pdf" : "04-phieu-chi-tien-mat.pdf",
  );

  await page.goto("/");
  await expect(page.getByText("InvoiceReferee")).toBeVisible();
  const health = await page.request.get("/api/health");
  expect(health.ok()).toBeTruthy();
  const healthBody = await health.json();
  captured.health = healthBody;
  expect(healthBody.mode).toBe("LIVE");

  await page.getByRole("button", { name: "+ Tạo hồ sơ mới" }).click();
  await page.getByLabel("Chứng từ (PDF/PNG/JPEG)").setInputFiles([
    ...SETTLEMENT_FILES,
    receipt,
  ]);
  await expect(page.getByText("Chứng từ đã chọn (3)")).toBeVisible();

  const settlementDraftResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      response.url().includes("/settlement/draft"),
    { timeout: 240_000 },
  );
  await page.getByRole("button", { name: "Đọc chứng từ" }).click();
  await expect(page.getByText("Kiểm tra bản nháp hồ sơ")).toBeVisible({ timeout: 240_000 });
  const settlementDraft = await (await settlementDraftResponse).json();
  captured.settlementDraft = {
    declared_advance: settlementDraft.declared_advance,
    incurred_total: settlementDraft.incurred_total,
    expense_count: settlementDraft.expenses?.length,
    warnings: settlementDraft.warnings,
    link: settlementDraft.link,
  };

  // This assertion proves the imported TU-TC01 reference itself was read and
  // selected as the link basis; the UI has not selected a standing activity.
  expect(settlementDraft.link).toMatchObject({
    status: "LINKED",
    activity_id: "activity:tc01",
    basis: "DOCUMENT_REFERENCE",
  });
  expect(settlementDraft.declared_advance).toBe(4_000_000);
  expect(settlementDraft.incurred_total).toBe(3_240_000);
  await expect(page.getByText(/Khoản ứng:/)).toBeVisible();

  const submitResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" && /\/submit(?:\?|$)/.test(response.url()),
    { timeout: 120_000 },
  );
  await page.getByRole("button", { name: "Xác nhận và nộp hồ sơ" }).click();
  const submitBody = await (await submitResponse).json();
  let caseId = submitBody.case_view?.id;
  expect(caseId).toBeTruthy();

  await expect(page.getByRole("heading", { name: "Hồ sơ đối soát" })).toBeVisible({ timeout: 90_000 });
  const initialResponse = await page.request.get(`/api/cases/${encodeURIComponent(caseId)}`);
  expect(initialResponse.ok()).toBeTruthy();
  const initialView = await initialResponse.json();
  captured.before = viewSnapshot(initialView);
  captured.expected = {
    T: 3_240_000,
    E: 3_240_000,
    A: 4_000_000,
    S: -760_000,
    instruction: { direction: "COLLECT", amount: 760_000 },
  };
  expect(captured.before).toMatchObject({ activity: "activity:tc01", A: 4_000_000 });
  captured.uiBefore = {
    T: await page.getByTestId("money-Tổng chi công việc").innerText().catch(() => "[not visible]"),
    E: await page.getByTestId("money-Chi phí đủ điều kiện").innerText().catch(() => "[not visible]"),
    A: await page.getByTestId("money-Ứng thực nhận").innerText().catch(() => "[not visible]"),
    S: await page.getByTestId("money-Chênh lệch (S)").innerText().catch(() => "[not visible]"),
  };
  await expect(page.getByTestId("money-Ứng thực nhận")).toContainText("4.000.000 ₫");

  // The accountant repeats the real UI read and confirmation for the same
  // source. The report is read-only; a repeated external key must not create a
  // second advance or change the pending collection instruction.
  await page.locator("#persona-select").selectOption("accountant");
  const row = page.getByRole("row").filter({
    hasText: "Chi phí tiếp khách phục vụ dự án Nâng cấp văn phòng 2026",
  });
  await expect(row).toBeVisible({ timeout: 30_000 });
  await row.click();
  await expect(page.getByRole("heading", { name: "Ghi nhận tạm ứng từ chứng từ" })).toBeVisible();
  await page.getByLabel("Phương thức ứng").selectOption(method);

  const advanceDraftResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      response.url().includes("/advance/draft"),
    { timeout: 240_000 },
  );
  await page.getByLabel("Chứng từ ứng").setInputFiles(receipt);
  await expect(page.getByTestId("advance-draft")).toBeVisible({ timeout: 240_000 });
  const advanceDraft = await (await advanceDraftResponse).json();
  const payerExtracted =
    advanceDraft.payer_name === "CÔNG TY TNHH GIẢI PHÁP CÔNG NGHỆ AN THỊNH";
  const payeeExtracted = advanceDraft.payee_name === "NGUYỄN MINH AN";
  captured.advanceDraft = {
    amount: advanceDraft.amount,
    payer_name: advanceDraft.payer_name,
    payee_name: advanceDraft.payee_name,
    transaction_reference: advanceDraft.transaction_reference,
    instrument_method: advanceDraft.instrument_method,
    instrument_status: advanceDraft.instrument_status,
    event_at: advanceDraft.event_at,
    already_recorded: advanceDraft.already_recorded,
    missing_fields: advanceDraft.missing_fields,
    payer_extraction_status: payerExtracted ? "PASS" : "FAIL",
    payee_extraction_status: payeeExtracted ? "PASS" : "FAIL",
  };
  expect(advanceDraft).toMatchObject({
    amount: 4_000_000,
    transaction_reference: method === "TRANSFER" ? "FT-TC01-0001" : "PC-TC01-0001",
    instrument_method: method,
    instrument_status: "COMPLETED",
    already_recorded: true,
  });
  expect(String(advanceDraft.event_at)).toMatch(/^(2026-10-05|05\/10\/2026)/);
  await expect(page.getByText(/đã có trong lịch sử công ty/)).toBeVisible();
  if (!payerExtracted || !payeeExtracted) {
    const corrections: Record<string, string> = {};
    if (!payerExtracted) {
      corrections.payer_name = "CÔNG TY TNHH GIẢI PHÁP CÔNG NGHỆ AN THỊNH";
      await page.getByLabel("Bên chi theo chứng từ").fill(corrections.payer_name);
    }
    if (!payeeExtracted) {
      corrections.payee_name = "NGUYỄN MINH AN";
      await page.getByLabel("Người nhận theo chứng từ").fill(corrections.payee_name);
    }
    captured.advanceDraft!.manual_corrections = {
      fields: corrections,
      basis: "Read from the source PDF; one or more model fields were null or incorrect.",
    };
  }

  const actualResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      /\/actuals(?:\?|$)/.test(response.url()),
    { timeout: 120_000 },
  );
  await explainAdvanceIfNeeded(page, "Đã đối chiếu chứng từ với khoản ứng mô phỏng đã có; không ghi nhận giao dịch mới.");
  await page.getByRole("button", { name: "Xác nhận ghi nhận" }).click();
  const actualBody = await (await actualResponse).json();
  caseId = actualBody.case_view?.id ?? caseId;
  await expect(page.getByText("Đã ghi nhận tiền ứng thực nhận.")).toBeVisible();

  const finalResponse = await page.request.get(`/api/cases/${encodeURIComponent(caseId)}`);
  expect(finalResponse.ok()).toBeTruthy();
  const finalView = await finalResponse.json();
  captured.after = viewSnapshot(finalView);
  expect(captured.after).toMatchObject({
    id: captured.before.id,
    activity: captured.before.activity,
    state: captured.before.state,
    T: captured.before.T,
    E: captured.before.E,
    A: captured.before.A,
    P: captured.before.P,
    R: captured.before.R,
    S: captured.before.S,
  });
  expect(captured.after).toMatchObject({ activity: "activity:tc01", A: 4_000_000 });
  expect(finalView.instructions).toEqual(initialView.instructions);
  expect(finalView.state).not.toBe("SETTLED");
  // Defer the expected settlement assertion until after the accountant's
  // idempotency check so a blocked cost basis does not skip branch B evidence.
  expect(captured.after).toMatchObject({ T: 3_240_000, E: 3_240_000, S: -760_000 });
  expect(finalView.instructions).toHaveLength(1);
  expect(finalView.instructions[0]).toMatchObject({ direction: "COLLECT", amount: 760_000 });
  expect(advanceDraft.payer_name).toBe("CÔNG TY TNHH GIẢI PHÁP CÔNG NGHỆ AN THỊNH");
  expect(advanceDraft.payee_name).toBe("NGUYỄN MINH AN");
  await page.screenshot({ path: testInfo.outputPath("final-dossier.png"), fullPage: true });
}

async function runExistingAdvanceReceipt(
  page: Page,
  testInfo: TestInfo,
  method: "TRANSFER" | "CASH",
) {
  const receipt = path.join(
    ADVANCE_DIR,
    method === "TRANSFER" ? "03-bien-nhan-chuyen-khoan.pdf" : "04-phieu-chi-tien-mat.pdf",
  );
  await page.goto("/");
  await expect(page.getByText("InvoiceReferee")).toBeVisible();
  const health = await page.request.get("/api/health");
  expect(health.ok()).toBeTruthy();
  captured.health = await health.json();
  expect(captured.health.mode).toBe("LIVE");

  await page.locator("#persona-select").selectOption("accountant");
  const listResponse = await page.request.get("/api/cases");
  expect(listResponse.ok()).toBeTruthy();
  const list = await listResponse.json();
  const matches = list.cases.filter((candidate: any) => candidate.activity === "activity:tc01");
  expect(matches).toHaveLength(1);
  const caseId = matches[0].id as string;
  const beforeResponse = await page.request.get(`/api/cases/${encodeURIComponent(caseId)}`);
  expect(beforeResponse.ok()).toBeTruthy();
  const beforeView = await beforeResponse.json();
  captured.before = viewSnapshot(beforeView);
  captured.expected = {
    A: 4_000_000,
    instruction_count_after: beforeView.instructions?.length ?? 0,
    instructions_unchanged: true,
  };

  const row = page.getByRole("row").filter({
    hasText: "Chi phí tiếp khách phục vụ dự án Nâng cấp văn phòng 2026",
  });
  await expect(row).toBeVisible({ timeout: 30_000 });
  await row.click();
  await expect(page.getByRole("heading", { name: "Ghi nhận tạm ứng từ chứng từ" })).toBeVisible();
  await expect(page.getByTestId("money-Ứng thực nhận")).toContainText("4.000.000 ₫");
  await page.getByLabel("Phương thức ứng").selectOption(method);

  const advanceDraftResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" && response.url().includes("/advance/draft"),
    { timeout: 240_000 },
  );
  await page.getByLabel("Chứng từ ứng").setInputFiles(receipt);
  await expect(page.getByTestId("advance-draft")).toBeVisible({ timeout: 240_000 });
  const advanceDraft = await (await advanceDraftResponse).json();
  const payerExtracted =
    advanceDraft.payer_name === "CÔNG TY TNHH GIẢI PHÁP CÔNG NGHỆ AN THỊNH";
  const payeeExtracted = advanceDraft.payee_name === "NGUYỄN MINH AN";
  captured.advanceDraft = {
    amount: advanceDraft.amount,
    payer_name: advanceDraft.payer_name,
    payee_name: advanceDraft.payee_name,
    transaction_reference: advanceDraft.transaction_reference,
    instrument_method: advanceDraft.instrument_method,
    instrument_status: advanceDraft.instrument_status,
    event_at: advanceDraft.event_at,
    already_recorded: advanceDraft.already_recorded,
    missing_fields: advanceDraft.missing_fields,
    payer_extraction_status: payerExtracted ? "PASS" : "FAIL",
    payee_extraction_status: payeeExtracted ? "PASS" : "FAIL",
  };
  expect(advanceDraft).toMatchObject({
    amount: 4_000_000,
    transaction_reference: method === "TRANSFER" ? "FT-TC01-0001" : "PC-TC01-0001",
    instrument_method: method,
    instrument_status: "COMPLETED",
    already_recorded: true,
  });
  expect(String(advanceDraft.event_at)).toMatch(/^(2026-10-05|05\/10\/2026)/);
  await expect(page.getByText(/đã có trong lịch sử công ty/)).toBeVisible();
  if (!payerExtracted || !payeeExtracted) {
    const corrections: Record<string, string> = {};
    if (!payerExtracted) {
      corrections.payer_name = "CÔNG TY TNHH GIẢI PHÁP CÔNG NGHỆ AN THỊNH";
      await page.getByLabel("Bên chi theo chứng từ").fill(corrections.payer_name);
    }
    if (!payeeExtracted) {
      corrections.payee_name = "NGUYỄN MINH AN";
      await page.getByLabel("Người nhận theo chứng từ").fill(corrections.payee_name);
    }
    captured.advanceDraft!.manual_corrections = {
      fields: corrections,
      basis: "Read from the source PDF; one or more model fields were null or incorrect.",
    };
  }

  const actualResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" && /\/actuals(?:\?|$)/.test(response.url()),
    { timeout: 120_000 },
  );
  await explainAdvanceIfNeeded(page, "Đã đối chiếu chứng từ với khoản ứng mô phỏng đã có; không ghi nhận giao dịch mới.");
  await page.getByRole("button", { name: "Xác nhận ghi nhận" }).click();
  const actualBody = await (await actualResponse).json();
  const finalCaseId = (actualBody.case_view?.id as string | undefined) ?? caseId;
  await expect(page.getByText("Đã ghi nhận tiền ứng thực nhận.")).toBeVisible();

  const afterResponse = await page.request.get(`/api/cases/${encodeURIComponent(finalCaseId)}`);
  expect(afterResponse.ok()).toBeTruthy();
  const afterView = await afterResponse.json();
  captured.after = viewSnapshot(afterView);
  expect(captured.after).toMatchObject({
    id: captured.before.id,
    activity: captured.before.activity,
    state: captured.before.state,
    T: captured.before.T,
    E: captured.before.E,
    A: captured.before.A,
    P: captured.before.P,
    R: captured.before.R,
    S: captured.before.S,
  });
  expect(captured.after).toMatchObject({ activity: "activity:tc01", A: 4_000_000 });
  expect(afterView.instructions).toEqual(beforeView.instructions);
  await expect(page.getByTestId("money-Ứng thực nhận")).toContainText("4.000.000 ₫");
  captured.uiBefore = {
    A: await page.getByTestId("money-Ứng thực nhận").innerText(),
  };
  await page.screenshot({ path: testInfo.outputPath("after-idempotent-re-upload.png"), fullPage: true });
  expect(advanceDraft.payer_name).toBe("CÔNG TY TNHH GIẢI PHÁP CÔNG NGHỆ AN THỊNH");
  expect(advanceDraft.payee_name).toBe("NGUYỄN MINH AN");
}

test("TC01 transfer B: accountant re-upload does not duplicate the existing advance", async ({ page }, testInfo) => {
  await runExistingAdvanceReceipt(page, testInfo, "TRANSFER");
});

test("TC01 cash A+B: TU-TC01 links and accountant re-upload is idempotent", async ({ page }, testInfo) => {
  await runTc01(page, testInfo, "CASH");
});

test("TC01 cash B: accountant re-upload does not duplicate the existing advance", async ({ page }, testInfo) => {
  await runExistingAdvanceReceipt(page, testInfo, "CASH");
});
