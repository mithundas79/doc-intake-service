import { test, expect } from "@playwright/test";
import path from "node:path";
import fs from "node:fs/promises";

const sample = (name: string) => path.resolve("../samples", name);

test("real upload, correction, explicit approval, persisted list and safe exports", async ({ page }, testInfo) => {
  await page.goto("/");
  await page.getByLabel("Upload document").setInputFiles(sample("incorrect-total.txt"));
  await expect(page.getByRole("heading", { name: "incorrect-total.txt", exact: true })).toBeVisible();
  await expect(page.getByTestId("document-state")).toHaveText("review", { timeout: 30000 });
  await expect(page.getByLabel("Original text")).toContainText("Total Due 349.84");
  await expect(page.getByRole("button", { name: "Approve document", exact: true })).toBeDisabled();
  await page.getByLabel("total", { exact: true }).fill("329.84");
  await page.getByLabel("Review note").fill("Checked arithmetic and corrected the stated total");
  await page.getByRole("button", { name: "Save corrections & revalidate" }).click();
  await expect(page.getByTestId("document-state")).toHaveText("ready");
  await page.getByRole("button", { name: "Approve document", exact: true }).click();
  await expect(page.getByTestId("document-state")).toHaveText("approved");
  await page.screenshot({ path: testInfo.outputPath("approved-document.png"), fullPage: true });
  await page.reload();
  await page.getByRole("button", { name: /incorrect-total.txt/ }).click();
  await expect(page.getByTestId("document-state")).toHaveText("approved");
  await expect(page.getByLabel("total", { exact: true })).toHaveValue("329.84");
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export approved JSON" }).click();
  const artifact = await download;
  expect(artifact.suggestedFilename()).toBe("approved-records.json");
  const json = JSON.parse(await fs.readFile((await artifact.path())!, "utf8"));
  expect(json).toHaveLength(1); expect(json[0].total).toBe("329.84");
  const csvDownload = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export approved CSV" }).click();
  const csv = await csvDownload;
  expect(await fs.readFile((await csv.path())!, "utf8")).toContain("329.84");
  await page.getByText(/Review history/).click();
  await expect(page.locator(".history")).toContainText("approve");
  await page.getByLabel("Upload document").setInputFiles(sample("incorrect-total.txt"));
  await expect(page.getByRole("heading", { name: "incorrect-total.txt", exact: true })).toBeVisible();
  await expect(page.getByTestId("document-state")).toHaveText("review");
  await expect(page.locator(".checks")).toContainText("Check: Not a duplicate");
  await page.getByLabel("Review note").fill("Duplicate original, do not export");
  await page.getByRole("button", { name: "Reject document", exact: true }).click();
  await expect(page.getByTestId("document-state")).toHaveText("rejected");
});

test("text PDF, actual OCR scan and manual-only contract are reviewable", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Upload document").setInputFiles(sample("two-page-invoice.pdf"));
  await expect(page.getByRole("heading", { name: "two-page-invoice.pdf", exact: true })).toBeVisible();
  await expect(page.getByTestId("document-state")).toHaveText("ready", { timeout: 30000 });
  await expect(page.locator('iframe[title="Original document"]')).toBeVisible();
  await expect(page.getByLabel("total", { exact: true })).toHaveValue("677.04");
  await page.getByLabel("Upload document").setInputFiles(sample("scanned-invoice.png"));
  await expect(page.getByRole("heading", { name: "scanned-invoice.png", exact: true })).toBeVisible();
  await expect(page.getByTestId("document-state")).toHaveText("review", { timeout: 30000 });
  await expect(page.getByAltText("Original document")).toBeVisible();
  await expect(page.getByLabel("total", { exact: true })).toHaveValue("677.04");
  await expect(page.getByText(/OCR used/)).toBeVisible();
  await page.getByLabel("Upload document").setInputFiles(sample("manual-contract.txt"));
  await expect(page.getByRole("heading", { name: "manual-contract.txt", exact: true })).toBeVisible();
  await expect(page.getByTestId("document-state")).toHaveText("review", { timeout: 30000 });
  await page.getByLabel("Document type").selectOption("contract");
  await page.getByLabel("I checked the document type against the original").check();
  await page.getByLabel("Review note").fill("Read all terms and confirmed counterparty and date");
  await page.getByRole("button", { name: "Save corrections & revalidate" }).click();
  await expect(page.getByTestId("document-state")).toHaveText("ready");
  await page.getByRole("button", { name: "Approve document", exact: true }).click();
  await expect(page.getByTestId("document-state")).toHaveText("approved");
});


test("late real backend poll cannot overwrite a different selected document", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Upload document").setInputFiles(sample("valid-invoice.txt"));
  await expect(page.getByRole("heading", { name: "valid-invoice.txt", exact: true })).toBeVisible();
  await expect(page.getByTestId("document-state")).not.toHaveText(/queued|processing/, { timeout: 30000 });
  let release!: () => void;
  let observed!: () => void;
  const held = new Promise<void>(resolve => { release = resolve; });
  const seen = new Promise<void>(resolve => { observed = resolve; });
  let intercepted = false;
  await page.route(/\/api\/documents\/[a-f0-9]{32}$/, async route => {
    // Forward to the real backend, then delay one actual response to model a slow connection.
    const response = await route.fetch();
    const value = await response.json();
    if (!intercepted && value.name === "scanned-invoice.png") {
      intercepted = true; observed(); await held;
    }
    await route.fulfill({ response });
  });
  await page.getByLabel("Upload document").setInputFiles(sample("scanned-invoice.png"));
  await expect(page.getByRole("heading", { name: "scanned-invoice.png", exact: true })).toBeVisible();
  await seen;
  await page.getByRole("button", { name: /valid-invoice.txt/ }).click();
  await expect(page.getByRole("heading", { name: "valid-invoice.txt", exact: true })).toBeVisible();
  release();
  await page.waitForTimeout(700);
  await expect(page.getByRole("heading", { name: "valid-invoice.txt", exact: true })).toBeVisible();
  await expect(page.getByLabel("total", { exact: true })).toHaveValue("677.04");
});
