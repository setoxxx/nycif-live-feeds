(() => {
  const VERSION = 'live-pipeline-panel-v01';
  const LIVE_FEEDS_BASE = 'https://raw.githubusercontent.com/setoxxx/nycif-live-feeds';
  const BRANCH_CANDIDATES = ['main'];

  const PATHS = {
    dashboard: 'status/nycif-live-pipeline-dashboard.json',
    delta: 'data/live_delta_report.json',
    coverage: 'data/reports/multi_source_coverage_report.json',
  };

  function fmtNum(value) {
    return Number.isFinite(Number(value)) ? Number(value).toLocaleString() : '0';
  }

  function fmtPct(value) {
    const n = Number(value);
    return Number.isFinite(n) ? `${n.toFixed(1)}%` : '—';
  }

  function fmtTime(value) {
    if (!value) return 'Unknown';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return date.toLocaleString([], { month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit' });
  }

  function esc(value) {
    return String(value ?? '').replace(/[&<>"']/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
  }

  async function fetchLiveFeedsJson(path) {
    let lastError = null;
    for (const branch of BRANCH_CANDIDATES) {
      try {
        const url = `${LIVE_FEEDS_BASE}/${branch}/${path}?v=${Date.now()}`;
        const response = await fetch(url, { cache: 'no-store' });
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

  function progressBar(label, pct, detail) {
    const width = Math.max(0, Math.min(100, Number(pct) || 0));
    return `
      <div class="stat">
        <div class="label">${esc(label)}</div>
        <div class="value">${esc(fmtPct(width))}</div>
        <div class="progress"><span style="width:${width}%"></span></div>
        ${detail ? `<div class="detail">${esc(detail)}</div>` : ''}
      </div>
    `;
  }

  function eventRow(event) {
    const title = event.title || event.event_name || 'Untitled event';
    const date = event.date || String(event.start_date_time || '').slice(0, 10) || 'Date TBA';
    const borough = event.borough || event.event_borough || (Array.isArray(event.boroughs) ? event.boroughs.join(', ') : '') || 'Borough TBA';
    const location = event.display_location || event.location || event.event_location || event.address || 'Location TBA';
    const sourceId = event.source_event_id || event.event_id || '';
    return `
      <tr>
        <td>${esc(date)}</td>
        <td>${esc(title)}</td>
        <td>${esc(borough)}</td>
        <td>${esc(String(location).slice(0, 120))}${String(location).length > 120 ? '…' : ''}</td>
        <td>${esc(sourceId || '—')}</td>
      </tr>
    `;
  }

  function renderPanel(root, data) {
    const { dashboard, delta, coverage, branches } = data;
    const counts = dashboard?.current_counts || {};
    const bars = dashboard?.progress_bars || {};
    const multi = dashboard?.multi_source || coverage?.overlap_analysis || {};
    const freshness = dashboard?.freshness || {};
    const added = Array.isArray(delta?.added_events) ? delta.added_events.slice(0, 5) : (dashboard?.samples?.newly_added_events || []).slice(0, 5);
    const calendarOnly = (coverage?.samples?.calendar_only || dashboard?.samples?.calendar_only_events || []).slice(0, 5);

    root.innerHTML = `
      <div class="notice ok">Loaded from nycif-live-feeds branch(es): ${esc(branches.join(', '))}. Read-only — no publish or mutation controls.</div>
      <div class="grid">
        <div class="stat">
          <div class="label">Current staged (map-ready QA feed)</div>
          <div class="value">${fmtNum(counts.staged_feed_events)}</div>
          <div class="detail">Staged manifest: ${esc(fmtTime(freshness.staged_manifest_generated_at_utc))}</div>
        </div>
        <div class="stat">
          <div class="label">GPS-valid permits</div>
          <div class="value">${fmtNum(counts.staged_with_valid_gps)}</div>
          <div class="detail">${esc(fmtPct(bars.auto_gps_match_pct || 0))} auto-match</div>
        </div>
        <div class="stat">
          <div class="label">GPS review tail</div>
          <div class="value">${fmtNum(counts.gps_review_queue)}</div>
          <div class="detail">${esc(fmtPct(bars.gps_review_tail_pct || 0))} of classified permits</div>
        </div>
        <div class="stat">
          <div class="label">Newly added (last delta)</div>
          <div class="value">${fmtNum(counts.newly_added_events ?? delta?.added_count ?? 0)}</div>
          <div class="detail">Removed ${fmtNum(counts.removed_events ?? delta?.removed_count ?? 0)} · Changed ${fmtNum(counts.changed_events ?? delta?.changed_count ?? 0)}</div>
        </div>
      </div>

      <h3>Pipeline progress</h3>
      <div class="grid">
        ${progressBar('Permit ingestion', bars.permit_ingestion_pct ?? 100, `${fmtNum(counts.classified_permit_rows)} classified rows`)}
        ${progressBar('Auto GPS matching', bars.auto_gps_match_pct, `${fmtNum(counts.staged_with_valid_gps)} with valid GPS`)}
        ${progressBar('GPS review tail', bars.gps_review_tail_pct, `${fmtNum(counts.gps_review_queue)} in review queue`)}
        ${progressBar('Multi-source coverage', bars.multi_source_coverage_pct, 'Permits + citywide calendar overlap audit')}
      </div>

      <h3>Multi-source coverage</h3>
      <div class="grid">
        <div class="stat">
          <div class="label">Permit rows (tvpp-9vvx)</div>
          <div class="value">${fmtNum(coverage?.sources_compared?.permit_open_data?.current_future_rows ?? counts.classified_permit_rows)}</div>
        </div>
        <div class="stat">
          <div class="label">Citywide calendar (nyc.gov/events API)</div>
          <div class="value">${fmtNum(coverage?.sources_compared?.citywide_calendar_api?.current_future_rows ?? counts.citywide_calendar_rows)}</div>
        </div>
        <div class="stat">
          <div class="label">Parks BigApps events</div>
          <div class="value">${fmtNum(coverage?.sources_compared?.parks_bigapps_events?.current_future_rows ?? counts.parks_bigapps_events_rows)}</div>
          <div class="detail">Official nycgovparks.org feed with inline coordinates</div>
        </div>
        <div class="stat">
          <div class="label">Parks facility reference rows</div>
          <div class="value">${fmtNum(counts.parks_facility_reference_with_coordinates ?? 0)}</div>
          <div class="detail">${fmtNum(counts.parks_facility_reference_rows ?? 0)} total staged for Phase 2C fill</div>
        </div>
        <div class="stat">
          <div class="label">Overlap (title + date)</div>
          <div class="value">${fmtNum(multi.title_date_overlap_unique_keys)}</div>
        </div>
        <div class="stat">
          <div class="label">Calendar-only gap</div>
          <div class="value">${fmtNum(multi.calendar_only_unique_keys)}</div>
          <div class="detail">Not yet in permit pipeline — manual review required</div>
        </div>
        <div class="stat">
          <div class="label">Parks-only gap (BigApps)</div>
          <div class="value">${fmtNum(multi.parks_only_unique_keys)}</div>
          <div class="detail">Parks feed rows not matched to permit title+date keys</div>
        </div>
      </div>

      <h3>Newly added events (top 5)</h3>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Date</th><th>Title</th><th>Borough</th><th>Location</th><th>Event ID</th></tr></thead>
          <tbody>
            ${added.length ? added.map(eventRow).join('') : '<tr><td colspan="5" class="empty">No newly added events in the latest delta report.</td></tr>'}
          </tbody>
        </table>
      </div>

      <h3>Calendar-only samples (not in permit pipeline)</h3>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Date</th><th>Title</th><th>Borough</th><th>Location</th><th>Event ID</th></tr></thead>
          <tbody>
            ${calendarOnly.length ? calendarOnly.map(eventRow).join('') : '<tr><td colspan="5" class="empty">No calendar-only samples in coverage report.</td></tr>'}
          </tbody>
        </table>
      </div>

      <div class="links" style="margin-top:12px">
        <a href="https://github.com/setoxxx/nycif-live-feeds/blob/main/status/nycif-live-pipeline-dashboard.json" target="_blank" rel="noopener noreferrer">Dashboard JSON</a>
        <a href="https://github.com/setoxxx/nycif-live-feeds/blob/main/data/live_delta_report.json" target="_blank" rel="noopener noreferrer">Delta report</a>
        <a href="https://github.com/setoxxx/nycif-live-feeds/blob/main/data/reports/multi_source_coverage_report.json" target="_blank" rel="noopener noreferrer">Coverage report</a>
        <a href="https://raw.githubusercontent.com/setoxxx/nycif-live-feeds/main/data/nycif_staged_live_events.json" target="_blank" rel="noopener noreferrer">Staged feed (raw)</a>
      </div>
      <div class="links" style="margin-top:8px">
        <button type="button" id="livePipelineRefreshV01" style="cursor:pointer;border:1px solid rgba(255,255,255,.12);border-radius:999px;padding:8px 14px;background:#182235;color:#60a5fa;font:inherit">Refresh live data</button>
      </div>
      <div class="detail" style="margin-top:8px">Last loaded: ${esc(fmtTime(dashboard?.generated_at_utc || delta?.generated_at_utc))}</div>
    `;

    document.getElementById('livePipelineRefreshV01')?.addEventListener('click', () => loadLivePipeline(true));
  }

  async function loadLivePipeline(force) {
    const root = document.getElementById('live-pipeline');
    const status = document.getElementById('live-pipeline-status');
    const badge = document.getElementById('snapshot-time');
    if (!root) return;

    if (status) status.textContent = force ? 'Refreshing live pipeline data…' : 'Loading live pipeline data from nycif-live-feeds…';
    root.innerHTML = '';

    try {
      const [dashboardResult, deltaResult, coverageResult] = await Promise.all([
        fetchLiveFeedsJson(PATHS.dashboard),
        fetchLiveFeedsJson(PATHS.delta),
        fetchLiveFeedsJson(PATHS.coverage),
      ]);

      const branches = [...new Set([dashboardResult.branch, deltaResult.branch, coverageResult.branch])];
      renderPanel(root, {
        dashboard: dashboardResult.payload,
        delta: deltaResult.payload,
        coverage: coverageResult.payload,
        branches,
      });

      const staged = dashboardResult.payload?.current_counts?.staged_feed_events;
      if (badge && staged != null) {
        badge.textContent = `Live: ${fmtNum(staged)} staged · ${fmtTime(dashboardResult.payload.generated_at_utc)}`;
        badge.className = 'badge ok';
      }
      if (status) {
        status.textContent = `Live pipeline loaded from ${branches.join(', ')}.`;
      }

      window.NYCIF_LIVE_PIPELINE_SUMMARY = {
        staged_feed_events: dashboardResult.payload?.current_counts?.staged_feed_events,
        newly_added_events: dashboardResult.payload?.current_counts?.newly_added_events ?? deltaResult.payload?.added_count,
        gps_review_queue: dashboardResult.payload?.current_counts?.gps_review_queue,
        calendar_only_unique_keys: dashboardResult.payload?.multi_source?.calendar_only_unique_keys
          ?? coverageResult.payload?.overlap_analysis?.calendar_only_unique_keys,
        parks_only_unique_keys: dashboardResult.payload?.multi_source?.parks_only_unique_keys
          ?? coverageResult.payload?.overlap_analysis?.parks_only_unique_keys,
      };
      document.dispatchEvent(new CustomEvent('nycif-live-pipeline-ready'));
    } catch (error) {
      root.innerHTML = `<div class="notice danger">Could not load live pipeline artifacts from nycif-live-feeds. Merge PR #149 on the backend repo and run generate_live_pipeline_dashboard_status.py, then refresh.<br><br>${esc(error.message || error)}</div>`;
      if (status) status.textContent = 'Live pipeline unavailable.';
    }
  }

  function init() {
    loadLivePipeline(false);
  }

  window.NYCIF_LIVE_PIPELINE_PANEL = { version: VERSION, refresh: () => loadLivePipeline(true) };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
