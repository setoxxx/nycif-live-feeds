/**
 * NYCIF Field Desk — News Desk + Parade Census staging overlay v02.
 *
 * Operator/assignment mode only (?desk=1 or ?assignment=1).
 * Merges news_desk_assignment_checklist + photographer money-day calendar.
 */
(function () {
  'use strict';

  function operatorMode() {
    try {
      const p = new URL(location.href).searchParams;
      return p.get('desk') === '1' || p.get('assignment') === '1';
    } catch {
      return false;
    }
  }
  if (!operatorMode()) return;

  const urlParams = (() => {
    try {
      return new URL(location.href).searchParams;
    } catch {
      return new URLSearchParams();
    }
  })();

  const feedRef = (() => {
    const raw = urlParams.get('feeds');
    if (raw && /^[A-Za-z0-9._/-]+$/.test(raw)) return raw;
    return 'main';
  })();
  const DATA_BASE = `https://raw.githubusercontent.com/setoxxx/nycif-live-feeds/${feedRef}/data`;
  const NYC = { minLat: 40.4774, maxLat: 40.9176, minLng: -74.2591, maxLng: -73.7004 };
  const STATUS_KEY = 'nycif-news-desk-status-v1';
  const PRIORITY_RANK = { highest: 0, high: 1, normal: 2, low: 3 };

  const LANE_COLORS = {
    parade_march: '#2563eb',
    religious_procession_feast: '#7c3aed',
    street_co_naming: '#b45309',
    heritage_cultural_parade: '#059669',
    pop_up_street_activation: '#ea580c',
    fan_zone_major_civic: '#dc2626',
    returning_viral_candidate: '#9333ea',
    parade: '#2563eb',
    march: '#2563eb',
    carnival: '#dc2626'
  };

  function inNycBox(lat, lng) {
    return lat >= NYC.minLat && lat <= NYC.maxLat && lng >= NYC.minLng && lng <= NYC.maxLng;
  }

  function certifyCoord(rawLat, rawLng) {
    const lat = Number(rawLat);
    const lng = Number(rawLng);
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) return { ok: false, reason: 'nonfinite' };
    if (Math.abs(lat) < 1e-9 && Math.abs(lng) < 1e-9) return { ok: false, reason: 'null_island' };
    if (inNycBox(lat, lng)) return { ok: true, lat, lng, reason: 'ok_nyc' };
    if (inNycBox(lng, lat)) return { ok: false, reason: 'swap_suspected' };
    return { ok: false, reason: 'out_of_box' };
  }

  function esc(v) {
    return String(v == null ? '' : v).replace(/[&<>"']/g, ch => (
      { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]
    ));
  }

  function loadStatuses() {
    try {
      return JSON.parse(localStorage.getItem(STATUS_KEY) || '{}');
    } catch {
      return {};
    }
  }

  function saveStatus(checklistId, status) {
    const all = loadStatuses();
    all[checklistId] = status;
    localStorage.setItem(STATUS_KEY, JSON.stringify(all));
  }

  async function fetchJson(url) {
    const res = await fetch(`${url}?cache=${Date.now()}`, { cache: 'no-store', headers: { Accept: 'application/json' } });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  }

  function priorityRank(p) {
    return PRIORITY_RANK[String(p || 'normal')] ?? 9;
  }

  function sortRows(rows) {
    return [...rows].sort((a, b) => {
      const pr = priorityRank(a.editorial_priority) - priorityRank(b.editorial_priority);
      if (pr !== 0) return pr;
      const score = Number(b.assignment_score || 0) - Number(a.assignment_score || 0);
      if (score !== 0) return score;
      return String(a.date || '').localeCompare(String(b.date || ''))
        || String(a.borough || '').localeCompare(String(b.borough || ''))
        || String(a.story_headline || a.title || '').localeCompare(String(b.story_headline || b.title || ''));
    });
  }

  function rowKey(row) {
    const pid = String(row.permit_event_id || '').trim();
    const day = String(row.date || '').slice(0, 10);
    if (pid && day) return `permit:${pid}@${day}`;
    return `title:${String(row.story_headline || row.title || '').toLowerCase()}@${day}@${row.borough || ''}`;
  }

  function moneyDayToChecklistRow(event) {
    const source = event.source && typeof event.source === 'object' ? event.source : {};
    const permitId = String(source.source_event_id || '').trim() || null;
    const score = Number(event.assignment_score || 0);
    let priority = 'normal';
    if (event.money_day && score >= 380) priority = 'highest';
    else if (event.money_day || score >= 300) priority = 'high';
    const why = ['photographer_money_day'];
    if (event.money_day) why.push('money_day');
    return {
      checklist_id: permitId && event.date ? `tvpp-9vvx:${permitId}@${event.date}` : `money:${event.id || event.title}@${event.date}`,
      story_headline: event.title || 'Untitled',
      story_lane: 'pop_up_street_activation',
      date: String(event.date || '').slice(0, 10),
      start_time: null,
      end_time: null,
      borough: event.borough || '',
      route_or_location: event.display_location || event.location || '',
      permit_event_id: permitId,
      editorial_priority: priority,
      news_desk_status: 'unchecked',
      confidence: permitId ? 'permit_confirmed' : 'strongly_supported',
      assignment_score: score,
      why_story: why,
      field_desk_link: event.field_desk_link || '',
      latitude: event.latitude,
      longitude: event.longitude,
      coordinate_status: event.coordinate_status || 'list_only',
      source_layer: 'photographer_assignment_calendar'
    };
  }

  function mergeAssignmentRows(checklistRows, moneyRows) {
    const merged = new Map();
    checklistRows.forEach(r => merged.set(rowKey(r), r));
    moneyRows.forEach(r => {
      const key = rowKey(r);
      const existing = merged.get(key);
      if (!existing) {
        merged.set(key, r);
        return;
      }
      merged.set(key, {
        ...existing,
        assignment_score: Math.max(Number(existing.assignment_score || 0), Number(r.assignment_score || 0)),
        why_story: [...new Set([...(existing.why_story || []), ...(r.why_story || [])])].sort(),
        editorial_priority: priorityRank(r.editorial_priority) < priorityRank(existing.editorial_priority)
          ? r.editorial_priority
          : existing.editorial_priority
      });
    });
    return sortRows([...merged.values()]);
  }

  function priorityBadge(priority) {
    const p = String(priority || 'normal');
    const cls = p === 'highest' ? 'highest' : p === 'high' ? 'high' : 'normal';
    return `<span class="nd-badge nd-priority-${cls}">${esc(p)}</span>`;
  }

  function rowCard(row) {
    const id = row.checklist_id || row.id || '';
    const stored = loadStatuses()[id];
    const status = stored || row.news_desk_status || 'unchecked';
    const coord = certifyCoord(row.latitude, row.longitude);
    const mapReady = row.coordinate_status === 'map_ready' && coord.ok;
    const why = Array.isArray(row.why_story) ? row.why_story.join(' · ') : '';
    const link = row.field_desk_link || '';
    const score = row.assignment_score ? `score ${row.assignment_score}` : '';
    return `<article class="nd-row" data-id="${esc(id)}">
      <div class="nd-row-head">
        <h3>${esc(row.story_headline || row.name || row.title)}</h3>
        ${priorityBadge(row.editorial_priority)}
        <span class="nd-badge nd-confidence">${esc(row.confidence || '')}</span>
      </div>
      <p class="nd-meta">${esc(row.date || '')}${row.start_time ? ' · ' + esc(row.start_time) : ''}${row.end_time ? '–' + esc(row.end_time) : ''}${row.borough ? ' · ' + esc(row.borough) : ''}</p>
      ${row.route_or_location || row.route ? `<p class="nd-loc">${esc(row.route_or_location || row.route)}</p>` : ''}
      <p class="nd-lane">${esc(row.story_lane || row.event_kind || '')}${score ? ` · ${esc(score)}` : ''}</p>
      ${why ? `<p class="nd-why">${esc(why)}</p>` : ''}
      <div class="nd-actions">
        ${link ? `<a href="${esc(link)}" target="_blank" rel="noopener noreferrer">Assignment link</a>` : ''}
        ${mapReady ? `<button type="button" class="nd-fly" data-lat="${coord.lat}" data-lng="${coord.lng}">Fly to pin</button>` : '<span class="nd-list-only">LIST ONLY</span>'}
        <label class="nd-status"><span>Status</span>
          <select class="nd-status-select" data-id="${esc(id)}">
            ${['unchecked', 'assigned', 'covered', 'passed', 'cancelled'].map(s =>
              `<option value="${s}"${status === s ? ' selected' : ''}>${s}</option>`
            ).join('')}
          </select>
        </label>
      </div>
    </article>`;
  }

  function censusPopup(row) {
    const lane = row.story_lane || row.event_kind || '';
    return `<article class="nd-popup">
      <div class="nd-staging-banner">Staging / editorial — not public promoted data</div>
      <h2>${esc(row.name || row.story_headline)}</h2>
      <p>${esc(row.date || '')}${row.start_time ? ' · ' + esc(row.start_time) : ''}${row.end_time ? '–' + esc(row.end_time) : ''}</p>
      <p><strong>Borough:</strong> ${esc(row.borough || '')}</p>
      ${row.route ? `<p><strong>Route:</strong> ${esc(row.route)}</p>` : ''}
      <p><strong>Lane:</strong> ${esc(lane)} · <strong>Priority:</strong> ${esc(row.editorial_priority || '')}</p>
      <p><strong>Confidence:</strong> ${esc(row.confidence || '')}${row.permit_event_id ? ` · <strong>Permit</strong> ${esc(row.permit_event_id)}` : ''}</p>
    </article>`;
  }

  const state = {
    checklist: null,
    moneyDay: null,
    census: null,
    activeTab: 'priority_unchecked',
    laneFilter: 'all',
    boroughFilter: 'all',
    priorityFilter: 'all',
    censusLayer: null,
    censusEnabled: false
  };

  function applyUrlHandshake() {
    const date = urlParams.get('date');
    const borough = urlParams.get('borough');
    if (date && /^\d{4}-\d{2}-\d{2}$/.test(date)) {
      const today = new Date().toISOString().slice(0, 10);
      const tomorrow = new Date(Date.now() + 86400000).toISOString().slice(0, 10);
      if (date === today) state.activeTab = 'today';
      else if (date === tomorrow) state.activeTab = 'tomorrow';
      else state.activeTab = 'next_7';
      state.urlDate = date;
    }
    if (borough) {
      state.boroughFilter = borough;
      const sel = document.getElementById('nycif-nd-borough-filter');
      if (sel) sel.value = borough;
    }
    const pri = urlParams.get('editorial_priority') || urlParams.get('priority');
    if (pri && ['highest', 'high', 'all'].includes(pri)) {
      state.priorityFilter = pri;
      const sel = document.getElementById('nycif-nd-priority-filter');
      if (sel) sel.value = pri;
    }
  }

  function tabRows() {
    const checklist = state.checklist;
    if (!checklist) return [];
    if (state.activeTab === 'assignment_merge') {
      const checklistPart = checklist.priority_unchecked || [];
      const moneyPart = (state.moneyDay || [])
        .filter(e => e.money_day && Number(e.assignment_score || 0) >= 280)
        .map(moneyDayToChecklistRow);
      return mergeAssignmentRows(checklistPart, moneyPart);
    }
    const tabMap = {
      today: checklist.today,
      tomorrow: checklist.tomorrow,
      next_7: checklist.next_7_days,
      priority_unchecked: checklist.priority_unchecked
    };
    return tabMap[state.activeTab] || checklist.all_rows || [];
  }

  function filteredRows() {
    let rows = tabRows();
    if (state.urlDate) {
      rows = rows.filter(r => String(r.date || '').slice(0, 10) === state.urlDate);
    }
    if (state.laneFilter !== 'all') {
      rows = rows.filter(r => (r.story_lane || r.event_kind) === state.laneFilter);
    }
    if (state.boroughFilter !== 'all') {
      rows = rows.filter(r => r.borough === state.boroughFilter);
    }
    if (state.priorityFilter === 'highest') {
      rows = rows.filter(r => r.editorial_priority === 'highest');
    } else if (state.priorityFilter === 'high') {
      rows = rows.filter(r => ['highest', 'high'].includes(String(r.editorial_priority || '')));
    }
    return sortRows(rows);
  }

  function syncMapFilters() {
    try {
      if (state.boroughFilter !== 'all' && typeof window.setBoroughFilter === 'function') {
        window.setBoroughFilter(state.boroughFilter);
      }
    } catch { /* optional hook */ }
  }

  function renderPanel() {
    const list = document.getElementById('nycif-news-desk-list');
    if (!list) return;
    const rows = filteredRows();
    list.innerHTML = rows.length
      ? rows.map(r => rowCard(r)).join('')
      : '<p class="nd-empty">No rows for this tab/filter.</p>';

    list.querySelectorAll('.nd-fly').forEach(btn => {
      btn.addEventListener('click', () => {
        const map = window.NYCIF_MAIN_MAP;
        const lat = Number(btn.dataset.lat);
        const lng = Number(btn.dataset.lng);
        if (map && Number.isFinite(lat) && Number.isFinite(lng)) {
          map.flyTo([lat, lng], 15, { duration: 0.8 });
        }
      });
    });
    list.querySelectorAll('.nd-status-select').forEach(sel => {
      sel.addEventListener('change', () => saveStatus(sel.dataset.id, sel.value));
    });
  }

  function setActiveTab(tab) {
    state.activeTab = tab;
    const block = document.getElementById('nycif-news-desk-block');
    if (block) {
      block.querySelectorAll('.nd-tabs button').forEach(b => {
        b.classList.toggle('active', b.dataset.tab === tab);
      });
    }
    renderPanel();
  }

  function installStyles() {
    if (document.getElementById('nycif-news-desk-style')) return;
    const style = document.createElement('style');
    style.id = 'nycif-news-desk-style';
    style.textContent = `
      #nycif-news-desk-block { display: grid; gap: 8px; margin-top: 8px; }
      #nycif-news-desk-block .nd-title { font-size: 10px; font-weight: 900; text-transform: uppercase; letter-spacing: .05em; color: #7a6128; }
      #nycif-news-desk-block .nd-staging-note { font-size: 10px; color: #9a3412; background: rgba(234,88,12,.1); padding: 6px 8px; border-radius: 8px; line-height: 1.35; }
      .nd-tabs { display: flex; flex-wrap: wrap; gap: 4px; }
      .nd-tabs button { font-size: 10px; padding: 4px 8px; border-radius: 999px; border: 1px solid rgba(0,0,0,.12); background: #fff; cursor: pointer; }
      .nd-tabs button.active { background: #b08d3e; color: #fff; border-color: #b08d3e; }
      .nd-filters { display: flex; flex-wrap: wrap; gap: 4px; }
      .nd-filters select { font-size: 10px; padding: 3px 6px; border-radius: 6px; max-width: 46%; }
      #nycif-news-desk-list { max-height: 42vh; overflow: auto; display: grid; gap: 6px; }
      .nd-row { border: 1px solid rgba(0,0,0,.08); border-radius: 10px; padding: 8px; background: rgba(255,255,255,.92); font-size: 11px; }
      .nd-row-head { display: flex; flex-wrap: wrap; gap: 4px; align-items: center; }
      .nd-row h3 { margin: 0; font-size: 12px; flex: 1 1 100%; }
      .nd-badge { display: inline-flex; padding: 1px 6px; border-radius: 999px; font-size: 9px; font-weight: 800; text-transform: uppercase; }
      .nd-priority-highest { background: #fee2e2; color: #991b1b; }
      .nd-priority-high { background: #ffedd5; color: #9a3412; }
      .nd-priority-normal { background: #f3f4f6; color: #4b5563; }
      .nd-confidence { background: #e0e7ff; color: #3730a3; }
      .nd-meta, .nd-loc, .nd-lane, .nd-why { margin: 2px 0; color: #4b5563; }
      .nd-actions { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin-top: 4px; }
      .nd-actions a { color: #44546b; font-weight: 800; font-size: 10px; }
      .nd-list-only { font-size: 9px; font-weight: 900; color: #9a3412; }
      .nd-status { display: inline-flex; gap: 4px; align-items: center; font-size: 10px; }
      .nd-marker { width: 28px; height: 28px; border-radius: 50%; border: 2px solid #fff; box-shadow: 0 4px 12px rgba(0,0,0,.3); }
      .nd-marker.highest { width: 34px; height: 34px; border-width: 3px; }
      .nd-popup { min-width: 220px; font: 500 12px/1.4 system-ui, sans-serif; }
      .nd-staging-banner { font-size: 9px; font-weight: 900; color: #9a3412; text-transform: uppercase; margin-bottom: 4px; }
      .nd-empty { font-size: 11px; color: #6b7280; }
    `;
    document.head.appendChild(style);
  }

  function ensureControls() {
    const panel = document.getElementById('layersPanel');
    if (!panel || document.getElementById('nycif-news-desk-block')) return;

    const block = document.createElement('div');
    block.id = 'nycif-news-desk-block';
    block.innerHTML = `
      <hr>
      <div class="nd-title">📰 News Desk Checklist <span class="desk-badge">staging</span></div>
      <div class="nd-staging-note">Editorial staging — not public promoted data. map_eligible=false on all rows.</div>
      <div class="nd-tabs" role="tablist">
        <button type="button" data-tab="assignment_merge">Assignment merge</button>
        <button type="button" data-tab="today">Today</button>
        <button type="button" data-tab="tomorrow">Tomorrow</button>
        <button type="button" data-tab="next_7">Next 7 days</button>
        <button type="button" data-tab="priority_unchecked" class="active">Priority unchecked</button>
      </div>
      <div class="nd-filters">
        <select id="nycif-nd-priority-filter" aria-label="Editorial priority filter">
          <option value="all">All priorities</option>
          <option value="highest">Highest only</option>
          <option value="high">Highest + high</option>
        </select>
        <select id="nycif-nd-lane-filter" aria-label="Story lane filter"><option value="all">All lanes</option></select>
        <select id="nycif-nd-borough-filter" aria-label="Borough filter"><option value="all">All boroughs</option></select>
      </div>
      <label class="check"><input type="checkbox" id="nycif-nd-census-toggle"> <span>🎭 Parade &amp; civic census pins (staging)</span></label>
      <div id="nycif-news-desk-status" class="nycif-desk-status"></div>
      <div id="nycif-news-desk-list"></div>
    `;
    panel.appendChild(block);

    block.querySelectorAll('.nd-tabs button').forEach(btn => {
      btn.addEventListener('click', () => setActiveTab(btn.dataset.tab));
    });

    document.getElementById('nycif-nd-lane-filter').addEventListener('change', e => {
      state.laneFilter = e.target.value;
      renderPanel();
    });
    document.getElementById('nycif-nd-borough-filter').addEventListener('change', e => {
      state.boroughFilter = e.target.value;
      syncMapFilters();
      renderPanel();
    });
    document.getElementById('nycif-nd-priority-filter').addEventListener('change', e => {
      state.priorityFilter = e.target.value;
      renderPanel();
    });
    document.getElementById('nycif-nd-census-toggle').addEventListener('change', e => {
      toggleCensusLayer(e.target.checked);
    });
  }

  function populateFilters() {
    const checklist = state.checklist;
    if (!checklist) return;
    const laneSel = document.getElementById('nycif-nd-lane-filter');
    const boroughSel = document.getElementById('nycif-nd-borough-filter');
    if (!laneSel || !boroughSel) return;
    const lanes = Object.keys(checklist.by_story_lane || {}).filter(k => (checklist.by_story_lane[k] || []).length);
    lanes.forEach(lane => {
      const opt = document.createElement('option');
      opt.value = lane;
      opt.textContent = lane.replace(/_/g, ' ');
      laneSel.appendChild(opt);
    });
    ['Manhattan', 'Brooklyn', 'Queens', 'Bronx', 'Staten Island', 'Multi-borough'].forEach(b => {
      const opt = document.createElement('option');
      opt.value = b;
      opt.textContent = b;
      boroughSel.appendChild(opt);
    });
    if (state.boroughFilter !== 'all') boroughSel.value = state.boroughFilter;
    if (state.priorityFilter !== 'all') {
      const priSel = document.getElementById('nycif-nd-priority-filter');
      if (priSel) priSel.value = state.priorityFilter;
    }
  }

  function laneColor(row) {
    return LANE_COLORS[row.story_lane] || LANE_COLORS[row.event_kind] || '#b08d3e';
  }

  function censusMarker(row) {
    const coord = certifyCoord(row.latitude || row.lat, row.longitude || row.lng);
    if (!coord.ok) return null;
    const priority = String(row.editorial_priority || 'normal');
    const color = laneColor(row);
    const size = priority === 'highest' ? 34 : priority === 'high' ? 30 : 26;
    const icon = window.L.divIcon({
      className: 'nd-marker-shell',
      html: `<div class="nd-marker ${priority}" style="background:${color};width:${size}px;height:${size}px"></div>`,
      iconSize: [size, size],
      iconAnchor: [size / 2, size / 2]
    });
    return window.L.marker([coord.lat, coord.lng], { icon, title: row.name, zIndexOffset: priority === 'highest' ? 6000 : 5000 })
      .bindPopup(censusPopup(row), { maxWidth: 320 });
  }

  async function toggleCensusLayer(enabled) {
    const map = window.NYCIF_MAIN_MAP;
    const status = document.getElementById('nycif-news-desk-status');
    state.censusEnabled = enabled;
    if (!enabled) {
      if (state.censusLayer && map) map.removeLayer(state.censusLayer);
      if (status) status.textContent = 'Parade census overlay hidden.';
      return;
    }
    if (!map || !window.L) {
      if (status) status.textContent = 'Map not ready.';
      return;
    }
    try {
      if (!state.census) {
        state.census = await fetchJson(`${DATA_BASE}/citywide_parade_census_snapshot.json`);
      }
      const entries = (state.census.priority_events || []).concat(state.census.entries || []);
      const seen = new Set();
      const markers = [];
      let listOnly = 0;
      entries.forEach(row => {
        const key = `${row.permit_event_id || row.name}@${row.date}`;
        if (seen.has(key)) return;
        seen.add(key);
        const m = censusMarker(row);
        if (m) markers.push(m);
        else listOnly += 1;
      });
      if (state.censusLayer) map.removeLayer(state.censusLayer);
      state.censusLayer = window.L.layerGroup(markers);
      state.censusLayer.addTo(map);
      if (status) {
        status.textContent = `Parade census: ${markers.length} staging pin(s) · ${listOnly} list-only (not plotted)`;
      }
    } catch (err) {
      if (status) status.textContent = `Census load failed: ${err.message}`;
    }
  }

  async function loadData() {
    const status = document.getElementById('nycif-news-desk-status');
    try {
      const [checklist, photo] = await Promise.all([
        fetchJson(`${DATA_BASE}/news_desk_assignment_checklist.json`),
        fetchJson(`${DATA_BASE}/photographer_assignment_calendar_2mo.json`)
      ]);
      state.checklist = checklist;
      state.moneyDay = Array.isArray(photo.events) ? photo.events : [];
      applyUrlHandshake();
      populateFilters();
      if (urlParams.get('assignment') === '1') {
        setActiveTab('assignment_merge');
      } else {
        renderPanel();
      }
      const c = checklist.counts || {};
      const merged = tabRows().length;
      if (status) {
        status.textContent = `Checklist ${c.total || 0} rows · priority unchecked ${c.priority_unchecked_count || 0} · showing ${merged}`;
      }
      window.NYCIF_NEWS_DESK_ASSIGNMENT_ROWS = mergeAssignmentRows(
        checklist.priority_unchecked || [],
        state.moneyDay.filter(e => e.money_day).map(moneyDayToChecklistRow)
      );
      syncMapFilters();
    } catch (err) {
      if (status) status.textContent = `Load failed: ${err.message}`;
    }
  }

  function boot() {
    if (!window.L) return;
    installStyles();
    ensureControls();
    loadData();
    console.info('[NYCIF] News Desk staging overlay v02 active (operator mode).');
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }

  window.NYCIF_NEWS_DESK = {
    certifyCoord,
    sortRows,
    mergeAssignmentRows,
    filteredRows: () => filteredRows(),
    loadStatuses,
    moneyDayToChecklistRow
  };
})();
