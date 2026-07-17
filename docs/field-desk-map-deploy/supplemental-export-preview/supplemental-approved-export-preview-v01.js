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

  const VERSION = 'supplemental-approved-export-preview-v02';
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
    'https://raw.githubusercontent.com/setoxxx/nycif-live-feeds/main/dist/supplemental_approved_export_feed.json';
  const DEFAULT_LITE_PINS_URL =
    'https://raw.githubusercontent.com/setoxxx/nycif-live-feeds/main/dist/supplemental_approved_export_map_pins.json';
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

  function mapPinsUrl() {
    try {
      const params = new URL(location.href).searchParams;
      const custom = params.get('exportPins');
      if (custom && /^https?:\/\//.test(custom)) return custom;
    } catch {
      /* fall through */
    }
    const full = feedUrl();
    if (full.includes('supplemental_approved_export_feed.json')) {
      return full.replace(
        'supplemental_approved_export_feed.json',
        'supplemental_approved_export_map_pins.json'
      );
    }
    return DEFAULT_LITE_PINS_URL;
  }

  function boundsFromPins(pins) {
    let minLat = Infinity;
    let maxLat = -Infinity;
    let minLng = Infinity;
    let maxLng = -Infinity;
    for (const pin of pins) {
      if (pin.lat < minLat) minLat = pin.lat;
      if (pin.lat > maxLat) maxLat = pin.lat;
      if (pin.lng < minLng) minLng = pin.lng;
      if (pin.lng > maxLng) maxLng = pin.lng;
    }
    return window.L.latLngBounds([minLat, minLng], [maxLat, maxLng]);
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

  function validateMapPinsPayload(payload) {
    if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
      throw new Error('Map pins feed must be a JSON object');
    }
    const artifactType = String(payload.artifact_type || '');
    if (artifactType !== 'supplemental_approved_export_map_pins') {
      throw new Error(`Refusing non-map-pins artifact: ${artifactType || 'unknown'}`);
    }
    if (payload.production_feed === true) {
      throw new Error('Refusing production_feed=true artifact in preview mode');
    }
    if (payload.promotion_allowed === true) {
      throw new Error('Refusing promotion_allowed=true artifact in preview mode');
    }
    if (!Array.isArray(payload.pins)) {
      throw new Error('Map pins feed missing pins array');
    }
    return payload;
  }

  function certifyLitePin(pin) {
    const coord = certifyCoord(pin?.lat, pin?.lng);
    if (!coord.ok) return null;
    return {
      ...pin,
      lat: coord.lat,
      lng: coord.lng,
    };
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

  function setPageMeta(feedText, mapText) {
    const feedMeta = document.getElementById('feedMeta');
    const mapMeta = document.getElementById('mapMeta');
    if (feedMeta && feedText) feedMeta.textContent = feedText;
    if (mapMeta && mapText) mapMeta.textContent = mapText;
  }

  function suppressServiceWorkerForPreview() {
    if (!previewExportMode() || !('serviceWorker' in navigator)) return;
    navigator.serviceWorker.getRegistrations()
      .then(regs => Promise.all(regs.map(reg => reg.unregister())))
      .catch(() => {});
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

  let SupplementalDotsLayerClass = null;

  function getSupplementalDotsLayerClass() {
    if (SupplementalDotsLayerClass) return SupplementalDotsLayerClass;
    if (!window.L?.Layer) {
      throw new Error('Leaflet is not loaded');
    }
    SupplementalDotsLayerClass = window.L.Layer.extend({
    initialize(pins) {
      this._pins = pins;
    },
    onAdd(map) {
      this._map = map;
      this._canvas = window.L.DomUtil.create('canvas', 'nycif-supplemental-dots-canvas');
      map.getPanes().overlayPane.appendChild(this._canvas);
      map.on('move zoom moveend zoomend resize viewreset', this._reset, this);
      map.on('click', this._onMapClick, this);
      this._reset();
      return this;
    },
    onRemove(map) {
      map.off('move zoom moveend zoomend resize viewreset', this._reset, this);
      map.off('click', this._onMapClick, this);
      window.L.DomUtil.remove(this._canvas);
    },
    _reset() {
      const map = this._map;
      const size = map.getSize();
      const topLeft = map.containerPointToLayerPoint([0, 0]);
      window.L.DomUtil.setPosition(this._canvas, topLeft);
      this._canvas.width = size.x;
      this._canvas.height = size.y;
      this._topLeft = topLeft;
      this._redraw();
    },
    _redraw() {
      const map = this._map;
      const ctx = this._canvas.getContext('2d');
      if (!ctx) return;
      ctx.clearRect(0, 0, this._canvas.width, this._canvas.height);
      const bounds = map.getBounds();
      const topLeft = this._topLeft;
      ctx.fillStyle = '#7c3aed';
      ctx.strokeStyle = '#ede9fe';
      ctx.lineWidth = 1;
      for (const pin of this._pins) {
        if (!bounds.contains([pin.lat, pin.lng])) continue;
        const pt = map.latLngToContainerPoint([pin.lat, pin.lng]);
        const x = pt.x - topLeft.x;
        const y = pt.y - topLeft.y;
        ctx.beginPath();
        ctx.arc(x, y, 5, 0, Math.PI * 2);
        ctx.fill();
        ctx.stroke();
      }
    },
    _onMapClick(event) {
      const map = this._map;
      const clickPt = map.latLngToContainerPoint(event.latlng);
      let best = null;
      let bestDist = 14;
      const bounds = map.getBounds();
      for (const pin of this._pins) {
        if (!bounds.contains([pin.lat, pin.lng])) continue;
        const pt = map.latLngToContainerPoint([pin.lat, pin.lng]);
        const dx = pt.x - clickPt.x;
        const dy = pt.y - clickPt.y;
        const dist = Math.hypot(dx, dy);
        if (dist < bestDist) {
          bestDist = dist;
          best = pin;
        }
      }
      if (best) {
        window.L.popup({ maxWidth: 350, minWidth: 250 })
          .setLatLng([best.lat, best.lng])
          .setContent(popupHtml(best))
          .openOn(map);
      }
    }
    });
    return SupplementalDotsLayerClass;
  }

  function buildMarkerLayer(map, pins, options = {}) {
    const { fitBounds = false, onProgress } = options;
    if (onProgress) onProgress(pins.length, pins.length);
    const LayerClass = getSupplementalDotsLayerClass();
    const layer = new LayerClass(pins).addTo(map);
    if (fitBounds && pins.length) {
      map.fitBounds(boundsFromPins(pins).pad(0.12));
    }
    return layer;
  }

  async function loadPinsFromLiteFeed(url) {
    const response = await fetch(`${url}?cache=${Date.now()}`, {
      cache: 'no-store',
      headers: { Accept: 'application/json' },
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = validateMapPinsPayload(await response.json());
    const pins = payload.pins.map(certifyLitePin).filter(Boolean);
    state.feedMeta = {
      artifactType: payload.artifact_type,
      exportEventCount: payload.export_event_count ?? pins.length,
      approvedQueueCount: payload.approved_queue_count ?? null,
      generatedAtUtc: payload.generated_at_utc || null,
      sourceUrl: url,
      feedKind: 'map_pins',
    };
    state.pins = pins;
    state.loaded = true;
    return state;
  }

  async function loadPinsFromFullFeed(url) {
    const response = await fetch(`${url}?cache=${Date.now()}`, {
      cache: 'no-store',
      headers: { Accept: 'application/json' },
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = validateExportPayload(await response.json());
    const pins = [];
    const events = payload.events;
    for (let index = 0; index < events.length; index += 1) {
      const pin = normalizePin(events[index], index);
      if (pin) pins.push(pin);
      if (index > 0 && index % 400 === 0) {
        await new Promise(resolve => setTimeout(resolve, 0));
      }
    }
    state.feedMeta = {
      artifactType: payload.artifact_type,
      exportEventCount: payload.export_event_count ?? pins.length,
      approvedQueueCount: payload.approved_queue_count ?? null,
      generatedAtUtc: payload.generated_at_utc || null,
      sourceUrl: url,
      feedKind: 'full_export',
    };
    state.pins = pins;
    state.loaded = true;
    return state;
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
    const liteUrl = mapPinsUrl();
    setStatus(`Loading supplemental map pins from ${liteUrl}…`);
    try {
      try {
        return await loadPinsFromLiteFeed(liteUrl);
      } catch (liteError) {
        console.warn('Lite map pins unavailable; falling back to full export feed.', liteError);
        const fullUrl = feedUrl();
        setStatus(`Loading full supplemental export feed from ${fullUrl}…`);
        return await loadPinsFromFullFeed(fullUrl);
      }
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
      if (state.layer) map.removeLayer(state.layer);
      setStatus(`Drawing ${state.pins.length.toLocaleString()} preview markers…`);
      state.layer = buildMarkerLayer(map, state.pins, {
        fitBounds: false,
      });
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

  function scheduleDeskAutoEnable() {
    let attempts = 0;
    const tick = () => {
      attempts += 1;
      const map = window.NYCIF_MAIN_MAP;
      const checkbox = document.getElementById('supplementalExportPreviewToggle');
      if (map && window.L && checkbox) {
        if (!checkbox.checked) {
          checkbox.checked = true;
          toggleOverlay(true);
        }
        return;
      }
      if (attempts < 160) setTimeout(tick, 250);
    };
    tick();
  }

  function bootDeskOverlay() {
    suppressServiceWorkerForPreview();
    installStyles();
    ensureBanner();
    ensureControls();
    scheduleDeskAutoEnable();
  }

  function bootStandaloneMap(mapElId) {
    suppressServiceWorkerForPreview();
    installStyles();
    ensureBanner();
    const mapNode = document.getElementById(mapElId || 'map');
    if (!mapNode || !window.L) return Promise.reject(new Error('Map container not ready'));

    setPageMeta('Fetching supplemental map pins…', 'Initializing map…');

    const map = window.L.map(mapNode).setView([40.7128, -74.006], 11);
    window.NYCIF_MAIN_MAP = map;
    window.L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 18,
      attribution: '&copy; OpenStreetMap',
    }).addTo(map);

    return loadExportFeed()
      .then(() => {
        setPageMeta(
          `Feed loaded · ${state.pins.length.toLocaleString()} approved export row(s)`,
          'Drawing purple preview dots…'
        );
        state.layer = buildMarkerLayer(map, state.pins, { fitBounds: true });
        setPageMeta(
          `${state.pins.length.toLocaleString()} approved export marker(s) · ${state.feedMeta?.feedKind || 'map'}`,
          `${state.pins.length.toLocaleString()} marker(s) on map · PREVIEW / NOT PRODUCTION`
        );
        return state;
      });
  }

  const api = {
    VERSION,
    standaloneMode,
    deskOverlayMode,
    previewExportMode,
    feedUrl,
    mapPinsUrl,
    validateExportPayload,
    validateMapPinsPayload,
    certifyLitePin,
    normalizePin,
    certifyCoord,
    loadExportFeed,
    buildMarkerLayer,
    toggleOverlay,
    bootStandaloneMap,
    setPageMeta,
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
