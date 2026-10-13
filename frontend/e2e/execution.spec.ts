import { expect, test } from "@playwright/test";

// T7 browser checkpoint: after a routine submit produces an instruction, the
// accountant records actual money and the projection/remaining update. Known
// received money is recorded even without an extra grant.

const GOOD_PDF = Buffer.from("%PDF-1.4\nchung tu demo\n%%EOF\n");

test("execution: record actual money updates the projection", async ({ page }) => {
  await page.goto("/");

  // The employee submits (intake is the employee workspace, plan R6 UX01).
  await page.locator("#activity-select").selectOption("activity:travel-g");
  await page.getByRole("button", { name: "Tạo hồ sơ" }).click();
  await page.getByLabel("Chứng từ (PDF/PNG/JPEG)").setInputFiles({
    name: "hoadon.pdf",
    mimeType: "application/pdf",
    buffer: GOOD_PDF,
  });
  await page.getByRole("button", { name: "Đính kèm" }).click();
  await page.getByRole("button", { name: "Nộp hồ sơ" }).click();

  // Switch to the accountant persona, who sees the order and records money.
  await page.getByLabel("Vai trò (demo)").selectOption("accountant");

  // An instruction exists; record a receipt of 2.000.000 with a responsible
  // completion confirmation (a bare amount is not verified money).
  await expect(page.getByTestId("instruction-PAY")).toBeVisible();
  await page.getByLabel("Số tiền đã nhận").fill("2000000");
  await page
    .getByLabel("Xác nhận đã chuyển (bắt buộc để tính là đã thực hiện)")
    .fill("Đã chuyển khoản, đối chiếu sao kê");
  await page.getByRole("button", { name: "Ghi nhận" }).click();

  await expect(page.getByText(/Đã ghi nhận tiền thực tế/)).toBeVisible();
  await expect(page.getByTestId("actual-P")).toContainText("2.000.000");
});
