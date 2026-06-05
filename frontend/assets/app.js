(function () {
  const STORAGE_KEY = "light_novel_workbench_state_v1";
  const ISSUE_STORAGE_KEY = "light_novel_issue_state_v1";
  const ACTIVE_PROJECT_KEY = "light_novel_active_project_v1";

  let reviewData = null;
  let issueReport = null;
  let issuesBySegment = {};
  let workbenchContext = null;
  let currentIssuesProjectId = "";
  let reviewStateCache = { segments: {}, issues: {} };

  function getConfig() {
    const base = window.WORKBENCH_CONFIG || {};
    const params = new URLSearchParams(window.location.search);
    const autoFromQuery =
      params.get("auto_approve") === "1" || params.get("autopilot") === "1";
    if (autoFromQuery && !base.AUTO_APPROVE) {
      return { ...base, AUTO_APPROVE: true, dryRunAutoApprove: true };
    }
    return base;
  }

  function log(line) {
    const el = document.getElementById("status-log");
    if (!el) return;
    const ts = new Date().toISOString().slice(11, 19);
    el.textContent = `[${ts}] ${line}\n` + el.textContent;
  }

  function escapeHtml(text) {
    return String(text)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function loadLocalReviewState() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      return raw ? JSON.parse(raw) : { segments: {} };
    } catch {
      return { segments: {} };
    }
  }

  function loadLocalIssueState() {
    try {
      const raw = localStorage.getItem(ISSUE_STORAGE_KEY);
      return raw ? JSON.parse(raw) : { issues: {} };
    } catch {
      return { issues: {} };
    }
  }

  function saveLocalReviewState(state) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  }

  function saveLocalIssueState(state) {
    localStorage.setItem(ISSUE_STORAGE_KEY, JSON.stringify(state));
  }

  function loadActiveProjectId() {
    try {
      return localStorage.getItem(ACTIVE_PROJECT_KEY) || "";
    } catch {
      return "";
    }
  }

  function saveActiveProjectId(projectId) {
    localStorage.setItem(ACTIVE_PROJECT_KEY, projectId);
  }

  async function fetchApiStatus() {
    const res = await fetch("/api/runtime/api-status");
    if (!res.ok) throw new Error(`/api/runtime/api-status ${res.status}`);
    return res.json();
  }

  async function loadReviewStateForProject(projectId) {
    if (!projectId) {
      reviewStateCache = { segments: {}, issues: {} };
      return reviewStateCache;
    }
    try {
      const res = await fetch(
        `/api/projects/${encodeURIComponent(projectId)}/review-state`
      );
      if (res.ok) {
        const payload = await res.json();
        reviewStateCache = payload.review_state || { segments: {}, issues: {} };
        reviewStateCache.segments = reviewStateCache.segments || {};
        reviewStateCache.issues = reviewStateCache.issues || {};
        return reviewStateCache;
      }
    } catch (_err) {
      /* fallback below */
    }
    const local = loadLocalReviewState();
    reviewStateCache = {
      segments: local.segments || {},
      issues: loadLocalIssueState().issues || {},
    };
    return reviewStateCache;
  }

  async function patchReviewState(projectId, patch) {
    if (!projectId) return false;
    try {
      const res = await fetch(
        `/api/projects/${encodeURIComponent(projectId)}/review-state`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(patch),
        }
      );
      if (res.ok) {
        const payload = await res.json();
        reviewStateCache = payload.review_state || reviewStateCache;
        return true;
      }
    } catch (_err) {
      /* local fallback */
    }
    if (patch.segments) {
      const local = loadLocalReviewState();
      local.segments = { ...(local.segments || {}), ...patch.segments };
      saveLocalReviewState(local);
      reviewStateCache.segments = local.segments;
    }
    if (patch.issues) {
      const localIssues = loadLocalIssueState();
      localIssues.issues = { ...(localIssues.issues || {}), ...patch.issues };
      saveLocalIssueState(localIssues);
      reviewStateCache.issues = localIssues.issues;
    }
    return false;
  }

  function segmentStatus(segment, state) {
    const id = segment.id || segment.segment_id;
    return state.segments?.[id]?.status || segment.status || "pending";
  }

  function issueStatus(issue, issueState) {
    return issueState.issues?.[issue.issue_id]?.status || issue.status || "open";
  }

  function renderBadge(status) {
    const cls = status === "approved" ? "ok" : "pending";
    return `<span class="badge ${cls}" data-status="${status}">${status}</span>`;
  }

  function renderSeverity(severity) {
    const cls =
      severity === "critical" || severity === "high"
        ? "severity-high"
        : severity === "medium"
          ? "severity-medium"
          : "severity-low";
    return `<span class="badge ${cls}">${severity}</span>`;
  }

  async function fetchMockData() {
    const res = await fetch("/assets/mock-data.json");
    if (!res.ok) throw new Error(`mock-data.json ${res.status}`);
    return res.json();
  }

  async function fetchIssueReport(preferredProjectId) {
    const pid = preferredProjectId || loadActiveProjectId();
    if (pid) {
      try {
        const res = await fetch(
          `/api/projects/${encodeURIComponent(pid)}/quality-review`
        );
        if (res.ok) {
          const payload = await res.json();
          payload._source = "api";
          return payload;
        }
      } catch (_apiErr) {
        /* fallback */
      }
    }
    const res = await fetch("/assets/review-issue-report.json");
    if (!res.ok) throw new Error(`review-issue-report.json ${res.status}`);
    const payload = await res.json();
    payload._source = "static";
    return payload;
  }

  async function fetchProjectsApi() {
    const res = await fetch("/api/projects");
    if (!res.ok) throw new Error(`/api/projects ${res.status}`);
    return res.json();
  }

  async function fetchWorkbenchDataApi(projectId) {
    const res = await fetch(`/api/projects/${encodeURIComponent(projectId)}/workbench-data`);
    if (!res.ok) throw new Error(`workbench-data ${res.status}`);
    return res.json();
  }

  async function switchActiveProjectApi(projectId) {
    const res = await fetch("/api/projects/active", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ project_id: projectId }),
    });
    if (!res.ok) throw new Error(`switch project ${res.status}`);
    return res.json();
  }

  async function loadWorkbenchContext(preferredProjectId) {
    try {
      const registry = await fetchProjectsApi();
      const projects = registry.projects || [];
      const activeId =
        preferredProjectId ||
        registry.active_project_id ||
        projects[0]?.id ||
        projects[0]?.project_id;
      if (!activeId) throw new Error("no projects in registry");
      const payload = await fetchWorkbenchDataApi(activeId);
      saveActiveProjectId(activeId);
      return {
        source: "api",
        projects,
        activeProjectId: activeId,
        segments: payload.segments || [],
        activeProject: payload.project || projects.find((p) => p.id === activeId),
      };
    } catch (apiErr) {
      const mock = await fetchMockData();
      const activeId = preferredProjectId || loadActiveProjectId() || mock.projects?.[0]?.id;
      return {
        source: "mock",
        projects: mock.projects || [],
        activeProjectId: activeId,
        segments: mock.segments || [],
        activeProject: mock.projects?.find((p) => p.id === activeId) || mock.projects?.[0],
        apiError: apiErr.message,
      };
    }
  }

  function indexIssues(report) {
    const map = {};
    for (const issue of report.issues || []) {
      if (!issue.segment_id) continue;
      if (!map[issue.segment_id]) map[issue.segment_id] = [];
      map[issue.segment_id].push(issue);
    }
    return map;
  }

  async function bindApiStatusPanel() {
    const modeEl = document.getElementById("api-mode-status");
    if (!modeEl) return;
    try {
      const status = await fetchApiStatus();
      modeEl.textContent = status.api_mode || "unknown";
      const keyEl = document.getElementById("api-key-status");
      const realEl = document.getElementById("real-api-enabled-status");
      const smokeEl = document.getElementById("api-smoke-summary");
      const hintEl = document.getElementById("api-config-hint");
      if (keyEl) {
        keyEl.textContent = status.has_api_key
          ? `已配置 (${status.detected_providers.join(", ")})`
          : "missing_api_key";
      }
      if (realEl) realEl.textContent = String(Boolean(status.real_api_tests_enabled));
      if (smokeEl) {
        smokeEl.textContent = status.last_smoke
          ? `最近 smoke：${status.last_smoke.mode} · success=${status.last_smoke.success} · ${status.last_smoke.created_at || "—"}`
          : "尚未运行 smoke；CLI: python3 scripts/run_real_api_smoke.py";
      }
      if (hintEl) hintEl.textContent = status.config_hint || "—";
      const cfg = getConfig();
      const banner = document.getElementById("mode-banner");
      if (banner) {
        banner.textContent = `${cfg.mockDataLabel} · api_mode=${status.api_mode}`;
      }
      const summary = document.getElementById("config-summary");
      if (summary) {
        summary.textContent = `apiMode=${status.api_mode}, has_key=${status.has_api_key}, real_enabled=${status.real_api_tests_enabled}`;
      }
    } catch (err) {
      modeEl.textContent = "unavailable";
      log(`api status error: ${err.message}`);
    }
  }

  function setupQuickstartForm() {
    const form = document.getElementById("quickstart-form");
    if (!form || form.dataset.bound === "1") return;
    form.dataset.bound = "1";
    form.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const projectId = document.getElementById("qs-project-id")?.value.trim();
      const name = document.getElementById("qs-project-name")?.value.trim() || projectId;
      const direction = document.getElementById("qs-direction")?.value || "JP_TO_CN";
      const sampleText = document.getElementById("qs-sample-text")?.value.trim();
      const resultEl = document.getElementById("quickstart-result");
      const reviewLink = document.getElementById("qs-review-link");
      if (!projectId || !sampleText) {
        if (resultEl) resultEl.textContent = "请填写项目 ID 与样本文本。";
        return;
      }
      try {
        let createRes = await fetch("/api/projects", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            project_id: projectId,
            name,
            language_direction: direction,
          }),
        });
        if (createRes.status === 400) {
          await switchActiveProjectApi(projectId);
        } else if (!createRes.ok) {
          throw new Error(`create project ${createRes.status}`);
        }
        const genRes = await fetch(
          `/api/projects/${encodeURIComponent(projectId)}/dry-run-generate`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ sample_text: sampleText }),
          }
        );
        if (!genRes.ok) throw new Error(`dry-run generate ${genRes.status}`);
        const genPayload = await genRes.json();
        saveActiveProjectId(projectId);
        if (resultEl) {
          resultEl.textContent = `已生成 ${genPayload.segments_created} 个 segment，可进入审核。`;
        }
        if (reviewLink) {
          reviewLink.href = genPayload.review_url || `/review.html?project=${encodeURIComponent(projectId)}`;
          reviewLink.hidden = false;
        }
        workbenchContext = await loadWorkbenchContext(projectId);
        bindHomePage(workbenchContext);
        log(`quickstart: ${projectId} dry-run segments=${genPayload.segments_created}`);
      } catch (err) {
        if (resultEl) resultEl.textContent = `失败：${err.message}`;
        log(`quickstart failed: ${err.message}`);
      }
    });
  }

  function bindIssuesPage(report) {
    const root = document.getElementById("issues-root");
    if (!root) return;
    issueReport = report;
    issuesBySegment = indexIssues(report);
    const issueState = reviewStateCache;

    const statusEl = document.getElementById("review-status");
    const totalEl = document.getElementById("issue-total");
    if (statusEl) statusEl.textContent = report.review_status || "—";
    if (totalEl) totalEl.textContent = String(report.summary?.total ?? report.issues.length);

    const typeSelect = document.getElementById("filter-type");
    if (typeSelect && typeSelect.options.length <= 1) {
      const types = [...new Set(report.issues.map((i) => i.issue_type))].sort();
      for (const t of types) {
        const opt = document.createElement("option");
        opt.value = t;
        opt.textContent = t;
        typeSelect.appendChild(opt);
      }
    }

    const sevFilter = document.getElementById("filter-severity")?.value || "";
    const typeFilter = document.getElementById("filter-type")?.value || "";
    const statusFilter = document.getElementById("filter-status")?.value || "";

    const filtered = report.issues.filter((issue) => {
      const st = issueStatus(issue, issueState);
      if (sevFilter && issue.severity !== sevFilter) return false;
      if (typeFilter && issue.issue_type !== typeFilter) return false;
      if (statusFilter && st !== statusFilter) return false;
      return true;
    });

    root.innerHTML = filtered
      .map((issue) => {
        const st = issueStatus(issue, issueState);
        const locked =
          issue.issue_type === "LOCKED_TERM_VIOLATION" || issue.auto_fixable === false;
        const humanFlag = issue.human_edited_segment
          ? '<span class="badge pending">human_edited</span>'
          : "";
        const diffBlock =
          issue.source_text_ref || issue.target_text_ref
            ? `<div class="diff-grid">
            <div><div class="panel-title">source_ref</div><p>${escapeHtml(issue.source_text_ref || "—")}</p></div>
            <div><div class="panel-title">target_ref</div><p>${escapeHtml(issue.target_text_ref || "—")}</p></div>
          </div>`
            : "";
        const projectId = issue.project_id || report.project_id || currentIssuesProjectId || "";
        const reviewLink = issue.segment_id
          ? `<a href="/review.html?project=${encodeURIComponent(projectId)}&segment=${encodeURIComponent(issue.segment_id)}#seg-${encodeURIComponent(issue.segment_id)}">对照定位 →</a>`
          : "";
        return `
        <article class="issue-card" data-issue-id="${issue.issue_id}">
          <header class="issue-header">
            <strong>${escapeHtml(issue.issue_type)}</strong>
            ${renderSeverity(issue.severity)}
            <span class="badge">${st}</span>
            ${humanFlag}
          </header>
          <p>${escapeHtml(issue.description)}</p>
          ${diffBlock}
          <p class="meta">segment: ${escapeHtml(issue.segment_id || "—")} · ${escapeHtml(issue.created_by)}</p>
          ${
            issue.suggested_fix
              ? `<p class="meta">建议：${escapeHtml(issue.suggested_fix)}</p>`
              : ""
          }
          <div class="actions">
            <button type="button" data-issue-action="ack" data-id="${issue.issue_id}">确认</button>
            <button type="button" class="primary" data-issue-action="resolve" data-id="${issue.issue_id}">标记已解决</button>
            <button type="button" disabled title="Round 49 不写入译文">自动修复（禁用）</button>
          </div>
          <p class="meta">${reviewLink}</p>
        </article>`;
      })
      .join("");

    if (!filtered.length) {
      root.innerHTML = '<p class="meta">无匹配 issue。</p>';
    }
  }

  function setupIssueHandlers(report) {
    const root = document.getElementById("issues-root");
    if (!root || root.dataset.issueBound === "1") return;
    root.dataset.issueBound = "1";
    root.addEventListener("click", async (ev) => {
      const btn = ev.target.closest("button[data-issue-action]");
      if (!btn) return;
      const id = btn.dataset.id;
      const action = btn.dataset.issueAction;
      const next =
        action === "resolve"
          ? "resolved"
          : action === "ack"
            ? "acknowledged"
            : "open";
      const entry = { status: next, at: new Date().toISOString() };
      await patchReviewState(currentIssuesProjectId, { issues: { [id]: entry } });
      log(`issue ${id} → ${next} (persisted)`);
      bindIssuesPage(report);
    });

    for (const sel of ["filter-severity", "filter-type", "filter-status"]) {
      const el = document.getElementById(sel);
      if (!el || el.dataset.bound === "1") continue;
      el.dataset.bound = "1";
      el.addEventListener("change", () => bindIssuesPage(report));
    }
  }

  async function applyAutoApprove(segment, projectId) {
    const cfg = getConfig();
    if (!cfg.AUTO_APPROVE && !cfg.dryRunAutoApprove) return false;
    const id = segment.id || segment.segment_id;
    await patchReviewState(projectId, {
      segments: {
        [id]: {
          status: "approved",
          autoApprove: true,
          at: new Date().toISOString(),
        },
      },
    });
    log(`AUTO_APPROVE: ${id} → approved`);
    return true;
  }

  function bindReviewPage(data) {
    const root = document.getElementById("review-root");
    if (!root) return;
    reviewData = data;
    const state = reviewStateCache;
    const cfg = getConfig();
    const apiLabel = document.getElementById("api-mode-label");
    const autoLabel = document.getElementById("auto-approve-label");
    const projectLabel = document.getElementById("active-project-label");
    if (apiLabel) apiLabel.textContent = cfg.apiMode || "unknown";
    if (autoLabel) autoLabel.textContent = String(Boolean(cfg.AUTO_APPROVE));
    const banner = document.getElementById("mode-banner");
    if (banner && cfg.mockDataLabel) {
      banner.textContent = `${cfg.mockDataLabel} · AUTO_APPROVE=${cfg.AUTO_APPROVE}`;
    }
    if (projectLabel && workbenchContext?.activeProject) {
      projectLabel.textContent = `${workbenchContext.activeProject.name} (${workbenchContext.activeProjectId})`;
    }

    root.innerHTML = data.segments
      .map((seg) => {
        const status = segmentStatus(seg, state);
        const segId = seg.id || seg.segment_id;
        const segIssues = issuesBySegment[segId] || [];
        const issueMarks = segIssues.length
          ? `<p class="issue-mark">${segIssues.length} 条 open issue · <a href="/issues.html?project=${encodeURIComponent(workbenchContext?.activeProjectId || "")}">查看</a></p>`
          : "";
        const highlight = segIssues.length ? " segment-has-issue" : "";
        return `
        <article class="segment${highlight}" id="seg-${segId}" data-segment-id="${segId}">
          ${issueMarks}
          <div class="grid-2">
            <div>
              <div class="panel-title">原文</div>
              <p>${escapeHtml(seg.source)}</p>
            </div>
            <div>
              <div class="panel-title">译文（mock）</div>
              <p>${escapeHtml(seg.draft)}</p>
            </div>
          </div>
          <p>状态：${renderBadge(status)}</p>
          <div class="actions">
            <button type="button" class="primary" data-action="approve" data-id="${segId}">通过</button>
            <button type="button" class="danger" data-action="reject" data-id="${segId}">驳回</button>
            <button type="button" data-action="auto" data-id="${segId}">触发自动通过</button>
          </div>
        </article>`;
      })
      .join("");

    const params = new URLSearchParams(window.location.search);
    const focus = params.get("segment");
    if (focus) {
      const el = document.getElementById(`seg-${focus}`);
      if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }

  async function runAutoApproveIfEnabled(data, projectId) {
    const cfg = getConfig();
    if (!cfg.AUTO_APPROVE) return;
    let autoCount = 0;
    for (const seg of data.segments) {
      if (segmentStatus(seg, reviewStateCache) === "pending") {
        if (await applyAutoApprove(seg, projectId)) autoCount += 1;
      }
    }
    if (autoCount > 0) bindReviewPage(data);
  }

  function bindHomePage(ctx) {
    const list = document.getElementById("project-list");
    if (!list) return;
    const activeId = ctx.activeProjectId;
    list.innerHTML = ctx.projects
      .map((p) => {
        const pid = p.id || p.project_id;
        const isActive = pid === activeId;
        return `
      <div class="card${isActive ? " card-active" : ""}">
        <h2>${escapeHtml(p.name)}${isActive ? ' <span class="badge ok">当前</span>' : ""}</h2>
        <p class="meta">方向 ${escapeHtml(p.direction || p.language_direction)} · ${p.chapters} 章 · 状态 ${escapeHtml(p.status)}</p>
        <p>
          <a href="/review.html?project=${encodeURIComponent(pid)}">进入对照审核 →</a>
          · <a href="/issues.html?project=${encodeURIComponent(pid)}">质量 Issue 列表 →</a>
          · <a href="/export.html?project=${encodeURIComponent(pid)}">导出 →</a>
          ${
            isActive
              ? ""
              : `<button type="button" class="primary" data-switch-project="${escapeHtml(pid)}">切换为当前项目</button>`
          }
        </p>
      </div>`;
      })
      .join("");

    const sourceEl = document.getElementById("data-source-label");
    if (sourceEl) {
      sourceEl.textContent =
        ctx.source === "api"
          ? "manifest API（workspace/manifests）"
          : `mock JSON fallback${ctx.apiError ? " — " + ctx.apiError : ""}`;
    }
  }

  function setupProjectSwitchHandler(ctx) {
    const list = document.getElementById("project-list");
    if (!list || list.dataset.switchBound === "1") return;
    list.dataset.switchBound = "1";
    list.addEventListener("click", async (ev) => {
      const btn = ev.target.closest("button[data-switch-project]");
      if (!btn) return;
      const projectId = btn.dataset.switchProject;
      try {
        if (ctx.source === "api") {
          await switchActiveProjectApi(projectId);
        }
        saveActiveProjectId(projectId);
        const next = await loadWorkbenchContext(projectId);
        workbenchContext = next;
        bindHomePage(next);
        log(`active project → ${projectId}`);
      } catch (err) {
        log(`switch failed: ${err.message}`);
      }
    });
  }

  function setupReviewProjectSelector(ctx) {
    const select = document.getElementById("project-switcher");
    if (!select) return;
    select.innerHTML = ctx.projects
      .map((p) => {
        const pid = p.id || p.project_id;
        const selected = pid === ctx.activeProjectId ? " selected" : "";
        return `<option value="${escapeHtml(pid)}"${selected}>${escapeHtml(p.name)}</option>`;
      })
      .join("");
    if (select.dataset.bound === "1") return;
    select.dataset.bound = "1";
    select.addEventListener("change", async () => {
      const projectId = select.value;
      try {
        if (ctx.source === "api") {
          await switchActiveProjectApi(projectId);
        }
        saveActiveProjectId(projectId);
        const next = await loadWorkbenchContext(projectId);
        workbenchContext = next;
        await loadReviewStateForProject(projectId);
        try {
          const report = await fetchIssueReport(projectId);
          issuesBySegment = indexIssues(report);
        } catch {
          issuesBySegment = {};
        }
        bindReviewPage({ segments: next.segments });
        log(`review project → ${projectId}`);
      } catch (err) {
        log(`project load failed: ${err.message}`);
      }
    });
  }

  function setupReviewClickHandler(projectId) {
    const root = document.getElementById("review-root");
    if (!root || root.dataset.bound === "1") return;
    root.dataset.bound = "1";
    root.addEventListener("click", async (ev) => {
      const btn = ev.target.closest("button[data-action]");
      if (!btn || !reviewData) return;
      const id = btn.dataset.id;
      const seg = reviewData.segments.find((s) => (s.id || s.segment_id) === id);
      if (!seg) return;
      const cfg = getConfig();
      const action = btn.dataset.action;
      let entry;
      if (action === "approve" || action === "auto") {
        entry = {
          status: "approved",
          autoApprove: action === "auto" || Boolean(cfg.AUTO_APPROVE),
          at: new Date().toISOString(),
        };
        log(`${action === "auto" ? "AUTO_APPROVE" : "manual"}: ${id} approved`);
      } else if (action === "reject") {
        entry = { status: "rejected", at: new Date().toISOString() };
        log(`rejected: ${id}`);
      } else {
        return;
      }
      await patchReviewState(projectId, { segments: { [id]: entry } });
      bindReviewPage(reviewData);
    });
  }

  async function bindExportPage(projectId) {
    const zhDir = document.getElementById("export-zh-dir");
    if (!zhDir) return;
    const projectInput = document.getElementById("export-project-id");
    if (projectInput && projectId) projectInput.value = projectId;

    async function refreshStatus() {
      const res = await fetch("/api/export/status");
      if (!res.ok) throw new Error(`export status ${res.status}`);
      const status = await res.json();
      document.getElementById("export-zh-dir").textContent = status.translated_dir;
      document.getElementById("export-bi-dir").textContent = status.bilingual_dir;
      document.getElementById("export-zh-count").textContent = String(status.translated_count);
      document.getElementById("export-bi-count").textContent = String(status.bilingual_count);
      const list = document.getElementById("export-file-list");
      if (list) {
        const files = [...(status.translated_files || []), ...(status.bilingual_files || [])];
        list.innerHTML = files.length
          ? files.map((f) => `<li>${escapeHtml(f)}</li>`).join("")
          : "<li>尚无导出文件</li>";
      }
      return status;
    }

    const refreshBtn = document.getElementById("export-refresh-btn");
    if (refreshBtn && refreshBtn.dataset.bound !== "1") {
      refreshBtn.dataset.bound = "1";
      refreshBtn.addEventListener("click", async () => {
        try {
          await refreshStatus();
          log("export status refreshed");
        } catch (err) {
          log(`export status error: ${err.message}`);
        }
      });
    }

    const runBtn = document.getElementById("export-run-btn");
    if (runBtn && runBtn.dataset.bound !== "1") {
      runBtn.dataset.bound = "1";
      runBtn.addEventListener("click", async () => {
        const pid = document.getElementById("export-project-id")?.value.trim();
        const overwrite = document.getElementById("export-overwrite")?.checked !== false;
        const resultEl = document.getElementById("export-result");
        try {
          const res = await fetch("/api/export/run", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              project_id: pid,
              source: "auto",
              overwrite,
            }),
          });
          const payload = await res.json();
          if (!res.ok) throw new Error(payload.error || `export ${res.status}`);
          if (resultEl) {
            resultEl.textContent = JSON.stringify(payload, null, 2);
          }
          await refreshStatus();
          log(`export OK: ${payload.source || "auto"}`);
        } catch (err) {
          if (resultEl) resultEl.textContent = String(err.message);
          log(`export failed: ${err.message}`);
        }
      });
    }

    try {
      await refreshStatus();
    } catch (err) {
      log(`export status error: ${err.message}`);
    }
  }

  document.addEventListener("DOMContentLoaded", async () => {
    try {
      if (document.getElementById("export-zh-dir")) {
        const params = new URLSearchParams(window.location.search);
        await bindExportPage(params.get("project") || loadActiveProjectId());
        return;
      }

      if (document.getElementById("api-status-card")) {
        await bindApiStatusPanel();
        setupQuickstartForm();
      }

      if (document.getElementById("issues-root")) {
        const params = new URLSearchParams(window.location.search);
        let preferredProject = params.get("project") || "";
        if (!preferredProject) {
          try {
            const registry = await fetchProjectsApi();
            preferredProject =
              registry.active_project_id || registry.projects?.[0]?.id || "";
          } catch {
            preferredProject = loadActiveProjectId() || "";
          }
        }
        currentIssuesProjectId = preferredProject;
        await loadReviewStateForProject(preferredProject);
        const report = await fetchIssueReport(preferredProject);
        bindIssuesPage(report);
        setupIssueHandlers(report);
        const src = report._source === "api" ? "quality-review API" : "static asset";
        log(`issue report loaded (${report.issues.length} items · ${src})`);
        return;
      }

      const params = new URLSearchParams(window.location.search);
      const preferredProject = params.get("project") || "";
      workbenchContext = await loadWorkbenchContext(preferredProject);
      await loadReviewStateForProject(workbenchContext.activeProjectId);

      try {
        const report = await fetchIssueReport(workbenchContext.activeProjectId);
        issuesBySegment = indexIssues(report);
      } catch {
        issuesBySegment = {};
      }

      bindHomePage(workbenchContext);
      setupProjectSwitchHandler(workbenchContext);
      setupReviewProjectSelector(workbenchContext);
      setupReviewClickHandler(workbenchContext.activeProjectId);
      bindReviewPage({ segments: workbenchContext.segments });
      await runAutoApproveIfEnabled(
        { segments: workbenchContext.segments },
        workbenchContext.activeProjectId
      );
      log(
        `loaded ${workbenchContext.segments.length} segment(s) from ${workbenchContext.source}` +
          (workbenchContext.activeProjectId ? ` · project=${workbenchContext.activeProjectId}` : "")
      );
    } catch (err) {
      log(`error: ${err.message}`);
      console.error(err);
    }
  });
})();
