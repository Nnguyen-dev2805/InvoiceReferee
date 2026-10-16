// S6 browser flows A-F (RECORDED_REPLAY fixture transport, 0 providers).
// Usage: BASE_URL=http://127.0.0.1:<port> node s6-flow-<x>.mjs
// Each script writes screenshots + summary.json into .runtime/s6-browser/<flow>/.
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
export const RUNTIME = join(ROOT, ".runtime", "s6-browser");
export const PDFS = join(RUNTIME, "pdfs");

export function flowDir(name) {
  const dir = join(RUNTIME, name);
  mkdirSync(dir, { recursive: true });
  return dir;
}

export function newSummary() {
  return { steps: [], ok: true };
}

export async function step(summary, name, fn) {
  try {
    const value = await fn();
    summary.steps.push({ name, ok: true, value: value ?? true });
    return value;
  } catch (error) {
    summary.steps.push({ name, ok: false, error: String(error).slice(0, 600) });
    summary.ok = false;
    throw error;
  }
}

export function saveSummary(dir, summary) {
  summary.ok = !summary.fatal && summary.steps.length > 0 && summary.steps.every((s) => s.ok);
  writeFileSync(join(dir, "summary.json"), JSON.stringify(summary, null, 2));
  console.log(JSON.stringify(summary, null, 2));
  return summary.ok;
}

export async function switchPersona(page, persona, base) {
  // Top-bar persona selector (label varies); fall back to the API.
  const select = page.locator("#persona-select");
  if ((await select.count()) > 0) {
    await select.selectOption(persona);
    await page.waitForTimeout(800);
    return;
  }
  await page.evaluate(async (p) => {
    const r = await fetch("/api/demo/persona", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Command-Id": `cmd:${Date.now()}` },
      body: JSON.stringify({ persona: p }),
    });
    if (!r.ok) throw new Error(`persona switch failed: ${r.status}`);
  }, persona);
  await page.reload();
}

export async function openLatestCase(page, base) {
  // Dashboard lists cases; open the first row.
  await page.goto(`${base}/`, { waitUntil: "networkidle" });
  const row = page.locator("tbody tr").first();
  await row.click({ timeout: 15000 });
}

export async function openIssuesTab(page) {
  await page.getByRole("tab", { name: /Vấn đề cần xử lý/ }).click({ timeout: 15000 });
}

export async function fillDigitalLines(page, consistent, selfExpense = true, amounts = null) {
  const suffix = amounts ? "self" : consistent ? "consistent" : "mismatch";
  const parts = amounts ? String(amounts[0]) : "2700000";
  const labor = amounts ? String(amounts[1]) : "1500000";
  await page.locator("#digital-purpose").fill("Sửa chữa máy in văn phòng");
  if (selfExpense) {
    await page.getByLabel("Lý do không nhận tạm ứng").fill("Tự chi, không nhận ứng");
  }
  // Line 1: parts, original invoice.
  await page.getByLabel("Nội dung khoản 1").fill("Mua linh kiện máy in");
  await page.getByLabel("Số tiền khoản 1").fill(parts);
  await page.getByLabel("Ngày chi khoản 1").fill("2026-10-08");
  await page.locator(`input[aria-label="Chứng từ khoản 1"]`).setInputFiles(join(PDFS, `invoice-${suffix}.pdf`));
  // Line 2: labor, alternative.
  await page.getByRole("button", { name: "+ Thêm khoản" }).click();
  await page.getByLabel("Nội dung khoản 2").fill("Nhân công sửa chữa");
  await page.getByLabel("Số tiền khoản 2").fill(labor);
  await page.getByLabel("Ngày chi khoản 2").fill("2026-10-09");
  await page.getByLabel("Tình trạng chứng từ khoản 2").selectOption("ALTERNATIVE");
  await page.getByLabel("Lý do thiếu chứng từ gốc khoản 2").fill("Nhà cung cấp không xuất hóa đơn");
  await page.locator(`input[aria-label="Chứng từ khoản 2"]`).setInputFiles([
    join(PDFS, `acceptance-${suffix}.pdf`),
    join(PDFS, `transfer-${suffix}.pdf`),
  ]);
}
