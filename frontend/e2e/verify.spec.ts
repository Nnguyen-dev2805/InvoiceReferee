import { expect, test } from "@playwright/test";

// T9 browser checkpoint: Verify runs the development suite through the same
// workflow and shows mode/total/expected-vs-actual/dangerous-miss from the DB.

test("verify: run the development suite and show the report", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Kiểm chứng (Verify)" })).toBeVisible();
  await page.getByRole("button", { name: "Chạy kiểm chứng" }).click();
  const report = page.getByTestId("verify-report");
  await expect(report).toBeVisible();
  await expect(report).toContainText("development");
  await expect(report).toContainText("Dangerous miss");
});
