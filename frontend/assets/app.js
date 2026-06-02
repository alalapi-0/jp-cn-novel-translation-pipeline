(function () {
  const STORAGE_KEY = "light_novel_workbench_state_v1";

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

  function log(line) {
    const el = document.getElementById("status-log");
    if (!el) return;
    const ts = new Date().toISOString().slice(11, 19);
    el.textContent = `[${ts}] ${line}\n` + el.textContent;
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

  function renderBadge(status) {
    const cls = status === "approved" ? "ok" : "pending";
    return `<span class="badge ${cls}" data-status="${status}">${status}</span>`;
  }

  async function fetchMockData() {
    const res = await fetch("/assets/mock-data.json");
    if (!res.ok) throw new Error(`mock-data.json ${res.status}`);
    return res.json();
  }

  let reviewData = null;

  function bindReviewPage(data) {
    const root = document.getElementById("review-root");
    if (!root) return;
    reviewData = data;
    const state = loadState();
    const cfg = window.WORKBENCH_CONFIG || {};
    document.getElementById("api-mode-label").textContent = cfg.apiMode || "unknown";
    document.getElementById("auto-approve-label").textContent = String(
      Boolean(cfg.AUTO_APPROVE)
    );

    root.innerHTML = data.segments
      .map((seg) => {
        const status = segmentStatus(seg, state);
        return `
        <article class="segment" data-segment-id="${seg.id}">
          <div class="grid-2">
            <div>
              <div class="panel-title">原文</div>
              <p>${seg.source}</p>
            </div>
            <div>
              <div class="panel-title">译文（mock）</div>
              <p>${seg.draft}</p>
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
        <h2>${p.name}</h2>
        <p class="meta">方向 ${p.direction} · ${p.chapters} 章 · 状态 ${p.status}</p>
        <p><a href="/review.html?project=${encodeURIComponent(p.id)}">进入对照审核 →</a></p>
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
      const data = await fetchMockData();
      bindHomePage(data);
      setupReviewClickHandler();
      bindReviewPage(data);
      const logEl = document.getElementById("status-log");
      if (logEl) log("mock data loaded");
    } catch (err) {
      const logEl = document.getElementById("status-log");
      if (logEl) log(`error: ${err.message}`);
      console.error(err);
    }
  });
})();
