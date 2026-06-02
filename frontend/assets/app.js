(function () {
  const STORAGE_KEY = "light_novel_workbench_state_v1";
  const ISSUE_STORAGE_KEY = "light_novel_issue_state_v1";

  function loadState() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      return raw ? JSON.parse(raw) : { segments: {} };
    } catch {
      return { segments: {} };
    }
  }

  function saveState(state) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  }

  function loadIssueState() {
    try {
      const raw = localStorage.getItem(ISSUE_STORAGE_KEY);
      return raw ? JSON.parse(raw) : { issues: {} };
    } catch {
      return { issues: {} };
    }
  }

  function saveIssueState(state) {
    localStorage.setItem(ISSUE_STORAGE_KEY, JSON.stringify(state));
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

  function applyAutoApprove(segment, state) {
    const cfg = window.WORKBENCH_CONFIG || {};
    if (!cfg.AUTO_APPROVE && !cfg.dryRunAutoApprove) return false;
    state.segments[segment.id] = {
      status: "approved",
      autoApprove: true,
      at: new Date().toISOString(),
    };
    saveState(state);
    log(`AUTO_APPROVE: ${segment.id} → approved (dry-run)`);
    return true;
  }

  function segmentStatus(segment, state) {
    return state.segments[segment.id]?.status || segment.status || "pending";
  }

  function issueStatus(issue, issueState) {
    return issueState.issues[issue.issue_id]?.status || issue.status || "open";
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

  async function fetchIssueReport() {
    const res = await fetch("/assets/review-issue-report.json");
    if (!res.ok) throw new Error(`review-issue-report.json ${res.status}`);
    return res.json();
  }

  let reviewData = null;
  let issueReport = null;
  let issuesBySegment = {};

  function indexIssues(report) {
    const map = {};
    for (const issue of report.issues || []) {
      if (!issue.segment_id) continue;
      if (!map[issue.segment_id]) map[issue.segment_id] = [];
      map[issue.segment_id].push(issue);
    }
    return map;
  }

  function bindIssuesPage(report) {
    const root = document.getElementById("issues-root");
    if (!root) return;
    issueReport = report;
    issuesBySegment = indexIssues(report);
    const issueState = loadIssueState();

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
        const reviewLink = issue.segment_id
          ? `<a href="/review.html?segment=${encodeURIComponent(issue.segment_id)}#seg-${encodeURIComponent(issue.segment_id)}">对照定位 →</a>`
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
            ${
              locked
                ? '<button type="button" disabled title="锁定术语不可自动改译文">自动修复（禁用）</button>'
                : '<button type="button" disabled title="Round 49 不写入译文">自动修复（禁用）</button>'
            }
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
    root.addEventListener("click", (ev) => {
      const btn = ev.target.closest("button[data-issue-action]");
      if (!btn) return;
      const id = btn.dataset.id;
      const action = btn.dataset.issueAction;
      const issueState = loadIssueState();
      const next =
        action === "resolve"
          ? "resolved"
          : action === "ack"
            ? "acknowledged"
            : "open";
      issueState.issues[id] = { status: next, at: new Date().toISOString() };
      saveIssueState(issueState);
      log(`issue ${id} → ${next} (local only, no translation overwrite)`);
      bindIssuesPage(report);
    });

    for (const sel of ["filter-severity", "filter-type", "filter-status"]) {
      const el = document.getElementById(sel);
      if (!el || el.dataset.bound === "1") continue;
      el.dataset.bound = "1";
      el.addEventListener("change", () => bindIssuesPage(report));
    }
  }

  function bindReviewPage(data) {
    const root = document.getElementById("review-root");
    if (!root) return;
    reviewData = data;
    const state = loadState();
    const cfg = window.WORKBENCH_CONFIG || {};
    const apiLabel = document.getElementById("api-mode-label");
    const autoLabel = document.getElementById("auto-approve-label");
    if (apiLabel) apiLabel.textContent = cfg.apiMode || "unknown";
    if (autoLabel) autoLabel.textContent = String(Boolean(cfg.AUTO_APPROVE));

    root.innerHTML = data.segments
      .map((seg) => {
        const status = segmentStatus(seg, state);
        const segIssues = issuesBySegment[seg.id] || [];
        const issueMarks = segIssues.length
          ? `<p class="issue-mark">${segIssues.length} 条 open issue · <a href="/issues.html">查看</a></p>`
          : "";
        const highlight = segIssues.length ? " segment-has-issue" : "";
        return `
        <article class="segment${highlight}" id="seg-${seg.id}" data-segment-id="${seg.id}">
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
            <button type="button" class="primary" data-action="approve" data-id="${seg.id}">通过</button>
            <button type="button" class="danger" data-action="reject" data-id="${seg.id}">驳回</button>
            <button type="button" data-action="auto" data-id="${seg.id}">触发自动通过</button>
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

    if (cfg.AUTO_APPROVE) {
      let autoCount = 0;
      for (const seg of data.segments) {
        if (segmentStatus(seg, state) === "pending") {
          if (applyAutoApprove(seg, state)) autoCount += 1;
        }
      }
      if (autoCount > 0) {
        bindReviewPage(data);
      }
    }
  }

  function bindHomePage(data) {
    const list = document.getElementById("project-list");
    if (!list) return;
    list.innerHTML = data.projects
      .map(
        (p) => `
      <div class="card">
        <h2>${escapeHtml(p.name)}</h2>
        <p class="meta">方向 ${escapeHtml(p.direction)} · ${p.chapters} 章 · 状态 ${escapeHtml(p.status)}</p>
        <p>
          <a href="/review.html?project=${encodeURIComponent(p.id)}">进入对照审核 →</a>
          · <a href="/issues.html">质量 Issue 列表 →</a>
        </p>
      </div>`
      )
      .join("");
  }

  function setupReviewClickHandler() {
    const root = document.getElementById("review-root");
    if (!root || root.dataset.bound === "1") return;
    root.dataset.bound = "1";
    root.addEventListener("click", (ev) => {
      const btn = ev.target.closest("button[data-action]");
      if (!btn || !reviewData) return;
      const id = btn.dataset.id;
      const seg = reviewData.segments.find((s) => s.id === id);
      if (!seg) return;
      const state = loadState();
      const cfg = window.WORKBENCH_CONFIG || {};
      const action = btn.dataset.action;
      if (action === "approve" || action === "auto") {
        state.segments[id] = {
          status: "approved",
          autoApprove: action === "auto" || Boolean(cfg.AUTO_APPROVE),
          at: new Date().toISOString(),
        };
        log(`${action === "auto" ? "AUTO_APPROVE" : "manual"}: ${id} approved`);
      } else if (action === "reject") {
        state.segments[id] = { status: "rejected", at: new Date().toISOString() };
        log(`rejected: ${id}`);
      }
      saveState(state);
      bindReviewPage(reviewData);
    });
  }

  document.addEventListener("DOMContentLoaded", async () => {
    try {
      if (document.getElementById("issues-root")) {
        const report = await fetchIssueReport();
        bindIssuesPage(report);
        setupIssueHandlers(report);
        log(`issue report loaded (${report.issues.length} items)`);
        return;
      }

      let report = null;
      try {
        report = await fetchIssueReport();
        issuesBySegment = indexIssues(report);
      } catch {
        issuesBySegment = {};
      }

      const data = await fetchMockData();
      bindHomePage(data);
      setupReviewClickHandler();
      bindReviewPage(data);
      log("mock data loaded");
    } catch (err) {
      log(`error: ${err.message}`);
      console.error(err);
    }
  });
})();
