import { test, expect } from "@playwright/test";

const DEMO_JP_CN = "demo-jp-cn";

test("issues dashboard lists fixture report", async ({ page }) => {
  await page.goto(`/issues.html?project=${DEMO_JP_CN}`);
  await expect(page.getByRole("heading", { name: "质量 Issue 审核" })).toBeVisible();
  await expect(page.getByText(/term_conflict/)).toBeVisible();
  const cards = page.locator(".issue-card");
  await expect(cards.getByText("LOCKED_TERM_VIOLATION", { exact: true }).first()).toBeVisible();
  await expect(cards.getByText("INCONSISTENT_TERM", { exact: true }).first()).toBeVisible();
  await expect(cards.getByText("MISTRANSLATION", { exact: true }).first()).toBeVisible();
});

test("locked term issue has auto-fix disabled", async ({ page }) => {
  await page.goto(`/issues.html?project=${DEMO_JP_CN}`);
  await expect(
    page.getByRole("button", { name: "自动修复（禁用）" }).first()
  ).toBeDisabled();
});

test("issue links to side-by-side review segment", async ({ page }) => {
  await page.goto(`/issues.html?project=${DEMO_JP_CN}`);
  await page.getByRole("link", { name: "对照定位 →" }).first().click();
  await expect(page).toHaveURL(
    new RegExp(`review\\.html\\?project=${DEMO_JP_CN}.*segment=seg-`)
  );
  await expect(page.locator("#seg-seg-001, [id='seg-seg-001']").first()).toBeVisible();
});

test("issue link preserves project when active project differs", async ({ page }) => {
  await page.goto(`/issues.html?project=${DEMO_JP_CN}`);
  const href = await page.getByRole("link", { name: "对照定位 →" }).first().getAttribute("href");
  expect(href).toContain(`project=${DEMO_JP_CN}`);
  expect(href).toMatch(/segment=seg-/);
});

test("issues page has no console errors", async ({ page }) => {
  const errors: string[] = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") errors.push(msg.text());
  });
  await page.goto(`/issues.html?project=${DEMO_JP_CN}`);
  await page.waitForLoadState("networkidle");
  expect(errors).toEqual([]);
});
