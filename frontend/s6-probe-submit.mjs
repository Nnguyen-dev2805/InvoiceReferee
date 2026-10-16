// Probe: capture the exact submit request/response for a digital case.
import { chromium } from "playwright";
import { join } from "node:path";
import { flowDir, fillDigitalLines } from "./s6-helpers.mjs";

const BASE = process.env.BROWSER_BASE_URL || "http://127.0.0.1:65133";
const DIR = flowDir("probe-submit");

const browser = await chromium.launch();
const page = await browser.newPage();
page.on("response", async (resp) => {
  if (resp.url().includes("/submit")) {
    console.log("SUBMIT", resp.status());
    try {
      console.log((await resp.text()).slice(0, 400));
    } catch {}
  }
});
await page.goto(BASE, { waitUntil: "networkidle" });
await page.getByRole("button", { name: "+ Tạo hồ sơ mới" }).click({ timeout: 15000 });
await page.getByText("Nhân viên tự chi").click({ timeout: 10000 });
await page.getByText("Lập trên web").click({ timeout: 10000 });
await fillDigitalLines(page, true);
await page.getByRole("button", { name: "Đọc & lập bản nháp" }).click();
await page.getByRole("button", { name: "Xác nhận và nộp hồ sơ" }).waitFor({ timeout: 120000 });
await page.screenshot({ path: join(DIR, "draft.png") });
await page.getByRole("button", { name: "Xác nhận và nộp hồ sơ" }).click();
await page.waitForTimeout(8000);
const banner = await page.getByRole("alert").count();
console.log("alerts:", banner);
if (banner > 0) console.log(await page.getByRole("alert").first().innerText());
await page.screenshot({ path: join(DIR, "after.png"), fullPage: true });
await browser.close();
