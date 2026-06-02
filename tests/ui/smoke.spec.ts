import { test, expect } from "@playwright/test";

test("homepage loads project dashboard", async ({ page }) => {
  await page.goto("/index.html");
  await expect(page.getByRole("heading", { name: "翻译工作台" })).toBeVisible();
  await expect(page.getByText("apiMode=dry-run")).toBeVisible();
  await expect(page.getByRole("link", { name: "进入对照审核 →" })).toBeVisible();
});

test("review page shows auto-approve controls", async ({ page }) => {
  await page.goto("/review.html");
  await expect(
    page.getByRole("heading", { name: "Side-by-side Translation Review" })
  ).toBeVisible();
  await expect(page.getByText(/AUTO_APPROVE.*true/)).toBeVisible();
  await expect(page.getByRole("button", { name: "触发自动通过" }).first()).toBeVisible();
});

test("index page has no console errors", async ({ page }) => {
  const errors: string[] = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") {
      errors.push(msg.text());
    }
  });
  await page.goto("/index.html");
  await page.waitForLoadState("networkidle");
  expect(errors).toEqual([]);
});
