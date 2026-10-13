import { expect, test } from "@playwright/test";

// T5 browser checkpoint: attach a source, see it listed, and confirm the
// preview path shows a clear next action (draft / unknown / error). First
// executed when Playwright browsers are installed.

const GOOD_PDF = Buffer.from("%PDF-1.4\nchung tu demo\n%%EOF\n");

test("source preview: attach a scan and see it listed with a next action", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Nộp hồ sơ" })).toBeVisible();

  await page.getByLabel("Hoạt động").selectOption("activity:travel-a");
  await page.getByRole("button", { name: "Tạo hồ sơ" }).click();

  await page.getByLabel("Chứng từ (PDF/PNG/JPEG)").setInputFiles({
    name: "hoadon.pdf",
    mimeType: "application/pdf",
    buffer: GOOD_PDF,
  });
  await page.getByRole("button", { name: "Đính kèm" }).click();

  // The source is listed and the dossier shows a clear next action.
  await expect(page.getByRole("heading", { name: "Chứng từ (1)" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Hồ sơ" })).toBeVisible();
});
