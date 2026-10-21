import { test, expect } from "@playwright/test";
import fs from "node:fs/promises";

test("built Pages preview: correct, revalidate, explicitly approve, export and reset", async ({ page }, testInfo) => {
  const errors: string[] = [], apiCalls: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  page.on("request", request => { if (new URL(request.url()).pathname.startsWith("/api")) apiCalls.push(request.url()); });
  const response = await page.goto("/doc-intake-service/");
  expect(response?.status()).toBe(200);
  await expect(page).toHaveTitle(/Guided sample preview/);
  await expect(page.getByRole("heading", { name: "Review before you approve." })).toBeVisible();
  await expect(page.locator(".boundary")).toContainText("no Python API, native OCR, live classifier or SQLite");
  await expect(page.locator("#document-state")).toHaveText("review");
  await expect(page.locator("#original-text")).toContainText("Total Due 349.84");
  await expect(page.getByRole("button", { name: "Approve sample", exact: true })).toBeDisabled();
  await page.screenshot({ path: testInfo.outputPath("guided-preview-start.png"), fullPage: true });

  // No approval has occurred: a real download must contain an empty array.
  let downloaded = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download approved JSON" }).click();
  let artifact = await downloaded;
  expect(JSON.parse(await fs.readFile((await artifact.path())!, "utf8"))).toEqual([]);

  await page.getByLabel("Total", { exact: true }).fill("329.84");
  await expect(page.getByRole("button", { name: "Approve sample", exact: true })).toBeDisabled();
  await page.getByRole("button", { name: "Save & revalidate", exact: true }).click();
  await expect(page.locator("#document-state")).toHaveText("ready");
  await expect(page.locator("#approved-count")).toHaveText("0");
  await page.getByRole("button", { name: "Approve sample", exact: true }).click();
  await expect(page.locator("#document-state")).toHaveText("approved");
  await expect(page.locator("#approved-count")).toHaveText("1");
  await expect(page.getByLabel("Total", { exact: true })).toBeDisabled();
  await expect(page.locator("#audit")).toContainText("349.84 -> 329.84");
  await expect(page.locator("#audit")).toContainText("Approved explicitly");

  downloaded = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download approved JSON" }).click();
  artifact = await downloaded;
  expect(artifact.suggestedFilename()).toBe("approved-sample-records.json");
  const records = JSON.parse(await fs.readFile((await artifact.path())!, "utf8"));
  expect(records).toHaveLength(1);
  expect(records[0]).toMatchObject({ id: "incorrect-total", total: "329.84", currency: "USD" });
  downloaded = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download approved CSV" }).click();
  artifact = await downloaded;
  expect(artifact.suggestedFilename()).toBe("approved-sample-records.csv");
  expect(await fs.readFile((await artifact.path())!, "utf8")).toContain('"329.84"');
  await page.screenshot({ path: testInfo.outputPath("guided-preview-approved.png"), fullPage: true });

  await page.getByRole("button", { name: "Reset all samples" }).click();
  await expect(page.locator("#document-state")).toHaveText("review");
  await expect(page.getByLabel("Total", { exact: true })).toHaveValue("349.84");
  await expect(page.locator("#approved-count")).toHaveText("0");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  expect(errors).toEqual([]);
  expect(apiCalls).toEqual([]);
});

test("manual review, rejection reason, reload reset and formula-safe CSV", async ({ page }, testInfo) => {
  await page.goto("/doc-intake-service/");
  await page.getByRole("button", { name: "Manual review sample", exact: true }).click();
  await expect(page.locator("#document-state")).toHaveText("review");
  await expect(page.locator("#original-text")).toContainText("SERVICE AGREEMENT");
  await page.getByRole("button", { name: "Save & revalidate", exact: true }).click();
  await expect(page.locator("#document-state")).toHaveText("review");
  await expect(page.getByRole("button", { name: "Approve sample", exact: true })).toBeDisabled();
  await page.getByLabel("I checked the document type against the original").check();
  await page.getByLabel("Review / rejection note").fill("Read the terms and verified the parties and date");
  await page.getByRole("button", { name: "Save & revalidate", exact: true }).click();
  await expect(page.locator("#document-state")).toHaveText("ready");
  await expect(page.locator(".validation")).not.toContainText("Subtotal + tax = total");
  await page.getByRole("button", { name: "Approve sample", exact: true }).click();
  await expect(page.locator("#document-state")).toHaveText("approved");
  await page.screenshot({ path: testInfo.outputPath("guided-preview-manual-approved.png"), fullPage: true });

  await page.getByRole("button", { name: "Valid invoice sample", exact: true }).click();
  await expect(page.locator("#document-state")).toHaveText("ready");
  await page.getByLabel("Total", { exact: true }).fill("999.00");
  await page.getByRole("button", { name: "Reject sample", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("rejection reason");
  await page.getByLabel("Review / rejection note").fill("Not needed for this sample run");
  await page.getByRole("button", { name: "Reject sample", exact: true }).click();
  await expect(page.locator("#document-state")).toHaveText("rejected");
  await expect(page.getByLabel("Total", { exact: true })).toHaveValue("677.04");
  await expect(page.locator(".decision-bar")).toContainText("Unsaved field/type edits were discarded");
  let downloaded = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download approved JSON" }).click();
  let artifact = await downloaded;
  const approved = JSON.parse(await fs.readFile((await artifact.path())!, "utf8"));
  expect(approved.map((record: { id: string }) => record.id)).toEqual(["manual-contract"]);

  await page.reload();
  await expect(page.locator("#approved-count")).toHaveText("0");
  await page.getByRole("button", { name: "Valid invoice sample", exact: true }).click();
  await page.getByLabel("Vendor / counterparty", { exact: true }).fill("=SAMPLE()");
  await page.getByRole("button", { name: "Save & revalidate", exact: true }).click();
  await page.getByRole("button", { name: "Approve sample", exact: true }).click();
  downloaded = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download approved CSV" }).click();
  artifact = await downloaded;
  expect(await fs.readFile((await artifact.path())!, "utf8")).toContain("'=SAMPLE()");
  await expect(page.getByRole("link", { name: "Install & test", exact: true })).toHaveAttribute("href", /blob\/main\/README\.md#install-the-complete-local-application$/);
  await expect(page.getByRole("link", { name: "Demo source", exact: true })).toHaveAttribute("href", /tree\/main\/demo$/);
});

test("keyboard focus survives save, final decision, reset and sample selection", async ({ page }) => {
  await page.goto("/doc-intake-service/");
  const total = page.getByLabel("Total", { exact: true });
  await total.focus();
  await total.fill("329.84");
  await total.press("Enter");
  await expect(page.locator("#document-state")).toHaveText("ready");
  await expect(total).toBeFocused();
  await page.getByRole("button", { name: "Approve sample", exact: true }).focus();
  await page.keyboard.press("Enter");
  await expect(page.locator("#document-state")).toHaveText("approved");
  await expect(page.locator("#document-state")).toBeFocused();
  const reset = page.getByRole("button", { name: "Reset all samples" });
  await reset.focus();
  await page.keyboard.press("Enter");
  await expect(page.locator("#document-state")).toHaveText("review");
  await expect(reset).toBeFocused();
  const manual = page.getByRole("button", { name: "Manual review sample", exact: true });
  await manual.focus();
  await page.keyboard.press("Enter");
  await expect(page.locator("#original-text")).toContainText("SERVICE AGREEMENT");
  await expect(manual).toBeFocused();
});
