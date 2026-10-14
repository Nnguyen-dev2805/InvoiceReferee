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

let dossierA = "";
let dossierB = "";

async function apiListCases(request: any) {
  const res = await request.get("/api/cases");
  expect(res.ok()).toBeTruthy();
  return (await res.json()).cases as any[];
}

async function apiGetCase(request: any, id: string) {
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

test("1. history+reference links the dossier, no activity choice", async ({
  page,
  request,
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
  await expect(page.getByText(/Đã nộp hồ sơ/)).toBeVisible({ timeout: 60_000 });
  const cases = await apiListCases(request);
  expect(cases.length).toBeGreaterThan(0);
  const view = await apiGetCase(request, cases[cases.length - 1].id);
  expect(view.state).not.toBe("DRAFT");
  expect(view.activity).toBe("activity:link-adv-a");
  dossierA = view.id;
  await page.screenshot({ path: "link-1-linked.png" });
});

test("3. two same-amount advances are asked, never auto-picked", async ({
  page,
  request,
}) => {
  await startDossier(page, [SETTLEMENT, INVOICE]);
  await expect(
    page.getByText("Hồ sơ này quyết toán cho khoản tạm ứng nào?"),
  ).toBeVisible({ timeout: 30_000 });
  const options = page.getByRole("radio");
  await expect(options).toHaveCount(2);
  // Submitting without a choice is refused; nothing is auto-linked.
  await submitDossier(page);
  await expect(page.getByRole("alert")).toBeVisible();
  await options.nth(1).check();
  await submitDossier(page);
  await expect(page.getByText(/Đã nộp hồ sơ/)).toBeVisible({ timeout: 60_000 });
  const casesB = await apiListCases(request);
  dossierB = casesB[casesB.length - 1].id;
  const viewB = await apiGetCase(request, dossierB);
  expect(viewB.activity).toBe("activity:link-adv-b");
  await page.screenshot({ path: "link-3-asked.png" });
});

test("6. invoice-only dossier without any advance is accepted", async ({
  page,
  request,
}) => {
  await startDossier(page, [INVOICE]);
  await submitDossier(page);
  await expect(page.getByText(/Đã nộp hồ sơ/)).toBeVisible({ timeout: 60_000 });
  const cases = await apiListCases(request);
  const view = await apiGetCase(request, cases[cases.length - 1].id);
  expect(view.state).not.toBe("DRAFT");
  await page.screenshot({ path: "link-6-noadvance.png" });
});

test("2. no advance record: accountant records the voucher via UI", async ({
  page,
  request,
}) => {
  await startDossier(page, [SETTLEMENT, INVOICE]);
  // Weak-only basis here as well (same purpose on both advances).
  await expect(
    page.getByText("Hồ sơ này quyết toán cho khoản tạm ứng nào?"),
  ).toBeVisible({ timeout: 30_000 });
  await page.getByRole("radio").nth(1).check();
  await submitDossier(page);
  await expect(page.getByText(/Đã nộp hồ sơ/)).toBeVisible({ timeout: 60_000 });
  const cases = await apiListCases(request);
  const dossierId = cases[cases.length - 1].id;

  await switchPersona(page, "Kế toán");
  // The advance panel works on the submitted dossier.
  await page.getByLabel("Chứng từ ứng").setInputFiles([RECEIPT]);
  await expect(page.getByTestId("advance-draft")).toBeVisible({
    timeout: 240_000,
  });
  // A second voucher code: the printed ADV-UC03-F01 already belongs to adv-A.
  await page.getByLabel("Mã giao dịch hoặc số phiếu").fill("ADV-UC03-F02");
  await page
    .getByLabel("Xác nhận của kế toán")
    .fill("Đã kiểm tra chứng từ ứng và xác nhận đã giao.");
  await page.getByRole("button", { name: "Xác nhận ghi nhận" }).click();
  await expect(page.getByText(/Đã ghi nhận tiền ứng thực nhận/)).toBeVisible({
    timeout: 60_000,
  });
  const view = await apiGetCase(request, dossierId);
  expect(view.actual_money?.A?.state).toBe("KNOWN");
  expect(view.actual_money?.A?.value).toBe(4_000_000);
  await page.screenshot({ path: "link-2-recorded.png" });
});

test("5. reloading the same advance transaction stays idempotent", async ({
  page,
  request,
}) => {
  expect(dossierA).not.toBe("");
  await switchPersona(page, "Kế toán");
  await page.goto("/");
  // Open the scenario-1 dossier again from the dashboard.
  const shortId = dossierA.replace("case:", "").slice(0, 8);
  await page.getByText(new RegExp(`Hồ sơ #${shortId}`)).first().click();
  for (let round = 0; round < 2; round++) {
    await page.getByLabel("Chứng từ ứng").setInputFiles([RECEIPT]);
    await expect(page.getByTestId("advance-draft")).toBeVisible({
      timeout: 240_000,
    });
    await page
      .getByLabel("Xác nhận của kế toán")
      .fill(`Ghi nhận lại cùng giao dịch lần ${round + 1}.`);
    await page.getByRole("button", { name: "Xác nhận ghi nhận" }).click();
    await expect(page.getByText(/Đã ghi nhận tiền ứng thực nhận/)).toBeVisible({
      timeout: 60_000,
    });
  }
  await expect(page.getByRole("alert")).toHaveCount(0);
  // The witnessed history is not counted twice: A stays 4m, not 8m.
  const view = await apiGetCase(request, dossierA);
  expect(view.actual_money?.A?.value).toBe(4_000_000);
  await page.screenshot({ path: "link-5-idempotent.png" });
});

test("4. voucher naming another payee never becomes confirmed A", async ({
  page,
  request,
}) => {
  // Dossier B never established an advance: the wrong-payee record must not
  // create one.
  expect(dossierB).not.toBe("");
  await switchPersona(page, "Kế toán");
  await page.goto("/");
  const shortB = dossierB.replace("case:", "").slice(0, 8);
  await page.getByText(new RegExp(`Hồ sơ #${shortB}`)).first().click();
  await page.getByLabel("Chứng từ ứng").setInputFiles([VOUCHER]);
  await expect(page.getByTestId("advance-draft")).toBeVisible({
    timeout: 240_000,
  });
  await page.getByLabel("Người nhận theo chứng từ").fill("Nguyễn Văn B");
  await page
    .getByLabel("Xác nhận của kế toán")
    .fill("Kiểm tra chứng từ ghi người nhận khác nhân viên hồ sơ.");
  await page.getByRole("button", { name: "Xác nhận ghi nhận" }).click();
  await expect(page.getByText(/Đã ghi nhận tiền ứng thực nhận/)).toBeVisible({
    timeout: 60_000,
  });
  // The event is preserved but OBSERVED: A is not established from it.
  const view = await apiGetCase(request, dossierB);
  const a = view.actual_money?.A;
  expect(a?.state).not.toBe("KNOWN");
  await page.screenshot({ path: "link-4-wrongpayee.png" });
});
