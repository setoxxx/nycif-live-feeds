(() => {
  const VERSION = 'live-pipeline-panel-v02';
  const LIVE_FEEDS_BASE = 'https://raw.githubusercontent.com/setoxxx/nycif-live-feeds';
  const BRANCH_CANDIDATES = ['main', 'cursor/milestone-10-productionize-resolver-5215'];

  const PATHS = {
    dashboard: 'status/nycif-live-pipeline-dashboard.json',
    delta: 'data/live_delta_report.json',
    coverage: 'data/reports/multi_source_coverage_report.json',
    stagedManifest: 'data/staged_live_manifest.json',
    testManifest: 'data/test_enriched_feed_manifest.json',
    milestone10: 'status/nycif-milestone-10-productionize-resolver.json',
    resolverReport: 'data/location_resolver_report.json',
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

  function medalCard(earned, title, detail) {
    const tone = earned ? 'ok' : 'warn';
    const icon = earned ? '🥇' : '⬜';
    return `
      <div class="stat medal-card medal-${tone}">
        <div class="label">${icon} ${esc(title)}</div>
        <div class="value">${earned ? 'Earned' : 'Pending'}</div>
        <div class="detail">${esc(detail)}</div>
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
    const { dashboard, delta, coverage, stagedManifest, testManifest, milestone10, resolverReport, branches } = data;
    const counts = dashboard?.current_counts || {};
    const bars = dashboard?.progress_bars || {};
    const multi = dashboard?.multi_source || coverage?.overlap_analysis || {};
    const supplemental = dashboard?.supplemental_review || {};
    const freshness = dashboard?.freshness || {};
    const categoryCounts = stagedManifest?.category_counts || {};
    const fitnessCount = Number(categoryCounts.fitness || 0);
    const gpsPct = Number(bars.auto_gps_match_pct || 0);
    const gpsTail = Number(counts.gps_review_queue || 0);
    const gatePass = bars.backend_gate_pass === true;
    const needsReview = Number(testManifest?.needs_review_events ?? NaN);
    const geoCalls = Number(testManifest?.location_resolver_live_geosearch_calls || 0);
    const gazetteerKeys = Number(multi.location_gazetteer_key_count || dashboard?.location_resolver?.gazetteer_key_count || 0);
    const added = Array.isArray(delta?.added_events) ? delta.added_events.slice(0, 5) : (dashboard?.samples?.newly_added_events || []).slice(0, 5);
    const calendarOnly = (coverage?.samples?.calendar_only || dashboard?.samples?.calendar_only_events || []).slice(0, 5);
    const repoBase = `https://github.com/setoxxx/nycif-live-feeds/blob/${branches[0] || 'main'}`;

    root.innerHTML = `
      <style>
        .medal-card.medal-ok { border-color: rgba(251,191,36,.45); background: linear-gradient(145deg,rgba(251,191,36,.12),rgba(52,211,153,.08)); }
        .medal-card.medal-warn { opacity: .85; }
        .medal-card .value { color: #fde68a; }
      </style>
      <div class="notice ok">Loaded from nycif-live-feeds branch(es): ${esc(branches.join(', '))}. Panel ${esc(VERSION)} · read-only.</div>

      <h3>🏅 Pipeline gold medals</h3>
      <div class="notice violet">Earned when backend QA artifacts prove the milestone — not public-map publish approval.</div>
      <div class="grid">
        ${medalCard(gpsPct >= 99.9, '100% permit GPS match', `${fmtNum(counts.staged_with_valid_gps)} permits with valid GPS (${fmtPct(gpsPct)})`)}
        ${medalCard(gpsTail === 0 && needsReview === 0, 'Zero GPS review tail', `Review queue ${fmtNum(gpsTail)} · test needs_review ${Number.isFinite(needsReview) ? fmtNum(needsReview) : '—'}`)}
        ${medalCard(gatePass, 'Backend reliability gate', gatePass ? 'gate_pass: true' : 'Run backend_reliability_gate.py')}
        ${medalCard(gazetteerKeys > 40000, 'Tiered geo resolver live', `${fmtNum(gazetteerKeys)} gazetteer keys · ${fmtNum(geoCalls)} live GeoSearch calls (last run)`)}
        ${medalCard(fitnessCount > 0, 'Fitness category on map', `${fmtNum(fitnessCount)} staged fitness/wellness events · opt-in filter 💪`)}
        ${medalCard(Number(multi.supplemental_staging_event_count || 0) > 0, 'Supplemental intake staged', `${fmtNum(multi.supplemental_staging_event_count || 0)} calendar+Parks rows for manual review`)}
      </div>

      <h3>Pipeline progress</h3>
      <div class="grid">
        ${progressBar('Permit ingestion', bars.permit_ingestion_pct ?? 100, `${fmtNum(counts.classified_permit_rows)} classified rows`)}
        ${progressBar('Auto GPS matching', bars.auto_gps_match_pct, `${fmtNum(counts.staged_with_valid_gps)} with valid GPS`)}
        ${progressBar('GPS review tail', bars.gps_review_tail_pct, `${fmtNum(counts.gps_review_queue)} in review queue`)}
        ${progressBar('Multi-source coverage', bars.multi_source_coverage_pct, 'Permits + citywide calendar overlap audit')}
      </div>

      <h3>Live counts</h3>
      <div class="grid">
        <div class="stat">
          <div class="label">Current staged (map-ready QA feed)</div>
          <div class="value">${fmtNum(counts.staged_feed_events)}</div>
          <div class="detail">Staged manifest: ${esc(fmtTime(freshness.staged_manifest_generated_at_utc || stagedManifest?.generated_at_utc))}</div>
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

      <h3>Map categories (staged feed)</h3>
      <div class="notice">Public map loads staged feed by default (M10). Fitness is opt-in in Filters → 💪 Fitness / wellness.</div>
      <div class="grid">
        <div class="stat"><div class="label">Sports</div><div class="value">${fmtNum(categoryCounts.sports)}</div></div>
        <div class="stat"><div class="label">Parks</div><div class="value">${fmtNum(categoryCounts.parks)}</div></div>
        <div class="stat"><div class="label">💪 Fitness</div><div class="value">${fmtNum(categoryCounts.fitness)}</div><div class="detail">Yoga, Zumba, wellness classes</div></div>
        <div class="stat"><div class="label">Market</div><div class="value">${fmtNum(categoryCounts.market)}</div></div>
        <div class="stat"><div class="label">Arts</div><div class="value">${fmtNum(categoryCounts.arts)}</div></div>
        <div class="stat"><div class="label">General</div><div class="value">${fmtNum(categoryCounts.general)}</div></div>
      </div>

      <h3>Multi-source coverage</h3>
      <div class="grid">
        <div class="stat"><div class="label">Permit rows (tvpp-9vvx)</div><div class="value">${fmtNum(coverage?.sources_compared?.permit_open_data?.current_future_rows ?? counts.classified_permit_rows)}</div></div>
        <div class="stat"><div class="label">Citywide calendar</div><div class="value">${fmtNum(coverage?.sources_compared?.citywide_calendar_api?.current_future_rows ?? counts.citywide_calendar_rows)}</div></div>
        <div class="stat"><div class="label">Parks BigApps events</div><div class="value">${fmtNum(coverage?.sources_compared?.parks_bigapps_events?.current_future_rows ?? counts.parks_bigapps_events_rows)}</div></div>
        <div class="stat"><div class="label">Calendar-only gap</div><div class="value">${fmtNum(multi.calendar_only_unique_keys)}</div></div>
        <div class="stat"><div class="label">Parks-only gap</div><div class="value">${fmtNum(multi.parks_only_unique_keys)}</div></div>
      </div>

      <h3>M9/M10 supplemental + geo resolver</h3>
      <div class="grid">
        <div class="stat"><div class="label">Supplemental staging feed</div><div class="value">${fmtNum(multi.supplemental_staging_event_count ?? 0)}</div></div>
        <div class="stat"><div class="label">Gazetteer keys</div><div class="value">${fmtNum(gazetteerKeys)}</div></div>
        <div class="stat"><div class="label">Resolver unresolved</div><div class="value">${fmtNum(dashboard?.location_resolver?.unresolved_count ?? resolverReport?.unresolved_count ?? 0)}</div></div>
        <div class="stat"><div class="label">GeoSearch cache</div><div class="value">${fmtNum(resolverReport?.live_geosearch_calls ?? geoCalls)}</div><div class="detail">NYC Planning official geocoder</div></div>
      </div>
      <div class="links" style="margin-top:8px">
        <a href="${repoBase}/docs/nycif-project-bookmark-prompt.md" target="_blank" rel="noopener noreferrer">Project bookmark prompt</a>
        <a href="${repoBase}/docs/wordpress-plugin-deploy/README.md" target="_blank" rel="noopener noreferrer">WordPress map plugin deploy</a>
        <a href="${repoBase}/data/supplemental_events_staging_feed.json" target="_blank" rel="noopener noreferrer">Supplemental staging feed</a>
        <a href="https://setoxxx.github.io/nycif-field-desk/?v=m10-staged-live&amp;resetFilters=1" target="_blank" rel="noopener noreferrer">Live map (staged default)</a>
        <a href="https://setoxxx.github.io/nycif-live-feeds/admin/admin/index.html" target="_blank" rel="noopener noreferrer">Interim live-feeds admin</a>
      </div>

      <h3>Newly added events (top 5)</h3>
      <div class="table-wrap"><table><thead><tr><th>Date</th><th>Title</th><th>Borough</th><th>Location</th><th>Event ID</th></tr></thead><tbody>
        ${added.length ? added.map(eventRow).join('') : '<tr><td colspan="5" class="empty">No newly added events in the latest delta report.</td></tr>'}
      </tbody></table></div>

      <div class="links" style="margin-top:12px">
        <button type="button" id="livePipelineRefreshV02" style="cursor:pointer;border:1px solid rgba(255,255,255,.12);border-radius:999px;padding:8px 14px;background:#182235;color:#60a5fa;font:inherit">Refresh live data</button>
      </div>
      <div class="detail" style="margin-top:8px">Milestone 10: ${esc(milestone10?.headline || '—')} · Last loaded: ${esc(fmtTime(dashboard?.generated_at_utc))}</div>
    `;

    document.getElementById('livePipelineRefreshV02')?.addEventListener('click', () => loadLivePipeline(true));
  }

  async function loadLivePipeline(force) {
    const root = document.getElementById('live-pipeline');
    const status = document.getElementById('live-pipeline-status');
    const badge = document.getElementById('snapshot-time');
    if (!root) return;

    if (status) status.textContent = force ? 'Refreshing live pipeline data…' : 'Loading live pipeline data from nycif-live-feeds…';
    root.innerHTML = '';

    try {
      const results = await Promise.all([
        fetchLiveFeedsJson(PATHS.dashboard),
        fetchLiveFeedsJson(PATHS.delta),
        fetchLiveFeedsJson(PATHS.coverage),
        fetchLiveFeedsJson(PATHS.stagedManifest).catch(() => ({ branch: 'none', payload: {} })),
        fetchLiveFeedsJson(PATHS.testManifest).catch(() => ({ branch: 'none', payload: {} })),
        fetchLiveFeedsJson(PATHS.milestone10).catch(() => ({ branch: 'none', payload: {} })),
        fetchLiveFeedsJson(PATHS.resolverReport).catch(() => ({ branch: 'none', payload: {} })),
      ]);

      const [dashboardResult, deltaResult, coverageResult, stagedManifestResult, testManifestResult, milestone10Result, resolverReportResult] = results;
      const branches = [...new Set(results.map((r) => r.branch).filter((b) => b && b !== 'none'))];

      renderPanel(root, {
        dashboard: dashboardResult.payload,
        delta: deltaResult.payload,
        coverage: coverageResult.payload,
        stagedManifest: stagedManifestResult.payload,
        testManifest: testManifestResult.payload,
        milestone10: milestone10Result.payload,
        resolverReport: resolverReportResult.payload,
        branches,
      });

      const staged = dashboardResult.payload?.current_counts?.staged_feed_events;
      const fitness = stagedManifestResult.payload?.category_counts?.fitness;
      if (badge && staged != null) {
        badge.textContent = `Live: ${fmtNum(staged)} staged · 💪 ${fmtNum(fitness || 0)} fitness · ${fmtTime(dashboardResult.payload.generated_at_utc)}`;
        badge.className = 'badge ok';
      }
      if (status) status.textContent = `Live pipeline ${VERSION} loaded from ${branches.join(', ')}.`;

      window.NYCIF_LIVE_PIPELINE_SUMMARY = {
        staged_feed_events: dashboardResult.payload?.current_counts?.staged_feed_events,
        newly_added_events: dashboardResult.payload?.current_counts?.newly_added_events ?? deltaResult.payload?.added_count,
        gps_review_queue: dashboardResult.payload?.current_counts?.gps_review_queue,
        auto_gps_match_pct: dashboardResult.payload?.progress_bars?.auto_gps_match_pct,
        backend_gate_pass: dashboardResult.payload?.progress_bars?.backend_gate_pass,
        fitness_event_count: stagedManifestResult.payload?.category_counts?.fitness,
        supplemental_staging_event_count: dashboardResult.payload?.multi_source?.supplemental_staging_event_count,
        location_gazetteer_key_count: dashboardResult.payload?.multi_source?.location_gazetteer_key_count,
        calendar_only_unique_keys: dashboardResult.payload?.multi_source?.calendar_only_unique_keys,
        parks_only_unique_keys: dashboardResult.payload?.multi_source?.parks_only_unique_keys,
      };
      document.dispatchEvent(new CustomEvent('nycif-live-pipeline-ready'));
    } catch (error) {
      root.innerHTML = `<div class="notice danger">Could not load live pipeline artifacts from nycif-live-feeds.<br><br>${esc(error.message || error)}</div>`;
      if (status) status.textContent = 'Live pipeline unavailable.';
    }
  }

  window.NYCIF_LIVE_PIPELINE_PANEL = { version: VERSION, refresh: () => loadLivePipeline(true) };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => loadLivePipeline(false));
  } else {
    loadLivePipeline(false);
  }
})();
