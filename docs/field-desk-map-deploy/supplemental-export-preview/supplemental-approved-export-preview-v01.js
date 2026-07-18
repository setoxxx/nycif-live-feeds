/**
 * NYCIF Field Desk — Supplemental Approved Export Preview v01.
 *
 * Admin/preview-only overlay for backend supplemental_approved_export_feed.json.
 * Loads approved supplemental events with clear "preview / not production" labeling.
 *
 * Activation:
 * - approved-export-preview.html (standalone QA page — preferred)
 * - desk.html?previewExport=1 (redirects to standalone for Safari stability)
 * - desk.html?previewExport=1&deskOverlay=1 (heavy desk overlay — admin only)
 *
 * Does NOT load GPS review artifacts, pending queue rows, or public production feeds.
 */
(function () {
  'use strict';

  function shouldRedirectDeskPreviewToStandalone() {
    if (document.documentElement?.dataset?.nycifSupplementalExportPreview === '1') {
      return false;
    }
    try {
      const url = new URL(location.href);
      return url.searchParams.get('previewExport') === '1'
        && url.searchParams.get('deskOverlay') !== '1';
    } catch {
      return false;
    }
  }

  function redirectDeskPreviewToStandalone() {
    const target = new URL('approved-export-preview.html', location.href);
    const current = new URL(location.href);
    ['exportFeed', 'exportPins', 'localExport', 'distExport'].forEach((key) => {
      const value = current.searchParams.get(key);
      if (value) target.searchParams.set(key, value);
    });
    if (typeof location !== 'undefined' && typeof location.replace === 'function') {
      location.replace(String(target));
    }
  }

  if (shouldRedirectDeskPreviewToStandalone()) {
    redirectDeskPreviewToStandalone();
    return;
  }

  const VERSION = 'supplemental-approved-export-preview-v06';
  const TIP_JAR_LINKS = [
    { id: 'cashapp', label: 'Cash App', emoji: '💵', url: 'https://cash.app/$NYCINFOCUS' },
    { id: 'venmo', label: 'Venmo', emoji: '💙', url: 'https://venmo.com/u/Howie-Doin' },
    { id: 'paypal', label: 'PayPal', emoji: '🅿️', url: 'https://py.pl/oxvv2Mgg0bztfniKXwpQWA' },
  ];
  const VIEWPORT_BUFFER = 0.15;
  const MARKER_SOFT_CAP = 600;
  const DAY_WINDOW = 7;
  const CHIP_DAY_NAMES = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
  const DAYS_IN_MONTH = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
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
  const DEFAULT_ANNIVERSARY_URL =
    'https://raw.githubusercontent.com/setoxxx/nycif-live-feeds/main/dist/supplemental_cultural_anniversary_staging.json';
  const DEFAULT_GEOFENCE_URL =
    'https://raw.githubusercontent.com/setoxxx/nycif-live-feeds/main/dist/supplemental_press_geofence_staging.json';
  const DEFAULT_PRECINCT_SHARD_BASE_URL =
    'https://raw.githubusercontent.com/setoxxx/nycif-live-feeds/main/dist/nypd_precincts/';
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
    dateMode: 'today',
    anniversaryByKey: new Map(),
    geofenceByKey: new Map(),
    precinctGeometryCache: new Map(),
    activeGeofenceLayer: null,
    enrichmentLoaded: false,
  };

  const dateKey = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  const todayKey = () => dateKey(new Date());
  const addDays = (d, n) => {
    const x = new Date(d);
    x.setDate(x.getDate() + n);
    return x;
  };

  function validCalendarDate(value) {
    const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(value ?? ''));
    if (!match) return null;
    const year = Number(match[1]);
    const month = Number(match[2]);
    const day = Number(match[3]);
    if (year < 2000 || year > 2100 || month < 1 || month > 12 || day < 1) return null;
    const leap = (year % 4 === 0 && year % 100 !== 0) || year % 400 === 0;
    const max = month === 2 && leap ? 29 : DAYS_IN_MONTH[month - 1];
    return day <= max ? match[0] : null;
  }

  function selectedDateKey() {
    if (state.dateMode === 'today') {
      return todayKey();
    }
    const valid = validCalendarDate(state.dateMode);
    if (valid && valid >= todayKey()) {
      return valid;
    }
    return todayKey();
  }

  function pinDateKey(pin) {
    const direct = validCalendarDate(String(pin?.dateKey || pin?.date || '').slice(0, 10));
    if (direct) return direct;
    const start = String(pin?.startDateTime || '');
    const match = /^(\d{4}-\d{2}-\d{2})/.exec(start);
    return (match && validCalendarDate(match[1])) || '';
  }

  function pinEndDay(pin, startDay) {
    if (!startDay) return startDay || '';
    const raw = /^(\d{4}-\d{2}-\d{2})/.exec(String(pin?.endDateTime || ''));
    const endDay = raw ? validCalendarDate(raw[1]) : '';
    return endDay && endDay >= startDay ? endDay : startDay;
  }

  function dateMatchesPin(pin, sel) {
    const start = pinDateKey(pin);
    if (!start) return false;
    const end = pin.endDay || pinEndDay(pin, start);
    return start <= sel && sel <= end;
  }

  function filterPinsForSelectedDate(pins, sel) {
    const selected = sel || selectedDateKey();
    return pins.filter(pin => dateMatchesPin(pin, selected));
  }

  function sortPinsByDate(pins) {
    return [...pins].sort((a, b) => {
      const da = pinDateKey(a) || '9999-99-99';
      const db = pinDateKey(b) || '9999-99-99';
      return da.localeCompare(db) || String(a.title || '').localeCompare(String(b.title || ''));
    });
  }

  function dateChipModel(baseDate) {
    const start = baseDate && typeof baseDate.getTime === 'function'
      ? new Date(baseDate.getTime())
      : new Date();
    const chips = [];
    for (let i = 0; i <= DAY_WINDOW; i += 1) {
      const d = addDays(start, i);
      let label;
      if (i === 0) label = 'Today';
      else if (i === 1) label = 'Tomorrow';
      else label = `${CHIP_DAY_NAMES[d.getDay()]} ${d.getMonth() + 1}/${d.getDate()}`;
      chips.push({ key: dateKey(d), label, offset: i });
    }
    return chips;
  }

  function friendlyDateLabel(key) {
    if (key === todayKey()) return 'today';
    const tomorrow = dateKey(addDays(new Date(), 1));
    if (key === tomorrow) return 'tomorrow';
    return key;
  }

  function readInitialDateMode() {
    try {
      const param = new URL(location.href).searchParams.get('previewDate');
      const valid = validCalendarDate(param);
      if (valid && valid >= todayKey()) {
        return valid;
      }
    } catch {
      /* fall through */
    }
    return 'today';
  }

  function visiblePinsForMap() {
    return sortPinsByDate(filterPinsForSelectedDate(state.pins));
  }

  state.dateMode = readInitialDateMode();

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

  function anniversaryStagingUrl() {
    try {
      const custom = new URL(location.href).searchParams.get('anniversaryStaging');
      if (custom && /^https?:\/\//.test(custom)) return custom;
    } catch {
      /* fall through */
    }
    return DEFAULT_ANNIVERSARY_URL;
  }

  function geofenceStagingUrl() {
    try {
      const custom = new URL(location.href).searchParams.get('geofenceStaging');
      if (custom && /^https?:\/\//.test(custom)) return custom;
    } catch {
      /* fall through */
    }
    return DEFAULT_GEOFENCE_URL;
  }

  function precinctShardBaseUrl() {
    try {
      const custom = new URL(location.href).searchParams.get('precinctShards');
      if (custom && /^https?:\/\//.test(custom)) return custom;
    } catch {
      /* fall through */
    }
    return DEFAULT_PRECINCT_SHARD_BASE_URL;
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
    const startDay = pinDateKey(pin);
    if (!startDay) return null;
    return {
      ...pin,
      lat: coord.lat,
      lng: coord.lng,
      dateKey: startDay,
      endDay: pinEndDay(pin, startDay),
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
    const startDay = pinDateKey({
      date: row.date,
      startDateTime: row.start_date_time,
      dateKey: row.date,
    });
    if (!startDay) return null;
    const endDay = pinEndDay({ endDateTime: row.end_date_time }, startDay);
    return {
      id: row.overlap_key || row.source_event_id || `supplemental-export-${index}`,
      title: row.title || 'Supplemental approved event',
      displayLocation: row.display_location || '',
      borough: row.borough || '',
      date: startDay,
      dateKey: startDay,
      endDay,
      startDateTime: row.start_date_time || '',
      endDateTime: row.end_date_time || '',
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
    if (!previewExportMode() || typeof navigator === 'undefined' || !('serviceWorker' in navigator)) {
      return;
    }
    try {
      navigator.serviceWorker.register = async function blockedServiceWorkerRegister() {
        return {
          scope: `${location.origin}/`,
          unregister: async () => true,
          update: async () => {},
        };
      };
    } catch {
      /* ignore */
    }
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
      .nycif-supplemental-preview-marker-wrap {
        position: relative;
        display: inline-block;
        width: 34px;
        height: 34px;
      }
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
      .nycif-supplemental-preview-anniversary-badge {
        position: absolute;
        top: -3px;
        right: -5px;
        min-width: 16px;
        height: 16px;
        padding: 0 4px;
        border-radius: 999px;
        background: #fbbf24;
        color: #78350f;
        border: 1.5px solid #fff;
        font: 800 9px/1 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        display: grid;
        place-items: center;
        box-shadow: 0 4px 10px rgba(0,0,0,.22);
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
      .nycif-supplemental-preview-popup .anniversary-tag {
        display: inline-flex;
        border-radius: 999px;
        padding: 3px 7px;
        margin-top: 6px;
        background: rgba(251,191,36,.18);
        color: #92400e;
        font-size: 10px;
        font-weight: 800;
        text-transform: uppercase;
        letter-spacing: .04em;
      }
      .nycif-supplemental-preview-popup .geofence-tag {
        display: inline-flex;
        border-radius: 999px;
        padding: 3px 7px;
        margin-top: 6px;
        margin-left: 6px;
        background: rgba(56,189,248,.16);
        color: #0369a1;
        font-size: 10px;
        font-weight: 800;
        text-transform: uppercase;
        letter-spacing: .04em;
      }
      .nycif-supplemental-preview-date-chips {
        display: flex;
        gap: 8px;
        overflow-x: auto;
        padding: 2px 0 12px;
        margin-bottom: 4px;
        scrollbar-width: thin;
      }
      .nycif-supplemental-preview-date-chips button {
        flex: 0 0 auto;
        border: 1px solid rgba(255,255,255,.12);
        background: rgba(255,255,255,.04);
        color: var(--text, #eef2ff);
        border-radius: 999px;
        padding: 8px 12px;
        font: 600 12px/1 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        cursor: pointer;
      }
      .nycif-supplemental-preview-date-chips button.active {
        background: rgba(124,58,237,.28);
        border-color: rgba(167,139,250,.55);
        color: #ede9fe;
      }
      .nycif-tip-jar {
        position: fixed;
        top: 12px;
        right: 12px;
        z-index: 1300;
        display: grid;
        justify-items: end;
        gap: 8px;
      }
      .nycif-tip-jar-btn {
        width: 52px;
        height: 52px;
        border: 2px solid rgba(251,191,36,.55);
        border-radius: 999px;
        background: linear-gradient(180deg, rgba(120,53,15,.95), rgba(69,26,3,.95));
        box-shadow: 0 10px 24px rgba(0,0,0,.35);
        cursor: pointer;
        display: grid;
        place-items: center;
        padding: 0;
      }
      .nycif-tip-jar-btn:focus-visible {
        outline: 2px solid #fbbf24;
        outline-offset: 2px;
      }
      .nycif-tip-jar-emoji {
        font-size: 26px;
        line-height: 1;
        transform-origin: 50% 85%;
        display: block;
      }
      .nycif-tip-jar.shake .nycif-tip-jar-emoji {
        animation: nycif-tip-jar-shake 0.55s ease-in-out;
      }
      @keyframes nycif-tip-jar-shake {
        0%, 100% { transform: rotate(0deg) translateY(0); }
        15% { transform: rotate(-14deg) translateY(1px); }
        30% { transform: rotate(12deg) translateY(-1px); }
        45% { transform: rotate(-10deg) translateY(1px); }
        60% { transform: rotate(8deg) translateY(0); }
        75% { transform: rotate(-6deg) translateY(1px); }
      }
      .nycif-tip-jar-panel {
        min-width: 220px;
        padding: 12px;
        border-radius: 14px;
        border: 1px solid rgba(251,191,36,.35);
        background: rgba(17,24,39,.96);
        box-shadow: 0 16px 36px rgba(0,0,0,.35);
        color: #fde68a;
      }
      .nycif-tip-jar-panel[hidden] { display: none; }
      .nycif-tip-jar-panel h3 {
        margin: 0 0 8px;
        font: 700 12px/1.2 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        color: #fcd34d;
      }
      .nycif-tip-jar-panel a {
        display: flex;
        align-items: center;
        gap: 8px;
        padding: 8px 10px;
        margin-top: 6px;
        border-radius: 10px;
        background: rgba(255,255,255,.05);
        color: #fff7ed;
        text-decoration: none;
        font: 600 13px/1.2 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      }
      .nycif-tip-jar-panel a:hover {
        background: rgba(251,191,36,.14);
      }
      .nycif-tip-jar-panel .pay-emoji {
        font-size: 18px;
        width: 22px;
        text-align: center;
      }
    `;
    document.head.appendChild(style);
  }

  function ensureTipJar() {
    if (!previewExportMode() || document.getElementById('nycifTipJar')) return;

    const root = document.createElement('div');
    root.id = 'nycifTipJar';
    root.className = 'nycif-tip-jar';
    root.innerHTML = `
      <button type="button" class="nycif-tip-jar-btn" id="nycifTipJarBtn"
        aria-expanded="false" aria-controls="nycifTipJarPanel" aria-label="Open tip jar">
        <span class="nycif-tip-jar-emoji" aria-hidden="true">🫙</span>
      </button>
      <div class="nycif-tip-jar-panel" id="nycifTipJarPanel" hidden>
        <h3>Tip jar — support NYC In Focus</h3>
        ${TIP_JAR_LINKS.map(link => `
          <a href="${esc(link.url)}" target="_blank" rel="noopener noreferrer">
            <span class="pay-emoji" aria-hidden="true">${link.emoji}</span>
            <span>${esc(link.label)}</span>
          </a>
        `).join('')}
      </div>
    `;
    document.body.appendChild(root);

    const button = document.getElementById('nycifTipJarBtn');
    const panel = document.getElementById('nycifTipJarPanel');
    if (!button || !panel) return;

    button.addEventListener('click', (event) => {
      event.stopPropagation();
      const open = panel.hidden;
      panel.hidden = !open;
      button.setAttribute('aria-expanded', String(open));
      if (open) root.classList.remove('shake');
    });

    document.addEventListener('click', (event) => {
      if (!root.contains(event.target)) {
        panel.hidden = true;
        button.setAttribute('aria-expanded', 'false');
      }
    });

    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && !panel.hidden) {
        panel.hidden = true;
        button.setAttribute('aria-expanded', 'false');
      }
    });

    const scheduleRandomShake = () => {
      const waitMs = 5000 + Math.floor(Math.random() * 9000);
      window.setTimeout(() => {
        if (!panel.hidden) {
          scheduleRandomShake();
          return;
        }
        root.classList.add('shake');
        window.setTimeout(() => root.classList.remove('shake'), 560);
        scheduleRandomShake();
      }, waitMs);
    };
    scheduleRandomShake();
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

  function pinKey(pin) {
    return String(pin?.id || pin?.overlap_key || '');
  }

  function anniversaryBadgeLabel(pin) {
    if (!pin?.culturalAnniversary) return '';
    if (Number.isFinite(pin.anniversaryNumber)) return String(pin.anniversaryNumber);
    return 'A';
  }

  function markerIconHtml(pin) {
    const badge = anniversaryBadgeLabel(pin);
    const badgeHtml = badge
      ? `<span class="nycif-supplemental-preview-anniversary-badge">${esc(badge)}</span>`
      : '';
    return `<span class="nycif-supplemental-preview-marker-wrap"><span class="nycif-supplemental-preview-marker">🟣</span>${badgeHtml}</span>`;
  }

  function popupHtml(pin) {
    const anniversaryBits = pin.culturalAnniversary
      ? `<span class="anniversary-tag">${pin.anniversaryNumber ? `${esc(pin.anniversaryNumber)}${pin.anniversaryNumber === 1 ? 'st' : pin.anniversaryNumber === 2 ? 'nd' : pin.anniversaryNumber === 3 ? 'rd' : 'th'} year` : 'Annual event'}</span>`
      : '';
    const geofenceBits = pin.assignedPrecinct
      ? `<span class="geofence-tag">Precinct ${esc(pin.assignedPrecinct)}</span>`
      : '';
    return `<article class="nycif-supplemental-preview-popup">
      <div class="preview-tag">Preview / not production</div>
      ${anniversaryBits || geofenceBits ? `<div>${anniversaryBits}${geofenceBits}</div>` : ''}
      <h2>${esc(pin.title)}</h2>
      ${pin.displayLocation ? `<p>${esc(pin.displayLocation)}</p>` : ''}
      ${pin.borough ? `<p><strong>Borough:</strong> ${esc(pin.borough)}</p>` : ''}
      ${pin.date ? `<p><strong>Date:</strong> ${esc(pin.date)}</p>` : ''}
      ${pin.anniversaryStory ? `<p><strong>Cultural story:</strong> ${esc(pin.anniversaryStory)}</p>` : ''}
      ${pin.assignedPrecinct ? `<p><strong>NYPD precinct geofence:</strong> ${esc(pin.assignedPrecinct)} (tap pin to outline boundary)</p>` : ''}
      ${pin.pressReleaseCandidate ? `<p><strong>Press candidate:</strong> yes (preview heuristic only)</p>` : ''}
      ${pin.geofenceStory && pin.pressReleaseCandidate ? `<p class="note">${esc(pin.geofenceStory)}</p>` : ''}
      ${pin.intakeType ? `<p><strong>Intake:</strong> ${esc(pin.intakeType)}</p>` : ''}
      ${pin.geocoderSource ? `<p><strong>Geocoder source:</strong> ${esc(pin.geocoderSource)}</p>` : ''}
      ${pin.geocoderConfidence ? `<p><strong>Confidence:</strong> ${esc(pin.geocoderConfidence)}</p>` : ''}
      <p class="note">Approved supplemental export preview only. promotion_allowed=false. Not on public map.</p>
    </article>`;
  }

  function clearActiveGeofence(map) {
    if (state.activeGeofenceLayer && map) {
      map.removeLayer(state.activeGeofenceLayer);
      state.activeGeofenceLayer = null;
    }
  }

  async function loadPrecinctGeometry(precinct) {
    const key = String(precinct || '');
    if (!key) return null;
    if (state.precinctGeometryCache.has(key)) {
      return state.precinctGeometryCache.get(key);
    }
    const base = precinctShardBaseUrl();
    const url = `${base}precinct-${encodeURIComponent(key)}.json`;
    const response = await fetch(`${url}?cache=${Date.now()}`, {
      cache: 'no-store',
      headers: { Accept: 'application/json' },
    });
    if (!response.ok) return null;
    const payload = await response.json();
    const geometry = payload?.geometry;
    if (!geometry || typeof geometry !== 'object') return null;
    state.precinctGeometryCache.set(key, geometry);
    return geometry;
  }

  async function showPrecinctGeofenceForPin(map, pin) {
    if (!map || !pin?.assignedPrecinct || !pin?.geofenceEnabled) return;
    try {
      const geometry = await loadPrecinctGeometry(pin.assignedPrecinct);
      if (!geometry) return;
      clearActiveGeofence(map);
      state.activeGeofenceLayer = window.L.geoJSON(
        { type: 'Feature', properties: { precinct: pin.assignedPrecinct }, geometry },
        {
          style: {
            color: '#38bdf8',
            weight: 2,
            fillColor: '#38bdf8',
            fillOpacity: 0.14,
          },
        }
      ).addTo(map);
    } catch (error) {
      console.warn('Precinct geofence preview failed', error);
    }
  }

  function applyEnrichmentToPins() {
    for (const pin of state.pins) {
      const key = pinKey(pin);
      const anniversary = state.anniversaryByKey.get(key);
      const geofence = state.geofenceByKey.get(key);
      if (anniversary) {
        pin.culturalAnniversary = true;
        pin.anniversaryNumber = anniversary.anniversary_number;
        pin.editionYear = anniversary.edition_year;
        pin.anniversaryStory = anniversary.story_placeholder || '';
      }
      if (geofence) {
        pin.assignedPrecinct = geofence.assigned_precinct;
        pin.geofenceEnabled = geofence.geofence_enabled_preview === true;
        pin.pressReleaseCandidate = geofence.press_release_candidate === true;
        pin.geofenceStory = geofence.story_placeholder || '';
      }
      pin.marker = null;
    }
  }

  function validateAnniversaryPayload(payload) {
    if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
      throw new Error('Anniversary staging must be a JSON object');
    }
    if (payload.artifact_type !== 'supplemental_cultural_anniversary_staging') {
      throw new Error(`Refusing non-anniversary artifact: ${payload.artifact_type || 'unknown'}`);
    }
    if (payload.production_feed === true || payload.promotion_allowed === true) {
      throw new Error('Refusing production/promotion anniversary artifact in preview mode');
    }
    if (!Array.isArray(payload.rows)) {
      throw new Error('Anniversary staging missing rows array');
    }
    return payload;
  }

  function validateGeofencePayload(payload) {
    if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
      throw new Error('Geofence staging must be a JSON object');
    }
    if (payload.artifact_type !== 'supplemental_press_geofence_staging') {
      throw new Error(`Refusing non-geofence artifact: ${payload.artifact_type || 'unknown'}`);
    }
    if (payload.production_feed === true || payload.promotion_allowed === true) {
      throw new Error('Refusing production/promotion geofence artifact in preview mode');
    }
    if (!Array.isArray(payload.rows)) {
      throw new Error('Geofence staging missing rows array');
    }
    return payload;
  }

  async function loadPreviewEnrichment() {
    const [anniversaryResult, geofenceResult] = await Promise.allSettled([
      fetch(`${anniversaryStagingUrl()}?cache=${Date.now()}`, {
        cache: 'no-store',
        headers: { Accept: 'application/json' },
      }).then(async (response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return validateAnniversaryPayload(await response.json());
      }),
      fetch(`${geofenceStagingUrl()}?cache=${Date.now()}`, {
        cache: 'no-store',
        headers: { Accept: 'application/json' },
      }).then(async (response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return validateGeofencePayload(await response.json());
      }),
    ]);

    state.anniversaryByKey = new Map();
    state.geofenceByKey = new Map();

    if (anniversaryResult.status === 'fulfilled') {
      for (const row of anniversaryResult.value.rows) {
        if (row?.overlap_key) state.anniversaryByKey.set(String(row.overlap_key), row);
      }
    } else {
      console.warn('Anniversary staging unavailable for preview.', anniversaryResult.reason);
    }

    if (geofenceResult.status === 'fulfilled') {
      for (const row of geofenceResult.value.rows) {
        if (row?.overlap_key) state.geofenceByKey.set(String(row.overlap_key), row);
      }
    } else {
      console.warn('Geofence staging unavailable for preview.', geofenceResult.reason);
    }

    applyEnrichmentToPins();
    state.enrichmentLoaded = true;
    return state;
  }

  function expandedBounds(map) {
    const bounds = map.getBounds();
    if (!bounds) return null;
    const padLat = (bounds.getNorth() - bounds.getSouth()) * VIEWPORT_BUFFER;
    const padLng = (bounds.getEast() - bounds.getWest()) * VIEWPORT_BUFFER;
    return window.L.latLngBounds(
      [bounds.getSouth() - padLat, bounds.getWest() - padLng],
      [bounds.getNorth() + padLat, bounds.getEast() + padLng]
    );
  }

  function makePreviewMarker(pin) {
    const marker = window.L.marker([pin.lat, pin.lng], {
      icon: window.L.divIcon({
        className: 'nycif-supplemental-preview-marker-shell',
        html: markerIconHtml(pin),
        iconSize: [38, 38],
        iconAnchor: [19, 19],
        popupAnchor: [0, -20],
      }),
      title: pin.title,
      riseOnHover: true,
    }).bindPopup(popupHtml(pin), {
      maxWidth: 350,
      minWidth: 250,
      autoPan: false,
      closeButton: true,
      autoClose: true,
      closeOnClick: true,
    });
    marker.on('click', () => {
      const map = window.NYCIF_MAIN_MAP;
      if (map) showPrecinctGeofenceForPin(map, pin);
    });
    return marker;
  }

  function ensureMarker(pin) {
    if (!pin.marker) {
      pin.marker = makePreviewMarker(pin);
    }
    return pin.marker;
  }

  function formatMapRenderMeta(stats) {
    const totalLoaded = stats.loadedTotal || stats.total || 0;
    const dayTotal = stats.total || 0;
    const dateLabel = stats.selectedDate ? friendlyDateLabel(stats.selectedDate) : 'today';
    let text = `${dayTotal.toLocaleString()} event${dayTotal === 1 ? '' : 's'} on ${dateLabel}`;
    if (totalLoaded && dayTotal !== totalLoaded) {
      text += ` · ${totalLoaded.toLocaleString()} loaded total`;
    }
    text += ' · PREVIEW / NOT PRODUCTION';
    if (stats.drawn < stats.inView) {
      text += ` · ${stats.drawn.toLocaleString()} shown of ${stats.inView.toLocaleString()} in view — pan/zoom for more`;
    } else if (stats.drawn < dayTotal) {
      text += ` · ${stats.drawn.toLocaleString()} shown in current view`;
    }
    return text;
  }

  function formatFeedMetaLine() {
    const selected = selectedDateKey();
    const dayCount = filterPinsForSelectedDate(state.pins, selected).length;
    const loaded = state.pins.length;
    const kind = state.feedMeta?.feedKind || 'map';
    const anni = state.anniversaryByKey?.size || 0;
    const geo = state.geofenceByKey?.size || 0;
    let line = `${dayCount.toLocaleString()} on ${friendlyDateLabel(selected)} · ${loaded.toLocaleString()} approved export row(s) total · ${kind}`;
    if (anni) line += ` · ${anni} cultural anniversary`;
    if (geo) line += ` · ${geo} precinct geofence`;
    return line;
  }

  function buildDateChips(containerId) {
    const host = document.getElementById(containerId || 'previewDateChips');
    if (!host) return;
    host.className = 'nycif-supplemental-preview-date-chips';
    host.innerHTML = '';
    const activeKey = selectedDateKey();
    dateChipModel(new Date()).forEach((chip) => {
      const mode = chip.offset === 0 ? 'today' : chip.key;
      const button = document.createElement('button');
      button.type = 'button';
      button.dataset.dateMode = mode;
      button.dataset.dateKey = chip.key;
      button.textContent = chip.label;
      if (chip.key === activeKey) {
        button.classList.add('active');
      }
      button.addEventListener('click', () => {
        state.dateMode = mode;
        buildDateChips(containerId);
        if (state.layer?.renderMarkers) {
          state.layer.renderMarkers();
        }
        setPageMeta(formatFeedMetaLine(), formatMapRenderMeta(state.layer?.getRenderStats?.() || {
          total: filterPinsForSelectedDate(state.pins).length,
          loadedTotal: state.pins.length,
          selectedDate: selectedDateKey(),
          drawn: 0,
          inView: 0,
        }));
      });
      host.appendChild(button);
    });
  }

  function buildMarkerLayer(map, getPins, options = {}) {
    const { fitBounds = false, onProgress, onRender } = options;
    if (!window.L?.layerGroup) {
      throw new Error('Leaflet is not loaded');
    }

    let pinsGetter = typeof getPins === 'function' ? getPins : () => getPins;
    let renderTimer = null;
    let moveTimer = null;
    const markers = window.L.layerGroup().addTo(map);
    const renderStats = {
      drawn: 0,
      inView: 0,
      total: 0,
      loadedTotal: state.pins.length,
      selectedDate: selectedDateKey(),
    };

    function renderMarkers() {
      const pins = pinsGetter();
      markers.clearLayers();
      const bounds = expandedBounds(map);
      const inView = bounds
        ? pins.filter(pin => bounds.contains([pin.lat, pin.lng]))
        : pins;
      const candidates = (inView.length ? inView : pins).slice(0, MARKER_SOFT_CAP);
      const batch = [];
      for (const pin of candidates) {
        const marker = ensureMarker(pin);
        if (marker) batch.push(marker);
      }
      batch.forEach(marker => markers.addLayer(marker));
      renderStats.drawn = batch.length;
      renderStats.inView = inView.length;
      renderStats.total = pins.length;
      renderStats.loadedTotal = state.pins.length;
      renderStats.selectedDate = selectedDateKey();
      if (onProgress) onProgress(batch.length, pins.length);
      if (onRender) onRender({ ...renderStats });
      return batch;
    }

    function scheduleRender() {
      clearTimeout(renderTimer);
      renderTimer = setTimeout(() => renderMarkers(), 40);
    }

    function onMapMoveEnd() {
      clearTimeout(moveTimer);
      moveTimer = setTimeout(() => scheduleRender(), 120);
    }

    map.on('moveend', onMapMoveEnd);
    map.on('zoomend', scheduleRender);

    markers.cleanup = () => {
      clearTimeout(renderTimer);
      clearTimeout(moveTimer);
      map.off('moveend', onMapMoveEnd);
      map.off('zoomend', scheduleRender);
    };
    markers.renderMarkers = renderMarkers;
    markers.getRenderStats = () => ({ ...renderStats });
    markers.setPinsGetter = (fn) => {
      pinsGetter = fn;
    };

    renderMarkers();

    if (fitBounds) {
      const pins = pinsGetter();
      if (pins.length) {
        map.fitBounds(boundsFromPins(pins).pad(0.12), { animate: false });
      }
    }

    return markers;
  }

  function removeMarkerLayer(map, layer) {
    if (!layer) return;
    if (typeof layer.cleanup === 'function') {
      layer.cleanup();
    }
    map.removeLayer(layer);
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
        await loadPinsFromLiteFeed(liteUrl);
      } catch (liteError) {
        console.warn('Lite map pins unavailable; falling back to full export feed.', liteError);
        const fullUrl = feedUrl();
        setStatus(`Loading full supplemental export feed from ${fullUrl}…`);
        await loadPinsFromFullFeed(fullUrl);
      }
      await loadPreviewEnrichment();
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
      removeMarkerLayer(map, state.layer);
      state.layer = null;
      setStatus('Supplemental approved export preview hidden.');
      return;
    }

    try {
      await loadExportFeed();
      removeMarkerLayer(map, state.layer);
      setStatus(`Drawing preview markers for ${friendlyDateLabel(selectedDateKey())}…`);
      state.layer = buildMarkerLayer(map, visiblePinsForMap, {
        fitBounds: false,
        onRender(stats) {
          setStatus(formatMapRenderMeta(stats));
        },
      });
    } catch (error) {
      console.error(error);
      const checkbox = document.getElementById('supplementalExportPreviewToggle');
      if (checkbox) checkbox.checked = false;
      setStatus(`Supplemental export preview failed: ${error.message}`);
    }
  }

  function scheduleDeskAutoEnable() {
    let attempts = 0;
    let enabled = false;
    const tick = () => {
      if (enabled) return;
      attempts += 1;
      const map = window.NYCIF_MAIN_MAP;
      const checkbox = document.getElementById('supplementalExportPreviewToggle');
      if (map && window.L && checkbox) {
        if (!checkbox.checked) {
          checkbox.checked = true;
          toggleOverlay(true);
        }
        enabled = true;
        return;
      }
      if (attempts < 160) setTimeout(tick, 250);
    };
    tick();
  }

  function bootDeskOverlay() {
    suppressServiceWorkerForPreview();
    installStyles();
    ensureTipJar();
    ensureBanner();
    ensureControls();
    scheduleDeskAutoEnable();
  }

  function bootStandaloneMap(mapElId) {
    suppressServiceWorkerForPreview();
    installStyles();
    ensureTipJar();
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
        buildDateChips('previewDateChips');
        setPageMeta(
          formatFeedMetaLine(),
          `Drawing preview markers for ${friendlyDateLabel(selectedDateKey())}…`
        );
        state.layer = buildMarkerLayer(map, visiblePinsForMap, {
          fitBounds: true,
          onRender(stats) {
            setPageMeta(formatFeedMetaLine(), formatMapRenderMeta(stats));
          },
        });
        return state;
      });
  }

  const api = {
    VERSION,
    TIP_JAR_LINKS,
    VIEWPORT_BUFFER,
    MARKER_SOFT_CAP,
    DAY_WINDOW,
    standaloneMode,
    deskOverlayMode,
    previewExportMode,
    feedUrl,
    mapPinsUrl,
    anniversaryStagingUrl,
    geofenceStagingUrl,
    precinctShardBaseUrl,
    validateExportPayload,
    validateMapPinsPayload,
    validateAnniversaryPayload,
    validateGeofencePayload,
    certifyLitePin,
    normalizePin,
    certifyCoord,
    pinKey,
    anniversaryBadgeLabel,
    markerIconHtml,
    applyEnrichmentToPins,
    loadPreviewEnrichment,
    validCalendarDate,
    pinDateKey,
    dateMatchesPin,
    filterPinsForSelectedDate,
    sortPinsByDate,
    selectedDateKey,
    dateChipModel,
    friendlyDateLabel,
    visiblePinsForMap,
    expandedBounds,
    ensureMarker,
    formatMapRenderMeta,
    formatFeedMetaLine,
    buildDateChips,
    loadExportFeed,
    buildMarkerLayer,
    removeMarkerLayer,
    toggleOverlay,
    bootStandaloneMap,
    setPageMeta,
    getState: () => ({ ...state, pins: [...state.pins] }),
  };

  window.NYCIF_SUPPLEMENTAL_EXPORT_PREVIEW = api;

  if (previewExportMode()) {
    suppressServiceWorkerForPreview();
  }

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
