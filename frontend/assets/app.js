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
  let runtimeApiStatus = null;
  let quickstartGenerating = false;
  let quickstartRealApiInFlight = false;
  let currentGenerationJob = null;
  let generationPollTimer = null;
  let generationPollProjectId = "";
  let quickstartPollTimer = null;
  let reviewSelectedSegmentId = null;

  const SEGMENT_STATUS_ZH = {
    pending: "待审核",
    approved: "已通过",
    rejected: "已驳回",
    draft: "草稿",
  };

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

  const WORKBENCH_MODE_ZH = {
    production: "生产模式",
    pilot: "Pilot 试跑",
    quickstart: "Quickstart 试译",
  };

  function workbenchModeLabel(status) {
    const mode = status?.workbench_mode || "quickstart";
    return WORKBENCH_MODE_ZH[mode] || mode;
  }

  function apiModeLabel(status) {
    if (!status) return "加载中…";
    if (status.has_api_key && status.api_mode === "real_api" && !status.workbench_real_api_ready) {
      return "Key 已配置，Workbench 真实 API 暂不可调用";
    }
    switch (status.api_mode) {
      case "real_api":
        return status.workbench_real_api_ready ? "真实 API 可用" : "Key 已配置，Workbench 真实 API 暂不可调用";
      case "dry_run":
        return "dry-run（有 Key，页面生成默认仍为 mock）";
      case "missing_api_key":
        return "MOCK / dry-run — 无 API Key";
      default:
        return String(status.api_mode || "unknown");
    }
  }

  function updateModeBanner(status) {
    const banner = document.getElementById("mode-banner");
    if (!banner || !status) return;
    banner.textContent = `${workbenchModeLabel(status)} · ${apiModeLabel(status)} · api_mode=${status.api_mode}`;
  }

  function draftPanelTitle(status, segment) {
    if (segment?.generated_by === "real_api") return "译文（真实 API）";
    if (status?.api_mode === "real_api") return "译文";
    return "译文（mock / dry-run）";
  }

  function showPageError(message) {
    const targets = [
      document.getElementById("review-root"),
      document.getElementById("project-list"),
      document.querySelector("main"),
    ].filter(Boolean);
    const root = targets[0];
    if (!root) return;
    root.innerHTML = `<div class="card"><p class="meta">${escapeHtml(message)}</p></div>`;
  }

  const EXPORT_SKIP_STATUS_ZH = {
    pending: "待审核",
    rejected: "已驳回",
    approved: "已通过",
    draft: "草稿",
  };

  function formatExportSkipStatus(skipped) {
    if (!skipped || typeof skipped !== "object") return "";
    const entries = Object.entries(skipped);
    if (!entries.length) return "";
    return entries
      .map(([key, value]) => {
        const label = EXPORT_SKIP_STATUS_ZH[key] || key;
        return `${label}(${key}):${value}`;
      })
      .join(", ");
  }

  function formatExportResult(payload) {
    if (!payload || typeof payload !== "object") return String(payload);
    const skipped = payload.segments_skipped_status || {};
    const skippedText = formatExportSkipStatus(skipped);
    const lines = [
      payload.skipped ? "导出跳过（文件已存在）" : "导出成功",
      payload.source ? `source=${payload.source}` : null,
      payload.project_id ? `project_id=${payload.project_id}` : null,
      payload.status_mode ? `status_mode=${payload.status_mode}` : null,
      payload.segments_total != null ? `segments_total=${payload.segments_total}` : null,
      payload.segments_exported != null ? `segments_exported=${payload.segments_exported}` : null,
      skippedText ? `segments_skipped_status=${skippedText}` : null,
      payload.translated_path ? `translated: ${payload.translated_path}` : null,
      payload.bilingual_path ? `bilingual: ${payload.bilingual_path}` : null,
      payload.message ? String(payload.message) : null,
    ].filter(Boolean);
    return lines.join("\n");
  }

  function formatTranslationAssetsResult(payload) {
    if (!payload || typeof payload !== "object") return String(payload);
    if (payload.exists === false) {
      return `尚未构建翻译记忆资产\nproject_id=${payload.project_id || ""}\nasset_path=${payload.asset_path || ""}`;
    }
    const stats = payload.stats || {};
    return [
      "翻译记忆资产可用",
      payload.project_id ? `project_id=${payload.project_id}` : null,
      payload.mode ? `mode=${payload.mode}` : null,
      payload.status_mode ? `status_mode=${payload.status_mode}` : null,
      payload.asset_path ? `asset_path=${payload.asset_path}` : null,
      stats.pairs != null ? `pairs=${stats.pairs}` : null,
      stats.term_candidates != null ? `term_candidates=${stats.term_candidates}` : null,
      stats.proper_noun_candidates != null ? `proper_noun_candidates=${stats.proper_noun_candidates}` : null,
      stats.api_calls != null ? `api_calls=${stats.api_calls}` : null,
      payload.created_at ? `created_at=${payload.created_at}` : null,
    ]
      .filter(Boolean)
      .join("\n");
  }

  function exportHighlightPaths(payload) {
    const paths = [];
    if (payload?.translated_path) paths.push(payload.translated_path);
    if (payload?.bilingual_path) paths.push(payload.bilingual_path);
    return paths;
  }

  async function refreshRuntimeApiStatus() {
    try {
      runtimeApiStatus = await fetchApiStatus();
      updateModeBanner(runtimeApiStatus);
      bindProductionResumeCard(runtimeApiStatus);
      return runtimeApiStatus;
    } catch (err) {
      if (document.getElementById("status-log")) {
        log(`api status error: ${err.message}`);
      }
      return null;
    }
  }

  async function fetchProductionRuns() {
    const res = await fetch("/api/runtime/production-runs");
    if (!res.ok) throw new Error(`/api/runtime/production-runs ${res.status}`);
    return res.json();
  }

  async function fetchProductionRunSegments(runId, chapter) {
    const params = new URLSearchParams();
    if (chapter) params.set("chapter", String(chapter));
    const qs = params.toString();
    const url = `/api/runtime/production-runs/${encodeURIComponent(runId)}/segments${qs ? `?${qs}` : ""}`;
    const res = await fetch(url);
    if (!res.ok) {
      const payload = await res.json().catch(() => ({}));
      throw new Error(payload.error || `production segments ${res.status}`);
    }
    return res.json();
  }

  function gateWarningCleanupCommand(warning) {
    const text = String(warning || "");
    if (text.startsWith("stale_lock:")) {
      const lockMatch = text.match(/stale_lock:\s*(\S+)/);
      const lockName = lockMatch?.[1] || "";
      return {
        label: `过期 worker 锁：${lockName}（进程已退出，可安全清理）`,
        command: "python3 scripts/pipeline_worker_registry.py --heal --json",
        altCommand: lockName ? `rm workspace/.locks/${lockName}` : "",
      };
    }
    return { label: text, command: "", altCommand: "" };
  }

  function renderGateWarnings(gate) {
    const ul = document.getElementById("pipeline-gate-warnings");
    if (!ul) return;
    ul.innerHTML = "";
    const warnings = (gate && gate.warnings) || [];
    if (!warnings.length) {
      ul.hidden = true;
      return;
    }
    ul.hidden = false;
    for (const w of warnings.slice(0, 8)) {
      const parsed = gateWarningCleanupCommand(w);
      const li = document.createElement("li");
      li.className = "gate-warning-item";
      const label = document.createElement("span");
      label.textContent = parsed.label;
      li.appendChild(label);
      if (parsed.command) {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.textContent = "复制清理命令";
        btn.addEventListener("click", async () => {
          try {
            await navigator.clipboard.writeText(parsed.command);
            log("已复制 Gate 清理命令");
          } catch {
            log(`复制失败：${parsed.command}`);
          }
        });
        li.appendChild(btn);
      }
      ul.appendChild(li);
    }
  }

  function bindProductionRunsDashboard(status) {
    const panel = document.getElementById("production-runs-panel");
    const grid = document.getElementById("production-runs-grid");
    if (!panel || !grid) return;
    const ps = status?.pipeline_status;
    const cards = ps?.active_run_cards || [];
    const hasRun = cards.length > 0 || Boolean(ps?.has_production_run);
    panel.hidden = !hasRun;
    const prodCta = document.getElementById("triage-production-cta");
    const quickCta = document.getElementById("triage-quickstart-cta");
    const nextHint = document.getElementById("triage-next-hint");
    if (prodCta) prodCta.hidden = !hasRun;
    if (quickCta) quickCta.classList.toggle("primary-cta", !hasRun);
    if (prodCta) prodCta.classList.toggle("primary-cta", hasRun);
    if (nextHint) {
      nextHint.textContent = hasRun
        ? "生产批次已就绪：可续跑翻译或进入对照审核。"
        : "创建 dry-run 项目 → 粘贴样本文本 → 进入对照审核。";
    }
    if (!hasRun) {
      grid.innerHTML = "";
      return;
    }
    const rows = cards.length
      ? cards
      : ps?.run_id
        ? [
            {
              run_id: ps.run_id,
              task_label: ps.phase === "refine" ? "历史润色任务（已禁用）" : "翻译批次",
              chapter_range_label: ps.chapter_range_label,
              status: ps.status,
              segment_progress_label: ps.segment_progress_label,
              last_heartbeat: ps.last_heartbeat,
              resume_command: ps.resume_command,
              review_url: `/review.html?production_run=${encodeURIComponent(ps.run_id)}`,
              is_default: true,
            },
          ]
        : [];
    grid.innerHTML = rows
      .map((card, idx) => {
        const cardId = `prod-run-card-${idx}`;
        return `<article class="production-run-card" id="${cardId}">
          <h3>${escapeHtml(card.task_label || "生产任务")}${card.is_default ? "（默认）" : ""}</h3>
          <p class="meta">${[
            `run_id：${card.run_id || "—"}`,
            card.chapter_range_label ? `章节：${card.chapter_range_label}` : "",
            card.status ? `状态：${card.status}` : "",
          ]
            .filter(Boolean)
            .join(" · ")}</p>
          <p class="meta">段落进度：${escapeHtml(card.segment_progress_label || "—")}</p>
          <p class="meta">最近心跳：${escapeHtml(card.last_heartbeat || "—")}</p>
          <p class="meta"><code class="prod-resume-cmd">${escapeHtml(card.resume_command || "—")}</code></p>
          <div class="actions">
            <button type="button" class="prod-copy-cmd-btn" data-cmd="${escapeHtml(card.resume_command || "")}">复制续跑命令</button>
            <a class="button-link" href="${escapeHtml(card.review_url || "/review.html")}">对照审核</a>
          </div>
        </article>`;
      })
      .join("");
    grid.querySelectorAll(".prod-copy-cmd-btn").forEach((btn) => {
      if (btn.dataset.bound === "1") return;
      btn.dataset.bound = "1";
      btn.addEventListener("click", async () => {
        const cmd = btn.getAttribute("data-cmd") || "";
        if (!cmd) return;
        try {
          await navigator.clipboard.writeText(cmd);
          log("已复制生产续跑命令");
        } catch {
          log(`复制失败，请手动复制：${cmd}`);
        }
      });
    });
  }

  function bindProductionResumeCard(status) {
    bindProductionRunsDashboard(status);
  }

  function nextRequestId(prefix) {
    const rand = Math.random().toString(36).slice(2, 10);
    return `${prefix}-${Date.now()}-${rand}`;
  }

  function validateProjectIdClient(projectId) {
    const raw = String(projectId || "");
    const messages = {
      "project_id must not contain leading or trailing whitespace": "项目 ID 首尾不能有空格",
      "project_id is required": "请填写项目 ID",
      "project_id must not be '.' or '..'": "项目 ID 不能为 '.' 或 '..'",
      "project_id must not contain '..'": "项目 ID 不能包含 '..'（路径穿越）",
      "project_id must not contain path separators": "项目 ID 不能包含 / 或 \\（请只用字母、数字、下划线、连字符）",
      "project_id must not contain whitespace": "项目 ID 不能包含空格",
      "project_id must start with a letter or digit and contain only letters, digits, '_' or '-'":
        "项目 ID 须以字母或数字开头，且仅含字母、数字、下划线或连字符（最多 64 字符）",
    };
    const toZh = (key) => messages[key] || key;
    if (raw !== raw.trim()) {
      return toZh("project_id must not contain leading or trailing whitespace");
    }
    const normalized = raw.trim();
    if (!normalized) return toZh("project_id is required");
    if (normalized === "." || normalized === "..") return toZh("project_id must not be '.' or '..'");
    if (normalized.includes("..")) return toZh("project_id must not contain '..'");
    if (normalized.includes("/") || normalized.includes("\\")) {
      return toZh("project_id must not contain path separators");
    }
    if (/\s/.test(normalized)) return toZh("project_id must not contain whitespace");
    if (!/^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$/.test(normalized)) {
      return toZh(
        "project_id must start with a letter or digit and contain only letters, digits, '_' or '-'"
      );
    }
    return null;
  }

  function reviewIncludeHiddenProjects() {
    return document.getElementById("show-test-projects")?.checked === true;
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

  function openIssuesForSegment(segId, issueState) {
    return (issuesBySegment[segId] || []).filter(
      (issue) => issueStatus(issue, issueState) === "open"
    );
  }

  function reviewSegmentIds() {
    return (reviewData?.segments || []).map((seg) => seg.id || seg.segment_id).filter(Boolean);
  }

  function focusSelectedSegmentButton() {
    if (!reviewSelectedSegmentId) return;
    const el = document.getElementById(`seg-${reviewSelectedSegmentId}`);
    if (!el) return;
    el.focus({ preventScroll: true });
    el.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function selectReviewSegmentByOffset(offset) {
    const ids = reviewSegmentIds();
    if (!ids.length) return false;
    const currentIndex = Math.max(0, ids.indexOf(reviewSelectedSegmentId));
    const nextIndex = Math.min(ids.length - 1, Math.max(0, currentIndex + offset));
    reviewSelectedSegmentId = ids[nextIndex];
    bindReviewPage(reviewData);
    focusSelectedSegmentButton();
    log(`review shortcut: selected ${reviewSelectedSegmentId}`);
    return true;
  }

  function segmentStatusBadgeClass(status) {
    if (status === "approved") return "badge-success";
    if (status === "rejected") return "badge-danger";
    if (status === "pending") return "badge-warning";
    return "badge-neutral";
  }

  function renderBadge(status) {
    const label = SEGMENT_STATUS_ZH[status] || status;
    const cls = segmentStatusBadgeClass(status);
    return `<span class="badge ${cls}" data-status="${status}" title="${escapeHtml(label)}（${escapeHtml(status)}）">${escapeHtml(label)}</span>`;
  }

  function generationModeBadge(segment) {
    if (segment?.generated_by === "real_api") {
      return '<span class="badge badge-real-api">真实 API</span>';
    }
    return '<span class="badge badge-mock">mock</span>';
  }

  function showQuickstartError(message, fieldId) {
    const bar = document.getElementById("quickstart-error-bar");
    if (bar) {
      bar.hidden = false;
      bar.textContent = message;
    }
    const resultEl = document.getElementById("quickstart-result");
    if (resultEl) resultEl.textContent = "";
    for (const id of ["qs-project-id-label"]) {
      const label = document.getElementById(id);
      if (label) label.classList.remove("field-error");
    }
    if (fieldId) {
      const label = document.getElementById(`${fieldId}-label`) || document.getElementById(fieldId)?.closest("label");
      if (label) label.classList.add("field-error");
      const hint = document.getElementById(`${fieldId}-hint`);
      if (hint) {
        hint.hidden = false;
        hint.textContent = message;
      }
    }
  }

  function clearQuickstartError() {
    const bar = document.getElementById("quickstart-error-bar");
    if (bar) {
      bar.hidden = true;
      bar.textContent = "";
    }
    const label = document.getElementById("qs-project-id-label");
    if (label) label.classList.remove("field-error");
    const hint = document.getElementById("qs-project-id-hint");
    if (hint) {
      hint.hidden = true;
      hint.textContent = "";
    }
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
    let apiFailed = false;
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
        apiFailed = true;
      } catch (_apiErr) {
        apiFailed = true;
        /* fallback */
      }
    }
    const res = await fetch("/assets/review-issue-report.json");
    if (!res.ok) throw new Error(`review-issue-report.json ${res.status}`);
    const payload = await res.json();
    payload._source = apiFailed ? "fallback_fixture" : "fixture";
    payload.project_id = payload.project_id || pid || "";
    return payload;
  }

  async function fetchProjectsApi(options = {}) {
    const params = new URLSearchParams();
    if (options.includeTest) params.set("include_test", "true");
    if (options.includeHistory) params.set("include_history", "true");
    const qs = params.toString() ? `?${params.toString()}` : "";
    const res = await fetch(`/api/projects${qs}`);
    if (!res.ok) throw new Error(`/api/projects ${res.status}`);
    return res.json();
  }

  function categoryBadge(category) {
    switch (category) {
      case "example":
        return '<span class="badge badge-success">示例</span>';
      case "test":
        return '<span class="badge badge-mock">测试</span>';
      case "history":
        return '<span class="badge badge-neutral">历史</span>';
      default:
        return '<span class="badge badge-success">用户</span>';
    }
  }

  function isHiddenProjectCategory(category) {
    return category === "test" || category === "history";
  }

  function visibleHomeProjects(projects, activeId) {
    return (projects || []).filter((p) => {
      const cat = p.category || "user";
      if (isHiddenProjectCategory(cat)) return false;
      return true;
    });
  }

  function setQuickstartGenerating(active) {
    quickstartGenerating = Boolean(active);
    const ready = runtimeApiStatus?.workbench_real_api_ready === true;
    for (const id of ["qs-dry-run-btn", "qs-real-api-btn", "qs-real-api-btn-hero"]) {
      const el = document.getElementById(id);
      if (!el) continue;
      if (id === "qs-real-api-btn" || id === "qs-real-api-btn-hero") {
        el.disabled = quickstartGenerating || quickstartRealApiInFlight || !ready;
      } else {
        el.disabled = quickstartGenerating;
      }
    }
  }

  function syncRealApiHeroCta(status) {
    const heroBtn = document.getElementById("qs-real-api-btn-hero");
    const reasonEl = document.getElementById("real-api-disabled-reason");
    if (!heroBtn) return;
    const ready = status?.workbench_real_api_ready === true;
    heroBtn.disabled = !ready || quickstartGenerating || quickstartRealApiInFlight;
    const reason =
      status?.workbench_real_api_block_reason_label ||
      status?.workbench_real_api_block_reason ||
      (!status?.has_api_key ? "未配置 API Key" : "预算或开关未满足");
    heroBtn.title = ready ? "跳转至创建表单并调用真实 API" : reason;
    if (reasonEl) {
      if (ready) {
        reasonEl.hidden = true;
        reasonEl.textContent = "";
      } else {
        reasonEl.hidden = false;
        reasonEl.textContent = `真实 API 不可用：${reason}`;
      }
    }
    if (heroBtn.dataset.bound !== "1") {
      heroBtn.dataset.bound = "1";
      heroBtn.addEventListener("click", () => {
        document.getElementById("quickstart-card")?.scrollIntoView({ behavior: "smooth" });
        document.getElementById("qs-real-api-btn")?.click();
      });
    }
  }

  function formatGenerateError(payload, fallback) {
    const code = payload?.error_code || payload?.error || null;
    const reason = payload?.message || payload?.error || fallback;
    const hint = payload?.hint ? `（建议：${payload.hint}）` : "";
    if (payload?.cost_guard) {
      const cg = payload.cost_guard;
      return `${reason}（预算上限 MAX_TEST_COST_USD=${cg.max_test_cost_usd ?? "—"}，预估/已用=${cg.projected_cost ?? cg.spent_usd ?? "—"}）`;
    }
    if (code) return `${code}: ${reason}${hint}`;
    return String(reason);
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

  async function runProjectLifecycleApi(projectId, action, extra = {}) {
    const res = await fetch(`/api/projects/${encodeURIComponent(projectId)}/lifecycle`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action, ...extra }),
    });
    const payload = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(payload.error || `${action} ${res.status}`);
    return payload;
  }

  function applyQuickstartPrefill(project) {
    if (!project || !document.getElementById("quickstart-form")) return;
    const projectId = project.id || project.project_id || "";
    const name = project.name || projectId;
    const direction = project.direction || project.language_direction || "JP_TO_CN";
    const idEl = document.getElementById("qs-project-id");
    const nameEl = document.getElementById("qs-project-name");
    const dirEl = document.getElementById("qs-direction");
    if (idEl && !idEl.value.trim()) idEl.value = projectId;
    if (nameEl && !nameEl.value.trim()) nameEl.value = name;
    if (dirEl && direction) dirEl.value = direction;
  }

  async function loadWorkbenchContext(preferredProjectId, options = {}) {
    const includeHidden = Boolean(options.includeHidden);
    const explicitProjectId = String(preferredProjectId || "").trim();
    try {
      const registry = await fetchProjectsApi({
        includeTest: includeHidden,
        includeHistory: includeHidden,
      });
      const projects = registry.projects || [];
      const projectIdOf = (p) => p.id || p.project_id;
      const visibleIds = new Set(projects.map(projectIdOf));

      if (explicitProjectId) {
        const payload = await fetchWorkbenchDataApi(explicitProjectId);
        saveActiveProjectId(explicitProjectId);
        const projectSummary =
          payload.project ||
          projects.find((p) => projectIdOf(p) === explicitProjectId) || {
            id: explicitProjectId,
            project_id: explicitProjectId,
            name: explicitProjectId,
          };
        const mergedProjects = [...projects];
        if (!mergedProjects.some((p) => projectIdOf(p) === explicitProjectId)) {
          mergedProjects.push(projectSummary);
        }
        return {
          source: "api",
          projects: mergedProjects,
          activeProjectId: explicitProjectId,
          segments: payload.segments || [],
          activeProject: projectSummary,
          explicitProject: true,
        };
      }

      const pickVisible = (candidate) =>
        candidate && visibleIds.has(candidate) ? candidate : null;
      const activeId =
        pickVisible(registry.active_project_id) ||
        pickVisible(loadActiveProjectId()) ||
        projectIdOf(projects[0]) ||
        null;
      if (!activeId) throw new Error("no projects in registry");
      const payload = await fetchWorkbenchDataApi(activeId);
      saveActiveProjectId(activeId);
      return {
        source: "api",
        projects,
        activeProjectId: activeId,
        segments: payload.segments || [],
        activeProject: payload.project || projects.find((p) => projectIdOf(p) === activeId),
      };
    } catch (apiErr) {
      if (explicitProjectId) {
        throw apiErr;
      }
      const mock = await fetchMockData();
      const activeId = loadActiveProjectId() || mock.projects?.[0]?.id;
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

  async function fetchGenerationJob(projectId) {
    if (!projectId) return null;
    const res = await fetch(`/api/projects/${encodeURIComponent(projectId)}/generation-job`);
    if (!res.ok) throw new Error(`generation-job ${res.status}`);
    const payload = await res.json();
    return payload.generation_job || null;
  }

  async function refreshGenerationJob(projectId) {
    if (!projectId) {
      currentGenerationJob = null;
      return null;
    }
    try {
      currentGenerationJob = await fetchGenerationJob(projectId);
      return currentGenerationJob;
    } catch {
      currentGenerationJob = null;
      return null;
    }
  }

  function stopGenerationPolling() {
    if (generationPollTimer) {
      window.clearInterval(generationPollTimer);
      generationPollTimer = null;
    }
    generationPollProjectId = "";
  }

  function startGenerationPolling(projectId) {
    if (!projectId) return;
    if (generationPollTimer && generationPollProjectId === projectId) return;
    stopGenerationPolling();
    generationPollProjectId = projectId;
    generationPollTimer = window.setInterval(async () => {
      const job = await refreshGenerationJob(projectId);
      const st = String(job?.status || "").toLowerCase();
      if (st === "queued" || st === "running") return;
      stopGenerationPolling();
      if (!job) return;
      if (st === "succeeded") {
        try {
          const includeHidden = reviewIncludeHiddenProjects();
          const next = await loadWorkbenchContext(projectId, { includeHidden });
          workbenchContext = next;
          await loadReviewStateForProject(projectId);
          bindReviewPage({ segments: next.segments || [] });
          if (document.getElementById("project-list")) bindHomePage(next);
          log(`generation completed: ${projectId}`);
        } catch (err) {
          log(`generation refresh failed: ${err.message}`);
        }
      } else if (st === "failed") {
        const reason = job.error_message || job.error_code || "unknown";
        log(`generation failed: ${reason}`);
        if (document.getElementById("review-root")) {
          bindReviewPage({ segments: workbenchContext?.segments || [] });
        }
      }
    }, 2000);
  }

  function generationJobHint(job) {
    if (!job) return "尚无生成任务记录。";
    const req = job.request_id ? `request_id=${job.request_id}` : "request_id=—";
    if (job.status === "queued" || job.status === "running") {
      return `生成任务进行中（${job.status}，${req}）。可留在本页等待，或返回首页继续操作。`;
    }
    if (job.status === "failed") {
      return `上次生成失败（${job.error_code || "generation_failed"}）。${job.error_message || "请返回首页重试。"}`;
    }
    if (job.status === "succeeded") {
      return `最近一次生成成功（segments=${job.segments_created || 0}，${req}）。`;
    }
    return `最近任务状态：${job.status || "unknown"}（${req}）。`;
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
      const status = await refreshRuntimeApiStatus();
      if (!status) {
        modeEl.textContent = "unavailable";
        return;
      }
      modeEl.textContent = status.api_mode || "unknown";
      const keyEl = document.getElementById("api-key-status");
      const realEl = document.getElementById("real-api-enabled-status");
      const smokeEl = document.getElementById("api-smoke-summary");
      const hintEl = document.getElementById("api-config-hint");
      const realGenBtn = document.getElementById("qs-real-api-btn");
      const realGenHint = document.getElementById("qs-real-api-hint");
      if (keyEl) {
        keyEl.textContent = status.has_api_key
          ? `已配置 (${status.detected_providers.join(", ")})`
          : "missing_api_key";
      }
      if (realEl) realEl.textContent = String(Boolean(status.real_api_tests_enabled));
      const budgetEl = document.getElementById("api-budget-summary");
      if (budgetEl) {
        budgetEl.textContent = `预算：MAX_TEST_COST_USD=${status.max_test_cost_usd} · MAX_TOKENS_PER_RUN=${status.max_tokens_per_run}`;
      }
      const keyReadyEl = document.getElementById("api-key-ready");
      if (keyReadyEl) {
        keyReadyEl.textContent = status.has_api_key
          ? `API Key：已配置（${(status.detected_providers || []).join(", ") || "—"}）`
          : "API Key：未配置";
      }
      const readyEl = document.getElementById("api-workbench-ready");
      if (readyEl) {
        readyEl.textContent = status.workbench_real_api_ready
          ? "Workbench 页面真实 API：可调用"
          : `Workbench 页面真实 API：不可调用（${status.workbench_real_api_block_reason_label || status.workbench_real_api_block_reason || "—"}）`;
      }
      const fixEl = document.getElementById("api-budget-fix");
      const fixTextEl = document.getElementById("api-budget-fix-text");
      const copyFixBtn = document.getElementById("api-copy-fix-cmd");
      const diagnosticLink = document.getElementById("api-diagnostic-link");
      const startupCmd =
        status.workbench_real_api_fix_command ||
        "export REAL_API_TESTS_ENABLED=true MAX_TEST_COST_USD=0.01 && npm run dev:frontend";
      if (fixEl) {
        if (status.workbench_real_api_fix_command || !status.workbench_real_api_ready) {
          fixEl.hidden = false;
          if (fixTextEl) {
            fixTextEl.textContent = status.workbench_real_api_ready
              ? ""
              : `一键启动（安全预算，不写入 .env）：${startupCmd}`;
          } else {
            fixEl.textContent = `修复命令（可复制）：${startupCmd}`;
          }
        } else {
          fixEl.hidden = true;
          if (fixTextEl) fixTextEl.textContent = "";
        }
      }
      if (copyFixBtn && copyFixBtn.dataset.bound !== "1") {
        copyFixBtn.dataset.bound = "1";
        copyFixBtn.addEventListener("click", async () => {
          const cmd =
            runtimeApiStatus?.workbench_real_api_fix_command ||
            "export REAL_API_TESTS_ENABLED=true MAX_TEST_COST_USD=0.01 && npm run dev:frontend";
          try {
            await navigator.clipboard.writeText(cmd);
            log("已复制启动命令到剪贴板");
          } catch {
            log(`复制失败，请手动复制：${cmd}`);
          }
        });
      }
      if (diagnosticLink && diagnosticLink.dataset.bound !== "1") {
        diagnosticLink.dataset.bound = "1";
        diagnosticLink.addEventListener("click", (ev) => {
          ev.preventDefault();
          const smoke = document.getElementById("api-smoke-history");
          if (smoke) {
            smoke.open = true;
            smoke.scrollIntoView({ behavior: "smooth", block: "nearest" });
          }
        });
      }
      if (smokeEl) {
        if (!status.last_smoke) {
          smokeEl.textContent = "尚无历史 smoke 记录";
        } else {
          const ls = status.last_smoke;
          const parts = [
            `mode=${ls.mode}`,
            `success=${ls.success}`,
            ls.created_at || "—",
          ];
          if (ls.ignorable && ls.ignorable_note) {
            parts.push(`（${ls.ignorable_note}）`);
          } else if (!ls.success && ls.error_summary) {
            parts.push(String(ls.error_summary));
          }
          smokeEl.textContent = parts.join(" · ");
        }
      }
      const runnerNote = document.getElementById("api-runner-note");
      if (runnerNote) {
        runnerNote.textContent = status.runner_status_note || "";
      }
      if (hintEl) hintEl.textContent = status.config_hint || "—";
      const pipelineSummary = document.getElementById("pipeline-gate-summary");
      const pipelineFixes = document.getElementById("pipeline-gate-fixes");
      const gate = status.pipeline_gate;
      if (pipelineSummary) {
        if (!gate) {
          pipelineSummary.textContent = "Gate 状态不可用";
        } else {
          pipelineSummary.textContent = [
            `决策：${gate.decision || "—"}`,
            gate.draft_completed_chapters != null
              ? `翻译完成章：${gate.draft_completed_chapters}`
              : null,
            `可导出章：${gate.exportable_chapters ?? gate.draft_completed_chapters ?? "—"}`,
            `活跃 worker：${gate.active_worker_count ?? 0}`,
            gate.stage_state_run_id ? `stage_state：${gate.stage_state_run_id} (${gate.stage_state_source || "—"})` : "",
          ]
            .filter(Boolean)
            .join(" · ");
        }
      }
      renderGateWarnings(gate);
      if (pipelineFixes) {
        pipelineFixes.innerHTML = "";
        const fixes = (gate && gate.fix_paths) || [];
        for (const step of fixes.slice(0, 5)) {
          const li = document.createElement("li");
          li.textContent = step.replace(/^rm -f /, "删除锁文件：");
          pipelineFixes.appendChild(li);
        }
        if (!fixes.length && gate && (gate.blocks || []).length) {
          const li = document.createElement("li");
          li.textContent = (gate.blocks || []).join("；");
          pipelineFixes.appendChild(li);
        }
      }
      if (realGenBtn) {
        realGenBtn.disabled =
          !status.workbench_real_api_ready || quickstartGenerating || quickstartRealApiInFlight;
        realGenBtn.title = status.workbench_real_api_ready
          ? `调用 OpenRouter（预算上限 $${status.max_test_cost_usd}）`
          : status.workbench_real_api_block_reason_label ||
            status.workbench_real_api_block_reason ||
            "真实 API 不可用";
      }
      syncRealApiHeroCta(status);
      if (realGenHint) {
        realGenHint.textContent = status.workbench_real_api_ready
          ? `真实 API 小样本：最多 3 段、每段 ≤400 字；预算上限 MAX_TEST_COST_USD=${status.max_test_cost_usd}。`
          : `页面 dry-run 始终为 mock。Workbench 真实 API 需 Key + REAL_API_TESTS_ENABLED=true + MAX_TEST_COST_USD>0（当前阻塞：${status.workbench_real_api_block_reason_label || status.workbench_real_api_block_reason || "—"}）。`;
      }
      const summary = document.getElementById("config-summary");
      if (summary) {
        summary.textContent = `apiMode=${status.api_mode}, has_key=${status.has_api_key}, real_enabled=${status.real_api_tests_enabled}`;
      }
      setQuickstartGenerating(quickstartGenerating);
    } catch (err) {
      modeEl.textContent = "unavailable";
      log(`api status error: ${err.message}`);
    }
  }

  async function ensureQuickstartProject(projectId, name, direction, resultEl) {
    const createRes = await fetch("/api/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        project_id: projectId,
        name,
        language_direction: direction,
      }),
    });
    if (createRes.status === 400) {
      const errPayload = await createRes.json().catch(() => ({}));
      const msg = String(errPayload.error || "");
      if (msg.includes("already exists")) {
        const existing = await fetchWorkbenchDataApi(projectId);
        const segCount = existing.segments?.length || 0;
        const confirmed = window.confirm(
          `项目「${projectId}」已存在（${segCount} 个 segment）。重新生成将覆盖现有内容。继续？`
        );
        if (!confirmed) {
          if (resultEl) resultEl.textContent = "已取消：未覆盖已有项目。";
          return false;
        }
        await switchActiveProjectApi(projectId);
      } else {
        throw new Error(msg || "invalid project_id");
      }
    } else if (!createRes.ok) {
      throw new Error(`create project ${createRes.status}`);
    }
    return true;
  }

  function stopQuickstartPolling() {
    if (quickstartPollTimer) {
      window.clearInterval(quickstartPollTimer);
      quickstartPollTimer = null;
    }
  }

  function applyQuickstartSuccess(projectId, genPayload, mode, resultEl, reviewLink) {
    clearQuickstartError();
    currentGenerationJob = genPayload.generation_job || currentGenerationJob;
    saveActiveProjectId(projectId);
    const label = mode === "real_api" ? "真实 API" : "dry-run mock";
    if (resultEl) {
      resultEl.textContent = `已用 ${label} 生成 ${genPayload.segments_created} 个 segment，可进入审核。`;
    }
    if (reviewLink) {
      reviewLink.href = genPayload.review_url || `/review.html?project=${encodeURIComponent(projectId)}`;
      reviewLink.hidden = false;
    }
  }

  async function pollQuickstartGeneration(projectId, requestId, mode, resultEl, reviewLink) {
    stopQuickstartPolling();
    if (resultEl) resultEl.textContent = "生成进行中，请稍候…";
    return new Promise((resolve, reject) => {
      const started = Date.now();
      const timeoutMs = 120000;
      quickstartPollTimer = window.setInterval(async () => {
        if (Date.now() - started > timeoutMs) {
          stopQuickstartPolling();
          reject(new Error("generation poll timeout"));
          return;
        }
        try {
          const job = await refreshGenerationJob(projectId);
          const jobReq = String(job?.request_id || "");
          const st = String(job?.status || "").toLowerCase();
          if (st === "queued" || st === "running") return;
          stopQuickstartPolling();
          if (st === "succeeded") {
            const replay =
              job && jobReq === requestId && job.response_payload && typeof job.response_payload === "object"
                ? job.response_payload
                : {
                    project_id: projectId,
                    request_id: requestId,
                    segments_created: job?.segments_created || 0,
                    review_url: `/review.html?project=${encodeURIComponent(projectId)}`,
                    generation_job: job,
                  };
            resolve(replay);
            return;
          }
          if (st === "failed") {
            reject(new Error(job?.error_message || job?.error_code || "generation_failed"));
            return;
          }
          reject(new Error("generation job missing after conflict"));
        } catch (err) {
          stopQuickstartPolling();
          reject(err);
        }
      }, 1500);
    });
  }

  async function runQuickstartGenerate(
    projectId,
    sampleText,
    mode,
    resultEl,
    reviewLink,
    requestId = ""
  ) {
    const endpoint =
      mode === "real_api"
        ? `/api/projects/${encodeURIComponent(projectId)}/real-api-generate`
        : `/api/projects/${encodeURIComponent(projectId)}/dry-run-generate`;
    const stableRequestId =
      requestId || nextRequestId(mode === "real_api" ? "realapi" : "dryrun");
    try {
      const genRes = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          sample_text: sampleText,
          request_id: stableRequestId,
        }),
      });
      let genPayload = await genRes.json().catch(() => ({}));
      if (
        genRes.status === 409 &&
        (genPayload?.error === "generation_in_progress" ||
          genPayload?.error_code === "generation_in_progress")
      ) {
        currentGenerationJob = genPayload.generation_job || currentGenerationJob;
        genPayload = await pollQuickstartGeneration(
          projectId,
          genPayload.request_id || stableRequestId,
          mode,
          resultEl,
          reviewLink
        );
      } else if (!genRes.ok) {
        throw new Error(formatGenerateError(genPayload, `${mode} generate ${genRes.status}`));
      }
      applyQuickstartSuccess(projectId, genPayload, mode, resultEl, reviewLink);
      workbenchContext = await loadWorkbenchContext(projectId);
      bindHomePage(workbenchContext);
      if (document.getElementById("api-status-card")) {
        applyQuickstartPrefill(workbenchContext.activeProject);
      }
      await bindHiddenProjectsPanel();
      log(`quickstart: ${projectId} ${mode} segments=${genPayload.segments_created}`);
      return genPayload;
    } finally {
      stopQuickstartPolling();
      if (document.getElementById("api-status-card")) {
        await bindApiStatusPanel();
      } else {
        await refreshRuntimeApiStatus();
      }
    }
  }

  function setupQuickstartForm() {
    const form = document.getElementById("quickstart-form");
    if (!form || form.dataset.bound === "1") return;
    form.dataset.bound = "1";
    const params = new URLSearchParams(window.location.search);
    const queryProjectId = String(params.get("project") || "").trim();
    if (queryProjectId) {
      const idEl = document.getElementById("qs-project-id");
      if (idEl && !idEl.value.trim()) idEl.value = queryProjectId;
    }
    form.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      if (quickstartGenerating || quickstartRealApiInFlight) return;
      setQuickstartGenerating(true);
      clearQuickstartError();
      const projectId = document.getElementById("qs-project-id")?.value.trim();
      const name = document.getElementById("qs-project-name")?.value.trim() || projectId;
      const direction = document.getElementById("qs-direction")?.value || "JP_TO_CN";
      const sampleText = document.getElementById("qs-sample-text")?.value.trim();
      const resultEl = document.getElementById("quickstart-result");
      const reviewLink = document.getElementById("qs-review-link");
      const requestId = nextRequestId("dryrun");
      try {
        if (!projectId || !sampleText) {
          const msg = !projectId ? "请填写项目 ID。" : "请填写样本文本。";
          showQuickstartError(msg, !projectId ? "qs-project-id" : null);
          return;
        }
        const idErr = validateProjectIdClient(projectId);
        if (idErr) {
          showQuickstartError(idErr, "qs-project-id");
          return;
        }
        const ok = await ensureQuickstartProject(projectId, name, direction, resultEl);
        if (!ok) return;
        await runQuickstartGenerate(
          projectId,
          sampleText,
          "dry_run",
          resultEl,
          reviewLink,
          requestId
        );
      } catch (err) {
        showQuickstartError(`失败：${err.message}`);
        log(`quickstart failed: ${err.message}`);
      } finally {
        setQuickstartGenerating(false);
      }
    });

    const projectIdInput = document.getElementById("qs-project-id");
    if (projectIdInput && projectIdInput.dataset.bound !== "1") {
      projectIdInput.dataset.bound = "1";
      projectIdInput.addEventListener("input", () => clearQuickstartError());
    }

    const realBtn = document.getElementById("qs-real-api-btn");
    if (realBtn && realBtn.dataset.bound !== "1") {
      realBtn.dataset.bound = "1";
      realBtn.addEventListener("click", async () => {
        if (quickstartRealApiInFlight || quickstartGenerating) return;
        clearQuickstartError();
        quickstartRealApiInFlight = true;
        setQuickstartGenerating(true);
        const projectId = document.getElementById("qs-project-id")?.value.trim();
        const name = document.getElementById("qs-project-name")?.value.trim() || projectId;
        const direction = document.getElementById("qs-direction")?.value || "JP_TO_CN";
        const sampleText = document.getElementById("qs-sample-text")?.value.trim();
        const resultEl = document.getElementById("quickstart-result");
        const reviewLink = document.getElementById("qs-review-link");
        const requestId = nextRequestId("realapi");
        try {
          if (!projectId || !sampleText) {
            const msg = !projectId ? "请填写项目 ID。" : "请填写样本文本。";
            showQuickstartError(msg, !projectId ? "qs-project-id" : null);
            return;
          }
          const idErr = validateProjectIdClient(projectId);
          if (idErr) {
            showQuickstartError(idErr, "qs-project-id");
            return;
          }
          const latestStatus = await refreshRuntimeApiStatus();
          if (latestStatus?.workbench_real_api_ready !== true) {
            if (resultEl) {
              resultEl.textContent = `真实 API 不可用：${latestStatus?.workbench_real_api_block_reason_label || latestStatus?.workbench_real_api_block_reason || "未配置"}`;
            }
            return;
          }
          const budget = latestStatus?.max_test_cost_usd ?? 0;
          const confirmed = window.confirm(
            `将调用 OpenRouter 真实翻译（最多 3 段，预算上限 MAX_TEST_COST_USD=${budget}）。继续？`
          );
          if (!confirmed) return;
          const ok = await ensureQuickstartProject(projectId, name, direction, resultEl);
          if (!ok) return;
          await runQuickstartGenerate(
            projectId,
            sampleText,
            "real_api",
            resultEl,
            reviewLink,
            requestId
          );
        } catch (err) {
          showQuickstartError(`失败：${err.message}`);
          log(`real-api quickstart failed: ${err.message}`);
        } finally {
          quickstartRealApiInFlight = false;
          setQuickstartGenerating(false);
        }
      });
    }
  }

  const ISSUE_SEVERITY_ORDER = { critical: 0, high: 1, medium: 2, low: 3 };

  function sortIssuesByPriority(issues, issueState) {
    return [...issues].sort((a, b) => {
      const aOpen = issueStatus(a, issueState) === "open" ? 0 : 1;
      const bOpen = issueStatus(b, issueState) === "open" ? 0 : 1;
      if (aOpen !== bOpen) return aOpen - bOpen;
      const aSev = ISSUE_SEVERITY_ORDER[a.severity] ?? 9;
      const bSev = ISSUE_SEVERITY_ORDER[b.severity] ?? 9;
      return aSev - bSev;
    });
  }

  function bindIssuesPage(report) {
    const root = document.getElementById("issues-root");
    if (!root) return;
    issueReport = report;
    issuesBySegment = indexIssues(report);
    const issueState = reviewStateCache;
    const allIssues = report.issues || [];
    const projectId = report.project_id || currentIssuesProjectId || "";

    const statusEl = document.getElementById("review-status");
    const totalEl = document.getElementById("issue-total");
    if (statusEl) statusEl.textContent = report.review_status || "—";
    if (totalEl) totalEl.textContent = String(report.summary?.total ?? allIssues.length);
    const sourceEl = document.getElementById("issue-data-source");
    if (sourceEl) {
      const raw = String(report._source || "unknown");
      sourceEl.textContent =
        raw === "api" ? "API" : raw === "fallback_fixture" ? "fallback→fixture" : "fixture";
      sourceEl.className =
        raw === "api" ? "badge badge-success" : raw === "fallback_fixture" ? "badge badge-warning" : "badge badge-neutral";
    }
    const projectEl = document.getElementById("issue-project-id");
    if (projectEl) {
      projectEl.textContent = projectId || "—";
    }

    const summaryBar = document.getElementById("issues-summary-bar");
    const filtersCard = document.getElementById("issues-filters-card");
    if (!allIssues.length) {
      if (summaryBar) summaryBar.hidden = true;
      if (filtersCard) filtersCard.hidden = true;
      root.innerHTML = `
        <div class="card issues-empty-state">
          <h2>暂无质量 Issue</h2>
          <p class="meta">当前项目尚未检测到机器审核 issue，或报告为空。可先完成对照审核，再导出已通过段落。</p>
          <div class="actions">
            <a class="button-link" href="/review.html?project=${encodeURIComponent(projectId)}">返回审核</a>
            <a class="button-link" href="/export.html?project=${encodeURIComponent(projectId)}">导出已通过段落</a>
          </div>
        </div>`;
      return;
    }
    if (filtersCard) filtersCard.hidden = false;

    const openCount = allIssues.filter((i) => issueStatus(i, issueState) === "open").length;
    const highCount = allIssues.filter(
      (i) =>
        issueStatus(i, issueState) === "open" &&
        (i.severity === "critical" || i.severity === "high")
    ).length;
    if (summaryBar) {
      summaryBar.hidden = false;
      summaryBar.innerHTML = `
        <div class="issues-summary-bar">
          <span><strong>${openCount}</strong> 条待处理（open）</span>
          <span><strong>${highCount}</strong> 条高严重度（critical/high）</span>
          <span class="meta">共 ${allIssues.length} 条 · 已按 open → 严重度排序</span>
        </div>`;
    }

    const typeSelect = document.getElementById("filter-type");
    if (typeSelect && typeSelect.options.length <= 1) {
      const types = [...new Set(allIssues.map((i) => i.issue_type))].sort();
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

    const filtered = sortIssuesByPriority(
      allIssues.filter((issue) => {
        const st = issueStatus(issue, issueState);
        if (sevFilter && issue.severity !== sevFilter) return false;
        if (typeFilter && issue.issue_type !== typeFilter) return false;
        if (statusFilter && st !== statusFilter) return false;
        return true;
      }),
      issueState
    );

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
    if (apiLabel) {
      apiLabel.textContent = runtimeApiStatus?.api_mode || "unknown";
    }
    if (autoLabel) autoLabel.textContent = String(Boolean(cfg.AUTO_APPROVE));
    if (runtimeApiStatus) updateModeBanner(runtimeApiStatus);
    if (projectLabel && workbenchContext?.activeProject) {
      projectLabel.textContent = `${workbenchContext.activeProject.name} (${workbenchContext.activeProjectId})`;
    }

    if (!data.segments || data.segments.length === 0) {
      const pid = workbenchContext?.activeProjectId || "";
      const status = workbenchContext?.activeProject?.status || "unknown";
      const job = currentGenerationJob;
      const includeDeleteHint =
        pid &&
        (String(workbenchContext?.activeProject?.category || "").toLowerCase() === "test" ||
          pid.startsWith("pw-") ||
          pid.startsWith("user-"));
      if (job && (job.status === "queued" || job.status === "running")) {
        startGenerationPolling(pid);
      } else {
        stopGenerationPolling();
      }
      const jobRunning = job && (job.status === "queued" || job.status === "running");
      root.innerHTML = `
        <div class="card empty-review">
          <h2>尚无 segment 可审核</h2>
          <p class="meta">项目「${escapeHtml(pid)}」当前没有译文 segment（状态：${escapeHtml(status)}）。</p>
          <p class="meta">${escapeHtml(generationJobHint(job))}</p>
          <p class="meta">可能原因：生成失败、尚未生成、或预算/并发导致写入未完成。</p>
          <p>
            <a href="/index.html?project=${encodeURIComponent(pid)}">返回 Quickstart 继续生成</a>
            · <a href="/review.html?project=${encodeURIComponent(pid)}">刷新本页</a>
            ${
              includeDeleteHint
                ? ` · <a href="/index.html?project=${encodeURIComponent(pid)}">返回首页重试/删除测试项目</a>`
                : ""
            }
          </p>
          <div class="actions">
            <button type="button" data-empty-action="retry" ${jobRunning ? "disabled" : ""}>标记可重试（draft_pending）</button>
            <button type="button" data-empty-action="archive" ${jobRunning ? "disabled" : ""}>归档项目</button>
            ${
              includeDeleteHint
                ? `<button type="button" class="danger" data-empty-action="delete" ${jobRunning ? "disabled" : ""}>删除测试项目</button>`
                : ""
            }
          </div>
        </div>`;
      return;
    }
    stopGenerationPolling();

    const params = new URLSearchParams(window.location.search);
    const focus = params.get("segment");
    const segIds = data.segments.map((s) => s.id || s.segment_id);
    if (focus && segIds.includes(focus)) {
      reviewSelectedSegmentId = focus;
    } else if (!reviewSelectedSegmentId || !segIds.includes(reviewSelectedSegmentId)) {
      reviewSelectedSegmentId = segIds[0] || null;
    }

    const selectedSeg =
      data.segments.find((s) => (s.id || s.segment_id) === reviewSelectedSegmentId) ||
      data.segments[0];
    const selectedId = selectedSeg.id || selectedSeg.segment_id;
    const selectedStatus = segmentStatus(selectedSeg, state);
    const selectedOpenIssues = openIssuesForSegment(selectedId, state);
    const showAutoBtn = Boolean(cfg.AUTO_APPROVE || cfg.dryRunAutoApprove);
    const autoBtnHtml = showAutoBtn
      ? `<button type="button" data-action="auto" data-id="${escapeHtml(selectedId)}">触发自动通过</button>`
      : "";

    const queueHtml = data.segments
      .map((seg) => {
        const segId = seg.id || seg.segment_id;
        const st = segmentStatus(seg, state);
        const active = segId === selectedId ? " is-active" : "";
        const openCount = openIssuesForSegment(segId, state).length;
        const issueDot = openCount ? ` · ${openCount} issue` : "";
        return `<li>
          <button type="button" class="review-queue-item${active}" data-segment-select="${escapeHtml(segId)}" id="seg-${escapeHtml(segId)}">
            <span class="queue-id">${escapeHtml(segId)}</span>
            ${renderBadge(st)}${issueDot}
          </button>
        </li>`;
      })
      .join("");

    const issueMarks = selectedOpenIssues.length
      ? `<p class="issue-mark">${selectedOpenIssues.length} 条 open issue · <a href="/issues.html?project=${encodeURIComponent(workbenchContext?.activeProjectId || "")}">查看</a></p>`
      : "";

    root.innerHTML = `
      <div class="review-layout">
        <aside class="review-queue">
          <h3>段落队列（${data.segments.length}）</h3>
          <ul class="review-queue-list">${queueHtml}</ul>
        </aside>
        <section class="review-reading${selectedOpenIssues.length ? " segment-has-issue" : ""}">
          <h3>对照阅读</h3>
          ${issueMarks}
          <div class="review-reading-panels">
            <div>
              <div class="panel-title">原文</div>
              <p>${escapeHtml(selectedSeg.source)}</p>
            </div>
            <div>
              <div class="panel-title">${escapeHtml(draftPanelTitle(runtimeApiStatus, selectedSeg))}</div>
              <p>${escapeHtml(selectedSeg.draft)}</p>
            </div>
          </div>
        </section>
        <aside class="review-meta">
          <h3>状态与操作</h3>
          <div class="review-meta-section">
            <div class="panel-title">审核状态</div>
            <p>${renderBadge(selectedStatus)} ${generationModeBadge(selectedSeg)}</p>
          </div>
          <div class="review-meta-section">
            <div class="panel-title">元数据</div>
            <p class="meta">segment：<code>${escapeHtml(selectedId)}</code></p>
            <p class="meta">项目：${escapeHtml(workbenchContext?.activeProjectId || "—")}</p>
          </div>
          <div class="review-meta-section">
            <div class="panel-title">操作</div>
            <div class="actions">
              <button type="button" class="primary" data-action="approve" data-id="${escapeHtml(selectedId)}">通过</button>
              <button type="button" class="danger" data-action="reject" data-id="${escapeHtml(selectedId)}">驳回</button>
              ${autoBtnHtml}
            </div>
          </div>
          <div class="review-meta-section review-shortcuts" aria-label="审核快捷键">
            <div class="panel-title">快捷键</div>
            <p class="meta"><kbd>J</kbd> / <kbd>↓</kbd> 下一段</p>
            <p class="meta"><kbd>K</kbd> / <kbd>↑</kbd> 上一段</p>
            <p class="meta"><kbd>A</kbd> 通过当前段</p>
            <p class="meta"><kbd>R</kbd> 驳回当前段</p>
          </div>
        </aside>
      </div>`;

    const mobileBar = document.getElementById("review-mobile-actions");
    if (mobileBar) {
      mobileBar.hidden = false;
      mobileBar.innerHTML = `
        <div class="actions">
          <button type="button" class="primary" data-action="approve" data-id="${escapeHtml(selectedId)}">通过</button>
          <button type="button" class="danger" data-action="reject" data-id="${escapeHtml(selectedId)}">驳回</button>
        </div>`;
    }

    if (focus) {
      const el = document.getElementById(`seg-${focus}`);
      if (el) el.scrollIntoView({ behavior: "smooth", block: "nearest" });
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

  function renderProjectCard(p, activeId) {
    const pid = p.id || p.project_id;
    const isActive = pid === activeId;
    const cat = p.category || "user";
    const status = String(p.status || "").toLowerCase();
    const lifecycleButtons = [
      status === "archived"
        ? ""
        : `<button type="button" data-project-action="archive" data-project-id="${escapeHtml(pid)}">归档</button>`,
      `<button type="button" data-project-action="retry" data-project-id="${escapeHtml(pid)}">重试（恢复为 draft_pending）</button>`,
      cat === "test"
        ? `<button type="button" class="danger" data-project-action="delete" data-project-id="${escapeHtml(pid)}">删除测试项目</button>`
        : "",
    ]
      .filter(Boolean)
      .join("");
    return `
      <div class="card${isActive ? " card-active" : ""}">
        <h2>${escapeHtml(p.name)} ${categoryBadge(cat)}${isActive ? ' <span class="badge ok">当前</span>' : ""}</h2>
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
        <div class="actions">
          ${lifecycleButtons}
        </div>
      </div>`;
  }

  async function bindHiddenProjectsPanel() {
    const details = document.getElementById("project-history-details");
    const list = document.getElementById("project-history-list");
    const countEl = document.getElementById("project-history-count");
    if (!details || !list) return;
    try {
      const registry = await fetchProjectsApi({ includeTest: true, includeHistory: true });
      const hidden = (registry.projects || []).filter((p) => {
        const cat = p.category || "user";
        return cat === "test" || cat === "history";
      });
      if (countEl) countEl.textContent = String(hidden.length);
      if (!hidden.length) {
        details.hidden = true;
        list.innerHTML = "";
        return;
      }
      details.hidden = false;
      const activeId = workbenchContext?.activeProjectId || registry.active_project_id || "";
      list.innerHTML = hidden.map((p) => renderProjectCard(p, activeId)).join("");
    } catch (err) {
      log(`hidden projects load failed: ${err.message}`);
    }
  }

  function bindHomePage(ctx) {
    const list = document.getElementById("project-list");
    if (!list) return;
    const activeId = ctx.activeProjectId;
    const visible = visibleHomeProjects(ctx.projects, activeId);
    const sorted = [...visible].sort((a, b) => {
      const aId = a.id || a.project_id;
      const bId = b.id || b.project_id;
      if (aId === activeId) return -1;
      if (bId === activeId) return 1;
      const aEx = (a.category || "") === "example" ? 1 : 0;
      const bEx = (b.category || "") === "example" ? 1 : 0;
      return aEx - bEx;
    });
    list.innerHTML = sorted.map((p) => renderProjectCard(p, activeId)).join("");

    const recentEl = document.getElementById("recent-projects-summary");
    if (recentEl) {
      const userRecent = sorted.filter((p) => {
        const cat = p.category || "user";
        return cat === "user" || (p.id || p.project_id) === activeId;
      });
      if (!userRecent.length && !sorted.length) {
        recentEl.textContent = "尚无用户项目，请创建 dry-run 项目。";
      } else {
        const names = sorted
          .slice(0, 3)
          .map((p) => p.name || p.id || p.project_id)
          .join("、");
        recentEl.textContent = `共 ${sorted.length} 个可见项目：${names}${sorted.length > 3 ? "…" : ""}`;
      }
    }

    const sourceEl = document.getElementById("data-source-label");
    if (sourceEl) {
      sourceEl.textContent =
        ctx.source === "api"
          ? "manifest API（workspace/manifests）"
          : `mock JSON fallback${ctx.apiError ? " — " + ctx.apiError : ""}`;
    }
  }

  function setupProjectSwitchHandler(ctx) {
    const containers = [
      document.getElementById("project-list"),
      document.getElementById("project-history-list"),
    ].filter(Boolean);
    for (const list of containers) {
      if (list.dataset.switchBound === "1") continue;
      list.dataset.switchBound = "1";
      list.addEventListener("click", async (ev) => {
        const switchBtn = ev.target.closest("button[data-switch-project]");
        if (switchBtn) {
          const projectId = switchBtn.dataset.switchProject;
          try {
            if (ctx.source === "api") {
              await switchActiveProjectApi(projectId);
            }
            saveActiveProjectId(projectId);
            const next = await loadWorkbenchContext(projectId);
            workbenchContext = next;
            await refreshGenerationJob(projectId);
            bindHomePage(next);
            await bindHiddenProjectsPanel();
            log(`active project → ${projectId}`);
          } catch (err) {
            log(`switch failed: ${err.message}`);
          }
          return;
        }

        const lifecycleBtn = ev.target.closest("button[data-project-action]");
        if (!lifecycleBtn) return;
        const action = lifecycleBtn.dataset.projectAction;
        const projectId = lifecycleBtn.dataset.projectId;
        if (!action || !projectId) return;
        try {
          let payload;
          if (action === "archive") {
            const confirmed = window.confirm(`确认归档项目「${projectId}」？归档后可通过“重试”恢复。`);
            if (!confirmed) return;
            payload = await runProjectLifecycleApi(projectId, action);
          } else if (action === "retry") {
            payload = await runProjectLifecycleApi(projectId, action);
          } else if (action === "delete") {
            const confirmed = window.confirm(
              `将删除测试项目「${projectId}」。此操作仅删除 workspace/manifests 与状态数据，不删除 runs。继续？`
            );
            if (!confirmed) return;
            const phrase = window.prompt(`请输入 DELETE ${projectId} 以确认删除：`, "");
            if (phrase == null) return;
            payload = await runProjectLifecycleApi(projectId, action, {
              confirm_delete: true,
              confirm_phrase: phrase,
            });
          } else {
            return;
          }
          const preferred = payload.active_project_id || (action === "delete" ? "" : projectId);
          const next = await loadWorkbenchContext(preferred);
          workbenchContext = next;
          await refreshGenerationJob(next.activeProjectId);
          bindHomePage(next);
          await bindHiddenProjectsPanel();
          if (document.getElementById("quickstart-result")) {
            const msg =
              action === "delete"
                ? `已删除测试项目：${projectId}`
                : action === "archive"
                  ? `已归档项目：${projectId}`
                  : `项目已恢复为 draft_pending：${projectId}`;
            document.getElementById("quickstart-result").textContent = msg;
          }
          log(`project lifecycle: ${action} ${projectId}`);
        } catch (err) {
          log(`project lifecycle failed: ${err.message}`);
        }
      });
    }
  }

  const PROJECT_GROUP_LABELS = {
    current: "当前项目",
    user: "用户项目",
    example: "示例项目",
    test: "测试项目",
    history: "历史项目",
  };

  function projectSelectorGroup(cat, activeId, pid) {
    if (pid === activeId) return "current";
    return cat || "user";
  }

  function renderProjectSwitcherOptions(projects, activeId, filterText = "") {
    const needle = String(filterText || "").trim().toLowerCase();
    const filtered = (projects || []).filter((p) => {
      if (!needle) return true;
      const pid = String(p.id || p.project_id || "").toLowerCase();
      const name = String(p.name || "").toLowerCase();
      return pid.includes(needle) || name.includes(needle);
    });
    const groups = new Map();
    for (const p of filtered) {
      const pid = p.id || p.project_id;
      const cat = p.category || "user";
      const groupKey = projectSelectorGroup(cat, activeId, pid);
      if (!groups.has(groupKey)) groups.set(groupKey, []);
      groups.get(groupKey).push(p);
    }
    const order = ["current", "user", "example", "test", "history"];
    const parts = [];
    for (const key of order) {
      const items = groups.get(key);
      if (!items?.length) continue;
      const label = PROJECT_GROUP_LABELS[key] || key;
      parts.push(`<optgroup label="${escapeHtml(label)}">`);
      for (const p of items) {
        const pid = p.id || p.project_id;
        const selected = pid === activeId ? " selected" : "";
        const cat = p.category && p.category !== "user" && key !== "current" ? ` [${p.category}]` : "";
        parts.push(
          `<option value="${escapeHtml(pid)}"${selected}>${escapeHtml(p.name)}${cat}</option>`
        );
      }
      parts.push("</optgroup>");
    }
    if (!parts.length) {
      return '<option value="" disabled>无匹配项目</option>';
    }
    return parts.join("");
  }

  function pickProductionDefaultRun(runs, pipelineStatus) {
    const inProgress = runs.filter((r) => r.status === "in_progress");
    const draftInProgress = inProgress
      .filter((r) => r.run_id !== pipelineStatus?.run_id || pipelineStatus?.phase !== "refine")
      .sort((a, b) => (b.chapter_offset || 0) - (a.chapter_offset || 0));
    if (draftInProgress.length) return draftInProgress[0].run_id;
    const defaultRun = runs.find((r) => r.is_default);
    if (defaultRun) return defaultRun.run_id;
    return runs[0]?.run_id || "";
  }

  async function populateProductionRunSwitcher(defaultRunId, options = {}) {
    const select = document.getElementById("production-run-switcher");
    if (!select) return "";
    try {
      const payload = await fetchProductionRuns();
      const runs = payload.runs || [];
      let chosen = defaultRunId;
      if (!chosen && options.autoSelectProduction) {
        const status = options.pipelineStatus || (await fetchApiStatus()).pipeline_status;
        chosen = pickProductionDefaultRun(runs, status);
      }
      const optionHtml = [
        `<option value="">— 使用 manifest 项目 —</option>`,
        ...runs.map((r) => {
          const progress = r.segment_progress_label ? ` · ${r.segment_progress_label}` : "";
          const label = `${r.run_id}${r.is_default ? "（默认）" : ""}${progress}`;
          const selected = r.run_id === chosen ? " selected" : "";
          return `<option value="${escapeHtml(r.run_id)}"${selected}>${escapeHtml(label)}</option>`;
        }),
      ];
      select.innerHTML = optionHtml.join("");
      return chosen;
    } catch (err) {
      select.innerHTML = '<option value="">生产 run 加载失败</option>';
      log(`production runs error: ${err.message}`);
      return "";
    }
  }

  async function loadProductionReview(runId, chapter) {
    const doc = await fetchProductionRunSegments(runId, chapter);
    const chapterSelect = document.getElementById("production-chapter-filter");
    if (chapterSelect) {
      const chapters = doc.chapters_available || [];
      chapterSelect.disabled = !chapters.length;
      chapterSelect.innerHTML = [
        '<option value="">全部章节</option>',
        ...chapters.map((n) => {
          const sel = String(n) === String(chapter || "") ? " selected" : "";
          return `<option value="${n}"${sel}>第 ${n} 章</option>`;
        }),
      ].join("");
    }
    const projectLabel = document.getElementById("active-project-label");
    if (projectLabel) {
      projectLabel.textContent = `生产 run：${runId}${chapter ? ` · 第 ${chapter} 章` : ""}`;
    }
    bindReviewPage({ segments: doc.segments || [] });
    log(`production review loaded: ${runId} segments=${(doc.segments || []).length}`);
  }

  function setupProductionRunSelector() {
    const select = document.getElementById("production-run-switcher");
    const chapterSelect = document.getElementById("production-chapter-filter");
    if (!select || select.dataset.bound === "1") return;
    select.dataset.bound = "1";
    const params = new URLSearchParams(window.location.search);
    const initialRun = params.get("production_run") || "";
    const workbenchMode = params.get("workbench_mode") || "";
    const autoProduction = workbenchMode === "production";
    populateProductionRunSwitcher(initialRun, { autoSelectProduction: autoProduction }).then(
      async (chosenRun) => {
        const runToLoad = initialRun || chosenRun;
        if (runToLoad) {
          if (chapterSelect) chapterSelect.disabled = false;
          await loadProductionReview(runToLoad, params.get("chapter") || "");
        }
      }
    );
    select.addEventListener("change", async () => {
      const runId = select.value;
      if (!runId) {
        if (workbenchContext) bindReviewPage({ segments: workbenchContext.segments || [] });
        return;
      }
      try {
        await loadProductionReview(runId, chapterSelect?.value || "");
      } catch (err) {
        log(`production review failed: ${err.message}`);
      }
    });
    if (chapterSelect && chapterSelect.dataset.bound !== "1") {
      chapterSelect.dataset.bound = "1";
      chapterSelect.addEventListener("change", async () => {
        const runId = select.value;
        if (!runId) return;
        try {
          await loadProductionReview(runId, chapterSelect.value || "");
        } catch (err) {
          log(`production chapter filter failed: ${err.message}`);
        }
      });
    }
  }

  function setupReviewProjectSelector(ctx) {
    const select = document.getElementById("project-switcher");
    if (!select) return;
    const searchEl = document.getElementById("project-switcher-search");
    const filterText = searchEl?.value || "";
    select.innerHTML = renderProjectSwitcherOptions(ctx.projects, ctx.activeProjectId, filterText);
    const labelEl = document.getElementById("active-project-label");
    if (labelEl) {
      const active = ctx.projects.find((p) => (p.id || p.project_id) === ctx.activeProjectId);
      labelEl.textContent = active
        ? `${active.name} (${ctx.activeProjectId})`
        : ctx.activeProjectId || "—";
    }
    if (searchEl && searchEl.dataset.bound !== "1") {
      searchEl.dataset.bound = "1";
      searchEl.addEventListener("input", () => {
        if (!workbenchContext) return;
        select.innerHTML = renderProjectSwitcherOptions(
          workbenchContext.projects,
          workbenchContext.activeProjectId,
          searchEl.value
        );
      });
    }
    const showTestEl = document.getElementById("show-test-projects");
    if (showTestEl && showTestEl.dataset.bound !== "1") {
      showTestEl.dataset.bound = "1";
      showTestEl.addEventListener("change", async () => {
        const activeId = workbenchContext?.activeProjectId || select.value || "";
        try {
          const next = await loadWorkbenchContext(activeId, {
            includeHidden: reviewIncludeHiddenProjects(),
          });
          workbenchContext = next;
          select.innerHTML = renderProjectSwitcherOptions(
            next.projects,
            next.activeProjectId,
            searchEl?.value || ""
          );
          if (labelEl) {
            const active = next.projects.find((p) => (p.id || p.project_id) === next.activeProjectId);
            labelEl.textContent = active
              ? `${active.name} (${next.activeProjectId})`
              : next.activeProjectId || "—";
          }
          log(reviewIncludeHiddenProjects() ? "已显示测试/历史项目" : "已隐藏测试/历史项目");
        } catch (err) {
          log(`项目列表刷新失败: ${err.message}`);
        }
      });
    }
    if (select.dataset.bound === "1") return;
    select.dataset.bound = "1";
    select.addEventListener("change", async () => {
      const projectId = select.value;
      try {
        if (ctx.source === "api") {
          await switchActiveProjectApi(projectId);
        }
        saveActiveProjectId(projectId);
        const next = await loadWorkbenchContext(projectId, { includeHidden: reviewIncludeHiddenProjects() });
        workbenchContext = next;
        await loadReviewStateForProject(projectId);
        await refreshGenerationJob(projectId);
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

  async function applyReviewSegmentAction(id, action, projectId) {
    if (!id || !reviewData) return;
    const seg = reviewData.segments.find((s) => (s.id || s.segment_id) === id);
    if (!seg) return;
    const cfg = getConfig();
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
    const activeProjectId = workbenchContext?.activeProjectId || projectId;
    await patchReviewState(activeProjectId, { segments: { [id]: entry } });
    bindReviewPage(reviewData);
  }

  async function handleReviewSegmentAction(btn, projectId) {
    if (!btn || !reviewData) return;
    await applyReviewSegmentAction(btn.dataset.id, btn.dataset.action, projectId);
  }

  function setupReviewKeyboardHandler(projectId) {
    if (document.body.dataset.reviewKeyboardBound === "1") return;
    document.body.dataset.reviewKeyboardBound = "1";
    document.addEventListener("keydown", async (ev) => {
      if (!document.getElementById("review-root") || !reviewData?.segments?.length) return;
      if (ev.metaKey || ev.ctrlKey || ev.altKey) return;
      const target = ev.target;
      const tag = target?.tagName?.toLowerCase();
      if (target?.isContentEditable || ["input", "textarea", "select"].includes(tag)) {
        return;
      }
      const key = ev.key.toLowerCase();
      if (key === "j" || ev.key === "ArrowDown") {
        ev.preventDefault();
        selectReviewSegmentByOffset(1);
        return;
      }
      if (key === "k" || ev.key === "ArrowUp") {
        ev.preventDefault();
        selectReviewSegmentByOffset(-1);
        return;
      }
      if (key === "a" || key === "r") {
        ev.preventDefault();
        const action = key === "a" ? "approve" : "reject";
        await applyReviewSegmentAction(reviewSelectedSegmentId, action, projectId);
        log(`review shortcut: ${action} ${reviewSelectedSegmentId}`);
      }
    });
  }

  function setupReviewClickHandler(projectId) {
    const root = document.getElementById("review-root");
    const mobileBar = document.getElementById("review-mobile-actions");
    const containers = [root, mobileBar].filter(Boolean);
    for (const container of containers) {
      if (!container || container.dataset.bound === "1") continue;
      container.dataset.bound = "1";
      container.addEventListener("click", async (ev) => {
      const selectBtn = ev.target.closest("button[data-segment-select]");
      if (selectBtn && reviewData) {
        reviewSelectedSegmentId = selectBtn.dataset.segmentSelect;
        bindReviewPage(reviewData);
        return;
      }
      const emptyBtn = ev.target.closest("button[data-empty-action]");
      if (emptyBtn) {
        const action = emptyBtn.dataset.emptyAction;
        const activeProjectId = workbenchContext?.activeProjectId || projectId;
        if (!action || !activeProjectId) return;
        try {
          let payload;
          if (action === "archive") {
            const confirmed = window.confirm(`确认归档项目「${activeProjectId}」？`);
            if (!confirmed) return;
            payload = await runProjectLifecycleApi(activeProjectId, "archive");
          } else if (action === "retry") {
            payload = await runProjectLifecycleApi(activeProjectId, "retry");
          } else if (action === "delete") {
            const confirmed = window.confirm(
              `将删除测试项目「${activeProjectId}」。仅删除 workspace 下 manifest 和状态数据，不删除 runs。继续？`
            );
            if (!confirmed) return;
            const phrase = window.prompt(`请输入 DELETE ${activeProjectId} 以确认删除：`, "");
            if (phrase == null) return;
            payload = await runProjectLifecycleApi(activeProjectId, "delete", {
              confirm_delete: true,
              confirm_phrase: phrase,
            });
          } else {
            return;
          }
          const preferred = payload.active_project_id || (action === "delete" ? "" : activeProjectId);
          const next = await loadWorkbenchContext(preferred, { includeHidden: reviewIncludeHiddenProjects() });
          workbenchContext = next;
          await loadReviewStateForProject(next.activeProjectId);
          await refreshGenerationJob(next.activeProjectId);
          try {
            const report = await fetchIssueReport(next.activeProjectId);
            issuesBySegment = indexIssues(report);
          } catch {
            issuesBySegment = {};
          }
          setupReviewProjectSelector(next);
          bindReviewPage({ segments: next.segments || [] });
          log(`review empty lifecycle: ${action} ${activeProjectId}`);
        } catch (err) {
          log(`review empty lifecycle failed: ${err.message}`);
        }
        return;
      }

      const btn = ev.target.closest("button[data-action]");
      if (!btn) return;
      await handleReviewSegmentAction(btn, projectId);
    });
    }
  }

  function showExportSuccessCard(payload) {
    const card = document.getElementById("export-success-card");
    const emptyEl = document.getElementById("export-session-empty");
    const badgeEl = document.getElementById("export-success-badge");
    const countEl = document.getElementById("export-success-count");
    const skipEl = document.getElementById("export-skip-stats");
    const filesEl = document.getElementById("export-success-files");
    const metaEl = document.getElementById("export-success-meta");
    if (!card || !filesEl) return;
    const paths = exportHighlightPaths(payload);
    const skipped = payload.segments_skipped_status || {};
    const skippedText = formatExportSkipStatus(skipped);
    const isSkip = Boolean(payload.skipped);
    card.hidden = false;
    if (emptyEl) emptyEl.hidden = true;
    if (badgeEl) {
      badgeEl.textContent = isSkip ? "导出跳过（文件已存在）" : "导出成功";
      badgeEl.className = isSkip ? "badge badge-warning" : "badge badge-success";
    }
    if (countEl) {
      const exported = payload.segments_exported ?? "—";
      const total = payload.segments_total ?? "—";
      countEl.textContent = `已导出 ${exported} / 共 ${total} 段 · 模式 ${payload.status_mode || "—"}`;
    }
    if (skipEl) {
      skipEl.textContent = skippedText ? `跳过统计：${skippedText}` : "跳过统计：无";
    }
    filesEl.innerHTML = paths.length
      ? paths
          .map(
            (p) => `<li class="export-file-row">
            <span class="export-recent">${escapeHtml(p)}</span>
            <button type="button" data-copy-path="${escapeHtml(p)}">复制路径</button>
          </li>`
          )
          .join("")
      : '<li class="export-file-row meta">（无新文件路径）</li>';
    if (metaEl) {
      metaEl.textContent = [
        payload.project_id ? `项目 ${payload.project_id}` : null,
        payload.source ? `来源 ${payload.source}` : null,
      ]
        .filter(Boolean)
        .join(" · ");
    }
    if (filesEl.dataset.copyBound !== "1") {
      filesEl.dataset.copyBound = "1";
      filesEl.addEventListener("click", async (ev) => {
        const btn = ev.target.closest("button[data-copy-path]");
        if (!btn) return;
        const path = btn.dataset.copyPath || "";
        try {
          await navigator.clipboard.writeText(path);
          log(`已复制路径：${path}`);
        } catch {
          log(`复制失败，请手动复制：${path}`);
        }
      });
    }
  }

  async function bindExportPage(projectId) {
    const zhDir = document.getElementById("export-zh-dir");
    if (!zhDir) return;
    const projectInput = document.getElementById("export-project-id");
    if (projectInput && projectId) projectInput.value = projectId;
    let highlightPaths = new Set();
    const historyLimit = 20;
    let historyShown = historyLimit;

    function currentExportProjectId() {
      return document.getElementById("export-project-id")?.value.trim() || projectId || "";
    }

    function exportStatusUrl() {
      const pid = currentExportProjectId();
      const params = new URLSearchParams();
      const filterCurrent = document.getElementById("export-filter-current")?.checked !== false;
      if (filterCurrent && pid) params.set("project_id", pid);
      const qs = params.toString();
      return qs ? `/api/export/status?${qs}` : "/api/export/status";
    }

    async function refreshStatus() {
      const res = await fetch(exportStatusUrl());
      if (!res.ok) throw new Error(`export status ${res.status}`);
      const status = await res.json();
      document.getElementById("export-zh-dir").textContent = status.translated_dir;
      document.getElementById("export-bi-dir").textContent = status.bilingual_dir;
      const filterCurrent = document.getElementById("export-filter-current")?.checked !== false;
      const totalZh = filterCurrent
        ? status.translated_count
        : status.total_translated_count ?? status.translated_count;
      const totalBi = filterCurrent
        ? status.bilingual_count
        : status.total_bilingual_count ?? status.bilingual_count;
      document.getElementById("export-zh-count").textContent = String(totalZh);
      document.getElementById("export-bi-count").textContent = String(totalBi);
      const prodSummaryEl = document.getElementById("export-production-summary");
      if (prodSummaryEl && status.production_summary) {
        const ps = status.production_summary;
        const parts = [
          `唯一终稿：${ps.canonical_final_exists ? ps.canonical_final_translation : "未生成"}`,
          `Workbench 临时导出：${ps.workbench_translated_count ?? totalZh}`,
          ps.last_export_at ? `最近导出：${ps.last_export_at}` : null,
        ].filter(Boolean);
        prodSummaryEl.textContent = parts.join(" · ");
      }
      const list = document.getElementById("export-file-list");
      const countEl = document.getElementById("export-file-count");
      const loadMoreBtn = document.getElementById("export-load-more-btn");
      if (list) {
        const files = [...(status.translated_files || []), ...(status.bilingual_files || [])];
        const total = totalZh + totalBi;
        if (countEl) {
          countEl.textContent = filterCurrent && status.filtered_project_id
            ? `${total}（当前项目 ${status.filtered_project_id}）`
            : String(total);
        }
        const shown = files.slice(0, historyShown);
        const hiddenCount = Math.max(0, files.length - shown.length);
        list.innerHTML = shown.length
          ? shown
              .map((f) => {
                const cls = highlightPaths.has(f) ? ' class="export-recent"' : "";
                return `<li${cls}>${escapeHtml(f)}</li>`;
              })
              .join("") +
            (hiddenCount > 0
              ? `<li class="meta">… 另有 ${hiddenCount} 个文件未列出</li>`
              : "")
          : filterCurrent
            ? "<li>当前项目尚无导出文件</li>"
            : "<li>尚无导出文件</li>";
        if (loadMoreBtn) {
          loadMoreBtn.hidden = hiddenCount <= 0;
          loadMoreBtn.textContent = `加载更多（+${Math.min(historyLimit, hiddenCount)}）`;
        }
      }
      return status;
    }

    async function refreshTranslationAssetsStatus() {
      const resultEl = document.getElementById("translation-assets-result");
      const pid = currentExportProjectId();
      if (!resultEl || !pid) return null;
      const res = await fetch(`/api/projects/${encodeURIComponent(pid)}/translation-assets`);
      const payload = await res.json();
      if (!res.ok) throw new Error(payload.error || `translation-assets ${res.status}`);
      resultEl.textContent = formatTranslationAssetsResult(payload);
      return payload;
    }

    const refreshBtn = document.getElementById("export-refresh-btn");
    if (refreshBtn && refreshBtn.dataset.bound !== "1") {
      refreshBtn.dataset.bound = "1";
      refreshBtn.addEventListener("click", async () => {
        try {
          historyShown = historyLimit;
          await refreshStatus();
          log("export status refreshed");
        } catch (err) {
          log(`export status error: ${err.message}`);
        }
      });
    }

    const filterEl = document.getElementById("export-filter-current");
    if (filterEl && filterEl.dataset.bound !== "1") {
      filterEl.dataset.bound = "1";
      filterEl.addEventListener("change", async () => {
        historyShown = historyLimit;
        try {
          await refreshStatus();
        } catch (err) {
          log(`export status error: ${err.message}`);
        }
      });
    }

    const loadMoreBtn = document.getElementById("export-load-more-btn");
    if (loadMoreBtn && loadMoreBtn.dataset.bound !== "1") {
      loadMoreBtn.dataset.bound = "1";
      loadMoreBtn.addEventListener("click", async () => {
        historyShown += historyLimit;
        try {
          await refreshStatus();
        } catch (err) {
          log(`export status error: ${err.message}`);
        }
      });
    }

    if (projectInput && projectInput.dataset.exportBound !== "1") {
      projectInput.dataset.exportBound = "1";
      projectInput.addEventListener("change", async () => {
        historyShown = historyLimit;
        try {
          await refreshStatus();
        } catch (err) {
          log(`export status error: ${err.message}`);
        }
      });
    }

    const manifestBtn = document.getElementById("export-manifest-btn");
    if (manifestBtn && manifestBtn.dataset.bound !== "1") {
      manifestBtn.dataset.bound = "1";
      manifestBtn.addEventListener("click", async () => {
        const pid = document.getElementById("export-project-id")?.value.trim();
        const overwrite = document.getElementById("export-overwrite")?.checked !== false;
        const statusMode = document.getElementById("export-status-mode")?.value || "approved";
        const resultEl = document.getElementById("export-result");
        if (!pid) {
          if (resultEl) resultEl.textContent = "请填写项目 ID";
          return;
        }
        let confirmDraft = false;
        if (statusMode === "draft") {
          confirmDraft = window.confirm(
            "Draft 导出会包含 pending/rejected 等未通过内容，仅适合临时对照。确认继续？"
          );
          if (!confirmDraft) {
            if (resultEl) resultEl.textContent = "已取消：draft 导出需要显式确认。";
            return;
          }
        }
        try {
          const res = await fetch("/api/export/run", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              project_id: pid,
              source: "manifest",
              overwrite,
              status_mode: statusMode,
              confirm_draft: confirmDraft,
            }),
          });
          const payload = await res.json();
          if (!res.ok) throw new Error(payload.error || `export ${res.status}`);
          highlightPaths = new Set(exportHighlightPaths(payload));
          showExportSuccessCard(payload);
          if (resultEl) resultEl.textContent = formatExportResult(payload);
          await refreshStatus();
          log(`manifest export OK: ${pid}`);
        } catch (err) {
          if (resultEl) resultEl.textContent = String(err.message);
          log(`manifest export failed: ${err.message}`);
        }
      });
    }

    const buildAssetsBtn = document.getElementById("build-assets-btn");
    if (buildAssetsBtn && buildAssetsBtn.dataset.bound !== "1") {
      buildAssetsBtn.dataset.bound = "1";
      buildAssetsBtn.addEventListener("click", async () => {
        const pid = currentExportProjectId();
        const resultEl = document.getElementById("translation-assets-result");
        if (!pid) {
          if (resultEl) resultEl.textContent = "请填写项目 ID";
          return;
        }
        try {
          const res = await fetch("/api/translation-assets/build", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              project_id: pid,
              mode: "agent",
              status_mode: "approved",
            }),
          });
          const payload = await res.json();
          if (!res.ok) throw new Error(payload.error || `translation-assets ${res.status}`);
          if (resultEl) resultEl.textContent = formatTranslationAssetsResult(payload);
          log(`translation assets built: ${pid}`);
        } catch (err) {
          if (resultEl) resultEl.textContent = String(err.message);
          log(`translation assets failed: ${err.message}`);
        }
      });
    }

    const refreshAssetsBtn = document.getElementById("refresh-assets-btn");
    if (refreshAssetsBtn && refreshAssetsBtn.dataset.bound !== "1") {
      refreshAssetsBtn.dataset.bound = "1";
      refreshAssetsBtn.addEventListener("click", async () => {
        try {
          await refreshTranslationAssetsStatus();
          log("translation assets status refreshed");
        } catch (err) {
          log(`translation assets status error: ${err.message}`);
        }
      });
    }

    const runSelect = document.getElementById("export-production-run");
    if (runSelect && runSelect.dataset.bound !== "1") {
      runSelect.dataset.bound = "1";
      try {
        const apiStatus = await fetchApiStatus().catch(() => ({}));
        const payload = await fetchProductionRuns();
        const runs = payload.runs || [];
        const params = new URLSearchParams(window.location.search);
        const autoProduction =
          params.get("workbench_mode") === "production" || apiStatus.workbench_mode === "production";
        const chosen = autoProduction
          ? pickProductionDefaultRun(runs, apiStatus.pipeline_status)
          : runs.find((r) => r.is_default)?.run_id || runs[0]?.run_id || "";
        runSelect.innerHTML = runs.length
          ? runs
              .map((r) => {
                const progress = r.segment_progress_label ? ` · ${r.segment_progress_label}` : "";
                const label = `${r.run_id}${r.is_default ? "（默认）" : ""}${progress}`;
                const selected = r.run_id === chosen ? " selected" : "";
                return `<option value="${escapeHtml(r.run_id)}"${selected}>${escapeHtml(label)}</option>`;
              })
              .join("")
          : '<option value="">无可用生产 run</option>';
      } catch (err) {
        runSelect.innerHTML = '<option value="">加载失败</option>';
        log(`export run list error: ${err.message}`);
      }
    }

    const runsBtn = document.getElementById("export-runs-btn");
    if (runsBtn && runsBtn.dataset.bound !== "1") {
      runsBtn.dataset.bound = "1";
      runsBtn.disabled = true;
      runsBtn.title = "历史 runs 导出已停用；请使用 manifest 导出或唯一最终译文导出。";
      runsBtn.addEventListener("click", async () => {
        const resultEl = document.getElementById("export-result");
        const message = "历史 runs 导出已停用；请使用 manifest 导出或唯一最终译文导出。";
        if (resultEl) resultEl.textContent = message;
        log(message);
      });
    }

    try {
      await refreshStatus();
      await refreshTranslationAssetsStatus();
    } catch (err) {
      log(`export status error: ${err.message}`);
    }
  }

  async function bootstrapWorkbench() {
    setupQuickstartForm();
    try {
      if (document.getElementById("export-zh-dir")) {
        const params = new URLSearchParams(window.location.search);
        await bindExportPage(params.get("project") || loadActiveProjectId());
        await refreshRuntimeApiStatus();
        return;
      }

      await refreshRuntimeApiStatus();

      if (document.getElementById("api-status-card")) {
        await bindApiStatusPanel();
        workbenchContext = await loadWorkbenchContext("", { includeHidden: false });
        bindHomePage(workbenchContext);
        await bindHiddenProjectsPanel();
        setupProjectSwitchHandler(workbenchContext);
        return;
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
        const src =
          report._source === "api"
            ? "quality-review API"
            : report._source === "fallback_fixture"
              ? "fallback fixture"
              : "fixture";
        log(`issue report loaded (${report.issues.length} items · ${src})`);
        return;
      }

      const params = new URLSearchParams(window.location.search);
      const preferredProject = params.get("project") || "";
      const includeHidden = reviewIncludeHiddenProjects();
      workbenchContext = await loadWorkbenchContext(preferredProject, { includeHidden });
      await loadReviewStateForProject(workbenchContext.activeProjectId);
      await refreshGenerationJob(workbenchContext.activeProjectId);

      try {
        const report = await fetchIssueReport(workbenchContext.activeProjectId);
        issuesBySegment = indexIssues(report);
      } catch {
        issuesBySegment = {};
      }

      bindHomePage(workbenchContext);
      await bindHiddenProjectsPanel();
      setupProjectSwitchHandler(workbenchContext);
      setupReviewProjectSelector(workbenchContext);
      setupProductionRunSelector();
      setupReviewClickHandler(workbenchContext.activeProjectId);
      setupReviewKeyboardHandler(workbenchContext.activeProjectId);
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
      showPageError(String(err.message || err));
      log(`error: ${err.message}`);
      console.error(err);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => {
      bootstrapWorkbench();
    });
  } else {
    bootstrapWorkbench();
  }
})();
