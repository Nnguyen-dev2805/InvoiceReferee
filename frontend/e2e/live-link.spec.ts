import { explainAdvanceIfNeeded } from "./advance_helpers";
import { expect, test } from "@playwright/test";
import path from "path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const PILOT = path.resolve(
  __dirname,
  "../../data/test-kit/uc03-pilot/f01-cong-tac-thu-lai-tien-thua/input",
);
const SETTLEMENT = path.join(PILOT, "01-giay-quyet-toan.pdf");
const INVOICE = path.join(PILOT, "02-hoa-don-dich-vu.pdf");
const RECEIPT = path.join(PILOT, "03-bien-nhan-chuyen-khoan.pdf");
const VOUCHER = path.join(PILOT, "04-phieu-chi-tien-mat.pdf");

test.describe.configure({ mode: "serial" });

async function apiListCases(page: any) {
  const request = page.request;
  const res = await request.get("/api/cases");
  expect(res.ok()).toBeTruthy();
  return (await res.json()).cases as any[];
}

async function apiGetCase(page: any, id: string) {
  const request = page.request;
  const res = await request.get(`/api/cases/${id}`);
  expect(res.ok()).toBeTruthy();
  return await res.json();
}

async function startDossier(page: any, files: string[]) {
  await page.goto("/");
  await page.getByRole("button", { name: "+ Tạo hồ sơ mới" }).click();
  await page.getByLabel("Chứng từ (PDF/PNG/JPEG)").setInputFiles(files);
  await page.getByRole("button", { name: "Đọc chứng từ" }).click();
  await expect(
    page.getByRole("button", { name: "Xác nhận và nộp hồ sơ" }),
  ).toBeVisible({ timeout: 240_000 });
}

async function submitDossier(page: any) {
  await page.getByRole("button", { name: "Xác nhận và nộp hồ sơ" }).click();
}

async function switchPersona(page: any, role: "Kế toán" | "Nhân viên") {
  await page.getByTitle("Chuyển đổi vai trò").click();
  await page.getByRole("button", { name: new RegExp(role) }).first().click();
  await expect(page.getByTitle("Chuyển đổi vai trò")).toContainText(role, {
    timeout: 15_000,
  });
}

async function openDossierById(page: any, id: string) {
  await page.goto("/");
  // Dashboard rows show "#<8hex>" cells (the "Hồ sơ #" prefix only exists in
  // the detail header).
  const shortId = id.replace("case:", "").slice(0, 8);
  await page.getByText(new RegExp(`#${shortId}`)).first().click();
  await expect(
    page.getByRole("heading", { name: "Hồ sơ đối soát" }),
  ).toBeVisible({ timeout: 30_000 });
}

async function findDossierByActivity(page: any, activity: string) {
  const cases = await apiListCases(page);
  return cases.find((c: any) => c.activity === activity)?.id ?? null;
}

async function openOrCreateLinkedDossier(page: any) {
  // Full runs already own an adv-A dossier (scenario 1); subset runs create
  // one. Either way the accountant reloads the same transfer receipt below.
  // Load the app first so the API client carries the demo session (wait
  // for the dashboard: the session cookie is set asynchronously on load).
  await page.goto("/");
  await expect(
    page.getByRole("button", { name: "+ Tạo hồ sơ mới" }),
  ).toBeVisible({ timeout: 30_000 });
  const existing = await findDossierByActivity(page, "activity:link-adv-a");
  if (existing) return existing as string;
  await startDossier(page, [SETTLEMENT, INVOICE, RECEIPT]);
  await expect(page.getByText(/Đã liên kết với hồ sơ/)).toBeVisible({
    timeout: 30_000,
  });
  await submitDossier(page);
  await expect(
    page.getByRole("heading", { name: "Hồ sơ đối soát" }),
  ).toBeVisible({ timeout: 60_000 });
  const mine = await apiListCases(page);
  return mine[mine.length - 1].id as string;
}

async function openOrCreateAskedDossier(page: any) {
  // Full runs already own an adv-B dossier (scenario 3); subset runs create
  // one through the ask-and-confirm flow. Load the app first for the session
  // (dashboard readiness proves the cookie is set).
  await page.goto("/");
  await expect(
    page.getByRole("button", { name: "+ Tạo hồ sơ mới" }),
  ).toBeVisible({ timeout: 30_000 });
  const existing = await findDossierByActivity(page, "activity:link-adv-b");
  if (existing) return existing as string;
  await startDossier(page, [SETTLEMENT, INVOICE]);
  await expect(
    page.getByText("Hồ sơ này quyết toán cho khoản tạm ứng nào?"),
  ).toBeVisible({ timeout: 30_000 });
  await page.getByRole("radio").nth(1).check();
  await submitDossier(page);
  await expect(
    page.getByRole("heading", { name: "Hồ sơ đối soát" }),
  ).toBeVisible({ timeout: 60_000 });
  const mine = await apiListCases(page);
  return mine[mine.length - 1].id as string;
}

test("1. history+reference links the dossier, no activity choice", async ({
  page,
}) => {
  await startDossier(page, [SETTLEMENT, INVOICE, RECEIPT]);
  // No standing-activity dropdown in the normal flow; one merged field.
  await expect(page.getByLabel("Hoạt động của hồ sơ")).toHaveCount(0);
  await expect(
    page.getByLabel("Nội dung đề nghị quyết toán:"),
  ).toBeVisible();
  // The backend linked the receipt's ADV-UC03-F01 to the recorded advance.
  await expect(page.getByText(/Đã liên kết với hồ sơ/)).toBeVisible({
    timeout: 30_000,
  });
  await submitDossier(page);
  await expect(
    page.getByRole("heading", { name: "Hồ sơ đối soát" }),
  ).toBeVisible({ timeout: 60_000 });
  const cases = await apiListCases(page);
  expect(cases.length).toBeGreaterThan(0);
  const view = await apiGetCase(page, cases[cases.length - 1].id);
  expect(view.state).not.toBe("DRAFT");
  expect(view.activity).toBe("activity:link-adv-a");
  await page.screenshot({ path: "link-1-linked.png" });
});

test("3. two same-amount advances are asked, never auto-picked", async ({
  page,
}) => {
  await startDossier(page, [SETTLEMENT, INVOICE]);
  await expect(
    page.getByText("Hồ sơ này quyết toán cho khoản tạm ứng nào?"),
  ).toBeVisible({ timeout: 30_000 });
  const options = page.getByRole("radio");
  await expect(options).toHaveCount(3);
  // Submitting without a choice is refused; nothing is auto-linked.
  await submitDossier(page);
  await expect(page.getByRole("alert")).toBeVisible();
  await options.nth(1).check();
  await submitDossier(page);
  await expect(
    page.getByRole("heading", { name: "Hồ sơ đối soát" }),
  ).toBeVisible({ timeout: 60_000 });
  const casesB = await apiListCases(page);
  const viewB = await apiGetCase(page, casesB[casesB.length - 1].id);
  expect(viewB.activity).toBe("activity:link-adv-b");
  await page.screenshot({ path: "link-3-asked.png" });
});

test("6. invoice-only dossier without any advance is accepted", async ({
  page,
}) => {
  await startDossier(page, [INVOICE]);
  await submitDossier(page);
  await expect(
    page.getByRole("heading", { name: "Hồ sơ đối soát" }),
  ).toBeVisible({ timeout: 60_000 });
  const cases = await apiListCases(page);
  const view = await apiGetCase(page, cases[cases.length - 1].id);
  expect(view.state).not.toBe("DRAFT");
  await page.screenshot({ path: "link-6-noadvance.png" });
});

test("2. no advance record: accountant records the voucher via UI", async ({
  page,
}) => {
  await startDossier(page, [SETTLEMENT, INVOICE]);
  // Weak-only basis here as well (same purpose on both advances).
  await expect(
    page.getByText("Hồ sơ này quyết toán cho khoản tạm ứng nào?"),
  ).toBeVisible({ timeout: 30_000 });
  await page.getByRole("radio").nth(2).check();
  await submitDossier(page);
  await expect(
    page.getByRole("heading", { name: "Hồ sơ đối soát" }),
  ).toBeVisible({ timeout: 60_000 });
  const cases = await apiListCases(page);
  const dossierId = cases[cases.length - 1].id;

  await switchPersona(page, "Kế toán");
  // Switching persona lands on the dashboard: open the adv-C dossier.
  await page.locator("tr", { hasText: "Tạm ứng C" }).first().click();
  // The advance panel works on the submitted dossier.
  await page.getByLabel("Chứng từ ứng").setInputFiles([RECEIPT]);
  await expect(page.getByTestId("advance-draft")).toBeVisible({
    timeout: 240_000,
  });
  // A second voucher code: the printed ADV-UC03-F01 already belongs to adv-A.
  await page.getByLabel("Mã giao dịch hoặc số phiếu").fill("ADV-UC03-F02");
  await explainAdvanceIfNeeded(page, "Đã kiểm tra chứng từ ứng và xác nhận đã giao.");
  await page.getByRole("button", { name: "Xác nhận ghi nhận" }).click();
  await expect(page.getByText(/Đã ghi nhận tiền ứng thực nhận/)).toBeVisible({
    timeout: 60_000,
  });
  const view = await apiGetCase(page, dossierId);
  expect(view.actual_money?.A?.state).toBe("KNOWN");
  expect(view.actual_money?.A?.value).toBe(4_000_000);
  await page.screenshot({ path: "link-2-recorded.png" });
});

test("5. reloading the same advance transaction stays idempotent", async ({
  page,
}) => {
  // Reuses scenario 1's adv-A dossier in full runs; creates its own in
  // subset runs. Either way the same transfer receipt is recorded twice.
  const dossierId = await openOrCreateLinkedDossier(page);
  await switchPersona(page, "Kế toán");
  await openDossierById(page, dossierId);
  let beforeA: number | null = null;
  for (let round = 0; round < 2; round++) {
    // Reset the input so choosing the same file fires a change event again.
    await page.getByLabel("Chứng từ ứng").setInputFiles([]);
    await page.getByLabel("Chứng từ ứng").setInputFiles([RECEIPT]);
    await expect(page.getByTestId("advance-draft")).toBeVisible({
      timeout: 240_000,
    });
    if (round === 1) {
      // The first round recorded this exact key: the draft says so upfront.
      await expect(
        page.getByText(/đã có trong lịch sử công ty/),
      ).toBeVisible({ timeout: 30_000 });
    }
    await explainAdvanceIfNeeded(page, `Ghi nhận lại cùng giao dịch lần ${round + 1}.`);
    await page.getByRole("button", { name: "Xác nhận ghi nhận" }).click();
    await expect(page.getByText(/Đã ghi nhận tiền ứng thực nhận/)).toBeVisible({
      timeout: 60_000,
    });
    const current = await apiGetCase(page, dossierId);
    if (round === 0) {
      beforeA = current.actual_money?.A?.value ?? null;
    } else {
      // Reloading the same key must not move A.
      expect(current.actual_money?.A?.value).toBe(beforeA);
    }
  }
  await expect(page.getByRole("alert")).toHaveCount(0);
  await page.screenshot({ path: "link-5-idempotent.png" });
});

test("4. voucher naming another payee never becomes confirmed A", async ({
  page,
}) => {
  // Reuses scenario 3's adv-B dossier in full runs (it never established an
  // advance); creates its own through ask-and-confirm in subset runs. The
  // wrong-payee record must not create an advance either way.
  const dossierId = await openOrCreateAskedDossier(page);
  await switchPersona(page, "Kế toán");
  await openDossierById(page, dossierId);
  await page.getByLabel("Chứng từ ứng").setInputFiles([VOUCHER]);
  await expect(page.getByTestId("advance-draft")).toBeVisible({
    timeout: 240_000,
  });
  await page.getByLabel("Người nhận theo chứng từ").fill("Nguyễn Văn B");
  await explainAdvanceIfNeeded(page, "Kiểm tra chứng từ ghi người nhận khác nhân viên hồ sơ.");
  await page.getByRole("button", { name: "Xác nhận ghi nhận" }).click();
  // Either notice is a successful record: the wrong-payee voucher lands as
  // an OBSERVED (unconfirmed) event, never a CONFIRMED advance.
  await expect(
    page.getByText(/Đã (ghi nhận tiền ứng thực nhận|lưu chứng từ để đối chiếu)/),
  ).toBeVisible({
    timeout: 60_000,
  });
  // The event is preserved but OBSERVED: A is not established from it.
  const view = await apiGetCase(page, dossierId);
  const a = view.actual_money?.A;
  expect(a?.state).not.toBe("KNOWN");
  await page.screenshot({ path: "link-4-wrongpayee.png" });
});
