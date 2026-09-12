import { test, expect } from "@playwright/test";

for (const viewport of [{ width: 1280, height: 900 }, { width: 390, height: 844 }]) {
  test(`approval binds exact content and stale save stays unaccepted ${viewport.width}`, async ({ page, request }, testInfo) => {
    await page.setViewportSize(viewport);
    await page.emulateMedia({ reducedMotion: "reduce" });
    const projectId = `approval-${viewport.width}-${Date.now()}`;
    const errors: string[] = [];
    const consoleErrors: string[] = [];
    const failedRequests: string[] = [];
    const failedResponses: { path: string; status: number }[] = [];
    page.on("console", m => { if (m.type() === "error") consoleErrors.push(m.text()); });
    page.on("requestfailed", r => failedRequests.push(new URL(r.url()).pathname));
    page.on("response", r => { if (r.status() >= 400) failedResponses.push({path: new URL(r.url()).pathname, status: r.status()}); });
    page.on("pageerror", e => errors.push(e.message));
    const created = await request.post("/api/projects", {
      data: { project_id: projectId, name: "审核版本回归（合成数据）", language_direction: "JP_TO_CN" },
    });
    expect(created.status()).toBe(201);
    const generate = async (text: string) => {
      const response = await request.post(`/api/projects/${projectId}/dry-run-generate`, { data: { sample_text: text } });
      expect(response.ok()).toBeTruthy();
    };
    const approvedBadge = page.locator(".review-meta .badge[data-status='approved']");
    const approve = () => viewport.width < 500
      ? page.locator("#review-mobile-actions button[data-action='approve']")
      : page.locator(".review-meta button[data-action='approve']");
    await generate("Synthetic content A.");
    await page.goto(`/review.html?project=${projectId}`);
    let releaseSave!: () => void;
    const saveGate = new Promise<void>(resolve => { releaseSave = resolve; });
    let patches = 0;
    const holdSave = async (route: any) => {
      if (route.request().method() === "PATCH") { patches++; await saveGate; }
      await route.continue();
    };
    await page.route(`**/api/projects/${projectId}/review-state`, holdSave);
    await approve().click();
    await expect(approve()).toBeDisabled();
    await expect(approve()).toContainText("保存中");
    await page.keyboard.press("a");
    await expect.poll(() => patches).toBe(1);
    releaseSave();
    await expect(approvedBadge).toBeVisible();
    await expect(approve()).toBeFocused();
    await page.unroute(`**/api/projects/${projectId}/review-state`, holdSave);
    await page.reload();
    await expect(approvedBadge).toBeVisible();
    const identityA = (await (await request.get(`/api/projects/${projectId}/workbench-data`)).json()).segments[0].approval_identity;
    await generate("Synthetic content B.");
    const staleResponse = page.waitForResponse(r => r.url().endsWith("/review-state") && r.request().method() === "PATCH");
    await approve().click();
    const rejected = await staleResponse;
    expect(rejected.status()).toBe(409);
    expect(rejected.request().postDataJSON().segments["seg-001"].expected_identity).toBe(identityA);
    await expect(page.getByRole("alert")).toContainText("本次操作未保存");
    await expect(page.getByRole("alert")).toBeFocused();
    await expect(approvedBadge).toHaveCount(0);
    await expect(page.locator(".review-meta .badge[data-status='review_required']")).toBeVisible();
    const staleExport = await request.post("/api/export/run", {
      data: { project_id: projectId, source: "manifest", status_mode: "approved" },
    });
    expect(staleExport.status()).toBe(400);
    expect((await staleExport.json()).error).toContain("no approved segments");
    await page.screenshot({ path: testInfo.outputPath("stale-reapproval.png"), fullPage: true });
    await page.getByRole("link", { name: "刷新后重新审核" }).click();
    await expect(page.locator(".review-reading")).toContainText("Synthetic content B.");
    await expect(approvedBadge).toHaveCount(0);
    await approve().click();
    await expect(approvedBadge).toBeVisible();
    await expect(page.getByRole("alert")).toHaveCount(0);
    await page.reload();
    await expect(approvedBadge).toBeVisible();
    const freshExport = await request.post("/api/export/run", { data: { project_id: projectId, source: "manifest", status_mode: "approved" } });
    expect(freshExport.status()).toBe(200);
    expect((await freshExport.json()).segments_exported).toBe(1);
    const freshMemory = await request.post("/api/translation-assets/build", { data: { project_id: projectId, mode: "agent", status_mode: "approved" } });
    expect(freshMemory.status()).toBe(200);
    expect((await freshMemory.json()).stats.pairs).toBe(1);
    await page.screenshot({ path: testInfo.outputPath("fresh-approved.png"), fullPage: true });
    const identityB = (await (await request.get(`/api/projects/${projectId}/workbench-data`)).json()).segments[0].approval_identity;
    await generate("Synthetic content C.");
    const identityC = (await (await request.get(`/api/projects/${projectId}/workbench-data`)).json()).segments[0].approval_identity;
    const newerApproval = await request.patch(`/api/projects/${projectId}/review-state`, {data:{segments:{"seg-001":{status:"approved",expected_identity:identityC}}}});
    expect(newerApproval.status()).toBe(200);
    const rejectButton = () => viewport.width < 500
      ? page.locator("#review-mobile-actions button[data-action='reject']")
      : page.locator(".review-meta button[data-action='reject']");
    const staleRejectionResponse = page.waitForResponse(r => r.url().endsWith("/review-state") && r.request().method() === "PATCH");
    await rejectButton().click();
    const staleRejection = await staleRejectionResponse;
    expect(staleRejection.status()).toBe(409);
    expect(staleRejection.request().postDataJSON().segments["seg-001"].expected_identity).toBe(identityB);
    await expect(page.getByRole("alert")).toContainText("本次操作未保存");
    await expect(page.locator(".review-meta .badge[data-status='rejected']")).toHaveCount(0);
    await expect(approvedBadge).toHaveCount(0);
    const preserved = (await (await request.get(`/api/projects/${projectId}/review-state`)).json()).review_state.segments["seg-001"];
    expect(preserved.status).toBe("approved");
    expect(preserved.approval_identity).toBe(identityC);
    await page.getByRole("link", { name: "刷新后重新审核" }).click();
    await expect(page.locator(".review-reading")).toContainText("Synthetic content C.");
    await expect(approvedBadge).toBeVisible();
    await rejectButton().click();
    await expect(page.locator(".review-meta .badge[data-status='rejected']")).toBeVisible();
    await page.reload();
    await expect(page.locator(".review-meta .badge[data-status='rejected']")).toBeVisible();
    const rejectedExport = await request.post("/api/export/run", {data:{project_id:projectId,source:"manifest",status_mode:"approved"}});
    expect(rejectedExport.status()).toBe(400);
    expect((await rejectedExport.json()).error).toContain("no approved segments");
    const rejectedMemory = await request.post("/api/translation-assets/build", {data:{project_id:projectId,mode:"agent",status_mode:"approved"}});
    expect(rejectedMemory.status()).toBe(400);
    expect((await rejectedMemory.json()).error).toContain("no approved translation pairs");
    await generate("Synthetic content D.");
    await page.reload();
    await expect(page.locator(".review-reading")).toContainText("Synthetic content D.");
    await expect(page.locator(".review-meta .badge[data-status='review_required']")).toBeVisible();
    await expect(page.locator(".review-meta .badge[data-status='rejected']")).toHaveCount(0);
    expect(failedRequests).toEqual([]);
    expect(failedResponses).toEqual([{path: `/api/projects/${projectId}/review-state`, status: 409}, {path: `/api/projects/${projectId}/review-state`, status: 409}]);
    expect(consoleErrors.filter(text => !text.includes("409 (Conflict)"))).toEqual([]);
    await testInfo.attach("browser-evidence", {body: JSON.stringify({viewport, identityA, pageErrors: errors, consoleErrors, failedRequests, failedResponses, staleExportStatus: 400, freshExportStatus: 200, freshMemoryPairs: 1, staleRejectionStatus: 409, newerApprovalPreserved: true, freshRejectionPersisted: true, changedContentInvalidatesRejection: true, rejectedExportAndMemoryStatus: 400}, null, 2), contentType:"application/json"});
    expect(await page.evaluate(() => localStorage.getItem("light_novel_workbench_state_v1"))).toBeNull();
    expect(errors).toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  });
}

test("legacy browser approval is retained as data but cannot become formal on read failure", async ({ page }) => {
  const projectId = `legacy-local-${Date.now()}`;
  const old = { segments: { "seg-001": { status: "approved", note: "legacy note" } } };
  await page.addInitScript(value => localStorage.setItem("light_novel_workbench_state_v1", JSON.stringify(value)), old);
  await page.route("**/api/projects", route => route.fulfill({json:{projects:[{id:projectId,name:"Legacy fixture"}],active_project_id:projectId}}));
  await page.route(`**/api/projects/${projectId}/workbench-data`, route => route.fulfill({json:{project:{id:projectId,name:"Legacy fixture"},segments:[{id:"seg-001",source:"Synthetic legacy",draft:"合成旧稿",status:"approved"}]}}));
  await page.route(`**/api/projects/${projectId}/review-state`, route => route.fulfill({status:503,json:{error:"fixture unavailable"}}));
  await page.route(`**/api/projects/${projectId}/generation-job`, route => route.fulfill({json:{job:null}}));
  await page.route(`**/api/projects/${projectId}/quality-review`, route => route.fulfill({json:{issues:[]}}));
  await page.goto(`/review.html?project=${projectId}`);
  await expect(page.locator(".review-meta .badge[data-status='approved']")).toHaveCount(0);
  await expect(page.getByRole("alert")).toContainText("无法读取");
  expect(await page.evaluate(() => JSON.parse(localStorage.getItem("light_novel_workbench_state_v1")!))).toEqual(old);
});
