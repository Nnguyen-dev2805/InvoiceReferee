import { expect, test } from "@playwright/test";

// T10 public smoke: a clean browser can find the main action in under a minute
// and run a routine flow. The server serves the built static UI.

const GOOD_PDF = Buffer.from("%PDF-1.4\nchung tu demo\n%%EOF\n");

test("public smoke: main flow is discoverable and runs", async ({ page }) => {
  const started = Date.now();
  await page.goto("/");
  // The primary action is visible immediately (no signup, no persona gate).
  await expect(page.getByRole("heading", { name: "Nộp hồ sơ" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Tạo hồ sơ" })).toBeVisible();
  expect(Date.now() - started).toBeLessThan(60_000);

  await page.locator("#activity-select").selectOption("activity:travel-c");
  await page.getByRole("button", { name: "Tạo hồ sơ" }).click();
  await page.getByLabel("Chứng từ (PDF/PNG/JPEG)").setInputFiles({
    name: "hoadon.pdf",
    mimeType: "application/pdf",
    buffer: GOOD_PDF,
  });
  await page.getByRole("button", { name: "Nộp hồ sơ" }).click();
  // The accountant sees the actionable order (role workspaces).
  await page.getByLabel("Vai trò (demo)").selectOption("accountant");
  await expect(page.getByTestId("instruction-PAY")).toBeVisible();
});

test("public smoke: health endpoint is reachable", async ({ request }) => {
  const response = await request.get("/api/health");
  expect(response.status()).toBe(200);
  expect((await response.json()).status).toBe("ok");
});
