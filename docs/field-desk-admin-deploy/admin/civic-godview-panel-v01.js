/**
 * Civic people-facing God View panel — bookmark current intake / map coverage.
 * Read-only. No publish / promote / location_cache controls.
 */
(() => {
  const VERSION = "civic-godview-panel-v01";
  const LIVE_FEEDS_BASE = "https://raw.githubusercontent.com/setoxxx/nycif-live-feeds";
  const BRANCH_CANDIDATES = ["main", "cursor/pin-integrity-shoot-day-gate-da92"];
  const DIGEST_PATH = "data/civic_people_facing_godview_digest.json";

  function esc(value) {
    return String(value ?? "").replace(/[&<>"']/g, (ch) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch])
    );
  }

  function fmtNum(value) {
    return Number.isFinite(Number(value)) ? Number(value).toLocaleString() : "0";
  }

  async function fetchDigest() {
    let lastError = null;
    for (const branch of BRANCH_CANDIDATES) {
      try {
        const url = `${LIVE_FEEDS_BASE}/${branch}/${DIGEST_PATH}?v=${Date.now()}`;
        const response = await fetch(url, { cache: "no-store" });
        if (!response.ok) {
          lastError = new Error(`${branch}/${DIGEST_PATH}: HTTP ${response.status}`);
          continue;
        }
        return { branch, payload: await response.json() };
      } catch (error) {
        lastError = error;
      }
    }
    throw lastError || new Error(`Could not load ${DIGEST_PATH}`);
  }

  function listHtml(items) {
    if (!items || !items.length) return "<li class=\"empty\">None listed.</li>";
    return items.map((item) => `<li>${esc(item)}</li>`).join("");
  }

  function render(root, branch, digest) {
    const counts = digest.counts || {};
    const qa = digest.qa || {};
    const checkpoint = digest.checkpoint || {};
    const fieldDesk = digest.field_desk || {};
    const gap = digest.food_access_gap || {};
    const pin = digest.pin_integrity || {};
    const shoot = digest.shoot_day_certified || {};
    const links = digest.artifact_links || {};

    root.innerHTML = `
      <div class="notice violet">Civic People-Facing God View ${esc(VERSION)} — project bookmark. Read-only; not a public-map publish control.</div>
      <div class="notice ok">Loaded from <code>${esc(branch)}</code>. Merged PR #${esc(checkpoint.merged_pr || 171)} · promotion_allowed=${esc(String(checkpoint.promotion_allowed))}.</div>
      <div class="notice">${esc(digest.public_map_policy || "")}</div>

      <h3>Pin Integrity KPI</h3>
      <div class="grid">
        <div class="stat"><div class="label">map_ready certified</div><div class="value">${esc(fmtNum(pin.map_ready_after_total ?? counts.pin_map_ready_certified))}</div><div class="detail">before ${esc(fmtNum(pin.map_ready_before_total))}</div></div>
        <div class="stat"><div class="label">Demotions</div><div class="value">${esc(fmtNum(pin.demotion_count ?? counts.pin_demotions))}</div><div class="detail">Prefer list_only over ocean pins</div></div>
        <div class="stat"><div class="label">Pin gate</div><div class="value">${pin.qa_pass ? "PASS" : "FAIL"}</div><div class="detail">${pin.qa_pass ? '<span class="notice ok">qa_pass</span>' : '<span class="notice danger">fail-closed</span>'}</div></div>
      </div>

      <h3>Shoot Day Certified (read-only)</h3>
      <div class="grid">
        <div class="stat"><div class="label">Today certified pins</div><div class="value">${esc(fmtNum(shoot.today_certified_pins ?? counts.shoot_day_today_certified))}</div><div class="detail">needs location ${esc(fmtNum(shoot.today_needs_location))}</div></div>
        <div class="stat"><div class="label">Tomorrow certified pins</div><div class="value">${esc(fmtNum(shoot.tomorrow_certified_pins ?? counts.shoot_day_tomorrow_certified))}</div><div class="detail">needs location ${esc(fmtNum(shoot.tomorrow_needs_location))}</div></div>
      </div>
      <div class="links">
        ${shoot.today_field_desk_link ? `<a href="${esc(shoot.today_field_desk_link)}" target="_blank" rel="noopener noreferrer">Field Desk today (assignment=1)</a>` : ""}
        ${shoot.tomorrow_field_desk_link ? `<a href="${esc(shoot.tomorrow_field_desk_link)}" target="_blank" rel="noopener noreferrer">Field Desk tomorrow (assignment=1)</a>` : ""}
        <a href="https://github.com/setoxxx/nycif-live-feeds/blob/${encodeURIComponent(branch)}/data/photographer_shoot_day_certified_pack.json" target="_blank" rel="noopener noreferrer">Shoot Day Certified pack JSON</a>
      </div>

      <h3>Where we are</h3>
      <div class="grid">
        <div class="stat"><div class="label">Accepted civic rows</div><div class="value">${esc(fmtNum(counts.accepted))}</div><div class="detail">Quarantined ${esc(fmtNum(counts.quarantined))}</div></div>
        <div class="stat"><div class="label">map_ready</div><div class="value">${esc(fmtNum(counts.map_ready))}</div><div class="detail">Native valid NYC pins</div></div>
        <div class="stat"><div class="label">list_only</div><div class="value">${esc(fmtNum(counts.list_only))}</div><div class="detail">Searchable; no invented pins</div></div>
        <div class="stat"><div class="label">proposed (review-only)</div><div class="value">${esc(fmtNum(counts.proposed))}</div><div class="detail">Separate proposals artifact</div></div>
        <div class="stat"><div class="label">Upcoming (next 7 days)</div><div class="value">${esc(fmtNum(counts.upcoming_next_7_days))}</div><div class="detail">30-day window ${esc(fmtNum(counts.upcoming_next_30_days))}</div></div>
        <div class="stat"><div class="label">Coverage QA</div><div class="value">${esc(qa.map_coverage_qa_pass ? "PASS" : "CHECK")}</div><div class="detail">Staging QA ${esc(qa.staging_qa_pass ? "pass" : "fail")}</div></div>
      </div>

      <h3>Lanes (do not collapse)</h3>
      <ul class="mini-list">
        <li><strong>Approved</strong> — ${esc((digest.lanes || {}).Approved || "permits")}</li>
        <li><strong>Review</strong> — ${esc((digest.lanes || {}).Review || "calendar/Parks ∪ civic")}</li>
        <li><strong>Help Places</strong> — ${esc((digest.lanes || {})["Help Places"] || "markets + directories")}</li>
      </ul>

      <h3>Field Desk next (human push)</h3>
      <div class="notice warn">cursor[bot] cannot push nycif-field-desk. Howard copies package ${esc(fieldDesk.package || "")}</div>
      <div class="links">
        <a href="https://setoxxx.github.io/nycif-field-desk/${esc(fieldDesk.preview_after_merge || "?v=civic-people-facing-v01&resetFilters=1&feeds=main")}" target="_blank" rel="noopener noreferrer">Field Desk civic preview</a>
        <a href="${esc(links.merged_pr || "https://github.com/setoxxx/nycif-live-feeds/pull/171")}" target="_blank" rel="noopener noreferrer">Merged PR #171</a>
        <a href="https://github.com/setoxxx/nycif-live-feeds/blob/${encodeURIComponent(branch)}/data/civic_people_facing_godview_digest.json" target="_blank" rel="noopener noreferrer">Civic God View digest JSON</a>
        <a href="https://github.com/setoxxx/nycif-live-feeds/blob/${encodeURIComponent(branch)}/docs/field-desk-map-deploy/civic-people-facing-v01/README.md" target="_blank" rel="noopener noreferrer">Pages push checklist</a>
      </div>

      <h3>Food-access honesty</h3>
      <div class="notice danger">${esc(gap.status || "known_gap")} — ${esc(gap.honesty || "No live citywide soup-kitchen pin feed.")}</div>

      <h3>Next human steps</h3>
      <ul class="mini-list">${listHtml(digest.next_human_steps)}</ul>

      <h3>Still unapproved / unpromoted</h3>
      <ul class="mini-list">${listHtml(digest.remain_unapproved_unpromoted)}</ul>
    `;
  }

  async function load(options = {}) {
    const root = document.getElementById("civic-god-view");
    const status = document.getElementById("civic-god-view-status");
    if (!root) return;
    if (status) {
      status.textContent = options.refresh
        ? "Refreshing civic God View digest…"
        : "Loading civic God View digest…";
    }
    try {
      const { branch, payload } = await fetchDigest();
      render(root, branch, payload || {});
      if (status) status.textContent = `Civic God View loaded from ${branch}.`;
      document.dispatchEvent(new CustomEvent("nycif-civic-godview-ready", { detail: { branch } }));
    } catch (error) {
      root.innerHTML = `<div class="notice danger">Could not load civic God View digest.<br><br>${esc(error.message || error)}<br><br>Expected: data/civic_people_facing_godview_digest.json on main (after coverage PR).</div>`;
      if (status) status.textContent = "Civic God View unavailable.";
    }
  }

  document.addEventListener("DOMContentLoaded", () => load());
  window.NYCIF_CIVIC_GODVIEW = { version: VERSION, load };
})();
