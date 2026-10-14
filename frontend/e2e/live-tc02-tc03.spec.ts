import { test, expect } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const PROJECT_ROOT = path.resolve(__dirname, "../..");
const TC02_DIR = path.join(PROJECT_ROOT, "data/tham-khao/uc-03/tc02-hop-le-cong-ty-thanh-toan-them");
const TC03_DIR = path.join(PROJECT_ROOT, "data/tham-khao/uc-03/tc03-hop-le-khong-phat-sinh-chenh-lech");

test.describe("InvoiceReferee Independent LIVE Audit — TC02 & TC03", () => {
  test.beforeEach(async ({ page }) => {
    // Collect console errors
    page.on("console", (msg) => {
      if (msg.type() === "error") {
        console.error(`[Browser Console Error]: ${msg.text()}`);
      }
    });
    // Collect failed requests
    page.on("requestfailed", (req) => {
      console.error(`[Request Failed]: ${req.method()} ${req.url()} - ${req.failure()?.errorText}`);
    });
  });

  test("TC02 — Mua thiết bị văn phòng: Công ty thanh toán thêm (PAY 400.000 đ)", async ({ page }) => {
    // 1. Load application
    await page.goto("/");
    await expect(page.getByText("InvoiceReferee")).toBeVisible();

    // 2. From Dashboard, click "+ Tạo hồ sơ mới" to enter Intake
    const createBtn = page.getByRole("button", { name: "+ Tạo hồ sơ mới" });
    await expect(createBtn).toBeVisible({ timeout: 15_000 });
    await createBtn.click();

    // 3. Upload real PDF sources
    const reportPdf = path.join(TC02_DIR, "report_hoan_ung.pdf");
    const invoicePdf = path.join(TC02_DIR, "hoa_don_dien_tu.pdf");

    const fileInput = page.getByLabel("Chứng từ (PDF/PNG/JPEG)");
    await fileInput.setInputFiles([reportPdf, invoicePdf]);

    // Verify 2 files are selected
    await expect(page.getByText("Tệp đã chọn sẵn sàng trích xuất (2):")).toBeVisible();

    // 4. Click "Đọc chứng từ" and wait for LIVE OCR + LLM parsing
    const readBtn = page.getByRole("button", { name: "Đọc chứng từ" });
    await expect(readBtn).toBeEnabled();
    await readBtn.click();

    // 5. Review draft step
    // LIVE OCR on 2 files can take 30-60s
    await expect(page.getByText("Kiểm tra bản nháp hồ sơ")).toBeVisible({ timeout: 180_000 });

    // Assert visual ground truth values extracted from PDFs:
    // Incurred: 5.400.000 đ, Advance: 5.000.000 đ, Diff: +400.000 đ
    await expect(page.getByText("5.400.000 ₫").first()).toBeVisible();
    await expect(page.locator("#draft-advance")).toHaveValue("5000000");
    await expect(page.getByText("400.000 ₫", { exact: true })).toBeVisible();
    await expect(page.getByText("(Công ty chi thêm)", { exact: true })).toBeVisible();

    // 6. Select activity matching TC02
    const activityChoice = page.getByRole("radio", { name: /activity:tc02/ });
    await activityChoice.check();
    await expect(activityChoice).toBeChecked();

    // 7. Click "Xác nhận và nộp hồ sơ"
    const submitBtn = page.getByRole("button", { name: "Xác nhận và nộp hồ sơ" });
    await expect(submitBtn).toBeEnabled();
    await submitBtn.click();

    // 8. Wait for background processing (Evidence Job + Admission + Reconciler)
    // The UI displays polling and then transitions to Dossier view
    await expect(page.getByRole("heading", { name: "Hồ sơ đối soát" })).toBeVisible({ timeout: 180_000 });

    // If case has an open question/issue (e.g. confirming payer), answer it with employee actor ID
    const answerInputTC02 = page.locator("[id^='answer-issue:']");
    if (await answerInputTC02.isVisible({ timeout: 5000 }).catch(() => false)) {
      await answerInputTC02.fill("5400000");
      const reasonInput = page.locator("input[id^='reason-issue:']");
      if (await reasonInput.isVisible()) {
        await reasonInput.fill("Nhân viên Nguyễn Minh An xác nhận trực tiếp thanh toán");
      }
      await page.getByRole("button", { name: "Gửi giải trình" }).click();
      await expect(answerInputTC02).not.toBeVisible({ timeout: 15_000 });
    }

    // 9. Multi-tier assertions on Dossier
    // Financial numbers: T = 5.400.000 đ, E = 5.400.000 đ, A = 5.000.000 đ, S = +400.000 đ
    const moneyT = page.getByTestId("money-Tổng chi công việc");
    await expect(moneyT).toContainText("5.400.000 ₫");

    const moneyE = page.getByTestId("money-Chi phí đủ điều kiện");
    await expect(moneyE).toContainText("5.400.000 ₫");

    const moneyA = page.getByTestId("money-Ứng thực nhận");
    await expect(moneyA).toContainText("5.000.000 ₫");

    const moneyS = page.getByTestId("money-Chênh lệch (S)");
    await expect(moneyS).toContainText("400.000 ₫");

    // Check payment basis
    const paymentBasis = page.getByTestId("payment-basis");
    await expect(paymentBasis).toBeVisible();

    // Switch to Accountant role to view instruction & execution
    await page.locator("#persona-select").selectOption("accountant");
    const tc02Row = page.getByRole("row").filter({
      hasText: "Mua thiết bị văn phòng phục vụ hoạt động công ty",
    });
    await expect(tc02Row).toBeVisible();
    await tc02Row.click();
    await expect(page.getByRole("heading", { name: "Hồ sơ đối soát" })).toBeVisible();

    // Verify Instruction: direction PAY (CHI), amount 400.000 đ
    const approvalSection = page.locator("section[aria-labelledby='approval-title']");
    await expect(approvalSection).toBeVisible();
    await expect(approvalSection).toContainText("CHI");
    await expect(approvalSection).toContainText("400.000 ₫");

    // 10. Verify DocumentViewer on left pane
    const docViewer = page.getByLabel("Trình xem chứng từ gốc");
    await expect(docViewer).toBeVisible();

    // 11. Page reload persistence check
    await page.reload();
    await expect(page.getByRole("heading", { name: "Hồ sơ đối soát" })).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId("money-Tổng chi công việc")).toContainText("5.400.000 ₫");
    await expect(page.getByTestId("money-Chênh lệch (S)")).toContainText("400.000 ₫");
  });

  test("TC03 — Chi phí lưu trú công tác: Cân bằng nghĩa vụ tiền (BALANCED / SETTLED, S = 0)", async ({ page }) => {
    // 1. Load application
    await page.goto("/");
    await expect(page.getByText("InvoiceReferee")).toBeVisible();

    // 2. From Dashboard, click "+ Tạo hồ sơ mới"
    const createBtn = page.getByRole("button", { name: "+ Tạo hồ sơ mới" });
    await expect(createBtn).toBeVisible({ timeout: 15_000 });
    await createBtn.click();

    // 3. Upload real PDF sources for TC03
    const reportPdf = path.join(TC03_DIR, "report_hoan_ung.pdf");
    const invoicePdf = path.join(TC03_DIR, "hoa_don_dien_tu.pdf");

    const fileInput = page.getByLabel("Chứng từ (PDF/PNG/JPEG)");
    await fileInput.setInputFiles([reportPdf, invoicePdf]);
    await expect(page.getByText("Tệp đã chọn sẵn sàng trích xuất (2):")).toBeVisible();

    // 4. Click "Đọc chứng từ" and wait for LIVE OCR + LLM parsing
    const readBtn = page.getByRole("button", { name: "Đọc chứng từ" });
    await expect(readBtn).toBeEnabled();
    await readBtn.click();

    // 5. Review draft step
    await expect(page.getByText("Kiểm tra bản nháp hồ sơ")).toBeVisible({ timeout: 180_000 });

    // Assert visual ground truth values extracted from TC03 PDFs:
    // Incurred: 4.320.000 đ, Advance: 4.320.000 đ, Diff: 0 ₫
    await expect(page.getByText("4.320.000 ₫").first()).toBeVisible();
    await expect(page.locator("#draft-advance")).toHaveValue("4320000");
    await expect(page.getByText("0 ₫", { exact: true }).first()).toBeVisible();
    await expect(page.getByText("(Cân bằng kê khai)", { exact: true })).toBeVisible();

    // 6. Select activity matching TC03
    const activityChoice = page.getByRole("radio", { name: /activity:tc03/ });
    await activityChoice.check();
    await expect(activityChoice).toBeChecked();

    // 7. Click "Xác nhận và nộp hồ sơ"
    const submitBtn = page.getByRole("button", { name: "Xác nhận và nộp hồ sơ" });
    await expect(submitBtn).toBeEnabled();
    await submitBtn.click();

    // 8. Wait for background processing (Evidence Job + Admission + Reconciler)
    await expect(page.getByRole("heading", { name: "Hồ sơ đối soát" })).toBeVisible({ timeout: 180_000 });

    // If case has an open question/issue (e.g. confirming payer), answer it with employee actor ID
    const answerInputTC03 = page.locator("[id^='answer-issue:']");
    if (await answerInputTC03.isVisible({ timeout: 5000 }).catch(() => false)) {
      await answerInputTC03.fill("4320000");
      const reasonInput = page.locator("input[id^='reason-issue:']");
      if (await reasonInput.isVisible()) {
        await reasonInput.fill("Nhân viên Nguyễn Minh An xác nhận trực tiếp thanh toán");
      }
      await page.getByRole("button", { name: "Gửi giải trình" }).click();
      await expect(answerInputTC03).not.toBeVisible({ timeout: 15_000 });
    }

    // 9. Multi-tier assertions on Dossier
    // Financial numbers: T = 4.320.000 đ, E = 4.320.000 đ, A = 4.320.000 đ, S = 0 ₫
    const moneyT = page.getByTestId("money-Tổng chi công việc");
    await expect(moneyT).toContainText("4.320.000 ₫");

    const moneyE = page.getByTestId("money-Chi phí đủ điều kiện");
    await expect(moneyE).toContainText("4.320.000 ₫");

    const moneyA = page.getByTestId("money-Ứng thực nhận");
    await expect(moneyA).toContainText("4.320.000 ₫");

    const moneyS = page.getByTestId("money-Chênh lệch (S)");
    await expect(moneyS).toContainText("0 ₫");

    // Case state should be SETTLED / Đã quyết toán
    await expect(page.getByText("Đã quyết toán")).toBeVisible();

    // Assert NO zero-amount instructions issued
    await page.locator("#persona-select").selectOption("accountant");
    const tc03Row = page.getByRole("row").filter({
      hasText: "Chi phí lưu trú trong chuyến công tác",
    });
    await expect(tc03Row).toBeVisible();
    await tc03Row.click();
    await expect(page.getByRole("heading", { name: "Hồ sơ đối soát" })).toBeVisible();
    const approvalSection = page.locator("section[aria-labelledby='approval-title']");
    await expect(approvalSection).toContainText("Chưa có lệnh chi hoặc thu cần thực hiện");

    // 10. Verify DocumentViewer on left pane
    const docViewer = page.getByLabel("Trình xem chứng từ gốc");
    await expect(docViewer).toBeVisible();

    // 11. Page reload persistence check
    await page.reload();
    await expect(page.getByRole("heading", { name: "Hồ sơ đối soát" })).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId("money-Tổng chi công việc")).toContainText("4.320.000 ₫");
    await expect(page.getByTestId("money-Chênh lệch (S)")).toContainText("0 ₫");
  });
});
