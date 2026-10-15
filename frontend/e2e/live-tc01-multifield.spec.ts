import { expect, test, type Page, type TestInfo } from "@playwright/test";
import { mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

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
  mode?: string;
  root_id?: string;
  activity_id?: string;
  context_digest?: string;
  settlement_draft?: Record<string, unknown>;
  advance_draft?: Record<string, unknown>;
  before_record?: Record<string, unknown>;
  after_record?: Record<string, unknown>;
  console_errors: string[];
  request_failures: Array<{ method: string; path: string; error: string | null }>;
};

let evidence: Evidence;

function snapshot(view: any) {
  return {
    id: view.id,
    activity: view.activity,
    state: view.state,
    A: view.actual_money?.A ?? null,
    coverage_record: view.coverage_record ?? null,
    activity_acceptances: view.activity_acceptances ?? [],
    money_history: (view.money_history ?? []).map((event: any) => ({
      kind: event.kind,
      amount: event.amount,
      verification_state: event.verification_state,
      allocation_state: event.allocation_state,
    })),
    instructions: view.instructions ?? [],
  };
}

async function capture(testInfo: TestInfo) {
  const body = JSON.stringify(evidence, null, 2);
  await testInfo.attach("tc01-multifield-live-evidence.json", {
    body,
    contentType: "application/json",
  });
  const dir = process.env.TC01_MULTIFIELD_EVIDENCE_DIR;
  if (dir) {
    mkdirSync(dir, { recursive: true });
    writeFileSync(path.join(dir, "playwright-evidence.json"), body, "utf8");
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

test("TC01 links an unregistered voucher by source-backed fields, then accountant records once", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("InvoiceReferee")).toBeVisible();
  const healthResponse = await page.request.get("/api/health");
  expect(healthResponse.ok()).toBeTruthy();
  const health = await healthResponse.json();
  evidence.mode = String(health.mode);
  expect(health.mode).toBe("LIVE");
  expect(health.live_ready).toBeTruthy();

  await page.getByRole("button", { name: /Tạo hồ sơ mới/ }).click();
  await page.getByLabel("Chứng từ (PDF/PNG/JPEG)").setInputFiles(SETTLEMENT_FILES);
  const settlementResponse = page.waitForResponse(
    (response) => response.request().method() === "POST" && response.url().includes("/settlement/draft"),
    { timeout: 240_000 },
  );
  await page.getByRole("button", { name: "Đọc chứng từ" }).click();
  await expect(page.getByText("Kiểm tra bản nháp hồ sơ")).toBeVisible({ timeout: 240_000 });
  const settlementDraft = await (await settlementResponse).json();
  evidence.settlement_draft = {
    declared_advance: settlementDraft.declared_advance,
    incurred_total: settlementDraft.incurred_total,
    link: settlementDraft.link,
  };
  expect(settlementDraft.declared_advance).toBe(4_000_000);
  expect(settlementDraft.incurred_total).toBe(3_240_000);

  const submitResponse = page.waitForResponse(
    (response) => response.request().method() === "POST" && /\/submit(?:\?|$)/.test(response.url()),
    { timeout: 120_000 },
  );
  await page.getByRole("button", { name: "Xác nhận và nộp hồ sơ" }).click();
  const submitted = await (await submitResponse).json();
  const rootId = String(submitted.case_view?.id ?? "");
  const activityId = String(submitted.case_view?.activity ?? "");
  expect(rootId).toBeTruthy();
  expect(activityId).toMatch(/^activity:proposed:/);
  evidence.root_id = rootId;
  evidence.activity_id = activityId;
  await expect(page.getByRole("heading", { name: "Hồ sơ đối soát" })).toBeVisible({ timeout: 120_000 });
  const beforeResponse = await page.request.get(`/api/cases/${encodeURIComponent(rootId)}`);
  expect(beforeResponse.ok()).toBeTruthy();
  evidence.before_record = snapshot(await beforeResponse.json());
  expect(evidence.before_record.money_history).toHaveLength(0);

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
  const draft = advanceResponse.draft;
  evidence.context_digest = (await (await page.request.get("/api/demo/session")).json()).diagnostics.context_digest;
  evidence.advance_draft = draft;

  expect(draft.activity_reference).toBe("TU-TC01");
  expect(draft.activity_link_status).toBe("LINKED");
  expect(draft.activity_link_basis).toBe("MULTI_FIELD_MATCH");
  expect(draft.matched_activity_id).toBe(activityId);
  expect(draft.activity_link_candidate_count).toBe(1);
  expect(draft.amount).toBe(4_000_000);
  expect(draft.payer_name).toBe(COMPANY_NAME);
  expect(draft.payee_name).toBe(EMPLOYEE_NAME);
  expect(draft.event_at).toBeTruthy();
  expect(draft.instrument_status).toBe("COMPLETED");
  const signals = Object.fromEntries(draft.activity_link_signals.map((signal: any) => [signal.field, signal.state]));
  expect(signals).toMatchObject({
    employee: "MATCHED",
    company: "MATCHED",
    purpose: "MATCHED",
    advance_amount: "MATCHED",
    time: "MATCHED",
    reference: "UNMAPPED",
    transaction: "MATCHED",
    candidates: "MATCHED",
  });

  await expect(page.getByText("Đã tự liên kết với hồ sơ này")).toBeVisible();
  await expect(page.getByLabel("Tôi xác nhận chứng từ ứng thuộc công việc trong hồ sơ này")).toHaveCount(0);
  await expect(page.getByLabel("Căn cứ đối chiếu với công việc")).toHaveCount(0);
  await expect(page.getByLabel("Bên chi theo chứng từ")).toHaveValue(COMPANY_NAME);
  await expect(page.getByLabel("Người nhận theo chứng từ")).toHaveValue(EMPLOYEE_NAME);
  await expect(
    page.getByRole("button", { name: /03-bien-nhan-chuyen-khoan\.pdf/ }),
  ).toHaveAttribute("aria-pressed", "true");

  await expect(page.getByLabel("Căn cứ bổ sung thông tin")).toHaveCount(0);
  await expect(page.getByLabel("Xác nhận của kế toán")).toHaveCount(0);
  const actualResponse = page.waitForResponse(
    (response) => response.request().method() === "POST" && /\/actuals(?:\?|$)/.test(response.url()),
    { timeout: 120_000 },
  );
  await page.getByRole("button", { name: "Xác nhận ghi nhận" }).click();
  const actual = await actualResponse;
  expect(actual.ok()).toBeTruthy();
  const view = (await actual.json()).case_view;
  evidence.after_record = snapshot(view);
  expect(view.activity_acceptances).toHaveLength(1);
  expect(view.activity_acceptances[0].link_basis).toBe("MULTI_FIELD_MATCH");
  expect(view.activity_acceptances[0].link_signals.length).toBeGreaterThanOrEqual(6);
  expect(view.money_history).toHaveLength(1);
  expect(view.money_history[0]).toMatchObject({
    kind: "ADVANCE_RECEIVED",
    amount: 4_000_000,
    verification_state: "CONFIRMED",
  });
  expect(view.coverage_record).toBeNull();
  expect(view.instructions).toEqual([]);

  await page.reload();
  const reopened = await page.request.get(`/api/cases/${encodeURIComponent(rootId)}`);
  expect(reopened.ok()).toBeTruthy();
  const persisted = await reopened.json();
  expect(persisted.activity_acceptances).toHaveLength(1);
  expect(persisted.activity_acceptances[0].link_basis).toBe("MULTI_FIELD_MATCH");
  expect(persisted.money_history).toHaveLength(1);
  expect(persisted.coverage_record).toBeNull();
  expect(persisted.instructions).toEqual([]);
});
