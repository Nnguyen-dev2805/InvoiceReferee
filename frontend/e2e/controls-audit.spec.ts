import { expect, test } from "@playwright/test";

// T8 browser checkpoint: Stop a root, see the audit trail record the actor and
// action, then Resume. The audit shows who did what, with before/after state.

const GOOD_PDF = Buffer.from("%PDF-1.4\nchung tu demo\n%%EOF\n");

test("controls: stop and resume are audited", async ({ page }) => {
  await page.goto("/");

  // The employee submits (intake workspace).
  await page.locator("#activity-select").selectOption("activity:travel-e");
  await page.getByRole("button", { name: "Tạo hồ sơ" }).click();
  await page.getByLabel("Chứng từ (PDF/PNG/JPEG)").setInputFiles({
    name: "hoadon.pdf",
    mimeType: "application/pdf",
    buffer: GOOD_PDF,
  });
  await page.getByRole("button", { name: "Đính kèm" }).click();
  await page.getByRole("button", { name: "Nộp hồ sơ" }).click();

  // The accountant controls the root (controls workspace).
  await page.getByLabel("Vai trò (demo)").selectOption("accountant");
  await page.getByRole("button", { name: "Dừng hồ sơ" }).click();
  // The case state reflects the Stop and the audit list records it.
  await expect(page.getByText(/Đã dừng/)).toBeVisible();
  await expect(
    page.getByTestId("controls-audit").getByText(/· STOP$/),
  ).toBeVisible();

  await page.getByRole("button", { name: "Tiếp tục" }).click();
  await expect(
    page.getByTestId("controls-audit").getByText(/· RESUME$/),
  ).toBeVisible();
});
