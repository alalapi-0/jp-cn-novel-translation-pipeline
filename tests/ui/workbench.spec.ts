import { test, expect } from "@playwright/test";

test.describe.configure({ mode: "serial" });

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
  const projectId = `pw-qs-${Date.now()}`;
  await page.goto("/index.html");
  await page.locator("#qs-project-id").fill(projectId);
  await page.locator("#qs-project-name").fill("User Quickstart");
  await page.locator("#qs-sample-text").fill("第一段落。\n\n第二段落。");
  await page.locator("#quickstart-form button[type='submit']").click();
  await expect(page.locator("#quickstart-result")).toContainText(/生成.*segment/);
  const reviewLink = page.locator("#qs-review-link");
  await expect(reviewLink).toBeVisible();
  await reviewLink.click();
  await expect(page).toHaveURL(new RegExp(`review\\.html\\?project=${projectId}`));
  await expect(page.locator(".segment").first()).toBeVisible();
});

test("review state persists after reload", async ({ page, request }) => {
  const projectId = `pw-rs-${Date.now()}`;
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
  const projectId = `pw-export-${Date.now()}`;
  await request.post("/api/projects", {
    data: { project_id: projectId, name: "Export", language_direction: "JP_TO_CN" },
  });
  await request.post(`/api/projects/${projectId}/dry-run-generate`, {
    data: { sample_text: "export me" },
  });
  await page.goto(`/export.html?project=${projectId}`);
  await page.locator("#export-manifest-btn").click();
  await expect(page.locator("#export-result")).toContainText(/source=manifest/);
  await expect(page.locator("#export-result")).toContainText(projectId);
});

test("export manifest默认仅导出 approved 并显示跳过统计", async ({ page, request }) => {
  const projectId = `pw-export-approved-${Date.now()}`;
  await request.post("/api/projects", {
    data: { project_id: projectId, name: "Export Approved", language_direction: "JP_TO_CN" },
  });
  await request.post(`/api/projects/${projectId}/dry-run-generate`, {
    data: { sample_text: "第一段。\n\n第二段。" },
  });
  await request.patch(`/api/projects/${projectId}/review-state`, {
    data: {
      segments: {
        "seg-001": { status: "approved", at: new Date().toISOString() },
        "seg-002": { status: "rejected", at: new Date().toISOString() },
      },
    },
  });
  await page.goto(`/export.html?project=${projectId}`);
  await page.locator("#export-manifest-btn").click();
  await expect(page.locator("#export-result")).toContainText(/status_mode=approved/);
  await expect(page.locator("#export-result")).toContainText(/segments_exported=1/);
  await expect(page.locator("#export-result")).toContainText(/segments_skipped_status=.*rejected:1/);
});

test("review selector包含并选中当前 test 项目", async ({ page, request }) => {
  const projectId = `pw-selector-${Date.now()}`;
  await request.post("/api/projects", {
    data: { project_id: projectId, name: "Selector", language_direction: "JP_TO_CN" },
  });
  await request.post(`/api/projects/${projectId}/dry-run-generate`, {
    data: { sample_text: "selector test" },
  });
  await page.goto(`/review.html?project=${projectId}`);
  await expect(page.locator("#project-switcher")).toHaveValue(projectId);
  await expect(page.locator(`#project-switcher option[value="${projectId}"]`)).toHaveCount(1);
  await expect(page.locator("#project-switcher")).toContainText("Selector");
});

test("issues 页面展示动态数据源与项目信息", async ({ page, request }) => {
  const projectId = `pw-issues-${Date.now()}`;
  await request.post("/api/projects", {
    data: { project_id: projectId, name: "Issues", language_direction: "JP_TO_CN" },
  });
  await request.post(`/api/projects/${projectId}/dry-run-generate`, {
    data: { sample_text: "issues page" },
  });
  await page.goto(`/issues.html?project=${projectId}`);
  await expect(page.locator("#issue-data-source")).toContainText(/API|fallback→fixture|fixture/);
  await expect(page.locator("#issue-project-id")).toContainText(projectId);
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

test("review page counts only open issues", async ({ page, request }) => {
  const projectId = `pw-issue-open-${Date.now()}`;
  await request.post("/api/projects", {
    data: {
      project_id: projectId,
      name: "Issue Open",
      language_direction: "JP_TO_CN",
      segments: [
        {
          id: "seg-001",
          segment_id: "seg-001",
          source: "詳細は {{PH_LINK_1}} および https://example.com/docs を参照。",
          draft: "详情请参阅文档。",
          status: "pending",
        },
        {
          id: "seg-002",
          segment_id: "seg-002",
          source: "彼女は学校に行かなかった。",
          draft: "她去了学校。",
          status: "pending",
        },
      ],
    },
  });
  const reportRes = await request.get(`/api/projects/${projectId}/quality-review`);
  expect(reportRes.ok()).toBeTruthy();
  const report = await reportRes.json();
  const issuesBySegment = (report.issues || []).reduce((acc: Record<string, any[]>, item: any) => {
    const sid = item.segment_id || "";
    if (!sid) return acc;
    if (!acc[sid]) acc[sid] = [];
    acc[sid].push(item);
    return acc;
  }, {});
  const targetSeg = Object.keys(issuesBySegment)[0];
  expect(targetSeg).toBeTruthy();
  const targetIssues = issuesBySegment[targetSeg];
  expect(targetIssues.length).toBeGreaterThan(0);
  await request.patch(`/api/projects/${projectId}/review-state`, {
    data: {
      issues: {
        [targetIssues[0].issue_id]: { status: "resolved", at: new Date().toISOString() },
      },
    },
  });

  await page.goto(`/review.html?project=${projectId}&segment=${targetSeg}`);
  const seg = page.locator(`#seg-${targetSeg}`);
  await expect(seg).toBeVisible();
  const expectedOpen = targetIssues.length - 1;
  if (expectedOpen > 0) {
    await expect(seg.locator(".issue-mark")).toContainText(`${expectedOpen} 条 open issue`);
  } else {
    await expect(seg.locator(".issue-mark")).toHaveCount(0);
  }
});

test("真实 API 按钮双击只触发一次确认和一次请求", async ({ page }) => {
  const projectId = `pw-real-click-${Date.now()}`;
  let confirmCount = 0;
  let createCount = 0;
  let generateCount = 0;

  page.on("dialog", async (dialog) => {
    confirmCount += 1;
    await dialog.accept();
  });

  await page.route("**/api/runtime/api-status", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        api_mode: "real_api",
        detected_providers: ["openrouter"],
        real_api_tests_enabled: true,
        has_api_key: true,
        configured_env_vars: ["OPENROUTER_API_KEY"],
        max_test_cost_usd: 0.05,
        max_tokens_per_run: 128,
        workbench_real_api_ready: true,
        workbench_real_api_block_reason: null,
        checked_at: new Date().toISOString(),
        config_hint: "ok",
        last_smoke: null,
        runner_status_note: null,
      }),
    });
  });

  await page.route(/.*\/api\/projects(\?.*)?$/, async (route) => {
    const method = route.request().method();
    if (method === "GET") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          projects: [
            {
              id: projectId,
              project_id: projectId,
              name: "DoubleClick",
              language_direction: "JP_TO_CN",
              direction: "JP_TO_CN",
              status: "draft_pending",
              chapters: 1,
              category: "test",
            },
          ],
          active_project_id: projectId,
          include_test: true,
          include_history: true,
        }),
      });
      return;
    }
    if (method !== "POST") {
      await route.continue();
      return;
    }
    createCount += 1;
    await route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify({
        project: {
          id: projectId,
          project_id: projectId,
          name: "DoubleClick",
          language_direction: "JP_TO_CN",
          direction: "JP_TO_CN",
          status: "draft_pending",
          chapters: 1,
          category: "test",
        },
        active_project_id: projectId,
      }),
    });
  });
  await page.route(`**/api/projects/${projectId}/generation-job`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ project_id: projectId, generation_job: null }),
    });
  });
  await page.route(`**/api/projects/${projectId}/quality-review`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        project_id: projectId,
        review_status: "ok",
        summary: { total: 0, by_type: {} },
        issues: [],
      }),
    });
  });
  await page.route(`**/api/projects/${projectId}/workbench-data`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        project: {
          id: projectId,
          project_id: projectId,
          name: "DoubleClick",
          language_direction: "JP_TO_CN",
          direction: "JP_TO_CN",
          status: "review_pending",
          chapters: 1,
          category: "test",
        },
        segments: [
          {
            id: "seg-001",
            segment_id: "seg-001",
            source: "A",
            draft: "B",
            status: "pending",
          },
        ],
      }),
    });
  });
  await page.route(`**/api/projects/${projectId}/real-api-generate`, async (route) => {
    generateCount += 1;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        project_id: projectId,
        request_id: "req-1",
        segments_created: 1,
        generation: "real_api",
        generation_meta: { provider: "stub", model: "stub", network_calls: 1 },
        review_url: `/review.html?project=${projectId}`,
        project: {
          id: projectId,
          project_id: projectId,
          name: "DoubleClick",
          language_direction: "JP_TO_CN",
          direction: "JP_TO_CN",
          status: "review_pending",
          chapters: 1,
          category: "test",
        },
        generation_job: {
          request_id: "req-1",
          status: "succeeded",
          mode: "real_api",
          segments_created: 1,
        },
      }),
    });
  });

  await page.goto("/index.html");
  await page.locator("#qs-project-id").fill(projectId);
  await page.locator("#qs-project-name").fill("DoubleClick");
  await page.locator("#qs-sample-text").fill("第一段");
  const btn = page.locator("#qs-real-api-btn");
  await Promise.all([btn.click(), btn.click()]);
  await expect(page.locator("#quickstart-result")).toContainText(/真实 API/);
  expect(confirmCount).toBe(1);
  expect(createCount).toBe(1);
  expect(generateCount).toBe(1);
});

test("空 draft_pending 项目可继续生成/归档/删除", async ({ page, request }) => {
  const projectId = `pw-empty-${Date.now()}`;
  await request.post("/api/projects", {
    data: { project_id: projectId, name: "Empty", language_direction: "JP_TO_CN" },
  });
  await page.goto(`/review.html?project=${projectId}`);
  await expect(page.getByText("尚无 segment 可审核")).toBeVisible();
  await expect(page.getByRole("link", { name: /返回 Quickstart 继续生成/ })).toHaveAttribute(
    "href",
    new RegExp(`index\\.html\\?project=${projectId}`)
  );

  page.once("dialog", async (dialog) => {
    expect(dialog.type()).toBe("confirm");
    await dialog.accept();
  });
  await page.getByRole("button", { name: "归档项目" }).click();
  await expect(page.locator("#review-root")).toContainText("状态：archived");

  await page.getByRole("button", { name: /标记可重试/ }).click();
  await expect(page.locator("#review-root")).toContainText("状态：draft_pending");

  let deleteDialogStep = 0;
  const deleteDialogHandler = async (dialog) => {
    deleteDialogStep += 1;
    if (deleteDialogStep === 1) {
      expect(dialog.type()).toBe("confirm");
      await dialog.accept();
      return;
    }
    expect(dialog.type()).toBe("prompt");
    await dialog.accept(`DELETE ${projectId}`);
    page.off("dialog", deleteDialogHandler);
  };
  page.on("dialog", deleteDialogHandler);
  await page.getByRole("button", { name: "删除测试项目" }).click();
  await expect.poll(() => deleteDialogStep).toBeGreaterThanOrEqual(2);
  await expect(page.locator(`#project-switcher option[value="${projectId}"]`)).toHaveCount(0);
});
