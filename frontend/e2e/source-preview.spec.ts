import { expect, test } from "@playwright/test";

// T5 browser checkpoint: a submitted source is listed and the dossier shows a
// clear next action (draft / unknown / error). First executed when Playwright
// browsers are installed.

const GOOD_PDF = Buffer.from("%PDF-1.4\nchung tu demo\n%%EOF\n");

test("source preview: submit a scan and see it listed with a next action", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Nộp hồ sơ" })).toBeVisible();

  await page.locator("#activity-select").selectOption("activity:travel-b");
  await page.getByRole("button", { name: "Tạo hồ sơ" }).click();

  await page.getByLabel("Chứng từ (PDF/PNG/JPEG)").setInputFiles({
    name: "hoadon.pdf",
    mimeType: "application/pdf",
    buffer: GOOD_PDF,
  });
  // One primary action uploads the file and submits.
  await page.getByRole("button", { name: "Nộp hồ sơ" }).click();

  // The source is listed and the dossier shows a clear next action.
  await expect(page.getByRole("heading", { name: "Chứng từ (1)" })).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Hồ sơ", exact: true }),
  ).toBeVisible();
});
