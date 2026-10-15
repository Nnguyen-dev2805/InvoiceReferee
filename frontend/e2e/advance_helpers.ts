import type { Page } from "@playwright/test";

/** Provide a source-review reason only for a visible exception, never routine receipt. */
export async function explainAdvanceIfNeeded(page: Page, reason: string) {
  const manualLink = page.getByLabel("Tôi xác nhận chứng từ ứng thuộc công việc trong hồ sơ này");
  if (await manualLink.count()) {
    await manualLink.check();
    await page.getByLabel("Căn cứ đối chiếu với công việc").fill(reason);
  } else {
    const correction = page.getByLabel("Căn cứ bổ sung thông tin", { exact: true });
    if (await correction.count()) await correction.fill(reason);
  }
}
