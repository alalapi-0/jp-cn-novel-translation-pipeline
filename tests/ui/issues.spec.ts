import { test, expect } from "@playwright/test";

test("issues dashboard lists fixture report", async ({ page }) => {
  await page.goto("/issues.html");
  await expect(
    page.getByRole("heading", { name: "Issue Review Dashboard" })
  ).toBeVisible();
  await expect(page.getByText(/term_conflict/)).toBeVisible();
  const cards = page.locator(".issue-card");
  await expect(cards.getByText("LOCKED_TERM_VIOLATION", { exact: true }).first()).toBeVisible();
  await expect(cards.getByText("INCONSISTENT_TERM", { exact: true }).first()).toBeVisible();
  await expect(cards.getByText("SEGMENT_ALIGNMENT_ERROR", { exact: true }).first()).toBeVisible();
});

test("locked term issue has auto-fix disabled", async ({ page }) => {
  await page.goto("/issues.html");
  await expect(
    page.getByRole("button", { name: "自动修复（禁用）" }).first()
  ).toBeDisabled();
});

test("issue links to side-by-side review segment", async ({ page }) => {
  await page.goto("/issues.html");
  await page.getByRole("link", { name: "对照定位 →" }).first().click();
  await expect(page).toHaveURL(/review\.html.*segment=seg-/);
  await expect(page.locator("#seg-seg-001, [id='seg-seg-001']").first()).toBeVisible();
});

test("issues page has no console errors", async ({ page }) => {
  const errors: string[] = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") errors.push(msg.text());
  });
  await page.goto("/issues.html");
  await page.waitForLoadState("networkidle");
  expect(errors).toEqual([]);
});
