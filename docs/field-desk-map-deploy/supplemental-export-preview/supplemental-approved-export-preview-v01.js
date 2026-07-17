/**
 * NYCIF Field Desk — Supplemental Approved Export Preview v01.
 *
 * Admin/preview-only overlay for backend supplemental_approved_export_feed.json.
 * Loads approved supplemental events with clear "preview / not production" labeling.
 *
 * Activation:
 * - desk.html?previewExport=1
 * - approved-export-preview.html (standalone QA page)
 *
 * Does NOT load GPS review artifacts, pending queue rows, or public production feeds.
 */
(function () {
  'use strict';

  const VERSION = 'supplemental-approved-export-preview-v01';
  const BLOCKED_ARTIFACT_TYPES = new Set([
    'gps_manual_approval_queue',
    'gps_review_geocoding_proposals',
    'gps_review_geocoding_filled_proposals',
    'gps_manual_approval_review_sheet',
    'gps_manual_approval_review_findings',
    'supplemental_manual_approval_queue',
    'supplemental_events_staging_feed',
  ]);
  const DEFAULT_BACKEND_URL =
    'https://raw.githubusercontent.com/setoxxx/nycif-live-feeds/main/data/supplemental_approved_export_feed.json';
  const LOCAL_EXPORT_URL = './data/supplemental_approved_export_feed.json';
  const DIST_EXPORT_URL = './data/supplemental_approved_export_feed.dist.json';
  const NYC = { minLat: 40.4774, maxLat: 40.9176, minLng: -74.2591, maxLng: -73.7004 };

  const state = {
    loaded: false,
    loading: false,
    feedMeta: null,
    pins: [],
    layer: null,
    banner: null,
  };

  function esc(value) {
    return String(value ?? '').replace(/[&<>"']/g, ch => ({
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#39;',
    }[ch]));
  }

  function standaloneMode() {
    return document.documentElement?.dataset?.nycifSupplementalExportPreview === '1';
  }

  function deskOverlayMode() {
    if (standaloneMode()) return false;
    try {
      return new URL(location.href).searchParams.get('previewExport') === '1';
    } catch {
      return false;
    }
  }

  function previewExportMode() {
    return standaloneMode() || deskOverlayMode();
  }

  function feedUrl() {
    try {
      const params = new URL(location.href).searchParams;
      const custom = params.get('exportFeed');
      if (custom && /^https?:\/\//.test(custom)) return custom;
      if (params.get('localExport') === '1') return LOCAL_EXPORT_URL;
      if (params.get('distExport') === '1') return DIST_EXPORT_URL;
    } catch {
      /* fall through */
    }
    return DEFAULT_BACKEND_URL;
  }

  function inNycBox(lat, lng) {
    return lat >= NYC.minLat && lat <= NYC.maxLat && lng >= NYC.minLng && lng <= NYC.maxLng;
  }

  function certifyCoord(rawLat, rawLng) {
    const lat = Number(rawLat);
    const lng = Number(rawLng);
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) {
      return { ok: false, reason: 'nonfinite' };
    }
    if (inNycBox(lat, lng)) {
      return { ok: true, lat, lng, reason: 'ok_nyc' };
    }
    if (inNycBox(lng, lat)) {
      return { ok: false, reason: 'swap_suspected' };
    }
    return { ok: false, reason: 'out_of_box' };
  }

  function validateExportPayload(payload) {
    if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
      throw new Error('Export feed must be a JSON object');
    }
    const artifactType = String(payload.artifact_type || '');
    if (BLOCKED_ARTIFACT_TYPES.has(artifactType)) {
      throw new Error(`Refusing review/staging artifact: ${artifactType}`);
    }
    if (artifactType !== 'supplemental_approved_export_feed') {
      throw new Error(`Refusing non-export artifact: ${artifactType || 'unknown'}`);
    }
    if (payload.production_feed === true) {
      throw new Error('Refusing production_feed=true artifact in preview mode');
    }
    if (payload.promotion_allowed === true) {
      throw new Error('Refusing promotion_allowed=true artifact in preview mode');
    }
    if (!Array.isArray(payload.events)) {
      throw new Error('Export feed missing events array');
    }
    return payload;
  }

  function normalizePin(row, index) {
    if (String(row.manual_review_status || '').toLowerCase() !== 'approved') {
      return null;
    }
    if (row.promotion_allowed === true || row.production_feed === true) {
      return null;
    }
    const coord = certifyCoord(row.lat ?? row.proposed_lat, row.lng ?? row.proposed_lng);
    if (!coord.ok) return null;
    return {
      id: row.overlap_key || row.source_event_id || `supplemental-export-${index}`,
      title: row.title || 'Supplemental approved event',
      displayLocation: row.display_location || '',
      borough: row.borough || '',
      date: row.date || '',
      startDateTime: row.start_date_time || '',
      geocoderSource: row.geocoder_source || '',
      geocoderConfidence: row.geocoder_confidence || '',
      confidenceReason: row.confidence_reason || '',
      intakeType: row.intake_type || '',
      sourceDataset: row.source_dataset || '',
      sourceEventId: row.source_event_id || '',
      manualReviewer: row.manual_reviewer || '',
      manualReviewedAtUtc: row.manual_reviewed_at_utc || '',
      approvalDecisionReason: row.approval_decision_reason || '',
      lat: coord.lat,
      lng: coord.lng,
    };
  }

  function setStatus(text) {
    const status = document.getElementById('status');
    if (status) status.textContent = text;
  }

  function installStyles() {
    if (document.getElementById('nycif-supplemental-export-preview-style')) return;
    const style = document.createElement('style');
    style.id = 'nycif-supplemental-export-preview-style';
    style.textContent = `
      .nycif-supplemental-preview-banner {
        position: fixed;
        top: 12px;
        left: 50%;
        transform: translateX(-50%);
        z-index: 1200;
        max-width: min(92vw, 720px);
        padding: 10px 14px;
        border-radius: 12px;
        border: 1px solid rgba(251,191,36,.45);
        background: rgba(120,53,15,.92);
        color: #fde68a;
        font: 700 12px/1.35 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        box-shadow: 0 12px 30px rgba(0,0,0,.28);
        text-align: center;
      }
      .nycif-supplemental-preview-banner small {
        display: block;
        margin-top: 4px;
        font-weight: 500;
        color: #fcd34d;
      }
      .nycif-supplemental-preview-block { display: grid; gap: 8px; }
      .nycif-supplemental-preview-note {
        margin: 8px 0 0;
        font-size: 11px;
        line-height: 1.35;
        color: rgba(255,255,255,.72);
      }
      .nycif-supplemental-preview-marker-shell { background: transparent; border: 0; }
      .nycif-supplemental-preview-marker {
        display: grid;
        place-items: center;
        width: 34px;
        height: 34px;
        border-radius: 999px;
        border: 2px solid rgba(255,255,255,.94);
        box-shadow: 0 9px 22px rgba(0,0,0,.34);
        background: #7c3aed;
        color: #fff;
        font-size: 15px;
      }
      .nycif-supplemental-preview-popup {
        min-width: 240px;
        max-width: 340px;
        padding: 12px 14px;
        border-radius: 16px;
        background: #fff;
        font: 500 12px/1.35 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        color: #111827;
        box-shadow: 0 18px 45px rgba(15,23,42,.16);
      }
      .nycif-supplemental-preview-popup .preview-tag {
        display: inline-flex;
        border-radius: 999px;
        padding: 3px 7px;
        background: rgba(124,58,237,.14);
        color: #5b21b6;
        font-size: 10px;
        font-weight: 900;
        text-transform: uppercase;
        letter-spacing: .04em;
      }
      .nycif-supplemental-preview-popup h2 {
        margin: 7px 0 5px;
        color: #0f172a;
        font-size: 15px;
        line-height: 1.15;
      }
      .nycif-supplemental-preview-popup p { margin: 4px 0; color: #111827; }
      .nycif-supplemental-preview-popup strong { color: #0f172a; }
      .nycif-supplemental-preview-popup .note { color: #4b5563; font-size: 11px; }
    `;
    document.head.appendChild(style);
  }

  function ensureBanner() {
    if (state.banner || !document.body) return;
    const banner = document.createElement('div');
    banner.className = 'nycif-supplemental-preview-banner';
    banner.setAttribute('role', 'status');
    banner.innerHTML =
      'PREVIEW — NOT PRODUCTION<small>Supplemental approved export feed only. Not merged into public map or location_cache.</small>';
    document.body.appendChild(banner);
    state.banner = banner;
  }

  function ensureControls() {
    const panel = document.getElementById('layersPanel');
    if (!panel || document.getElementById('supplementalExportPreviewBlock')) return;

    const block = document.createElement('div');
    block.id = 'supplementalExportPreviewBlock';
    block.className = 'nycif-supplemental-preview-block';
    block.innerHTML = `
      <hr>
      <p class="panel-label">Preview / not production</p>
      <label class="check">
        <input type="checkbox" id="supplementalExportPreviewToggle">
        <span>🟣 Supplemental approved export (preview)</span>
      </label>
      <p class="nycif-supplemental-preview-note">
        Loads <code>supplemental_approved_export_feed.json</code> from the backend repo.
        Approved supplemental rows only — not GPS review queues or pending approvals.
      </p>
    `;
    panel.appendChild(block);

    const checkbox = document.getElementById('supplementalExportPreviewToggle');
    if (checkbox) {
      checkbox.addEventListener('change', () => toggleOverlay(checkbox.checked));
    }
  }

  function popupHtml(pin) {
    return `<article class="nycif-supplemental-preview-popup">
      <div class="preview-tag">Preview / not production</div>
      <h2>${esc(pin.title)}</h2>
      ${pin.displayLocation ? `<p>${esc(pin.displayLocation)}</p>` : ''}
      ${pin.borough ? `<p><strong>Borough:</strong> ${esc(pin.borough)}</p>` : ''}
      ${pin.date ? `<p><strong>Date:</strong> ${esc(pin.date)}</p>` : ''}
      ${pin.intakeType ? `<p><strong>Intake:</strong> ${esc(pin.intakeType)}</p>` : ''}
      ${pin.geocoderSource ? `<p><strong>Geocoder source:</strong> ${esc(pin.geocoderSource)}</p>` : ''}
      ${pin.geocoderConfidence ? `<p><strong>Confidence:</strong> ${esc(pin.geocoderConfidence)}</p>` : ''}
      <p class="note">Approved supplemental export preview only. promotion_allowed=false. Not on public map.</p>
    </article>`;
  }

  function markerFor(pin) {
    const icon = window.L.divIcon({
      className: 'nycif-supplemental-preview-marker-shell',
      html: '<div class="nycif-supplemental-preview-marker">🟣</div>',
      iconSize: [34, 34],
      iconAnchor: [17, 17],
      popupAnchor: [0, -18],
    });
    return window.L.marker([pin.lat, pin.lng], {
      icon,
      title: pin.title,
      zIndexOffset: 880,
    }).bindPopup(popupHtml(pin), { maxWidth: 350, minWidth: 250 });
  }

  async function loadExportFeed() {
    if (state.loaded) return state;
    if (state.loading) {
      while (state.loading) {
        await new Promise(resolve => setTimeout(resolve, 50));
      }
      return state;
    }

    state.loading = true;
    const url = feedUrl();
    setStatus(`Loading supplemental approved export preview from ${url}…`);
    try {
      const response = await fetch(`${url}?cache=${Date.now()}`, {
        cache: 'no-store',
        headers: { Accept: 'application/json' },
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const payload = validateExportPayload(await response.json());
      const pins = payload.events
        .map((row, index) => normalizePin(row, index))
        .filter(Boolean);
      state.feedMeta = {
        artifactType: payload.artifact_type,
        exportEventCount: payload.export_event_count ?? pins.length,
        approvedQueueCount: payload.approved_queue_count ?? null,
        generatedAtUtc: payload.generated_at_utc || null,
        sourceUrl: url,
      };
      state.pins = pins;
      state.loaded = true;
      return state;
    } finally {
      state.loading = false;
    }
  }

  async function toggleOverlay(enabled) {
    const map = window.NYCIF_MAIN_MAP;
    if (!map || !window.L) {
      setStatus('Map is still loading. Try again in a moment.');
      return;
    }

    if (!enabled) {
      if (state.layer) map.removeLayer(state.layer);
      setStatus('Supplemental approved export preview hidden.');
      return;
    }

    try {
      await loadExportFeed();
      if (!state.layer) {
        state.layer = window.L.layerGroup(state.pins.map(markerFor));
      }
      state.layer.addTo(map);
      setStatus(
        `Supplemental approved export preview · ${state.pins.length.toLocaleString()} marker${
          state.pins.length === 1 ? '' : 's'
        } · PREVIEW / NOT PRODUCTION`
      );
    } catch (error) {
      console.error(error);
      const checkbox = document.getElementById('supplementalExportPreviewToggle');
      if (checkbox) checkbox.checked = false;
      setStatus(`Supplemental export preview failed: ${error.message}`);
    }
  }

  function bootDeskOverlay() {
    installStyles();
    ensureBanner();
    ensureControls();
  }

  function bootStandaloneMap(mapElId) {
    installStyles();
    ensureBanner();
    const mapNode = document.getElementById(mapElId || 'map');
    if (!mapNode || !window.L) return Promise.reject(new Error('Map container not ready'));

    const map = window.L.map(mapNode).setView([40.7128, -74.006], 11);
    window.NYCIF_MAIN_MAP = map;
    window.L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 18,
      attribution: '&copy; OpenStreetMap',
    }).addTo(map);

    return loadExportFeed().then(() => {
      state.layer = window.L.layerGroup(state.pins.map(markerFor)).addTo(map);
      if (state.pins.length) {
        const bounds = window.L.latLngBounds(state.pins.map(pin => [pin.lat, pin.lng]));
        map.fitBounds(bounds.pad(0.12));
      }
      return state;
    });
  }

  const api = {
    VERSION,
    standaloneMode,
    deskOverlayMode,
    previewExportMode,
    feedUrl,
    validateExportPayload,
    normalizePin,
    certifyCoord,
    loadExportFeed,
    toggleOverlay,
    bootStandaloneMap,
    getState: () => ({ ...state, pins: [...state.pins] }),
  };

  window.NYCIF_SUPPLEMENTAL_EXPORT_PREVIEW = api;

  if (!deskOverlayMode()) {
    return;
  }

  function bootWhenReady() {
    if (!window.L) return;
    bootDeskOverlay();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bootWhenReady);
  } else {
    bootWhenReady();
  }
})();
