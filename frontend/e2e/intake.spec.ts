import { expect, test } from "@playwright/test";

// T2 browser checkpoint as a spec (first executed at T6, when Playwright
// browsers are installed): select/create twice, attach and list a source.

const GOOD_PDF = Buffer.from("%PDF-1.4\nchung tu demo\n%%EOF\n");

test("intake: create twice reuses one root, attach and list a source", async ({
  page,
}) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Nộp hồ sơ" }),
  ).toBeVisible();

  await page.getByLabel("Hoạt động").selectOption("activity:travel-a");
  await page.getByRole("button", { name: "Tạo hồ sơ" }).click();

  const caseCode = page.getByTestId("case-code");
  await expect(caseCode).toContainText("case:");
  const firstRoot = await caseCode.textContent();

  await page.getByRole("button", { name: "Tạo hồ sơ" }).click();
  await expect(caseCode).toHaveText(firstRoot ?? "");

  await page.getByLabel("Chứng từ (PDF/PNG/JPEG)").setInputFiles({
    name: "hoadon.pdf",
    mimeType: "application/pdf",
    buffer: GOOD_PDF,
  });
  await page.getByRole("button", { name: "Đính kèm" }).click();

  await expect(page.getByText(/Đã đính kèm 1 chứng từ/)).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Chứng từ (1)" }),
  ).toBeVisible();

  // Keyboard path: Tab reaches the primary action and it stays operable.
  await page.getByLabel("Chứng từ (PDF/PNG/JPEG)").focus();
  await page.keyboard.press("Tab");
  await expect(page.getByRole("button", { name: "Đính kèm" })).toBeFocused();
});
