import { test, expect } from "@playwright/test";

const MISSING_PAGES = [
  { name: "Glossary Editor", path: "/glossary.html" },
  { name: "Character Profile Editor", path: "/character.html" },
  { name: "Polish Diff", path: "/polish-diff.html" },
];

test("homepage loads project dashboard", async ({ page }) => {
  await page.goto("/index.html");
  await expect(page.getByRole("heading", { name: "翻译工作台" })).toBeVisible();
  await expect(page.locator("#api-mode-status")).toContainText(/missing_api_key|dry_run|real_api/);
  await expect(page.locator("#api-key-status")).toContainText(/missing_api_key|已配置/);
  await expect(page.getByRole("link", { name: "进入对照审核 →" }).first()).toBeVisible();
});

test("project home shows chapter manager summary", async ({ page }) => {
  await page.goto("/index.html");
  await expect(page.getByRole("heading", { name: /示例项目（日译中）/ })).toBeVisible();
  await expect(page.getByRole("heading", { name: /示例项目（中译日）/ })).toBeVisible();
  await expect(page.getByText(/2 章/).first()).toBeVisible();
  await expect(page.getByText(/review_pending/).first()).toBeVisible();
});

test("review page shows auto-approve controls", async ({ page }) => {
  await page.goto("/review.html");
  await expect(
    page.getByRole("heading", { name: "Side-by-side Translation Review" })
  ).toBeVisible();
  await expect(page.getByText(/AUTO_APPROVE.*false/)).toBeVisible();
  await expect(page.getByRole("button", { name: "触发自动通过" }).first()).toBeVisible();
});

test("review page keeps pending until manual approve", async ({ page, request }) => {
  const projectId = `pw-pending-${Date.now()}`;
  await request.post("/api/projects", {
    data: {
      project_id: projectId,
      name: "Pending Test",
      language_direction: "JP_TO_CN",
    },
  });
  await request.post(`/api/projects/${projectId}/dry-run-generate`, {
    data: { sample_text: "テスト段落。" },
  });
  await page.goto(`/review.html?project=${projectId}`);
  const badge = page.locator(".segment .badge[data-status='pending']").first();
  await expect(badge).toBeVisible();
  await page.reload();
  await expect(page.locator(".segment .badge[data-status='pending']").first()).toBeVisible();
});

test("autopilot query enables auto-approve", async ({ page }) => {
  await page.goto("/review.html?project=demo-jp-cn&auto_approve=1");
  await expect(page.getByText(/AUTO_APPROVE.*true/)).toBeVisible();
});

test("review page has approve and reject buttons", async ({ page }) => {
  await page.goto("/review.html");
  await expect(page.getByRole("button", { name: "通过" }).first()).toBeVisible();
  await expect(page.getByRole("button", { name: "驳回" }).first()).toBeVisible();
});

test("navigation from index to review via link", async ({ page }) => {
  await page.goto("/index.html");
  await page.getByRole("link", { name: "进入对照审核 →" }).first().click();
  await expect(page).toHaveURL(/review\.html/);
  await expect(
    page.getByRole("heading", { name: "Side-by-side Translation Review" })
  ).toBeVisible();
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

test("review page has no console errors", async ({ page }) => {
  const errors: string[] = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") {
      errors.push(msg.text());
    }
  });
  await page.goto("/review.html");
  await page.waitForLoadState("networkidle");
  expect(errors).toEqual([]);
});

for (const missing of MISSING_PAGES) {
  test.skip(`${missing.name} page not in static MVP (${missing.path})`, async ({ page }) => {
    const res = await page.goto(missing.path);
    expect(res?.status()).toBe(404);
  });
}
