/**
 * News Desk + Parade Census QA panel for God View admin.
 * Read-only — loads civic_people_facing_godview_digest.json from live-feeds.
 * Prefers main; falls back to PR branch until News Desk fields land on main.
 */
(() => {
  "use strict";
  const VERSION = "news-desk-godview-panel-v01";
  const LIVE_FEEDS = "https://raw.githubusercontent.com/setoxxx/nycif-live-feeds";
  const BRANCH_CANDIDATES = ["main", "cursor/citywide-parade-census-bfb8"];
  const DIGEST_PATH = "data/civic_people_facing_godview_digest.json";

  function esc(value) {
    return String(value ?? "").replace(/[&<>"']/g, (ch) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch])
    );
  }

  function fmtNum(value) {
    return Number.isFinite(Number(value)) ? Number(value).toLocaleString() : "0";
  }

  function hasNewsDeskFields(payload) {
    return payload
      && typeof payload === "object"
      && payload.news_desk_checklist
      && typeof payload.news_desk_checklist === "object";
  }

  async function fetchDigest() {
    let lastError = null;
    let fallback = null;
    for (const branch of BRANCH_CANDIDATES) {
      try {
        const url = `${LIVE_FEEDS}/${branch}/${DIGEST_PATH}?v=${Date.now()}`;
        const response = await fetch(url, { cache: "no-store" });
        if (!response.ok) {
          lastError = new Error(`${branch}/${DIGEST_PATH}: HTTP ${response.status}`);
          continue;
        }
        const payload = await response.json();
        if (hasNewsDeskFields(payload)) {
          return { branch, payload };
        }
        // Keep first successful digest as last-resort fallback.
        if (!fallback) fallback = { branch, payload };
      } catch (error) {
        lastError = error;
      }
    }
    if (fallback) return fallback;
    throw lastError || new Error(`Could not load ${DIGEST_PATH}`);
  }

  function render(root, branch, digest) {
    const checklist = digest.news_desk_checklist || {};
    const census = digest.parade_census || {};
    const assignment =
      checklist.assignment_mode_link ||
      "https://setoxxx.github.io/nycif-field-desk/?v=civic-people-facing-v01&resetFilters=1&feeds=main&mode=all&assignment=1";

    root.innerHTML = `
      <div class="notice violet">News Desk + Parade Census ${esc(VERSION)} — read-only staging QA. Not a publish control.</div>
      <div class="notice ok">Loaded from <code>${esc(branch)}</code> · ${esc(digest.public_map_policy || "Staging only")}</div>
      <div class="notice">map_eligible stays false / promotion_allowed false until explicit human promotion. Public map default feed unchanged.</div>

      <h3>Checklist KPIs</h3>
      <div class="grid">
        <div class="stat"><div class="label">Checklist QA</div><div class="value">${checklist.qa_pass ? "PASS" : "CHECK"}</div><div class="detail">total ${esc(fmtNum(checklist.total_rows))}</div></div>
        <div class="stat"><div class="label">Today stories</div><div class="value">${esc(fmtNum(checklist.today_count))}</div><div class="detail">priority unchecked ${esc(fmtNum(checklist.priority_unchecked_count))}</div></div>
        <div class="stat"><div class="label">Map-ready checklist</div><div class="value">${esc(fmtNum(checklist.map_ready_count))}</div><div class="detail">list_only demoted rows stay off map</div></div>
      </div>

      <h3>Parade census KPIs</h3>
      <div class="grid">
        <div class="stat"><div class="label">Parade census QA</div><div class="value">${census.qa_pass ? "PASS" : "CHECK"}</div><div class="detail">merged ${esc(fmtNum(census.merged_total))}</div></div>
        <div class="stat"><div class="label">Priority events</div><div class="value">${esc(fmtNum(census.priority_event_count))}</div><div class="detail">anchor matches ${esc(fmtNum(census.anchor_permit_matches))}</div></div>
      </div>

      <div class="links" style="margin-top:12px">
        <a href="${esc(assignment)}" target="_blank" rel="noopener noreferrer">Open Assignment mode</a>
        <a href="https://github.com/setoxxx/nycif-live-feeds/blob/${encodeURIComponent(branch)}/data/news_desk_assignment_checklist.json" target="_blank" rel="noopener noreferrer">Checklist JSON</a>
        <a href="https://github.com/setoxxx/nycif-live-feeds/blob/${encodeURIComponent(branch)}/data/citywide_parade_census_snapshot.json" target="_blank" rel="noopener noreferrer">Parade census JSON</a>
        <a href="https://github.com/setoxxx/nycif-live-feeds/blob/${encodeURIComponent(branch)}/data/news_desk_assignment_checklist_report.json" target="_blank" rel="noopener noreferrer">Checklist QA report</a>
      </div>
    `;
  }

  async function load(options = {}) {
    const root = document.getElementById("news-desk-god-view");
    const status = document.getElementById("news-desk-god-view-status");
    if (!root) return;
    if (status) {
      status.textContent = options.refresh
        ? "Refreshing News Desk God View digest…"
        : "Loading News Desk + Parade Census digest…";
    }
    try {
      const { branch, payload } = await fetchDigest();
      render(root, branch, payload || {});
      if (status) status.textContent = `News Desk God View loaded from ${branch}.`;
      window.NYCIF_NEWS_DESK_GODVIEW_SUMMARY = {
        branch,
        checklist_qa_pass: Boolean((payload.news_desk_checklist || {}).qa_pass),
        parade_qa_pass: Boolean((payload.parade_census || {}).qa_pass),
      };
      document.dispatchEvent(new CustomEvent("nycif-news-desk-godview-ready", { detail: { branch } }));
    } catch (error) {
      root.innerHTML = `<div class="notice danger">Could not load News Desk QA summary.<br><br>${esc(error.message || error)}<br><br>Expected: data/civic_people_facing_godview_digest.json with news_desk_checklist (PR #179 / main after merge).</div>`;
      if (status) status.textContent = "News Desk God View unavailable.";
    }
  }

  document.addEventListener("DOMContentLoaded", () => load());
  window.NYCIF_NEWS_DESK_GODVIEW = { version: VERSION, load };
})();
