import { expect, test } from "@playwright/test";

const PDF = Buffer.from("%PDF-1.4\nchung tu demo\n%%EOF\n");

test("new dossier draft does not invent a budget question", async ({ page }) => {
  // The isolated server runs STUB without an evidence reader. This UI check
  // stops at its honest reader-configuration error after observing DRAFT.
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Hồ sơ quyết toán của tôi" })).toBeVisible();

  await page.getByRole("button", { name: "+ Tạo hồ sơ mới" }).click();
  await page.getByLabel("Chứng từ (PDF/PNG/JPEG)").setInputFiles({
    name: "chung-tu.pdf",
    mimeType: "application/pdf",
    buffer: PDF,
  });

  const createdResponse = page.waitForResponse(
    (response) => response.request().method() === "POST" && new URL(response.url()).pathname === "/api/cases",
  );
  await page.getByRole("button", { name: "Đọc chứng từ" }).click();
  const created = await (await createdResponse).json();
  const caseView = created.case_view;

  expect(caseView.state).toBe("DRAFT");
  expect(caseView.activity).toMatch(/^activity:proposed:/);
  expect(caseView.issues).not.toContainEqual(
    expect.objectContaining({ field_or_rule: "budget:B" }),
  );
  expect(caseView.issues.filter((issue: { kind: string }) => issue.kind === "AUTHORITY")).toEqual([]);

  const response = await page.request.get(`/api/cases/${encodeURIComponent(caseView.id)}`);
  expect(response.ok()).toBeTruthy();
  const reloaded = await response.json();
  expect(reloaded.state).toBe("DRAFT");
  expect(reloaded.issues).not.toContainEqual(
    expect.objectContaining({ field_or_rule: "budget:B" }),
  );
  await expect(page.getByRole("alert")).toContainText(
    "Chưa cấu hình đọc chứng từ (LIVE)",
  );
  await expect(page.getByText(/Ngân sách hoạt động \(B\)/)).toHaveCount(0);
});
