import { test, expect } from "@playwright/test";

const ILLEGAL_PROJECT_ID_RE = /must not contain|path separators|invalid project_id/i;

test("quickstart rejects illegal project id", async ({ page }) => {
  await page.goto("/index.html");
  await page.locator("#qs-project-id").fill("../bad");
  await page.locator("#qs-project-name").fill("Bad");
  await page.locator("#qs-sample-text").fill("テスト");
  await page.locator("#quickstart-form button[type='submit']").click();
  await expect(page.locator("#quickstart-result")).toContainText(ILLEGAL_PROJECT_ID_RE);
});

test("quickstart creates user project and links to review", async ({ page }) => {
  const projectId = `user-qs-${Date.now()}`;
  await page.goto("/index.html");
  await page.locator("#qs-project-id").fill(projectId);
  await page.locator("#qs-project-name").fill("User Quickstart");
  await page.locator("#qs-sample-text").fill("第一段落。\n\n第二段落。");
  await page.locator("#quickstart-form button[type='submit']").click();
  await expect(page.locator("#quickstart-result")).toContainText(/已生成/);
  const reviewLink = page.locator("#qs-review-link");
  await expect(reviewLink).toBeVisible();
  await reviewLink.click();
  await expect(page).toHaveURL(new RegExp(`review\\.html\\?project=${projectId}`));
  await expect(page.locator(".segment").first()).toBeVisible();
});

test("review state persists after reload", async ({ page, request }) => {
  const projectId = `user-rs-${Date.now()}`;
  await request.post("/api/projects", {
    data: { project_id: projectId, name: "RS", language_direction: "JP_TO_CN" },
  });
  await request.post(`/api/projects/${projectId}/dry-run-generate`, {
    data: { sample_text: "persist test" },
  });
  await page.goto(`/review.html?project=${projectId}`);
  await page.getByRole("button", { name: "通过" }).first().click();
  await expect(page.locator(".badge[data-status='approved']").first()).toBeVisible();
  await page.reload();
  await expect(page.locator(".badge[data-status='approved']").first()).toBeVisible();
});

test("export manifest fails for unknown project", async ({ page }) => {
  await page.goto("/export.html");
  await page.locator("#export-project-id").fill("missing-project-xyz");
  await page.locator("#export-manifest-btn").click();
  await expect(page.locator("#export-result")).toContainText(/unknown project_id/i);
});

test("export manifest exports only selected project", async ({ page, request }) => {
  const projectId = `user-export-${Date.now()}`;
  await request.post("/api/projects", {
    data: { project_id: projectId, name: "Export", language_direction: "JP_TO_CN" },
  });
  await request.post(`/api/projects/${projectId}/dry-run-generate`, {
    data: { sample_text: "export me" },
  });
  await page.goto(`/export.html?project=${projectId}`);
  await page.locator("#export-manifest-btn").click();
  await expect(page.locator("#export-result")).toContainText(/"source": "manifest"/);
  await expect(page.locator("#export-result")).toContainText(projectId);
});

test("homepage hides pw test projects by default", async ({ page, request }) => {
  const hiddenId = `pw-ui-hidden-${Date.now()}`;
  await request.post("/api/projects", {
    data: { project_id: hiddenId, name: "Hidden PW", language_direction: "JP_TO_CN" },
  });
  await page.goto("/index.html");
  await expect(page.getByRole("heading", { name: /示例项目（日译中）/ })).toBeVisible();
  await expect(page.locator("#project-list")).not.toContainText(hiddenId);
});

test("illegal project id via API returns 400 json", async ({ request }) => {
  const res = await request.post("/api/projects", {
    data: { project_id: "../bad", name: "x", language_direction: "JP_TO_CN" },
  });
  expect(res.status()).toBe(400);
  const body = await res.json();
  expect(body.error).toMatch(ILLEGAL_PROJECT_ID_RE);
});
