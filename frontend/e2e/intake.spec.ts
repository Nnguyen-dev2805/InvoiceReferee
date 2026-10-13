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

  // Keyboard path: with a file selected the primary action is enabled and can
  // receive keyboard focus. (After attaching, the button is disabled by design,
  // so this check belongs here, not after the click.)
  const attachButton = page.getByRole("button", { name: "Đính kèm" });
  await expect(attachButton).toBeEnabled();
  await attachButton.focus();
  await expect(attachButton).toBeFocused();

  await page.getByRole("button", { name: "Đính kèm" }).click();

  await expect(page.getByText(/Đã đính kèm 1 chứng từ/)).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Chứng từ (1)" }),
  ).toBeVisible();
});
