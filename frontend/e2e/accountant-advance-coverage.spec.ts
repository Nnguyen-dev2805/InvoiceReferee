import { explainAdvanceIfNeeded } from "./advance_helpers";
import { mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test, type Page, type TestInfo } from "@playwright/test";

const PROJECT_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const SETTLEMENT_DIR = path.join(
  PROJECT_ROOT,
  "data/tham-khao/uc-03/tc01-hop-le-nhan-vien-hoan-tra-tien-thua",
);
const SETTLEMENT_FILES = [
  path.join(SETTLEMENT_DIR, "report_hoan_ung.pdf"),
  path.join(SETTLEMENT_DIR, "hoa_don_dien_tu.pdf"),
];
const ADVANCE_FILE = path.join(
  PROJECT_ROOT,
  "data/demo/tc01-chung-tu-ung/03-bien-nhan-chuyen-khoan.pdf",
);
const COMPANY_NAME = "CÔNG TY TNHH GIẢI PHÁP CÔNG NGHỆ AN THỊNH";
const EMPLOYEE_NAME = "NGUYỄN MINH AN";

type Evidence = {
  provider_mode?: string;
  case_id?: string;
  activity_id?: string;
  context_digest?: string | null;
  source_hashes?: Record<string, string>;
  settlement_draft?: Record<string, unknown>;
  advance_draft?: Record<string, unknown>;
  before_advance?: Record<string, unknown>;
  after_advance?: Record<string, unknown>;
  after_coverage?: Record<string, unknown>;
  restarted?: Record<string, unknown>;
  reload_error?: string;
  console_errors: string[];
  request_failures: Array<{ method: string; path: string; error: string | null }>;
};

let evidence: Evidence;

function snapshot(view: any) {
  const money = view.actual_money ?? {};
  return {
    id: view.id,
    activity: view.activity,
    state: view.state,
    T: money.T ?? null,
    E: money.E ?? null,
    A: money.A ?? null,
    P: money.P ?? null,
    R: money.R ?? null,
    S: money.S ?? null,
    activity_acceptances: view.activity_acceptances ?? [],
    coverage_current: view.coverage_current ?? false,
    coverage_record: view.coverage_record ?? null,
    money_history: (view.money_history ?? []).map((event: any) => ({
      kind: event.kind,
      amount: event.amount,
      verification_state: event.verification_state,
      allocation_state: event.allocation_state,
    })),
    instructions: (view.instructions ?? []).map((item: any) => ({
      direction: item.direction,
      amount: item.amount,
      status: item.status,
    })),
    issues: (view.issues ?? []).map((issue: any) => ({
      kind: issue.kind,
      field_or_rule: issue.field_or_rule,
      owner: issue.owner,
      status: issue.status,
    })),
  };
}

async function capture(testInfo: TestInfo) {
  const body = JSON.stringify(evidence, null, 2);
  await testInfo.attach("accountant-advance-coverage-evidence.json", {
    body,
    contentType: "application/json",
  });
  const directory = process.env.ACCOUNTANT_FLOW_EVIDENCE_DIR;
  if (directory) {
    mkdirSync(directory, { recursive: true });
    writeFileSync(path.join(directory, "playwright-evidence.json"), body, "utf8");
  }
}

test.beforeEach(async ({ page }) => {
  evidence = { console_errors: [], request_failures: [] };
  page.on("console", (message) => {
    if (message.type() === "error") evidence.console_errors.push(message.text());
  });
  page.on("requestfailed", (request) => {
    evidence.request_failures.push({
      method: request.method(),
      path: new URL(request.url()).pathname,
      error: request.failure()?.errorText ?? null,
    });
  });
});

test.afterEach(async ({ page }, testInfo) => {
  await capture(testInfo);
  if (testInfo.status !== testInfo.expectedStatus) {
    await page.screenshot({ path: testInfo.outputPath("failure.png"), fullPage: true }).catch(() => undefined);
  }
});

test("TC01 new activity: durable advance, scoped coverage, COLLECT 760000", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("InvoiceReferee")).toBeVisible();

  const healthResponse = await page.request.get("/api/health");
  expect(healthResponse.ok()).toBeTruthy();
  const health = await healthResponse.json();
  evidence.provider_mode = String(health.mode);
  expect(health.mode).toBe("LIVE");
  expect(health.live_ready).toBeTruthy();

  await page.getByRole("button", { name: /Tạo hồ sơ mới/ }).click();
  await page.getByLabel("Chứng từ (PDF/PNG/JPEG)").setInputFiles(SETTLEMENT_FILES);
  await expect(page.getByText("Chứng từ đã chọn (2)")).toBeVisible();

  const settlementDraftResponse = page.waitForResponse(
    (response) => response.request().method() === "POST" && response.url().includes("/settlement/draft"),
    { timeout: 240_000 },
  );
  await page.getByRole("button", { name: "Đọc chứng từ" }).click();
  await expect(page.getByText("Kiểm tra bản nháp hồ sơ")).toBeVisible({ timeout: 240_000 });
  const settlementDraft = await (await settlementDraftResponse).json();
  evidence.settlement_draft = {
    declared_advance: settlementDraft.declared_advance,
    incurred_total: settlementDraft.incurred_total,
    expenses: settlementDraft.expenses,
    link: settlementDraft.link,
    warnings: settlementDraft.warnings,
  };

  // Never select a standing sample activity to make the case pass. The submitted
  // root remains the new server-generated proposal unless the uploaded sources
  // themselves establish a unique link.
  expect(settlementDraft.link?.status).not.toBe("CONFLICT");
  if (settlementDraft.link?.status === "NEEDS_CONFIRMATION") {
    throw new Error(`TC01 needs a human activity-link choice: ${JSON.stringify(settlementDraft.link)}`);
  }
  expect(settlementDraft.declared_advance).toBe(4_000_000);
  expect(settlementDraft.incurred_total).toBe(3_240_000);

  const submitResponse = page.waitForResponse(
    (response) => response.request().method() === "POST" && /\/submit(?:\?|$)/.test(response.url()),
    { timeout: 120_000 },
  );
  await page.getByRole("button", { name: "Xác nhận và nộp hồ sơ" }).click();
  const submitted = await (await submitResponse).json();
  const caseId = String(submitted.case_view?.id ?? "");
  expect(caseId).toBeTruthy();
  evidence.case_id = caseId;
  evidence.activity_id = String(submitted.case_view.activity);
  expect(evidence.activity_id).toMatch(/^activity:proposed:/);

  await expect(page.getByRole("heading", { name: "Hồ sơ đối soát" })).toBeVisible({ timeout: 120_000 });
  const beforeResponse = await page.request.get(`/api/cases/${encodeURIComponent(caseId)}`);
  expect(beforeResponse.ok()).toBeTruthy();
  const before = await beforeResponse.json();
  evidence.context_digest = (await (await page.request.get("/api/demo/session")).json()).diagnostics.context_digest;
  evidence.before_advance = snapshot(before);
  expect(before.money_history ?? []).toHaveLength(0);

  await page.locator("#persona-select").selectOption("accountant");
  const row = page.getByRole("row").filter({ hasText: "Hồ sơ quyết toán chi phí" });
  await expect(row).toBeVisible({ timeout: 60_000 });
  await row.click();
  await page.getByRole("tab", { name: "Sổ cái & Dòng tiền" }).click();
  await expect(page.getByRole("heading", { name: "Ghi nhận tạm ứng từ chứng từ" })).toBeVisible();

  const draftResponse = page.waitForResponse(
    (response) => response.request().method() === "POST" && response.url().includes("/advance/draft"),
    { timeout: 240_000 },
  );
  await page.getByLabel("Phương thức ứng").selectOption("TRANSFER");
  await page.getByLabel("Chứng từ ứng").setInputFiles(ADVANCE_FILE);
  await expect(page.getByTestId("advance-draft")).toBeVisible({ timeout: 240_000 });
  const advanceResponse = await (await draftResponse).json();
  const advanceDraft = advanceResponse.draft;
  evidence.advance_draft = {
    ...advanceDraft,
    refs: advanceDraft.refs,
    persisted_source_count: advanceResponse.case_view.sources.length,
  };
  expect(advanceDraft.amount).toBe(4_000_000);
  expect(advanceDraft.payee_name).toBe(EMPLOYEE_NAME);
  expect(advanceDraft.instrument_status).toBe("COMPLETED");
  await expect(page.getByLabel("Người nhận theo chứng từ")).toHaveValue(EMPLOYEE_NAME);
  await expect(page.getByLabel("Người nhận theo chứng từ")).toHaveClass(/text-sm/);

  if (advanceDraft.activity_link_status === "CONFLICT") {
    throw new Error(`Advance voucher references conflicting work: ${JSON.stringify(advanceDraft)}`);
  }
  if (advanceDraft.activity_link_status !== "LINKED") {
    await page.getByLabel("Tôi xác nhận chứng từ ứng thuộc công việc trong hồ sơ này").check();
    await page.getByLabel("Căn cứ đối chiếu với công việc").fill(
      "Hai giấy quyết toán và chứng từ ứng cùng mô tả công việc tiếp khách; đã kiểm tra đúng nhân viên nhận tiền.",
    );
  }
  const manualCorrections: Record<string, string> = {};
  if (advanceDraft.payer_name === null) {
    manualCorrections.payer_name = COMPANY_NAME;
    await page.getByLabel("Bên chi theo chứng từ").fill(COMPANY_NAME);
  } else {
    expect(advanceDraft.payer_name).toBe(COMPANY_NAME);
  }
  if (advanceDraft.payee_name === null) {
    manualCorrections.payee_name = EMPLOYEE_NAME;
    await page.getByLabel("Người nhận theo chứng từ").fill(EMPLOYEE_NAME);
  } else {
    expect(advanceDraft.payee_name).toBe(EMPLOYEE_NAME);
  }
  evidence.advance_draft.manual_corrections = manualCorrections;
  await explainAdvanceIfNeeded(page, "Đã kiểm tra chứng từ chuyển khoản hoàn tất và đối chiếu người chi, người nhận, số tiền, ngày giao dịch.");
  const actualResponse = page.waitForResponse(
    (response) => response.request().method() === "POST" && /\/actuals(?:\?|$)/.test(response.url()),
    { timeout: 120_000 },
  );
  await page.getByRole("button", { name: "Xác nhận ghi nhận" }).click();
  const actualHttpResponse = await actualResponse;
  expect(actualHttpResponse.ok()).toBeTruthy();
  const actualResult = await actualHttpResponse.json();
  expect(actualResult.case_view.activity_acceptances).toHaveLength(1);
  const settlementSourceId = advanceResponse.case_view.sources.find(
    (source: { filename: string | null }) => source.filename === "report_hoan_ung.pdf",
  )?.id;
  expect(settlementSourceId).toBeTruthy();
  expect(actualResult.case_view.activity_acceptances[0].refs).toEqual(
    expect.arrayContaining([expect.objectContaining({ source_id: settlementSourceId })]),
  );
  const afterAdvanceResponse = await page.request.get(`/api/cases/${encodeURIComponent(caseId)}`);
  const afterAdvance = await afterAdvanceResponse.json();
  evidence.after_advance = snapshot(afterAdvance);
  expect(afterAdvance.money_history).toContainEqual(
    expect.objectContaining({ kind: "ADVANCE_RECEIVED", amount: 4_000_000, verification_state: "CONFIRMED" }),
  );

  // One source-bound receipt confirmation also enables dossier-scoped reconciliation.
  await expect(page.getByRole("checkbox", { name: /đã ghi nhận đầy đủ các khoản tiền/i })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Xác nhận lịch sử ban đầu" })).toHaveCount(0);
  const afterCoverage = afterAdvance;
  evidence.after_coverage = snapshot(afterCoverage);
  expect(afterCoverage.coverage_current).toBe(true);
  expect(afterCoverage.actual_money.E).toMatchObject({ value: 3_240_000, state: "KNOWN" });
  expect(afterCoverage.actual_money.A).toMatchObject({ value: 4_000_000, state: "KNOWN" });
  expect(afterCoverage.actual_money.P).toMatchObject({ value: 0, state: "KNOWN" });
  expect(afterCoverage.actual_money.R).toMatchObject({ value: 0, state: "KNOWN" });
  expect(afterCoverage.actual_money.S).toMatchObject({ value: -760_000, state: "KNOWN" });
  expect(afterCoverage.instructions).toEqual(
    expect.arrayContaining([expect.objectContaining({ direction: "COLLECT", amount: 760_000 })]),
  );

  await page.reload();
  const reopened = await page.request.get(`/api/cases/${encodeURIComponent(caseId)}`);
  expect(reopened.ok()).toBeTruthy();
  evidence.restarted = snapshot(await reopened.json());
  expect(evidence.restarted).toMatchObject({
    A: { value: 4_000_000, state: "KNOWN" },
    S: { value: -760_000, state: "KNOWN" },
    coverage_current: true,
    instructions: expect.arrayContaining([expect.objectContaining({ direction: "COLLECT", amount: 760_000 })]),
  });
});
