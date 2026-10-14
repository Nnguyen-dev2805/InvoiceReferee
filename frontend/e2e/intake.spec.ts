import { expect, test } from "@playwright/test";

// T2 browser checkpoint: select/create twice (same activity reuses one root),
// then one primary action uploads the selected file and submits.

const GOOD_PDF = Buffer.from("%PDF-1.4\nchung tu demo\n%%EOF\n");

test("intake: create twice reuses one root, then submit uploads the source", async ({
  page,
}) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Nộp hồ sơ" }),
  ).toBeVisible();

  await page.locator("#activity-select").selectOption("activity:travel-a");
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

  // One primary action: the submit button uploads the pending file and submits.
  const submitButton = page.getByRole("button", { name: "Nộp hồ sơ" });
  await expect(submitButton).toBeEnabled();
  await submitButton.click();

  await expect(page.getByText(/Đã nộp hồ sơ/)).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Chứng từ (1)" }),
  ).toBeVisible();
});
