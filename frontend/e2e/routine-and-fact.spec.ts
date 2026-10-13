import { expect, test } from "@playwright/test";

// T6 browser checkpoint: a routine root becomes one actionable instruction with
// no human recheck; a root missing a payer becomes a FACT card owned by the
// right person. The STUB server seeds demo transcriptions for the activities.

const GOOD_PDF = Buffer.from("%PDF-1.4\nchung tu demo\n%%EOF\n");

async function openAndSubmit(page, activityId: string) {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Nộp hồ sơ" })).toBeVisible();
  await page.locator("#activity-select").selectOption(activityId);
  await page.getByRole("button", { name: "Tạo hồ sơ" }).click();
  await page.getByLabel("Chứng từ (PDF/PNG/JPEG)").setInputFiles({
    name: "hoadon.pdf",
    mimeType: "application/pdf",
    buffer: GOOD_PDF,
  });
  await page.getByRole("button", { name: "Đính kèm" }).click();
  await expect(page.getByRole("heading", { name: "Chứng từ (1)" })).toBeVisible();
  await page.getByRole("button", { name: "Nộp hồ sơ" }).click();
}

test("routine: one actionable payment, no human recheck", async ({ page }) => {
  await openAndSubmit(page, "activity:travel-c");

  // The accountant sees exactly one instruction of 3.000.000.
  await expect(
    page.getByRole("heading", { name: /Yêu cầu cần thực hiện \(1\)/ }),
  ).toBeVisible();
  await expect(page.getByTestId("instruction-PAY")).toContainText("3.000.000");
  // No question card is required for a routine root (no human recheck).
  await expect(page.getByTestId("question-FACT")).toHaveCount(0);
  await expect(page.getByTestId("question-POLICY")).toHaveCount(0);
  await expect(page.getByTestId("question-AUTHORITY")).toHaveCount(0);
});

test("fact: missing payer becomes an answerable card, no instruction", async ({
  page,
}) => {
  await openAndSubmit(page, "activity:travel-d");

  await expect(
    page.getByRole("heading", { name: /Việc cần xử lý \(1\)/ }),
  ).toBeVisible();
  await expect(page.getByTestId("question-FACT")).toBeVisible();
  // No actionable instruction is issued while a material fact is unresolved.
  await expect(page.getByTestId("instruction-PAY")).toHaveCount(0);
});
