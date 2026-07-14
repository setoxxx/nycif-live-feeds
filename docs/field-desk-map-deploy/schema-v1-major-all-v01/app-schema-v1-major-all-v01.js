(() => {
  const VERSION = 'schema-v1-major-all-v01';
  const STORAGE_KEY = 'nycif-field-desk-state-v06-safe';
  const DEFAULT_VERSION = 'schema-v1-major-all-v01';
  const LIST_PAGE = 100;
  const VIEWPORT_MARKER_CAP = 450;
  const SEARCH_DEBOUNCE_MS = 180;
  const NYC_CENTER = [40.7128, -74.006];
  const FEED_HOST = (location.hostname === 'localhost' || location.hostname === '127.0.0.1')
    ? ''
    : 'https://raw.githubusercontent.com/setoxxx/nycif-live-feeds/main';
  const FEEDS = {
    major: `${FEED_HOST}/data/events_schema_v1_major.json`,
    approved: `${FEED_HOST}/data/events_schema_v1_staged.json`,
    review: `${FEED_HOST}/data/events_schema_v1_supplemental_review.json`,
    approvedManifest: `${FEED_HOST}/data/schema-v1/approved/manifest.json`,
    reviewManifest: `${FEED_HOST}/data/schema-v1/review/manifest.json`,
    legacyMajor: `${FEED_HOST}/nycif_major_radar_map_events.json`,
    legacyStaged: `${FEED_HOST}/data/nycif_staged_live_events.json`,
    legacySupp: `${FEED_HOST}/data/supplemental_events_staging_feed.json`
  };
  const CATEGORY_META = {
    sports: { emoji: '🏟️', label: 'Sports' },
    fitness: { emoji: '💪', label: 'Fitness / wellness' },
    parks: { emoji: '🌳', label: 'Parks / recreation' },
    arts: { emoji: '🎭', label: 'Arts / culture' },
    market: { emoji: '🛍️', label: 'Markets / fairs' },
    civic: { emoji: '📣', label: 'Civic / neighborhood' },
    government: { emoji: '🏛️', label: 'Government / hearings' },
    education: { emoji: '📚', label: 'Education / training' },
    family: { emoji: '👨‍👩‍👧', label: 'Kids / family' },
    services: { emoji: '🤝', label: 'Benefits / services' },
    environment: { emoji: '🌎', label: 'Environment' },
    volunteer: { emoji: '🙋', label: 'Volunteer' },
    jobs: { emoji: '💼', label: 'Jobs / careers' },
    housing: { emoji: '🏠', label: 'Housing / tenant help' },
    general: { emoji: '📍', label: 'General' }
  };
  const ALL_CATEGORY_KEYS = Object.keys(CATEGORY_META);
  const BOROUGHS = ['All', 'Manhattan', 'Brooklyn', 'Queens', 'Bronx', 'Staten Island'];
  const DAY_NAMES = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
  const SCHEMA = window.NYCIF_EVENT_FEED_SCHEMA_V1;
  const debug = (() => { try { return new URL(location.href).searchParams.get('debugMap') === '1'; } catch { return false; } })();

  const state = {
    viewMode: 'major',
    sourceFilter: 'all',
    events: [],
    byId: new Map(),
    search: '',
    borough: 'all',
    sort: 'priority',
    dateMode: 'next7',
    categories: Object.fromEntries(ALL_CATEGORY_KEYS.map(k => [k, true])),
    photoOnly: false,
    nypdOnly: false,
    userLocation: null,
    listShown: LIST_PAGE,
    userChangedFilters: false,
    banner: '',
    fallbackUsed: false,
    timings: {},
    feedMeta: {},
    errors: [],
    markerObjects: 0
  };

  const els = {
    map: document.getElementById('map'),
    status: document.getElementById('status'),
    brandCount: document.getElementById('brandCount'),
    layersBtn: document.getElementById('layersBtn'),
    layersPanel: document.getElementById('layersPanel'),
    locateBtn: document.getElementById('locateBtn'),
    nearMeBtn: document.getElementById('nearMeBtn'),
    deskBtn: document.getElementById('deskBtn'),
    deskDrawer: document.getElementById('deskDrawer'),
    closeDeskBtn: document.getElementById('closeDeskBtn'),
    modeMajor: document.getElementById('modeMajor'),
    modeAll: document.getElementById('modeAll'),
    sourceFilter: document.getElementById('sourceFilter'),
    banner: document.getElementById('viewBanner'),
    photoOnly: document.getElementById('photoOnly'),
    nypdOnly: document.getElementById('nypdOnly'),
    searchInput: document.getElementById('searchInput'),
    sortSelect: document.getElementById('sortSelect'),
    dateChips: document.getElementById('dateChips'),
    boroughs: document.getElementById('boroughs'),
    listMeta: document.getElementById('listMeta'),
    eventList: document.getElementById('eventList'),
    loadMoreBtn: document.getElementById('loadMoreBtn'),
    resetFiltersBtn: document.getElementById('resetFiltersBtn'),
    retryFeedBtn: document.getElementById('retryFeedBtn'),
    debugPanel: document.getElementById('debugPanel')
  };

  const map = L.map(els.map, { zoomControl: true, closePopupOnClick: false, tap: false }).setView(NYC_CENTER, 11);
  window.NYCIF_MAIN_MAP = map;
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { attribution: '&copy; OpenStreetMap contributors' }).addTo(map);
  const useCluster = typeof L.markerClusterGroup === 'function';
  const markers = useCluster
    ? L.markerClusterGroup({ showCoverageOnHover: false, maxClusterRadius: 55, spiderfyOnMaxZoom: true, disableClusteringAtZoom: 16 })
    : L.layerGroup();
  markers.addTo(map);
  let userMarker = null;
  let userAccuracy = null;
  let searchTimer = null;
  let renderTimer = null;

  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const norm = v => String(v ?? '').toLowerCase().replace(/\s+/g, ' ').trim();
  const dateKey = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  const todayKey = () => dateKey(new Date());
  const addDays = (d, n) => { const x = new Date(d); x.setDate(x.getDate() + n); return x; };
  // Next 7 days = today through today + 7 (inclusive), matching prior Field Desk dayRange.
  const dayRange = () => ({ today: todayKey(), end: dateKey(addDays(new Date(), 7)) });
  const status = t => { if (els.status) els.status.textContent = t; };
  const setBanner = t => { state.banner = t || ''; if (els.banner) { els.banner.hidden = !state.banner; els.banner.textContent = state.banner; } };

  function eventDate(row) {
    const nycifDate = row?.nycif?.event_date;
    if (/^\d{4}-\d{2}-\d{2}$/.test(String(nycifDate || ''))) return nycifDate;
    const direct = String(row.date || '').slice(0, 10);
    if (/^\d{4}-\d{2}-\d{2}$/.test(direct)) return direct;
    const start = String(row.start_date_time || '');
    if (/^\d{4}-\d{2}-\d{2}/.test(start)) return start.slice(0, 10);
    return '';
  }

  function toUiEvent(schemaEvent, fallbackSource) {
    const nycif = schemaEvent.nycif || {};
    const catKey = CATEGORY_META[schemaEvent.category] ? schemaEvent.category : 'general';
    const mapReady = nycif.coordinate_status === 'map_ready'
      && Number.isFinite(schemaEvent.latitude)
      && Number.isFinite(schemaEvent.longitude);
    const layer = nycif.data_layer || fallbackSource;
    const review = layer === 'review_supplemental';
    const title = schemaEvent.title || 'Untitled event';
    const location = schemaEvent.location || '';
    const borough = schemaEvent.borough || '';
    const e = {
      ...schemaEvent,
      lat: schemaEvent.latitude,
      lng: schemaEvent.longitude,
      dateKey: eventDate(schemaEvent),
      categoryKey: catKey,
      categoryMeta: CATEGORY_META[catKey],
      mapReady,
      isReview: review,
      isMajor: schemaEvent.significance === 'major' || !!nycif.is_major,
      photoPick: !!nycif.photo_pick,
      fieldDefault: !!nycif.field_default,
      crowd_level: nycif.crowd_level,
      major_reason: nycif.major_reason,
      major_score: nycif.major_score || 0,
      verification_status: nycif.verification_status,
      assignment_feed: nycif.assignment_feed,
      searchText: norm([title, location, borough, catKey, schemaEvent.source?.dataset, schemaEvent.source?.source_event_id, nycif.event_type, nycif.major_reason].filter(Boolean).join(' ')),
      marker: null
    };
    e.priority = Number(e.major_score || 0)
      + (e.isMajor ? 500 : 0)
      + (e.photoPick ? 120 : 0)
      + (e.verification_status === 'nypd_field_intel' ? 800 : 0);
    return e;
  }

  function upsertEvents(schemaEvents, sourceLabel) {
    for (const raw of schemaEvents) {
      const e = toUiEvent(raw, sourceLabel);
      if (!e.id) continue;
      const existing = state.byId.get(e.id);
      if (existing?.marker) e.marker = existing.marker;
      state.byId.set(e.id, e);
    }
    state.events = [...state.byId.values()];
  }

  async function fetchJson(url, label) {
    const t0 = performance.now();
    const res = await fetch(`${url}${url.includes('?') ? '&' : '?'}cache=${Date.now()}`, {
      cache: 'no-store',
      headers: { Accept: 'application/json' }
    });
    const fetchMs = performance.now() - t0;
    if (!res.ok) throw new Error(`${label} HTTP ${res.status}`);
    const t1 = performance.now();
    const json = await res.json();
    const parseMs = performance.now() - t1;
    state.timings[label] = { fetchMs: Math.round(fetchMs), parseMs: Math.round(parseMs), url, status: res.status };
    return { json, status: res.status, url };
  }

  async function loadSchemaFeed(preferredUrl, fallbackUrl, dataLayer, label) {
    try {
      const { json, url } = await fetchJson(preferredUrl, label);
      if (!SCHEMA) throw new Error('schema helper missing');
      const envelope = SCHEMA.projectEnvelope(json, dataLayer, json.generated_at_utc);
      if (envelope.schema_version !== '1.0') throw new Error(`${label} bad schema_version`);
      state.feedMeta[label] = { url, total: envelope.total, schema_version: envelope.schema_version, fallback: false };
      return envelope;
    } catch (err) {
      state.errors.push(String(err.message || err));
      if (!fallbackUrl) throw err;
      status(`${label} schema feed failed; using legacy fallback…`);
      const { json, url } = await fetchJson(fallbackUrl, `${label}-fallback`);
      const envelope = SCHEMA.projectEnvelope(json, dataLayer, json.generated_at_utc);
      state.fallbackUsed = true;
      state.feedMeta[label] = { url, total: envelope.total, schema_version: envelope.schema_version, fallback: true };
      setBanner(`Schema feed issue for ${label}. Legacy fallback is in use.`);
      return envelope;
    }
  }

  function isNypd(e) {
    return e.verification_status === 'nypd_field_intel' || /nypd/i.test(e.title || '');
  }

  function milesBetween(a, b) {
    if (!a || !b || !Number.isFinite(b.lat) || !Number.isFinite(b.lng)) return null;
    const R = 3958.8;
    const toRad = x => x * Math.PI / 180;
    const dLat = toRad(b.lat - a.lat);
    const dLng = toRad(b.lng - a.lng);
    const lat1 = toRad(a.lat);
    const lat2 = toRad(b.lat);
    const x = Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLng / 2) ** 2;
    return 2 * R * Math.asin(Math.sqrt(x));
  }

  function dateMatches(e) {
    if (!e.dateKey) return false;
    const { today, end } = dayRange();
    if (state.dateMode === 'next7') return e.dateKey >= today && e.dateKey <= end;
    if (state.dateMode === 'all') return e.dateKey >= today;
    if (state.dateMode === 'today') return e.dateKey === today;
    if (/^\d{4}-\d{2}-\d{2}$/.test(state.dateMode)) return e.dateKey === state.dateMode;
    return e.dateKey >= today;
  }

  function sourceMatches(e) {
    if (state.viewMode === 'major') return e.isMajor && !e.isReview;
    if (state.sourceFilter === 'approved') return !e.isReview;
    if (state.sourceFilter === 'review') return e.isReview;
    return true;
  }

  function eventMatches(e) {
    return sourceMatches(e)
      && dateMatches(e)
      && !!state.categories[e.categoryKey]
      && (!state.photoOnly || e.photoPick)
      && (!state.nypdOnly || isNypd(e))
      && (state.borough === 'all' || e.borough === state.borough)
      && (!state.search || e.searchText.includes(state.search));
  }

  function sortEvents(a, b) {
    if (state.sort === 'near') {
      const da = milesBetween(state.userLocation, a) ?? 999999;
      const db = milesBetween(state.userLocation, b) ?? 999999;
      return da - db || b.priority - a.priority;
    }
    if (state.sort === 'borough') return (a.borough || 'zz').localeCompare(b.borough || 'zz') || b.priority - a.priority;
    if (state.sort === 'type') return (a.nycif?.event_type || 'zz').localeCompare(b.nycif?.event_type || 'zz') || b.priority - a.priority;
    if (state.sort === 'time') return (a.dateKey || '9999').localeCompare(b.dateKey || '9999') || b.priority - a.priority;
    return b.priority - a.priority || (a.dateKey || '').localeCompare(b.dateKey || '');
  }

  function appleMapsUrl(e) { return `https://maps.apple.com/?daddr=${e.lat},${e.lng}&q=${encodeURIComponent(e.title)}`; }
  function googleMapsUrl(e) { return `https://www.google.com/maps/dir/?api=1&destination=${e.lat},${e.lng}&travelmode=driving`; }

  function popupHtml(e) {
    const src = e.isReview ? 'Expanded review (not production-approved)' : (e.isMajor ? 'Major events' : 'Approved / staged');
    return `<article class="popup-card"><div class="popup-source">${esc(src)}</div><div class="popup-category"><span>${esc(e.categoryMeta.emoji)}</span> ${esc(e.categoryMeta.label)}</div><h2>${esc(e.title)}</h2><dl><div><dt>Date</dt><dd>${esc(e.dateKey || 'n/a')}</dd></div>${e.borough ? `<div><dt>Borough</dt><dd>${esc(e.borough)}</dd></div>` : ''}${e.location ? `<div><dt>Location</dt><dd>${esc(e.location)}</dd></div>` : ''}${e.major_reason ? `<div><dt>Why major</dt><dd>${esc(e.major_reason)}</dd></div>` : ''}</dl>${e.mapReady ? `<div class="field-actions"><a class="field-action" target="_blank" rel="noopener" href="${esc(appleMapsUrl(e))}">Apple Maps</a><a class="field-action" target="_blank" rel="noopener" href="${esc(googleMapsUrl(e))}">Google Maps</a></div>` : '<div class="popup-photo">LIST ONLY — coordinates pending</div>'}</article>`;
  }

  function makeMarker(e) {
    const cls = ['marker', `marker--${e.categoryKey}`, e.photoPick ? 'marker--photo' : '', isNypd(e) ? 'marker--nypd' : '', e.isMajor ? 'marker--major' : ''].filter(Boolean).join(' ');
    return L.marker([e.lat, e.lng], {
      icon: L.divIcon({
        className: 'marker-shell',
        html: `<span class="${cls}"><span class="emoji">${e.categoryMeta.emoji}</span></span>`,
        iconSize: [38, 38],
        iconAnchor: [19, 19],
        popupAnchor: [0, -24]
      }),
      title: e.title,
      riseOnHover: true
    }).bindPopup(popupHtml(e), { maxWidth: 330, autoPan: true, closeButton: true, autoClose: false, closeOnClick: false });
  }

  function ensureMarker(e) {
    if (!e.mapReady) return null;
    if (!e.marker) e.marker = makeMarker(e);
    return e.marker;
  }

  function inMapBounds(e, bounds) {
    if (!e.mapReady || !bounds) return false;
    return bounds.contains([e.lat, e.lng]);
  }

  function countForMode(mode) {
    const { today, end } = dayRange();
    return state.events.filter(e => {
      if (!e.dateKey || e.dateKey < today || e.dateKey > end) return false;
      if (mode === 'major') return e.isMajor && !e.isReview;
      return true;
    }).length;
  }

  function updateModeButtons() {
    const majorN = countForMode('major');
    const allN = countForMode('all');
    if (els.modeMajor) {
      els.modeMajor.textContent = `Major Events (${majorN.toLocaleString()})`;
      els.modeMajor.classList.toggle('active', state.viewMode === 'major');
      els.modeMajor.setAttribute('aria-pressed', String(state.viewMode === 'major'));
    }
    if (els.modeAll) {
      els.modeAll.textContent = `All Events (${allN.toLocaleString()})`;
      els.modeAll.classList.toggle('active', state.viewMode === 'all');
      els.modeAll.setAttribute('aria-pressed', String(state.viewMode === 'all'));
    }
    if (els.sourceFilter) els.sourceFilter.hidden = state.viewMode !== 'all';
  }

  function applyZeroMajorFallback(visible) {
    if (state.viewMode !== 'major' || state.userChangedFilters) return visible;
    if (visible.length) return visible;
    const upcomingMajor = state.events
      .filter(e => e.isMajor && !e.isReview && e.dateKey && e.dateKey >= todayKey())
      .sort((a, b) => a.dateKey.localeCompare(b.dateKey));
    if (upcomingMajor.length) {
      state.dateMode = upcomingMajor[0].dateKey;
      setBanner(`No Major Events in the next 7 days. Showing the next major date: ${state.dateMode}.`);
      buildDateChips();
      return state.events.filter(eventMatches).sort(sortEvents);
    }
    state.viewMode = 'all';
    state.dateMode = 'next7';
    setBanner('No upcoming Major Events were found. Showing all events for the next seven days.');
    updateModeButtons();
    buildDateChips();
    return state.events.filter(eventMatches).sort(sortEvents);
  }

  function renderMarkers(visible) {
    const t0 = performance.now();
    if (markers.clearLayers) markers.clearLayers();
    const bounds = map.getBounds();
    const mapReady = visible.filter(e => e.mapReady);
    let draw;
    if (useCluster) {
      draw = mapReady.slice(0, 2500);
    } else {
      const inView = mapReady.filter(e => inMapBounds(e, bounds));
      draw = (inView.length ? inView : mapReady).slice(0, VIEWPORT_MARKER_CAP);
    }
    const batch = [];
    for (const e of draw) {
      const m = ensureMarker(e);
      if (m) batch.push(m);
    }
    if (useCluster && markers.addLayers) markers.addLayers(batch);
    else batch.forEach(m => markers.addLayer(m));
    state.markerObjects = batch.length;
    state.timings.markerUpdateMs = Math.round(performance.now() - t0);
    return draw;
  }

  function card(e) {
    const dist = milesBetween(state.userLocation, e);
    const distLabel = Number.isFinite(dist) ? (dist < 0.1 ? 'nearby' : `${dist.toFixed(dist < 10 ? 1 : 0)} mi`) : '';
    return `<button type="button" class="event-item" data-id="${esc(e.id)}"><span class="item-top"><span class="item-source">${esc(e.categoryMeta.emoji)} ${esc(e.categoryMeta.label)}</span><span class="item-tags">${e.isReview ? '<span class="item-tag nycif-source-review">REVIEW</span>' : '<span class="item-tag">LIVE</span>'}${e.mapReady ? '' : '<span class="item-tag nycif-list-only">LIST ONLY</span>'}${e.isMajor ? '<span class="item-tag">MAJOR</span>' : ''}${distLabel ? `<span class="item-tag near">${esc(distLabel)}</span>` : ''}</span></span><strong>${esc(e.title)}</strong><span>${esc(e.dateKey || 'Date unavailable')}</span><small>${esc([e.borough, e.location, e.nycif?.event_type].filter(Boolean).join(' • '))}</small>${e.mapReady ? `<span class="quick-actions"><a href="${esc(appleMapsUrl(e))}" target="_blank" rel="noopener">Directions</a></span>` : ''}</button>`;
  }

  function render() {
    const t0 = performance.now();
    updateModeButtons();
    let visible = state.events.filter(eventMatches).sort(sortEvents);
    visible = applyZeroMajorFallback(visible);
    const drawn = renderMarkers(visible);
    const shown = Math.min(state.listShown, visible.length);
    const listOnly = visible.filter(e => !e.mapReady).length;
    els.listMeta.textContent = `${state.events.length.toLocaleString()} total · ${visible.length.toLocaleString()} match filters · ${drawn.length.toLocaleString()} markers ${useCluster ? 'clustered/capped' : 'in view'} · showing ${shown.toLocaleString()} of ${visible.length.toLocaleString()} list results${listOnly ? ` · ${listOnly.toLocaleString()} list-only` : ''}`;
    els.eventList.innerHTML = visible.slice(0, shown).map(card).join('') || '<div class="empty">No events match this view. Try Show All Events or Reset Filters.</div>';
    if (els.loadMoreBtn) {
      els.loadMoreBtn.hidden = shown >= visible.length;
      els.loadMoreBtn.textContent = `Load 100 more (${Math.max(0, visible.length - shown).toLocaleString()} remaining)`;
    }
    els.eventList.querySelectorAll('[data-id]').forEach(btn => {
      btn.addEventListener('click', ev => {
        if (ev.target.closest('a')) return;
        focusEvent(btn.dataset.id);
      });
    });
    if (els.brandCount) {
      els.brandCount.textContent = `${visible.length.toLocaleString()} ${state.viewMode === 'major' ? 'major' : 'events'} · ${state.dateMode === 'next7' ? 'next 7 days' : state.dateMode}`;
    }
    status(`${state.viewMode === 'major' ? 'Major' : 'All'} · ${visible.length.toLocaleString()} match · ${drawn.length.toLocaleString()} markers · v${VERSION}`);
    state.timings.listRenderMs = Math.round(performance.now() - t0);
    if (debug) updateDebug(visible, drawn);
    return visible;
  }

  function focusEvent(id) {
    const e = state.byId.get(id);
    if (!e) return;
    if (!e.mapReady) {
      status(`${e.title}: coordinate pending; list-only record.`);
      setDesk(true);
      return;
    }
    const marker = ensureMarker(e);
    map.flyTo([e.lat, e.lng], Math.max(map.getZoom(), 15), { duration: 0.55 });
    setTimeout(() => marker?.openPopup(), 420);
    setDesk(false);
  }

  function updateDebug(visible, drawn) {
    if (!els.debugPanel) return;
    els.debugPanel.hidden = false;
    els.debugPanel.textContent = JSON.stringify({
      version: VERSION,
      viewMode: state.viewMode,
      feeds: state.feedMeta,
      total: state.events.length,
      filtered: visible.length,
      markers: drawn.length,
      markerObjects: state.markerObjects,
      listShown: Math.min(state.listShown, visible.length),
      fallbackUsed: state.fallbackUsed,
      errors: state.errors.slice(-8),
      timings: state.timings,
      cluster: useCluster
    }, null, 2);
  }

  function publicDefaults() {
    return {
      borough: 'all',
      sort: 'priority',
      dateMode: 'next7',
      viewMode: 'major',
      sourceFilter: 'all',
      categories: Object.fromEntries(ALL_CATEGORY_KEYS.map(k => [k, true])),
      photoOnly: false,
      nypdOnly: false,
      nycifDefaultVersion: DEFAULT_VERSION
    };
  }

  function forceReset() {
    try {
      const u = new URL(location.href);
      const v = u.searchParams.get('v');
      return u.searchParams.get('resetFilters') === '1'
        || v === DEFAULT_VERSION
        || v === 'map-restore-v02'
        || v === 'data-explorer-v01';
    } catch { return false; }
  }

  function loadPrefs() {
    try {
      if (forceReset()) localStorage.removeItem(STORAGE_KEY);
      const p = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');
      const d = publicDefaults();
      const migrate = forceReset() || p.nycifDefaultVersion !== DEFAULT_VERSION;
      const use = migrate ? d : {
        ...d,
        ...p,
        categories: { ...d.categories, ...(p.categories || {}) },
        viewMode: p.viewMode === 'all' ? 'all' : 'major'
      };
      // Legacy parade -> civic
      if (use.categories.parade != null && use.categories.civic == null) use.categories.civic = !!use.categories.parade;
      Object.assign(state, {
        borough: use.borough,
        sort: use.sort,
        dateMode: use.dateMode,
        viewMode: use.viewMode || 'major',
        sourceFilter: use.sourceFilter || 'all',
        categories: Object.fromEntries(ALL_CATEGORY_KEYS.map(k => [k, use.categories[k] !== false])),
        photoOnly: !!use.photoOnly,
        nypdOnly: !!use.nypdOnly
      });
      savePrefs();
    } catch {
      Object.assign(state, publicDefaults());
    }
  }

  function savePrefs() {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({
      borough: state.borough,
      sort: state.sort === 'near' && !state.userLocation ? 'priority' : state.sort,
      dateMode: state.dateMode,
      viewMode: state.viewMode,
      sourceFilter: state.sourceFilter,
      categories: { ...state.categories },
      photoOnly: state.photoOnly,
      nypdOnly: state.nypdOnly,
      nycifDefaultVersion: DEFAULT_VERSION
    }));
  }

  function setLayers(open) {
    els.layersPanel.hidden = !open;
    els.layersBtn.setAttribute('aria-expanded', String(open));
    setTimeout(() => map.invalidateSize(), 100);
  }
  function setDesk(open) {
    els.deskDrawer.hidden = !open;
    els.deskBtn.setAttribute('aria-expanded', String(open));
    setTimeout(() => map.invalidateSize(), 100);
  }

  function buildBoroughs() {
    els.boroughs.innerHTML = BOROUGHS.map(b => {
      const v = b === 'All' ? 'all' : b;
      return `<button type="button" class="${state.borough === v ? 'active' : ''}" data-borough="${esc(v)}">${esc(b)}</button>`;
    }).join('');
  }

  function dateCounts() {
    const { today, end } = dayRange();
    const pool = state.events.filter(e => {
      if (state.viewMode === 'major') return e.isMajor && !e.isReview;
      if (state.sourceFilter === 'approved') return !e.isReview;
      if (state.sourceFilter === 'review') return e.isReview;
      return true;
    });
    return {
      today: pool.filter(e => e.dateKey === today).length,
      next7: pool.filter(e => e.dateKey && e.dateKey >= today && e.dateKey <= end).length,
      all: pool.filter(e => e.dateKey && e.dateKey >= today).length
    };
  }

  function buildDateChips() {
    const counts = dateCounts();
    const days = Array.from({ length: 8 }, (_, i) => addDays(new Date(), i));
    els.dateChips.innerHTML = `<div class="date-chip-track"><button type="button" data-date-mode="next7" class="${state.dateMode === 'next7' ? 'active' : ''}">Next 7 days (${counts.next7.toLocaleString()})</button>${days.map((d, i) => {
      const k = dateKey(d);
      const n = state.events.filter(e => {
        if (e.dateKey !== k) return false;
        if (state.viewMode === 'major') return e.isMajor && !e.isReview;
        return true;
      }).length;
      const label = i === 0 ? `Today (${n})` : `${DAY_NAMES[d.getDay()]} ${d.getMonth() + 1}/${d.getDate()} (${n})`;
      return `<button type="button" data-date-mode="${esc(k)}" class="${state.dateMode === k ? 'active' : ''}">${esc(label)}</button>`;
    }).join('')}<button type="button" data-date-mode="all" class="${state.dateMode === 'all' ? 'active' : ''}">All upcoming (${counts.all.toLocaleString()})</button></div>`;
  }

  function setUserLocation(lat, lng, accuracy) {
    const here = [lat, lng];
    state.userLocation = { lat, lng };
    if (userMarker) userMarker.setLatLng(here);
    else {
      userMarker = L.marker(here, {
        icon: L.divIcon({ className: 'user-location-shell', html: '<span class="user-location">🗽</span>', iconSize: [36, 44], iconAnchor: [18, 42] }),
        zIndexOffset: 4000
      }).addTo(map).bindPopup(`<strong>You are here</strong><br>Accuracy: ${Math.round(accuracy || 0)} meters`);
    }
    if (userAccuracy) { userAccuracy.setLatLng(here); userAccuracy.setRadius(accuracy || 0); }
    else userAccuracy = L.circle(here, { radius: accuracy || 0, color: '#d40000', weight: 2, fillColor: '#d40000', fillOpacity: 0.08 }).addTo(map);
  }

  function locateUser(options = {}) {
    if (!navigator.geolocation) { status('Location is not available in this browser.'); return; }
    status('Finding your location…');
    navigator.geolocation.getCurrentPosition(pos => {
      const { latitude, longitude, accuracy } = pos.coords;
      setUserLocation(latitude, longitude, accuracy);
      if (options.sortNear) { state.sort = 'near'; if (els.sortSelect) els.sortSelect.value = 'near'; savePrefs(); }
      map.flyTo([latitude, longitude], Math.max(map.getZoom(), 14), { duration: 0.6 });
      userMarker.openPopup();
      scheduleRender();
    }, err => status(`Location failed: ${err.message}`), { enableHighAccuracy: true, timeout: 12000, maximumAge: 15000 });
  }

  function scheduleRender() {
    clearTimeout(renderTimer);
    renderTimer = setTimeout(() => render(), 40);
  }

  function bindUi() {
    els.layersBtn?.addEventListener('click', () => setLayers(els.layersPanel.hidden));
    els.deskBtn?.addEventListener('click', () => setDesk(els.deskDrawer.hidden));
    els.closeDeskBtn?.addEventListener('click', () => setDesk(false));
    els.locateBtn?.addEventListener('click', () => locateUser());
    els.nearMeBtn?.addEventListener('click', () => locateUser({ sortNear: true }));
    els.modeMajor?.addEventListener('click', () => {
      state.userChangedFilters = true;
      state.viewMode = 'major';
      state.listShown = LIST_PAGE;
      setBanner('');
      savePrefs();
      scheduleRender();
    });
    els.modeAll?.addEventListener('click', () => {
      state.userChangedFilters = true;
      state.viewMode = 'all';
      state.listShown = LIST_PAGE;
      setBanner('');
      savePrefs();
      scheduleRender();
    });
    els.sourceFilter?.addEventListener('change', () => {
      state.userChangedFilters = true;
      state.sourceFilter = els.sourceFilter.value;
      state.listShown = LIST_PAGE;
      savePrefs();
      scheduleRender();
    });
    [els.photoOnly, els.nypdOnly].filter(Boolean).forEach(i => i.addEventListener('change', () => {
      state.userChangedFilters = true;
      state[i.id] = i.checked;
      savePrefs();
      scheduleRender();
    }));
    document.querySelectorAll('[data-cat]').forEach(i => i.addEventListener('change', () => {
      state.userChangedFilters = true;
      state.categories[i.dataset.cat] = i.checked;
      savePrefs();
      scheduleRender();
    }));
    els.searchInput?.addEventListener('input', () => {
      state.userChangedFilters = true;
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => {
        state.search = norm(els.searchInput.value);
        state.listShown = LIST_PAGE;
        scheduleRender();
      }, SEARCH_DEBOUNCE_MS);
    });
    els.sortSelect?.addEventListener('change', () => {
      state.userChangedFilters = true;
      state.sort = els.sortSelect.value;
      savePrefs();
      if (state.sort === 'near' && !state.userLocation) locateUser({ sortNear: true });
      else scheduleRender();
    });
    els.boroughs?.addEventListener('click', ev => {
      const b = ev.target.closest('[data-borough]');
      if (!b) return;
      state.userChangedFilters = true;
      state.borough = b.dataset.borough;
      els.boroughs.querySelectorAll('button').forEach(x => x.classList.toggle('active', x === b));
      savePrefs();
      scheduleRender();
    });
    els.dateChips?.addEventListener('click', ev => {
      const b = ev.target.closest('[data-date-mode]');
      if (!b) return;
      state.userChangedFilters = true;
      state.dateMode = b.dataset.dateMode;
      state.listShown = LIST_PAGE;
      buildDateChips();
      savePrefs();
      scheduleRender();
    });
    els.loadMoreBtn?.addEventListener('click', () => { state.listShown += LIST_PAGE; scheduleRender(); });
    els.resetFiltersBtn?.addEventListener('click', () => {
      Object.assign(state, publicDefaults(), { events: state.events, byId: state.byId, timings: state.timings, feedMeta: state.feedMeta });
      state.userChangedFilters = false;
      state.listShown = LIST_PAGE;
      setBanner('');
      if (els.searchInput) els.searchInput.value = '';
      syncUi();
      savePrefs();
      buildDateChips();
      scheduleRender();
    });
    els.retryFeedBtn?.addEventListener('click', () => bootFeeds());
    map.on('moveend', () => { if (!useCluster) scheduleRender(); });
  }

  function syncUi() {
    if (els.photoOnly) els.photoOnly.checked = state.photoOnly;
    if (els.nypdOnly) els.nypdOnly.checked = state.nypdOnly;
    if (els.sortSelect) els.sortSelect.value = state.sort;
    if (els.sourceFilter) els.sourceFilter.value = state.sourceFilter;
    document.querySelectorAll('[data-cat]').forEach(i => { i.checked = !!state.categories[i.dataset.cat]; });
    updateModeButtons();
  }

  async function bootFeeds() {
    const tBoot = performance.now();
    state.errors = [];
    status('Loading Major Events…');
    let majorIds = new Set();
    try {
      const major = await loadSchemaFeed(FEEDS.major, FEEDS.legacyMajor, 'approved_staged', 'major');
      major.events.forEach(e => {
        e.significance = 'major';
        e.nycif = { ...(e.nycif || {}), is_major: true, data_layer: 'approved_staged', assignment_feed: 'major' };
        majorIds.add(e.id);
      });
      state.byId.clear();
      upsertEvents(major.events, 'approved_staged');
      state.timings.timeToFirstMajorMs = Math.round(performance.now() - tBoot);
      const visible = render();
      if (visible.filter(e => e.mapReady).length) {
        map.fitBounds(visible.filter(e => e.mapReady).slice(0, 200).map(e => [e.lat, e.lng]), { padding: [44, 44], maxZoom: 12 });
      }
    } catch (err) {
      state.errors.push(String(err.message || err));
      setBanner(`Major feed failed: ${err.message}`);
      status(`Major feed failed: ${err.message}`);
    }

    status('Loading approved and review events in background…');
    try {
      const [approved, review] = await Promise.all([
        loadSchemaFeed(FEEDS.approved, FEEDS.legacyStaged, 'approved_staged', 'approved'),
        loadSchemaFeed(FEEDS.review, FEEDS.legacySupp, 'review_supplemental', 'review')
      ]);
      const majorBySeidDate = new Set();
      // Rebuild majorIds against approved events using source_event_id + date.
      // (IDs are stable as base@date from schema projection.)
      approved.events.forEach(e => {
        const key = `${e.source?.source_event_id || ''}|${e.nycif?.event_date || ''}`;
        if (majorIds.has(e.id)) majorBySeidDate.add(key);
      });
      // Also accept any event already flagged in major feed file.
      approved.events.forEach(e => {
        if (majorIds.has(e.id) || e.significance === 'major' || e.nycif?.is_major) {
          e.significance = 'major';
          e.nycif = { ...(e.nycif || {}), is_major: true, assignment_feed: 'major' };
        }
      });
      state.byId.clear();
      upsertEvents(approved.events, 'approved_staged');
      upsertEvents(review.events, 'review_supplemental');
      buildDateChips();
      scheduleRender();
      status(`Loaded ${state.events.length.toLocaleString()} schema-v1 records.`);
    } catch (err) {
      state.errors.push(String(err.message || err));
      setBanner(`All Events background load failed: ${err.message}`);
    }
  }

  async function boot() {
    if (!SCHEMA) {
      status('Schema helper missing; cannot boot unified viewer.');
      return;
    }
    loadPrefs();
    syncUi();
    bindUi();
    buildBoroughs();
    buildDateChips();
    if ('serviceWorker' in navigator) navigator.serviceWorker.register('./service-worker.js').catch(() => {});
    await bootFeeds();
    window.NYCIF_UNIFIED_VIEWER = {
      version: VERSION,
      getSummary: () => ({
        total: state.events.length,
        major: state.events.filter(e => e.isMajor && !e.isReview).length,
        approved: state.events.filter(e => !e.isReview).length,
        review: state.events.filter(e => e.isReview).length,
        mapReady: state.events.filter(e => e.mapReady).length,
        listOnly: state.events.filter(e => !e.mapReady).length,
        markerObjects: state.markerObjects,
        cluster: useCluster,
        timings: state.timings,
        feedMeta: state.feedMeta
      })
    };
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, { once: true });
  else boot();
})();
