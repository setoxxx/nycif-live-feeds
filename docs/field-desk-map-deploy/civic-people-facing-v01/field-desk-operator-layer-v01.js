/**
 * NYCIF Field Desk — Operator Desk Layer v01 (premium / operator only).
 *
 * Adds the operator "money-day" lanes (Shoot-Day Certified, Money-Day,
 * Viral Recurrence) plus a Civic coverage KPI to the map — but ONLY when the
 * page is opened in operator mode (?desk=1 or ?assignment=1). For a normal
 * public visitor this file adds no DOM, makes no network requests, and leaves
 * the published public map completely unchanged.
 *
 * Pin integrity: every coordinate is re-certified client-side before it can
 * become a marker (finite, not Null Island, inside the NYC metro box, not an
 * obvious lat/lng swap, and flagged certified_pin + map_ready by the backend
 * pin-integrity gate). Rows that fail are shown in a list-only appendix with a
 * LIST ONLY badge — never as a pin. No coordinates are ever invented.
 *
 * Data source: setoxxx/nycif-live-feeds (backend), same ref as the map feed.
 */
(function () {
  'use strict';

  // ---- Operator-mode gate ------------------------------------------------
  function operatorMode() {
    try {
      const p = new URL(location.href).searchParams;
      return p.get('desk') === '1' || p.get('assignment') === '1';
    } catch {
      return false;
    }
  }
  if (!operatorMode()) {
    return; // Public visitors get nothing from this file.
  }

  // ---- Feed ref (mirror the app's resolution) ----------------------------
  const feedRef = (() => {
    try {
      const raw = new URL(location.href).searchParams.get('feeds');
      if (raw && /^[A-Za-z0-9._/-]+$/.test(raw)) return raw;
    } catch { /* fall through */ }
    return 'main';
  })();
  const DATA_BASE = `https://raw.githubusercontent.com/setoxxx/nycif-live-feeds/${feedRef}/data`;

  // ---- NYC pin certification (client-side, fail-closed) ------------------
  // NYC metro bounding box (documented): the five boroughs plus a small
  // margin. Anything outside is refused for map_ready, never plotted.
  const NYC = { minLat: 40.4774, maxLat: 40.9176, minLng: -74.2591, maxLng: -73.7004 };

  function inNycBox(lat, lng) {
    return lat >= NYC.minLat && lat <= NYC.maxLat && lng >= NYC.minLng && lng <= NYC.maxLng;
  }

  // Returns { ok, lat, lng, reason }. Never mutates or invents coordinates.
  function certifyCoord(rawLat, rawLng) {
    const lat = Number(rawLat);
    const lng = Number(rawLng);
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) {
      return { ok: false, reason: 'nonfinite' };
    }
    if (Math.abs(lat) < 1e-9 && Math.abs(lng) < 1e-9) {
      return { ok: false, reason: 'null_island' };
    }
    if (inNycBox(lat, lng)) {
      return { ok: true, lat, lng, reason: 'ok_nyc' };
    }
    // Detect an unambiguous lat/lng swap (values transposed). Refuse — do not
    // auto-correct — so a bad row can never masquerade as a good pin.
    if (inNycBox(lng, lat)) {
      return { ok: false, reason: 'swap_suspected' };
    }
    return { ok: false, reason: 'out_of_box' };
  }

  // A row may only become a pin if the backend certified it AND it re-certifies
  // here. Belt and suspenders: "no ocean pins" holds even if the feed regresses.
  function certifyRow(row, lat, lng) {
    const backendOk = row.certified_pin === true
      && row.coordinate_status === 'map_ready';
    const coord = certifyCoord(lat, lng);
    if (!backendOk) {
      return { ok: false, reason: 'not_certified_by_gate' };
    }
    return coord;
  }

  // ---- Lane definitions --------------------------------------------------
  // Each lane extracts { pins: [certified rows], listOnly: [rows w/o pin] }
  // from its dataset. Extractors never fabricate coordinates.
  const LANES = {
    shootToday: {
      label: '⭐ Shoot Day — Today',
      file: 'photographer_shoot_day_certified_pack.json',
      markerClass: 'nycif-desk-marker-shoot',
      extract: data => extractShootDay(data, 'today')
    },
    shootTomorrow: {
      label: '⭐ Shoot Day — Tomorrow',
      file: 'photographer_shoot_day_certified_pack.json',
      markerClass: 'nycif-desk-marker-shoot',
      extract: data => extractShootDay(data, 'tomorrow')
    },
    money: {
      label: '💰 Money Days (next 60d)',
      file: 'photographer_assignment_calendar_2mo.json',
      markerClass: 'nycif-desk-marker-money',
      extract: extractMoneyDay
    },
    viral: {
      label: '🔁 Viral Magnets (returning likely)',
      file: 'photographer_viral_recurrence_matches.json',
      markerClass: 'nycif-desk-marker-viral',
      extract: extractViral
    }
  };

  function normalizeRow(row, laneLabels) {
    const c = certifyRow(row, row.latitude, row.longitude);
    const base = {
      id: row.id || row.event_id || row.cemsid || '',
      title: row.title || 'Untitled',
      date: row.date || (row.start_date_time || '').slice(0, 10) || '',
      start: row.start_date_time || '',
      end: row.end_date_time || '',
      borough: row.borough || '',
      location: row.display_location || row.location || '',
      dataset: (row.source && row.source.dataset) || '',
      recurrence: row.recurrence_label || '',
      why: Array.isArray(row.why_selected) ? row.why_selected.join(', ') : (row.why_selected || ''),
      score: Number(row.assignment_score || row.match_score || 0),
      mapLink: row.map_link || '',
      fieldDeskLink: row.field_desk_link || '',
      reason: c.reason
    };
    if (c.ok) {
      base.lat = c.lat;
      base.lng = c.lng;
      base.certified = true;
    } else {
      base.certified = false;
    }
    return base;
  }

  function splitPins(rows) {
    const pins = [];
    const listOnly = [];
    rows.forEach(raw => {
      const row = normalizeRow(raw);
      if (row.certified) pins.push(row);
      else listOnly.push(row);
    });
    return { pins, listOnly };
  }

  function extractShootDay(data, which) {
    const block = data && data[which];
    if (!block) return { pins: [], listOnly: [], dateLabel: which };
    const certified = Array.isArray(block.go_shoot_certified) ? block.go_shoot_certified : [];
    const needs = Array.isArray(block.needs_location) ? block.needs_location : [];
    const split = splitPins(certified);
    // needs_location rows are already list-only by design; keep them separate.
    const needsRows = needs.map(r => normalizeRow(r));
    return {
      pins: split.pins,
      listOnly: split.listOnly.concat(needsRows),
      dateLabel: block.date || which
    };
  }

  function extractMoneyDay(data) {
    const events = Array.isArray(data && data.events) ? data.events : [];
    // Money days from real "today" forward, ranked by assignment score.
    const todayKey = new Date().toISOString().slice(0, 10);
    const upcoming = events.filter(e => (e.date || '') >= todayKey);
    const split = splitPins(upcoming);
    split.pins.sort((a, b) => b.score - a.score);
    return { pins: split.pins, listOnly: split.listOnly, dateLabel: 'next 60 days' };
  }

  function extractViral(data) {
    const matches = Array.isArray(data && data.matches) ? data.matches : [];
    // Current-side coordinates only — never invent from the prior-year row.
    const rows = matches
      .filter(m => m && m.current && m.recurrence_label === 'returning_likely')
      .map(m => ({ ...m.current, recurrence_label: m.recurrence_label, match_score: m.match_score }));
    const split = splitPins(rows);
    split.pins.sort((a, b) => b.score - a.score);
    return { pins: split.pins, listOnly: split.listOnly, dateLabel: 'returning likely' };
  }

  // ---- State -------------------------------------------------------------
  const laneState = Object.fromEntries(Object.keys(LANES).map(k => [k, {
    loaded: false, data: null, result: null, layer: null, enabled: false
  }]));
  let civicLoaded = false;

  // ---- Styles ------------------------------------------------------------
  function installStyles() {
    if (document.getElementById('nycif-desk-layer-style')) return;
    const style = document.createElement('style');
    style.id = 'nycif-desk-layer-style';
    style.textContent = `
      .nycif-desk-block { display: grid; gap: 6px; margin-top: 6px; }
      .nycif-desk-block .desk-title {
        display: flex; align-items: center; gap: 6px;
        font-size: 10px; font-weight: 900; text-transform: uppercase;
        letter-spacing: .05em; color: #7a6128; margin: 2px 0;
      }
      .nycif-desk-block .desk-badge {
        display: inline-flex; padding: 1px 6px; border-radius: 999px;
        background: rgba(176,141,62,.16); color: #7a6128; font-size: 9px; font-weight: 900;
      }
      .nycif-desk-status { font-size: 10px; color: #4b5563; line-height: 1.35; }
      .nycif-desk-kpi {
        margin-top: 4px; padding: 6px 8px; border-radius: 10px;
        background: rgba(176,141,62,.10); color: #3f3a2f; font-size: 10px; line-height: 1.4;
      }
      .nycif-desk-marker {
        display: grid; place-items: center; width: 32px; height: 32px;
        border-radius: 999px 999px 999px 4px; border: 2px solid #fff;
        box-shadow: 0 8px 20px rgba(0,0,0,.34); color: #fff; font-size: 15px;
      }
      .nycif-desk-marker-shoot { background: #b08d3e; }
      .nycif-desk-marker-money { background: #2f6f4f; }
      .nycif-desk-marker-viral { background: #7c4dff; }
      .nycif-desk-popup { min-width: 220px; max-width: 300px; font: 500 12px/1.4 system-ui, -apple-system, sans-serif; color: #1d1d1f; }
      .nycif-desk-popup .tag { display: inline-flex; padding: 2px 7px; border-radius: 999px; background: rgba(176,141,62,.16); color: #7a6128; font-size: 10px; font-weight: 900; text-transform: uppercase; }
      .nycif-desk-popup h2 { margin: 6px 0 4px; font-size: 15px; line-height: 1.15; }
      .nycif-desk-popup p { margin: 3px 0; }
      .nycif-desk-popup .muted { color: #6b7280; font-size: 11px; }
      .nycif-desk-popup a { color: #44546b; font-weight: 800; }
      .nycif-desk-listonly { margin-top: 4px; display: grid; gap: 3px; }
      .nycif-desk-listonly .li {
        font-size: 10px; color: #4b5563; padding: 3px 5px; border-radius: 7px;
        background: rgba(107,114,128,.08);
      }
      .nycif-desk-listonly .li b { color: #9a3412; font-weight: 900; }
    `;
    document.head.appendChild(style);
  }

  // ---- Rendering ---------------------------------------------------------
  function esc(v) {
    return String(v == null ? '' : v).replace(/[&<>"']/g, ch => (
      { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]
    ));
  }

  function timeLabel(row) {
    const t = String(row.start || '');
    const m = t.match(/T(\d{2}):(\d{2})/);
    if (!m || (m[1] === '00' && m[2] === '00')) return '';
    let h = Number(m[1]);
    const ap = h >= 12 ? 'PM' : 'AM';
    h = h % 12 || 12;
    return `${h}:${m[2]} ${ap}`;
  }

  function popupHtml(row, laneLabel) {
    const time = timeLabel(row);
    const link = /^https:\/\//.test(row.mapLink) ? row.mapLink
      : `https://www.google.com/maps?q=${row.lat},${row.lng}`;
    return `<article class="nycif-desk-popup">
      <div class="tag">${esc(laneLabel)} · certified</div>
      <h2>${esc(row.title)}</h2>
      <p class="muted">${esc(row.date)}${time ? ' · ' + esc(time) : ''}${row.borough ? ' · ' + esc(row.borough) : ''}</p>
      ${row.location ? `<p>${esc(row.location)}</p>` : ''}
      ${row.recurrence ? `<p class="muted">${esc(row.recurrence)}</p>` : ''}
      ${row.why ? `<p class="muted">${esc(row.why)}</p>` : ''}
      <p><a href="${esc(link)}" target="_blank" rel="noopener noreferrer">Directions</a></p>
    </article>`;
  }

  function markerFor(row, lane) {
    const icon = window.L.divIcon({
      className: `${lane.markerClass}-shell`,
      html: `<div class="nycif-desk-marker ${lane.markerClass}">${lane.label.slice(0, 2)}</div>`,
      iconSize: [32, 32],
      iconAnchor: [16, 30],
      popupAnchor: [0, -26]
    });
    return window.L.marker([row.lat, row.lng], { icon, title: row.title, zIndexOffset: 5000 })
      .bindPopup(popupHtml(row, lane.label), { maxWidth: 320, minWidth: 220 });
  }

  function setStatus(text) {
    const el = document.getElementById('nycif-desk-status');
    if (el) el.textContent = text;
  }

  function renderListOnly(result) {
    const wrap = document.getElementById('nycif-desk-listonly');
    if (!wrap) return;
    const rows = [];
    Object.values(laneState).forEach(s => {
      if (s.enabled && s.result && s.result.listOnly) {
        s.result.listOnly.slice(0, 8).forEach(r => rows.push(r));
      }
    });
    wrap.innerHTML = rows.length
      ? rows.map(r => `<div class="li"><b>LIST ONLY</b> ${esc(r.title)}${r.borough ? ' · ' + esc(r.borough) : ''} <span style="opacity:.7">(${esc(r.reason)})</span></div>`).join('')
      : '';
  }

  async function fetchJson(url) {
    const res = await fetch(`${url}?cache=${Date.now()}`, { cache: 'no-store', headers: { Accept: 'application/json' } });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  }

  async function toggleLane(key, enabled) {
    const map = window.NYCIF_MAIN_MAP;
    const lane = LANES[key];
    const state = laneState[key];
    if (!map || !window.L) {
      setStatus('Map is still loading. Try again in a moment.');
      return;
    }
    state.enabled = enabled;
    if (!enabled) {
      if (state.layer) map.removeLayer(state.layer);
      renderListOnly();
      setStatus(`${lane.label} hidden.`);
      return;
    }
    try {
      setStatus(`Loading ${lane.label}…`);
      if (!state.loaded) {
        state.data = await fetchJson(`${DATA_BASE}/${lane.file}`);
        state.loaded = true;
      }
      state.result = lane.extract(state.data);
      if (!state.layer) {
        state.layer = window.L.layerGroup(state.result.pins.map(row => markerFor(row, lane)));
      }
      state.layer.addTo(map);
      const p = state.result.pins.length;
      const l = state.result.listOnly.length;
      setStatus(`${lane.label}: ${p} certified pin${p === 1 ? '' : 's'}${l ? ` · ${l} list-only` : ''} · ${esc(state.result.dateLabel)}`);
      renderListOnly();
    } catch (err) {
      console.error('[NYCIF desk]', key, err);
      const cb = document.getElementById(`nycif-desk-toggle-${key}`);
      if (cb) cb.checked = false;
      state.enabled = false;
      setStatus(`${lane.label} failed to load (${err.message}).`);
    }
  }

  async function loadCivicKpi() {
    if (civicLoaded) return;
    const el = document.getElementById('nycif-desk-civic-kpi');
    if (!el) return;
    try {
      const rep = await fetchJson(`${DATA_BASE}/civic_people_facing_map_coverage_report.json`);
      const counts = rep.coordinate_status_counts_staging || {};
      civicLoaded = true;
      el.textContent = `Civic coverage — map_ready ${Number(counts.map_ready || 0).toLocaleString()} · `
        + `list_only ${Number(counts.list_only || 0).toLocaleString()}`
        + (counts.proposed != null ? ` · proposed ${Number(counts.proposed).toLocaleString()}` : '')
        + `. Civic events already appear on the public map; list_only/proposed stay off the map as pins.`;
    } catch (err) {
      el.textContent = `Civic coverage unavailable (${err.message}).`;
    }
  }

  // ---- Controls (gated; appended to the Filters panel) -------------------
  function ensureControls() {
    const panel = document.getElementById('layersPanel');
    if (!panel || document.getElementById('nycif-desk-block')) return;

    const block = document.createElement('div');
    block.id = 'nycif-desk-block';
    block.className = 'nycif-desk-block';
    const toggles = Object.entries(LANES).map(([key, lane]) => `
      <label class="check"><input type="checkbox" id="nycif-desk-toggle-${key}"> <span>${esc(lane.label)}</span></label>
    `).join('');
    block.innerHTML = `
      <hr>
      <div class="desk-title">🎥 Operator Desk <span class="desk-badge">certified pins only</span></div>
      ${toggles}
      <div id="nycif-desk-status" class="nycif-desk-status"></div>
      <div id="nycif-desk-listonly" class="nycif-desk-listonly"></div>
      <div id="nycif-desk-civic-kpi" class="nycif-desk-kpi">Loading civic coverage…</div>
    `;
    panel.appendChild(block);

    Object.keys(LANES).forEach(key => {
      const cb = document.getElementById(`nycif-desk-toggle-${key}`);
      if (cb) cb.addEventListener('change', () => toggleLane(key, cb.checked));
    });
    loadCivicKpi();
  }

  function boot() {
    if (!window.L) return;
    installStyles();
    ensureControls();
    console.info('[NYCIF] Operator Desk layer active (operator mode). Public map surface unchanged.');
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }

  // Expose for tests / God View reuse.
  window.NYCIF_OPERATOR_DESK = {
    certifyCoord,
    certifyRow,
    extractShootDay,
    extractMoneyDay,
    extractViral,
    LANES: Object.fromEntries(Object.entries(LANES).map(([k, v]) => [k, { label: v.label, file: v.file }]))
  };
})();
