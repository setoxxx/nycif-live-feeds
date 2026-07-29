/* NYCIF God View — Daily News Desk data health (read-only). */
(() => {
  "use strict";

  const VERSION = "daily-data-health-panel-v01";

  function esc(value) {
    return String(value ?? "").replace(/[&<>"']/g, (ch) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch])
    );
  }

  function fmtNum(value) {
    const number = Number(value);
    return Number.isFinite(number) ? number.toLocaleString() : "—";
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

  function badge(status) {
    const normalized = String(status || "UNKNOWN").toUpperCase();
    const css = normalized === "READY" || normalized === "PASS" ? "ok" : normalized === "BLOCKED" || normalized === "FAIL" ? "danger" : "warn";
    return `<span class="badge ${css}">${esc(normalized)}</span>`;
  }

  function sourceRows(health) {
    return (health.sources || []).map((source) => `
      <tr>
        <td><strong>${esc(source.name)}</strong><div class="detail"><code>${esc(source.artifact)}</code></div></td>
        <td>${source.fresh ? badge("PASS") : badge("FAIL")}</td>
        <td>${esc(fmtTime(source.generated_at_utc))}</td>
        <td>${source.age_hours == null ? "—" : `${esc(source.age_hours)}h`}</td>
        <td>${esc(fmtNum(source.record_count))}</td>
        <td>${esc(source.fetch_mode || "live")}${source.live_fetch === false ? " · fallback" : ""}</td>
      </tr>
    `).join("");
  }

  function derivedRows(health) {
    return (health.derived_artifacts || []).map((item) => `
      <tr>
        <td><strong>${esc(item.name)}</strong><div class="detail"><code>${esc(item.artifact)}</code></div></td>
        <td>${item.fresh ? badge("PASS") : badge("FAIL")}</td>
        <td>${esc(fmtTime(item.generated_at_utc))}</td>
        <td>${item.age_hours == null ? "—" : `${esc(item.age_hours)}h`}</td>
        <td>${esc(fmtNum(item.record_count))}</td>
      </tr>
    `).join("");
  }

  function gateCard(label, pass, detail) {
    return `<div class="stat"><div class="label">${esc(label)}</div><div class="value">${pass ? "PASS" : "FAIL"}</div>${detail ? `<div class="detail">${esc(detail)}</div>` : ""}</div>`;
  }

  function render(state) {
    const health = state?.daily_data_health;
    if (!health) return;

    let section = document.getElementById("daily-data-health-section");
    if (!section) {
      section = document.createElement("section");
      section.id = "daily-data-health-section";
      section.className = "panel";
      const projectControl = document.getElementById("project-control");
      projectControl?.insertAdjacentElement("afterend", section);
    }

    const pipeline = health.pipeline || {};
    const blockers = health.blockers || [];
    const rollback = health.rollback || {};
    const ready = health.status === "READY" && health.release_ready === true;

    section.innerHTML = `
      <div style="display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:12px">
        <div>
          <h2 style="margin-bottom:4px">News Desk Daily Data Health</h2>
          <p class="section-intro" style="margin:0">The public feed may refresh only when every official source, occurrence, reconciliation, and duplicate gate passes.</p>
        </div>
        ${badge(health.status)}
      </div>
      <div class="notice ${ready ? "ok" : "danger"}">
        ${esc(health.operating_rule || "Do not publish unless status is READY.")}
        <br><strong>Generated:</strong> ${esc(fmtTime(health.generated_at_utc))}
      </div>

      <h3>Official source freshness</h3>
      <div class="table-wrap"><table>
        <thead><tr><th>Source</th><th>Gate</th><th>Generated</th><th>Age</th><th>Rows</th><th>Fetch mode</th></tr></thead>
        <tbody>${sourceRows(health) || "<tr><td colspan='6'>No source status.</td></tr>"}</tbody>
      </table></div>

      <h3 style="margin-top:16px">Derived map artifacts</h3>
      <div class="table-wrap"><table>
        <thead><tr><th>Artifact</th><th>Gate</th><th>Generated</th><th>Age</th><th>Rows</th></tr></thead>
        <tbody>${derivedRows(health) || "<tr><td colspan='5'>No artifact status.</td></tr>"}</tbody>
      </table></div>

      <h3 style="margin-top:16px">Integrity and accounting gates</h3>
      <div class="grid">
        ${gateCard("Strict reconciliation", pipeline.strict_reconciliation === true, `Unexplained Calendar/Parks gap: ${fmtNum(pipeline.calendar_parks_unaccounted_gap)}`)}
        ${gateCard("Canonical identity", pipeline.canonical_identity_clean === true, "Zero schema/identity errors required")}
        ${gateCard("Cross-source dedupe", pipeline.cross_source_dedupe_clean === true, "Approved public markers")}
        ${gateCard("Shared-CEMS dedupe", pipeline.shared_cems_dedupe_clean === true, "Zero fatal blocked groups")}
        ${gateCard("Recurring-date preservation", Number(pipeline.cross_date_street_occurrences_suppressed || 0) === 0, `${fmtNum(pipeline.cross_date_street_occurrences_suppressed)} cross-date occurrences suppressed`)}
        ${gateCard("Exact duplicate cleanup", true, `${fmtNum(pipeline.exact_occurrence_duplicates_suppressed)} exact occurrences suppressed`)}
      </div>

      <h3 style="margin-top:16px">Blocking reasons</h3>
      ${blockers.length ? `<ul class="control-list">${blockers.map((item) => `<li><strong>${esc(item.code || "blocker")}</strong><span class="detail">${esc(item.message || "")}</span><code>${esc(item.artifact || "")}</code></li>`).join("")}</ul>` : `<div class="notice ok">No daily-data blockers.</div>`}

      <h3 style="margin-top:16px">Rollback</h3>
      <div class="stat">
        <div class="label">Previous serving feed commit</div>
        <div class="value"><code>${esc(rollback.previous_public_feed_commit || "Recorded during the next production refresh")}</code></div>
        <div class="detail">${esc(rollback.strategy || health.rollback_rule || "Failed refreshes leave the serving feed unchanged.")}</div>
      </div>
    `;

    window.NYCIF_DAILY_DATA_HEALTH_PANEL = { version: VERSION, health };
  }

  document.addEventListener("nycif-godview-project-ready", (event) => render(event.detail?.state));
  const existing = window.NYCIF_GODVIEW_PROJECT_STATE?.state;
  if (existing) render(existing);
})();
