/**
 * Discovery Taxonomy God View panel — newly pulled + rejected/review queues.
 * Read-only. Fetches digests from nycif-live-feeds raw GitHub.
 */
(() => {
  const VERSION = "discovery-godview-panel-v02";
  const LIVE_FEEDS_BASE = "https://raw.githubusercontent.com/setoxxx/nycif-live-feeds";
  const BRANCH_CANDIDATES = [
    "cursor/discovery-taxonomy-v02-27bf",
    "main",
  ];

  const PATHS = {
    digest: "data/events_discovery_godview_digest_v02.json",
    assist: "data/howard_classification_assist_v02.json",
    delta: "data/live_delta_report.json",
    recon: "data/events_discovery_reconciliation_v02.json",
  };

  function esc(value) {
    return String(value ?? "").replace(/[&<>"']/g, (ch) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch])
    );
  }

  function fmtNum(value) {
    return Number.isFinite(Number(value)) ? Number(value).toLocaleString() : "0";
  }

  async function fetchBranchJson(path) {
    let lastError = null;
    for (const branch of BRANCH_CANDIDATES) {
      try {
        const url = `${LIVE_FEEDS_BASE}/${branch}/${path}?v=${Date.now()}`;
        const response = await fetch(url, { cache: "no-store" });
        if (!response.ok) {
          lastError = new Error(`${branch}/${path}: HTTP ${response.status}`);
          continue;
        }
        return { branch, payload: await response.json() };
      } catch (error) {
        lastError = error;
      }
    }
    throw lastError || new Error(`Could not load ${path}`);
  }

  function rowsHtml(rows, cols) {
    if (!rows || !rows.length) {
      return `<tr><td colspan="${cols}" class="empty">No rows in this slice.</td></tr>`;
    }
    return rows
      .map((r) => {
        const title = esc(r.title || "Untitled");
        const date = esc(r.date || "—");
        const loc = esc(String(r.location || "—").slice(0, 90));
        const reason = esc(r.reason_for_review || r.reason || r.pattern_bucket || "—");
        const cls = esc(r.current_classification || r.suggested_category || "—");
        const action = esc(r.recommended_action || r.suggestion_note || "—");
        return `<tr><td>${date}</td><td>${title}</td><td>${loc}</td><td>${cls}</td><td>${reason}</td><td>${action}</td></tr>`;
      })
      .join("");
  }

  function render(root, data) {
    const digest = data.digest || {};
    const assist = data.assist || {};
    const queues = digest.queue_totals || {};
    const delta = digest.daily_delta || {};
    const pipe = digest.pipeline_snapshot || {};
    const needs = (assist.needs_howard_label_titles || []).slice(0, 40);
    const lowSample = (digest.review_queues_preview?.low_confidence_sample || []).slice(0, 15);
    const missingSample = (digest.review_queues_preview?.missing_coordinates_sample || []).slice(0, 15);
    const gpsSample = (digest.review_queues_preview?.gps_review_sample || []).slice(0, 15);
    const invalidSample = (digest.review_queues_preview?.invalid_rejected_sample || []).slice(0, 15);
    const addedSample = (delta.added_sample || []).slice(0, 20);
    const patternCounts = assist.pattern_counts || digest.howard_assist?.pattern_counts || {};

    root.innerHTML = `
      <div class="notice violet">Discovery God View ${esc(VERSION)} — operator desk for daily intake, not the public map. Read-only.</div>
      <div class="notice ok">Loaded from branch: ${esc(data.branch)}. Accepted canonical ${esc(fmtNum(pipe.accepted_canonical_records))} · reconciles=${esc(String(pipe.reconciles))}.</div>

      <h3>Today’s intake cards</h3>
      <div class="grid">
        <div class="stat"><div class="label">Newly added (delta)</div><div class="value">${esc(fmtNum(delta.added_count))}</div><div class="detail">Removed ${esc(fmtNum(delta.removed_count))} · Changed ${esc(fmtNum(delta.changed_count))}</div></div>
        <div class="stat"><div class="label">Hard invalid rejected</div><div class="value">${esc(fmtNum(queues.hard_invalid_rejected))}</div><div class="detail">Malformed / no identity-date-title</div></div>
        <div class="stat"><div class="label">Low-confidence (needs label)</div><div class="value">${esc(fmtNum(queues.low_confidence_general_fallback))}</div><div class="detail">Fell back to category=general</div></div>
        <div class="stat"><div class="label">List-only missing GPS</div><div class="value">${esc(fmtNum(queues.missing_or_invalid_coordinates_list_only))}</div><div class="detail">Still searchable; no invented pins</div></div>
        <div class="stat"><div class="label">GPS review queue (Phase 1)</div><div class="value">${esc(fmtNum(queues.phase1_gps_review_queue))}</div><div class="detail">Not rejected — waiting GPS memory/review</div></div>
        <div class="stat"><div class="label">Legacy major quarantine</div><div class="value">${esc(fmtNum(queues.legacy_major_quarantined))}</div><div class="detail">Demoted until current major evidence</div></div>
        <div class="stat"><div class="label">Possible duplicate groups</div><div class="value">${esc(fmtNum(queues.possible_duplicate_groups))}</div><div class="detail">Not auto-merged</div></div>
      </div>

      <h3>Howard assist — pattern buckets to confirm</h3>
      <div class="notice">Confirm these suggested rules once and daily pulls will classify with less error. Titles still under <code>needs_howard_label</code> need a one-line category reply.</div>
      <div class="grid">
        ${Object.entries(patternCounts)
          .map(
            ([k, v]) =>
              `<div class="stat"><div class="label">${esc(k)}</div><div class="value">${esc(fmtNum(v))}</div></div>`
          )
          .join("") || '<div class="empty">No pattern counts yet.</div>'}
      </div>
      <details open>
        <summary>Titles that still need Howard’s category (${needs.length} shown)</summary>
        <ul class="mini-list">
          ${needs.map((t) => `<li>${esc(t)}</li>`).join("") || "<li class='muted'>None — all low-confidence rows matched a suggested pattern.</li>"}
        </ul>
      </details>

      <h3>Newly pulled events</h3>
      <div class="table-wrap"><table><thead><tr><th>Date</th><th>Title</th><th>Location</th><th>Class</th><th>Reason</th><th>Action</th></tr></thead><tbody>
        ${
          addedSample.length
            ? addedSample
                .map((r) => {
                  return `<tr><td>${esc(r.date || "—")}</td><td>${esc(r.title || "—")}</td><td>${esc(String(r.location || "—").slice(0, 90))}</td><td>—</td><td>newly_added_delta</td><td>review on map desk</td></tr>`;
                })
                .join("")
            : '<tr><td colspan="6" class="empty">No newly added events in the latest delta (added_count=0). Next daily sync will populate this table.</td></tr>'
        }
      </tbody></table></div>

      <h3>Rejected / review queues</h3>
      <details open>
        <summary>Hard invalid rejected (${esc(fmtNum(queues.hard_invalid_rejected))})</summary>
        <div class="table-wrap"><table><thead><tr><th>Date</th><th>Title</th><th>Location</th><th>Class</th><th>Reason</th><th>Action</th></tr></thead><tbody>
          ${rowsHtml(invalidSample, 6)}
        </tbody></table></div>
      </details>
      <details open>
        <summary>Low confidence → general (${esc(fmtNum(queues.low_confidence_general_fallback))})</summary>
        <div class="table-wrap"><table><thead><tr><th>Date</th><th>Title</th><th>Location</th><th>Class</th><th>Reason</th><th>Action</th></tr></thead><tbody>
          ${rowsHtml(lowSample, 6)}
        </tbody></table></div>
      </details>
      <details>
        <summary>Missing coordinates / list-only (${esc(fmtNum(queues.missing_or_invalid_coordinates_list_only))})</summary>
        <div class="table-wrap"><table><thead><tr><th>Date</th><th>Title</th><th>Location</th><th>Class</th><th>Reason</th><th>Action</th></tr></thead><tbody>
          ${rowsHtml(missingSample, 6)}
        </tbody></table></div>
      </details>
      <details>
        <summary>Phase 1 GPS review queue sample (${esc(fmtNum(queues.phase1_gps_review_queue))})</summary>
        <div class="table-wrap"><table><thead><tr><th>Date</th><th>Title</th><th>Location</th><th>Class</th><th>Reason</th><th>Action</th></tr></thead><tbody>
          ${rowsHtml(gpsSample, 6)}
        </tbody></table></div>
      </details>

      <div class="links" style="margin-top:12px">
        <a href="https://github.com/setoxxx/nycif-live-feeds/blob/${encodeURIComponent(data.branch)}/data/howard_classification_assist_v02.json" target="_blank" rel="noopener noreferrer">Howard assist JSON</a>
        <a href="https://github.com/setoxxx/nycif-live-feeds/blob/${encodeURIComponent(data.branch)}/data/events_discovery_godview_digest_v02.json" target="_blank" rel="noopener noreferrer">Full God View digest</a>
        <a href="${LIVE_FEEDS_BASE}/${encodeURIComponent(data.branch)}/data/howard_classification_assist_v02.json" target="_blank" rel="noopener noreferrer">Raw assist JSON</a>
        <button type="button" id="discoveryGodViewRefresh" style="cursor:pointer;border:1px solid rgba(255,255,255,.12);border-radius:999px;padding:8px 14px;background:#182235;color:#60a5fa;font:inherit">Refresh discovery queues</button>
      </div>
    `;

    document.getElementById("discoveryGodViewRefresh")?.addEventListener("click", () => {
      void load({ forceRefresh: true });
    });
  }

  async function load(options = {}) {
    const forceRefresh = Boolean(options && options.forceRefresh);
    const root = document.getElementById("discovery-god-view");
    const status = document.getElementById("discovery-god-view-status");
    if (!root) return;
    if (status) {
      status.textContent = forceRefresh
        ? "Refreshing discovery God View digest…"
        : "Loading discovery God View digest…";
    }
    root.innerHTML = "";
    try {
      const digestResult = await fetchBranchJson(PATHS.digest);
      const assistResult = await fetchBranchJson(PATHS.assist).catch(() => ({
        branch: digestResult.branch,
        payload: {},
      }));
      render(root, {
        branch: digestResult.branch,
        digest: digestResult.payload,
        assist: assistResult.payload,
      });
      if (status) {
        status.textContent = `Discovery God View loaded from ${digestResult.branch}.`;
      }
      window.NYCIF_DISCOVERY_GODVIEW_SUMMARY = {
        branch: digestResult.branch,
        queue_totals: digestResult.payload?.queue_totals,
        delta_added: digestResult.payload?.daily_delta?.added_count,
        force_refresh: forceRefresh,
      };
      document.dispatchEvent(new CustomEvent("nycif-discovery-godview-ready"));
    } catch (error) {
      root.innerHTML = `<div class="notice danger">Could not load discovery God View digest.<br><br>${esc(error.message || error)}<br><br>Expected: data/events_discovery_godview_digest_v02.json on discovery-taxonomy-v02 branch.</div>`;
      if (status) status.textContent = "Discovery God View unavailable.";
    }
  }

  window.NYCIF_DISCOVERY_GODVIEW_PANEL = {
    version: VERSION,
    refresh: () => {
      void load({ forceRefresh: true });
    },
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => {
      void load();
    });
  } else {
    void load();
  }
})();
