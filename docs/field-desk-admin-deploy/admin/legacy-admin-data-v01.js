/**
 * Legacy admin historical sections — defers to dynamic panels when available.
 */
(() => {
  const VERSION = "legacy-admin-data-v01";

  function esc(value) {
    return String(value ?? "").replace(/[&<>"']/g, (ch) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch])
    );
  }

  function setHtml(id, html) {
    const el = document.getElementById(id);
    if (el) el.innerHTML = html;
  }

  function renderHistoricalNotice() {
    const notice = `
      <div class="notice ok">
        Historical snapshots below are static/local. For current operational status use
        <strong>Project Control Center</strong> (top), <strong>Live Pipeline</strong>, and
        <strong>Discovery God View</strong> panels — they load fresh JSON from nycif-live-feeds main.
      </div>
    `;
    ["project-status", "source-freshness", "overview"].forEach((id) => {
      const el = document.getElementById(id);
      if (el && !el.dataset.legacyHydrated) {
        el.insertAdjacentHTML("afterbegin", notice);
        el.dataset.legacyHydrated = "1";
      }
    });
  }

  function hydrateFromProjectState(state) {
    if (!state) return;
    const summary = state.status_summary || state.command_center?.current_stage;
    if (summary) {
      setHtml(
        "project-status",
        `<p class="detail">${esc(summary)}</p><p class="muted">Full timeline: see Project Control Center above.</p>`
      );
    }
    const counts = state.counts || {};
    setHtml(
      "overview",
      `<div class="grid">
        <div class="stat"><div class="label">Discovery approved</div><div class="value">${esc(counts.discovery_approved_events ?? "—")}</div></div>
        <div class="stat"><div class="label">Supplemental approved</div><div class="value">${esc(counts.supplemental_approved ?? "—")}</div></div>
      </div>`
    );
  }

  document.addEventListener("nycif-godview-project-ready", (event) => {
    hydrateFromProjectState(event.detail?.state);
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", renderHistoricalNotice);
  } else {
    renderHistoricalNotice();
  }

  window.NYCIF_LEGACY_ADMIN_DATA = { version: VERSION };
})();
