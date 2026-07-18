/**
 * God View Project Control Center — dynamic timeline, workstreams, issues.
 * Read-only. Loads status/nycif-godview-project-state-v02.json from live-feeds.
 */
(() => {
  const VERSION = "god-view-project-control-v01";
  const LIVE_FEEDS_BASE = "https://raw.githubusercontent.com/setoxxx/nycif-live-feeds";
  const BRANCH_CANDIDATES = ["main", "cursor/dynamic-godview-project-state-c1f9"];
  const STATE_PATH = "status/nycif-godview-project-state-v02.json";

  function esc(value) {
    return String(value ?? "").replace(/[&<>"']/g, (ch) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch])
    );
  }

  function fmtNum(value) {
    return Number.isFinite(Number(value)) ? Number(value).toLocaleString() : "0";
  }

  function fmtTime(value) {
    if (!value) return "Unknown";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return date.toLocaleString([], {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
  }

  function hoursSince(iso) {
    if (!iso) return Infinity;
    const ms = Date.now() - new Date(iso).getTime();
    return Number.isFinite(ms) ? ms / 3600000 : Infinity;
  }

  async function fetchState() {
    let lastError = null;
    for (const branch of BRANCH_CANDIDATES) {
      try {
        const url = `${LIVE_FEEDS_BASE}/${branch}/${STATE_PATH}?v=${Date.now()}`;
        const response = await fetch(url, { cache: "no-store" });
        if (!response.ok) {
          lastError = new Error(`${branch}/${STATE_PATH}: HTTP ${response.status}`);
          continue;
        }
        return { branch, state: await response.json() };
      } catch (error) {
        lastError = error;
      }
    }
    throw lastError || new Error(`Could not load ${STATE_PATH}`);
  }

  function statusClass(status) {
    const s = String(status || "").toLowerCase();
    if (s === "complete" || s === "ready") return "ok";
    if (s === "locked" || s === "not_started") return "violet";
    if (s === "blocked") return "danger";
    return "warn";
  }

  function renderBadges(state) {
    const cc = state.command_center || {};
    const health = cc.health || "unknown";
    const healthClass = health === "green" ? "ok" : health === "red" ? "danger" : "warn";
    return `
      <span class="badge ${healthClass}">Health: ${esc(health)}</span>
      <span class="badge ok">${esc(fmtNum(cc.completion_percent))}% complete</span>
      <span class="badge">Updated ${esc(fmtTime(state.generated_at_utc))}</span>
    `;
  }

  function renderSummary(state) {
    const counts = state.counts || {};
    return `
      <div class="stat project-stat"><div class="label">Discovery approved</div><div class="value">${esc(fmtNum(counts.discovery_approved_events))}</div></div>
      <div class="stat project-stat"><div class="label">Major events</div><div class="value">${esc(fmtNum(counts.discovery_major_events))}</div></div>
      <div class="stat project-stat"><div class="label">Supplemental approved</div><div class="value">${esc(fmtNum(counts.supplemental_approved))}</div></div>
      <div class="stat project-stat"><div class="label">Supplemental rejected</div><div class="value">${esc(fmtNum(counts.supplemental_rejected))}</div></div>
      <div class="stat project-stat"><div class="label">White Island cluster</div><div class="value">${esc(fmtNum(counts.white_island_cluster_count))}</div></div>
      <div class="stat project-stat"><div class="label">Review layer events</div><div class="value">${esc(fmtNum(counts.discovery_review_events))}</div></div>
    `;
  }

  function renderTimelineColumn(title, items, tone) {
    const rows = (items || [])
      .map((item) => {
        const prLinks = (item.pr_urls || [])
          .map((url) => `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">PR</a>`)
          .join(" ");
        return `<li>
          <strong>${esc(item.title)}</strong>
          <span class="badge ${statusClass(item.status)}">${esc(item.status || "—")}</span>
          <span class="detail">${esc(item.summary || "")}</span>
          ${prLinks ? `<div class="links">${prLinks}</div>` : ""}
        </li>`;
      })
      .join("");
    return `
      <div class="roadmap-column ${tone}">
        <h3>${esc(title)}</h3>
        <ul class="control-list">${rows || "<li class='muted'>No items.</li>"}</ul>
      </div>
    `;
  }

  function renderRoadmap(state) {
    const timeline = state.timeline || {};
    return `
      ${renderTimelineColumn("Now", timeline.now, "warn")}
      ${renderTimelineColumn("Next", timeline.next, "ok")}
      ${renderTimelineColumn("Later", timeline.later, "violet")}
    `;
  }

  function renderWorkstreams(state) {
    return (state.workstreams || [])
      .map((ws) => {
        const blockers = (ws.blockers || []).map((b) => `<li>${esc(b)}</li>`).join("");
        return `
          <div class="workstream-column">
            <h3>${esc(ws.title)}</h3>
            <span class="badge ${statusClass(ws.status)}">${esc(ws.status)}</span>
            <p class="detail">${esc(ws.summary || "")}</p>
            ${blockers ? `<ul class="mini-list">${blockers}</ul>` : ""}
          </div>
        `;
      })
      .join("");
  }

  function renderDecisions(state) {
    return (state.decisions || [])
      .map(
        (d) => `
        <div class="decision-entry">
          <div class="decision-meta"><span>${esc(d.date)}</span><span>${esc(d.status)}</span></div>
          <strong>${esc(d.title)}</strong>
          <div class="detail">${esc(d.rationale)}</div>
        </div>
      `
      )
      .join("");
  }

  function renderRisks(state) {
    return (state.risks || [])
      .map(
        (r) => `
        <div class="risk-entry">
          <strong>${esc(r.title)}</strong>
          <div class="detail">Control: ${esc(r.control)}</div>
        </div>
      `
      )
      .join("");
  }

  function renderIssuesList(issues, emptyLabel) {
    if (!issues || !issues.length) {
      return `<p class="muted">${esc(emptyLabel)}</p>`;
    }
    return `<ul class="control-list">${issues
      .map(
        (issue) => `
        <li>
          <a href="${esc(issue.url)}" target="_blank" rel="noopener noreferrer">#${esc(issue.number)}</a>
          <strong>${esc(issue.title)}</strong>
          <span class="detail">${esc((issue.labels || []).join(", "))}</span>
        </li>
      `
      )
      .join("")}</ul>`;
  }

  function renderDeployment(state) {
    const dep = state.deployment || {};
    const gates = state.qa_gates || {};
    return `
      <div class="stat"><div class="label">Field Desk map</div><div class="value"><a href="${esc(dep.field_desk_map)}" target="_blank" rel="noopener noreferrer">Open</a></div></div>
      <div class="stat"><div class="label">God View admin</div><div class="value"><a href="${esc(dep.field_desk_admin)}" target="_blank" rel="noopener noreferrer">Open</a></div></div>
      <div class="stat"><div class="label">WordPress /map/</div><div class="value"><a href="${esc(dep.wordpress_map)}" target="_blank" rel="noopener noreferrer">Open</a></div></div>
      <div class="stat"><div class="label">Backend gate</div><div class="value">${gates.backend_reliability_gate?.qa_pass ? "PASS" : "FAIL"}</div></div>
      <div class="stat"><div class="label">Discovery QA</div><div class="value">${gates.discovery_taxonomy?.qa_pass ? "PASS" : "FAIL"}</div></div>
      <div class="stat"><div class="label">GPS audit</div><div class="value">${gates.public_map_gps_audit?.qa_pass ? "PASS" : gates.public_map_gps_audit?.artifact ? "CHECK" : "N/A"}</div></div>
    `;
  }

  function render(state, branch) {
    const cc = state.command_center || {};
    const tracker = state.github_tracker || {};
    const chat = state.chat_integration_handoff || {};

    const objective = document.getElementById("current-objective");
    const stage = document.getElementById("current-stage");
    const gate = document.getElementById("current-gate-label");
    const nextGate = document.getElementById("next-gate-label");
    const futureLock = document.getElementById("future-work-lock");
    if (objective) objective.textContent = cc.current_objective || "—";
    if (stage) stage.textContent = cc.current_stage || "—";
    if (gate) gate.textContent = cc.current_gate || "—";
    if (nextGate) nextGate.textContent = cc.next_gate || "—";
    if (futureLock) futureLock.textContent = cc.future_work_lock || "—";

    const badges = document.getElementById("project-badges");
    if (badges) badges.innerHTML = renderBadges(state);

    const summary = document.getElementById("project-summary");
    if (summary) summary.innerHTML = renderSummary(state);

    const roadmap = document.getElementById("roadmap-columns");
    if (roadmap) roadmap.innerHTML = renderRoadmap(state);

    const workstreams = document.getElementById("workstream-board");
    if (workstreams) workstreams.innerHTML = renderWorkstreams(state);

    const decisions = document.getElementById("decision-log");
    if (decisions) decisions.innerHTML = renderDecisions(state);

    const risks = document.getElementById("risk-list");
    if (risks) risks.innerHTML = renderRisks(state);

    const deployment = document.getElementById("deployment-status");
    if (deployment) deployment.innerHTML = renderDeployment(state);

    const links = document.getElementById("deployment-links");
    if (links) {
      links.innerHTML = `
        <a href="${LIVE_FEEDS_BASE}/${encodeURIComponent(branch)}/${STATE_PATH}" target="_blank" rel="noopener noreferrer">Raw project state JSON</a>
        <a href="https://github.com/setoxxx/nycif-live-feeds/actions" target="_blank" rel="noopener noreferrer">Live-feeds Actions</a>
        <a href="https://github.com/setoxxx/nycif-field-desk/actions" target="_blank" rel="noopener noreferrer">Field-desk Actions</a>
        <button type="button" id="godViewRefresh" style="cursor:pointer;border:1px solid rgba(255,255,255,.12);border-radius:999px;padding:8px 14px;background:#182235;color:#60a5fa;font:inherit">Refresh project state</button>
      `;
      document.getElementById("godViewRefresh")?.addEventListener("click", () => void load(true));
    }

    const bookmarks = document.getElementById("canonical-bookmarks");
    if (bookmarks) {
      const dep = state.deployment || {};
      bookmarks.innerHTML = `
        <a href="${esc(dep.field_desk_map)}" target="_blank" rel="noopener noreferrer">Public map</a>
        <a href="${esc(dep.field_desk_admin)}" target="_blank" rel="noopener noreferrer">God View admin</a>
        <a href="${esc(dep.wordpress_map)}" target="_blank" rel="noopener noreferrer">WordPress map</a>
        <a href="./calendar.html">Assignment Desk Calendar</a>
      `;
    }

    const actions = document.getElementById("project-actions");
    if (actions) {
      actions.innerHTML = `
        <a class="primary-action" href="${esc(state.deployment?.field_desk_map || "#")}" target="_blank" rel="noopener noreferrer">Open live map</a>
        <a href="#live-pipeline-section">Live pipeline</a>
        <a href="#discovery-god-view-section">Discovery queues</a>
      `;
    }

    const freshness = document.getElementById("project-state-freshness");
    if (freshness) {
      const ageH = hoursSince(state.generated_at_utc);
      freshness.hidden = false;
      if (ageH > 48) {
        freshness.className = "notice warn";
        freshness.textContent = `Project state is ${Math.round(ageH)}h old (branch ${branch}). CI should regenerate status/nycif-godview-project-state-v02.json.`;
      } else {
        freshness.className = "notice ok";
        freshness.textContent = `Project state loaded from ${branch} · generated ${fmtTime(state.generated_at_utc)}.`;
      }
    }

    // Inject GitHub tracker section after workstreams if not present
    let trackerSection = document.getElementById("github-tracker-section");
    if (!trackerSection) {
      const workstreamsPanel = document.getElementById("workstreams");
      if (workstreamsPanel) {
        trackerSection = document.createElement("section");
        trackerSection.className = "panel";
        trackerSection.id = "github-tracker-section";
        workstreamsPanel.insertAdjacentElement("afterend", trackerSection);
      }
    }
    if (trackerSection) {
      trackerSection.innerHTML = `
        <h2>Open PRs &amp; issues (snapshot)</h2>
        <p class="section-intro">Read-only GitHub snapshot from CI — not live API calls from the browser.</p>
        <div class="grid">
          <div class="workstream-column">
            <h3>Open PRs (live-feeds)</h3>
            ${renderIssuesList(
              (tracker.open_prs || []).map((pr) => ({
                number: pr.number,
                title: pr.title,
                url: pr.url,
                labels: [pr.draft ? "draft" : "open", pr.branch].filter(Boolean),
              })),
              "No open PR snapshot — run generate_godview_project_state.py --fetch-github in CI."
            )}
          </div>
          <div class="workstream-column">
            <h3>Open issues (field-desk)</h3>
            ${renderIssuesList(tracker.open_issues_field_desk, "No field-desk issue snapshot yet.")}
          </div>
          <div class="workstream-column">
            <h3>Chat handoff (M12)</h3>
            <span class="badge violet">${esc(chat.status || "not_started")}</span>
            <p class="detail">Repo: ${esc(chat.target_repo || "nycif-field-desk")}</p>
            <ul class="mini-list">${(chat.open_decisions || [])
              .map((d) => `<li>${esc(d)}</li>`)
              .join("")}</ul>
          </div>
        </div>
      `;
    }
  }

  async function load(forceRefresh) {
    const loading = document.getElementById("project-control-loading");
    const content = document.getElementById("project-control-content");
    if (loading) loading.hidden = false;
    if (content) content.hidden = true;

    try {
      const { branch, state } = await fetchState();
      render(state, branch);
      if (loading) loading.hidden = true;
      if (content) content.hidden = false;
      window.NYCIF_GODVIEW_PROJECT_STATE = { branch, state, version: VERSION, force_refresh: forceRefresh };
      document.dispatchEvent(new CustomEvent("nycif-godview-project-ready", { detail: { branch, state } }));
    } catch (error) {
      if (loading) {
        loading.innerHTML = `<div class="notice danger">Could not load project state.<br><br>${esc(
          error.message || error
        )}<br><br>Expected: ${esc(STATE_PATH)} on nycif-live-feeds main.</div>`;
      }
    }
  }

  window.NYCIF_GODVIEW_PROJECT_CONTROL = {
    version: VERSION,
    refresh: () => load(true),
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => void load(false));
  } else {
    void load(false);
  }
})();
