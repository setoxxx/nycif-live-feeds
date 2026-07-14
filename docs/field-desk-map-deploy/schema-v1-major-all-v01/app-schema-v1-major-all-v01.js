(() => {
  const DISCOVERY = window.NYCIF_DISCOVERY_V02 || null;
  const VERSION = (DISCOVERY && DISCOVERY.version) || 'schema-v1-major-all-v01';
  const STORAGE_KEY = 'nycif-field-desk-state-v06-safe';
  const DEFAULT_VERSION = VERSION;
  const LIST_PAGE = 100;
  const VIEWPORT_BUFFER = 0.15;
  const MAJOR_MARKER_SOFT_CAP = 800;
  const ALL_MARKER_SOFT_CAP = 600;
  const SEARCH_DEBOUNCE_MS = 180;
  const NYC_CENTER = [40.7128, -74.006];
  const SCHEMA = window.NYCIF_EVENT_FEED_SCHEMA_V1;
  const FEED_ROOT = (DISCOVERY && DISCOVERY.feedRoot) || 'schema-v1';
  const localHost = location.hostname === 'localhost' || location.hostname === '127.0.0.1';
  const feedBranch = (() => {
    try {
      const raw = new URL(location.href).searchParams.get('feeds');
      if (!raw) return 'main';
      if (/^[A-Za-z0-9._/-]+$/.test(raw)) return raw;
      return 'main';
    } catch {
      return 'main';
    }
  })();
  const hasFeedOverride = (() => {
    try {
      return new URL(location.href).searchParams.has('feeds');
    } catch {
      return false;
    }
  })();
  const FEED_HOST = localHost && !hasFeedOverride
    ? ''
    : `https://raw.githubusercontent.com/setoxxx/nycif-live-feeds/${feedBranch}`;
  const pageUrl = (layer, cursor) => {
    const name = String(cursor || '').replace(/\.json$/i, '');
    return `${FEED_HOST}/data/${FEED_ROOT}/${layer}/pages/${name}.json`;
  };
  const FEEDS = {
    major: FEED_HOST + `/data/${FEED_ROOT}/major/events.json`,
    majorFallback: FEED_HOST + (
      DISCOVERY
        ? '/data/events_discovery_v02_major.json'
        : '/data/events_schema_v1_major.json'
    ),
    approvedManifest: FEED_HOST + `/data/${FEED_ROOT}/approved/manifest.json`,
    reviewManifest: FEED_HOST + `/data/${FEED_ROOT}/review/manifest.json`,
    approvedPage: cursor => pageUrl('approved', cursor),
    reviewPage: cursor => pageUrl('review', cursor)
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
    general: { emoji: '📍', label: 'General' },
    tours: { emoji: '🗺️', label: 'Tours / history' }
  };
  if (DISCOVERY && DISCOVERY.categoryMeta) {
    Object.keys(DISCOVERY.categoryMeta).forEach(key => {
      CATEGORY_META[key] = { ...(CATEGORY_META[key] || {}), ...DISCOVERY.categoryMeta[key] };
    });
  }
  const ALL_CATEGORY_KEYS = Object.keys(CATEGORY_META);
  const BOROUGHS = ['All', 'Manhattan', 'Brooklyn', 'Queens', 'Bronx', 'Staten Island'];
  const DAY_NAMES = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
  const debug = (() => {
    try { return new URL(location.href).searchParams.get('debugMap') === '1'; }
    catch { return false; }
  })();

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
    errors: [],
    markerObjects: 0,
    peakMarkerObjects: 0,
    indexComplete: false,
    pagesLoaded: { approved: 0, review: 0 },
    pagesTotal: { approved: 0, review: 0 },
    loadToken: 0,
    manifests: { approved: null, review: null }
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
    debugPanel: document.getElementById('debugPanel'),
    indexStatus: document.getElementById('indexStatus')
  };

  if (!els.map || !SCHEMA) {
    if (els.status) {
      els.status.textContent = 'Map boot failed: required map/schema elements are missing.';
    }
    return;
  }

  const map = L.map(els.map, { zoomControl: true, closePopupOnClick: false, tap: false }).setView(NYC_CENTER, 11);
  window.NYCIF_MAIN_MAP = map;

  let popupCentering = false;

  map.on('popupopen', event => {
    document.body.classList.add('nycif-popup-open');

    const source = event.popup && event.popup._source;
    if (!source || typeof source.getLatLng !== 'function') {
      return;
    }

    const selectedLocation = source.getLatLng();
    const currentCenter = map.getCenter();

    if (currentCenter.distanceTo(selectedLocation) < 1) {
      return;
    }

    popupCentering = true;

    map.once('moveend', () => {
      popupCentering = false;
    });

    map.panTo(selectedLocation, {
      animate: true,
      duration: 0.32,
      easeLinearity: 0.25
    });

    window.setTimeout(() => {
      popupCentering = false;
    }, 700);
  });

  map.on('popupclose', () => {
    document.body.classList.remove('nycif-popup-open');
  });
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; OpenStreetMap contributors',
    crossOrigin: true
  }).addTo(map);

  const clusterEnabled = (() => {
    try {
      return new URL(location.href).searchParams.get('clusters') === '1';
    } catch {
      return false;
    }
  })();
  const useCluster = clusterEnabled && typeof L.markerClusterGroup === 'function';
  const markers = useCluster
    ? L.markerClusterGroup({ showCoverageOnHover: false, maxClusterRadius: 55, spiderfyOnMaxZoom: true, disableClusteringAtZoom: 16 })
    : L.layerGroup();
  markers.addTo(map);
  let userMarker = null;
  let userAccuracy = null;
  let searchTimer = null;
  let renderTimer = null;
  let moveTimer = null;
  let swRegistered = false;

  const norm = v => String(v ?? '').toLowerCase().replace(/\s+/g, ' ').trim();
  const dateKey = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  const todayKey = () => dateKey(new Date());
  const addDays = (d, n) => { const x = new Date(d); x.setDate(x.getDate() + n); return x; };
  const dayRange = () => ({ today: todayKey(), end: dateKey(addDays(new Date(), 7)) });
  const status = t => { if (els.status) els.status.textContent = t; };
  const setBanner = t => {
    state.banner = t || '';
    if (!els.banner) {
      return;
    }
    els.banner.hidden = !state.banner;
    els.banner.textContent = state.banner;
  };
  const setIndexStatus = t => {
    if (!els.indexStatus) {
      return;
    }
    els.indexStatus.hidden = !t;
    els.indexStatus.textContent = t || '';
  };

  function eventDate(row) {
    const nycifDate = row?.nycif?.event_date;
    if (/^\d{4}-\d{2}-\d{2}$/.test(String(nycifDate || ''))) {
      return nycifDate;
    }
    const direct = String(row.date || '').slice(0, 10);
    if (/^\d{4}-\d{2}-\d{2}$/.test(direct)) {
      return direct;
    }
    const start = String(row.start_date_time || '');
    if (/^\d{4}-\d{2}-\d{2}/.test(start)) {
      return start.slice(0, 10);
    }
    return '';
  }

  function toUiEvent(schemaEvent) {
    const nycif = schemaEvent.nycif || {};
    const catKey = CATEGORY_META[schemaEvent.category] ? schemaEvent.category : 'general';
    const mapReady = nycif.coordinate_status === 'map_ready'
      && Number.isFinite(schemaEvent.latitude)
      && Number.isFinite(schemaEvent.longitude);
    const review = (nycif.data_layer || '') === 'review_supplemental';
    const title = schemaEvent.title || 'Untitled event';
    const location = schemaEvent.location || '';
    const borough = schemaEvent.borough || '';
    const interests = Array.isArray(schemaEvent.interests)
      ? schemaEvent.interests.map(v => String(v || '')).filter(Boolean)
      : [];
    const tags = Array.isArray(schemaEvent.tags)
      ? schemaEvent.tags.map(v => String(v || '')).filter(Boolean)
      : [];
    const e = {
      ...schemaEvent,
      lat: schemaEvent.latitude,
      lng: schemaEvent.longitude,
      dateKey: eventDate(schemaEvent),
      categoryKey: catKey,
      categoryMeta: CATEGORY_META[catKey],
      interests,
      tags,
      event_role: schemaEvent.event_role || 'public_event',
      parent_event_id: schemaEvent.parent_event_id || null,
      mapReady,
      isReview: review,
      isMajor: schemaEvent.significance === 'major' || !!nycif.is_major,
      photoPick: !!nycif.photo_pick,
      verification_status: nycif.verification_status,
      major_reason: nycif.major_reason,
      major_score: nycif.major_score || 0,
      searchText: norm([
        title,
        location,
        borough,
        catKey,
        interests.join(' '),
        tags.join(' '),
        schemaEvent.source?.dataset,
        schemaEvent.source?.source_event_id,
        nycif.event_type,
        nycif.major_reason,
        schemaEvent.event_role
      ].filter(Boolean).join(' ')),
      marker: null
    };
    e.priority = Number(e.major_score || 0) + (e.isMajor ? 500 : 0) + (e.photoPick ? 120 : 0);
    if (e.verification_status === 'nypd_field_intel') {
      e.priority += 800;
    }
    return e;
  }

  function categoryFilterMatch(e) {
    if (state.categories[e.categoryKey]) {
      return true;
    }
    if (!DISCOVERY) {
      return false;
    }
    return (e.interests || []).some(interest => !!state.categories[interest]);
  }

  function markerEligible(e) {
    if (!e.mapReady) {
      return false;
    }
    if (!DISCOVERY) {
      return true;
    }
    if (e.event_role !== 'public_event') {
      return false;
    }
    if (e.parent_event_id) {
      return false;
    }
    const disposition = e.nycif && e.nycif.display_disposition;
    if (disposition && disposition !== 'standalone_public_event') {
      return false;
    }
    return true;
  }

  function upsertEvents(schemaEvents) {
    for (const raw of schemaEvents) {
      const e = toUiEvent(raw);
      if (!e.id) {
        continue;
      }
      const existing = state.byId.get(e.id);
      if (existing?.marker) {
        e.marker = existing.marker;
      }
      if (existing?.isMajor && !e.isMajor) {
        e.isMajor = true;
        e.significance = 'major';
      }
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
    if (!res.ok) {
      throw new Error(`${label} unavailable (${res.status})`);
    }
    const t1 = performance.now();
    const json = await res.json();
    state.timings[label] = {
      fetchMs: Math.round(fetchMs),
      parseMs: Math.round(performance.now() - t1),
      url,
      status: res.status
    };
    return json;
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
    } catch {
      return false;
    }
  }

  function loadPrefs() {
    try {
      if (forceReset()) {
        localStorage.removeItem(STORAGE_KEY);
      }
      const parsed = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');
      const defaults = publicDefaults();
      const migrate = forceReset() || parsed.nycifDefaultVersion !== DEFAULT_VERSION;
      const use = migrate ? defaults : {
        ...defaults,
        ...parsed,
        categories: { ...defaults.categories, ...(parsed.categories || {}) },
        viewMode: parsed.viewMode === 'all' ? 'all' : 'major'
      };
      if (use.categories.parade != null && use.categories.civic == null) {
        use.categories.civic = !!use.categories.parade;
      }
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

  function dateMatches(e) {
    if (!e.dateKey) {
      return false;
    }
    const { today, end } = dayRange();
    if (state.dateMode === 'next7') {
      return e.dateKey >= today && e.dateKey <= end;
    }
    if (state.dateMode === 'all') {
      return e.dateKey >= today;
    }
    if (state.dateMode === 'today') {
      return e.dateKey === today;
    }
    if (/^\d{4}-\d{2}-\d{2}$/.test(state.dateMode)) {
      return e.dateKey === state.dateMode;
    }
    return e.dateKey >= today;
  }

  function sourceMatches(e) {
    if (state.viewMode === 'major') {
      return e.isMajor && !e.isReview;
    }
    if (state.sourceFilter === 'approved') {
      return !e.isReview;
    }
    if (state.sourceFilter === 'review') {
      return e.isReview;
    }
    return true;
  }

  function eventMatches(e) {
    return sourceMatches(e)
      && dateMatches(e)
      && categoryFilterMatch(e)
      && (!state.photoOnly || e.photoPick)
      && (!state.nypdOnly || e.verification_status === 'nypd_field_intel')
      && (state.borough === 'all' || e.borough === state.borough)
      && (!state.search || e.searchText.includes(state.search));
  }

  function milesBetween(a, b) {
    if (!a || !b || !Number.isFinite(b.lat) || !Number.isFinite(b.lng)) {
      return null;
    }
    const R = 3958.8;
    const toRad = x => x * Math.PI / 180;
    const dLat = toRad(b.lat - a.lat);
    const dLng = toRad(b.lng - a.lng);
    const lat1 = toRad(a.lat);
    const lat2 = toRad(b.lat);
    const x = Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLng / 2) ** 2;
    return 2 * R * Math.asin(Math.sqrt(x));
  }

  function sortEvents(a, b) {
    if (state.sort === 'near') {
      const da = milesBetween(state.userLocation, a) ?? 999999;
      const db = milesBetween(state.userLocation, b) ?? 999999;
      return da - db || b.priority - a.priority;
    }
    if (state.sort === 'borough') {
      return (a.borough || 'zz').localeCompare(b.borough || 'zz') || b.priority - a.priority;
    }
    if (state.sort === 'type') {
      return String(a.nycif?.event_type || 'zz').localeCompare(String(b.nycif?.event_type || 'zz')) || b.priority - a.priority;
    }
    if (state.sort === 'time') {
      return (a.dateKey || '9999').localeCompare(b.dateKey || '9999') || b.priority - a.priority;
    }
    return b.priority - a.priority || (a.dateKey || '').localeCompare(b.dateKey || '');
  }

  function mapsUrl(kind, e) {
    if (!e.mapReady) {
      return null;
    }
    if (kind === 'apple') {
      return `https://maps.apple.com/?daddr=${e.lat},${e.lng}&q=${encodeURIComponent(e.title)}`;
    }
    return `https://www.google.com/maps/dir/?api=1&destination=${e.lat},${e.lng}&travelmode=driving`;
  }

  function clearChildren(node) {
    while (node.firstChild) node.firstChild.remove();
  }

  function appendText(parent, tag, text, className) {
    const el = document.createElement(tag);
    if (className) {
      el.className = className;
    }
    el.textContent = text == null ? '' : String(text);
    parent.appendChild(el);
    return el;
  }

  function appendSafeLink(parent, href, label, className) {
    const safe = SCHEMA.safeExternalUrl(href);
    if (!safe) {
      return null;
    }
    const a = document.createElement('a');
    a.href = safe;
    a.target = '_blank';
    a.rel = 'noopener noreferrer';
    if (className) {
      a.className = className;
    }
    a.textContent = label;
    parent.appendChild(a);
    return a;
  }

  function eventSourceLabel(e) {
    if (e.isReview) {
      return 'Expanded review (not production-approved)';
    }
    if (e.isMajor) {
      return 'Major events';
    }
    return 'Approved / staged';
  }

  function reviewTagClass(isReview) {
    return isReview ? 'item-tag nycif-source-review' : 'item-tag';
  }

  function formatDistanceLabel(dist) {
    if (dist < 0.1) {
      return 'nearby';
    }
    const digits = dist < 10 ? 1 : 0;
    return `${dist.toFixed(digits)} mi`;
  }

  function viewModeNoun() {
    return state.viewMode === 'major' ? 'major' : 'events';
  }

  function dateModeLabel() {
    return state.dateMode === 'next7' ? 'next 7 days' : state.dateMode;
  }

  function viewModeTitle() {
    return state.viewMode === 'major' ? 'Major' : 'All';
  }

  function listOnlySuffix(count) {
    if (!count) {
      return '';
    }
    return ` · ${count.toLocaleString()} list-only`;
  }

  function popupRoot(e) {
    const root = document.createElement('article');
    root.className = 'popup-card';

    const cat = appendText(root, 'div', '', 'popup-category');
    appendText(cat, 'span', e.categoryMeta.emoji);
    cat.appendChild(document.createTextNode(` ${e.categoryMeta.label}`));
    appendText(root, 'h2', e.title);
    const dl = document.createElement('dl');
    const addRow = (dt, dd) => {
      if (!dd) {
        return;
      }
      const wrap = document.createElement('div');
      appendText(wrap, 'dt', dt);
      appendText(wrap, 'dd', dd);
      dl.appendChild(wrap);
    };
    const displayDate = /^\d{4}-\d{2}-\d{2}$/.test(String(e.dateKey || ''))
      ? `${e.dateKey.slice(5, 7)}/${e.dateKey.slice(8, 10)}/${e.dateKey.slice(2, 4)}`
      : (e.dateKey || 'Date unavailable');
    addRow('Date', displayDate);
    addRow('Borough', e.borough);
    addRow('Location', e.location);
    root.appendChild(dl);
    if (e.mapReady) {
      const actions = document.createElement('div');
      actions.className = 'field-actions';
      appendSafeLink(actions, mapsUrl('apple', e), 'Apple Maps', 'field-action');
      appendSafeLink(actions, mapsUrl('google', e), 'Google Maps', 'field-action');
      root.appendChild(actions);
    } else {
      appendText(root, 'div', 'LIST ONLY — coordinates pending', 'popup-photo');
    }
    return root;
  }

  function makeMarker(e) {
    const cls = ['marker', `marker--${e.categoryKey}`];
    if (e.photoPick) {
      cls.push('marker--photo');
    }
    if (e.isMajor) {
      cls.push('marker--major');
    }
    const marker = L.marker([e.lat, e.lng], {
      icon: L.divIcon({
        className: 'marker-shell',
        html: `<span class="${cls.join(' ')}"><span class="emoji"></span></span>`,
        iconSize: [38, 38],
        iconAnchor: [19, 19],
        popupAnchor: [0, -24]
      }),
      title: e.title,
      riseOnHover: true
    });
    // Set emoji via textContent after icon create for trusted static shell only.
    marker.on('add', () => {
      const emoji = marker.getElement()?.querySelector('.emoji');
      if (emoji) {
        emoji.textContent = e.categoryMeta.emoji;
      }
    });
    marker.bindPopup(popupRoot(e), {
      maxWidth: 360,
      minWidth: 300,
      autoPan: false,
      autoPanPadding: [28, 28],
      closeButton: true,
      autoClose: true,
      closeOnClick: true,
      className: 'nycif-event-popup'
    });
    return marker;
  }

  function ensureMarker(e) {
    if (!markerEligible(e)) {
      return null;
    }
    if (!e.marker) {
      e.marker = makeMarker(e);
    }
    return e.marker;
  }

  function expandedBounds() {
    const bounds = map.getBounds();
    if (!bounds) {
      return null;
    }
    const padLat = (bounds.getNorth() - bounds.getSouth()) * VIEWPORT_BUFFER;
    const padLng = (bounds.getEast() - bounds.getWest()) * VIEWPORT_BUFFER;
    return L.latLngBounds(
      [bounds.getSouth() - padLat, bounds.getWest() - padLng],
      [bounds.getNorth() + padLat, bounds.getEast() + padLng]
    );
  }

  function renderMarkers(visible) {
    const t0 = performance.now();
    if (markers.clearLayers) {
      markers.clearLayers();
    }
    const mapReady = visible.filter(e => markerEligible(e));
    let candidates;
    if (state.viewMode === 'major') {
      candidates = mapReady.slice(0, MAJOR_MARKER_SOFT_CAP);
    } else {
      const bounds = expandedBounds();
      const inView = bounds ? mapReady.filter(e => bounds.contains([e.lat, e.lng])) : mapReady;
      candidates = (inView.length ? inView : mapReady).slice(0, ALL_MARKER_SOFT_CAP);
    }
    const batch = [];
    for (const e of candidates) {
      const marker = ensureMarker(e);
      if (marker) {
        batch.push(marker);
      }
    }
    if (useCluster && markers.addLayers) {
      markers.addLayers(batch);
    }
    else batch.forEach(marker => markers.addLayer(marker));
    state.markerObjects = batch.length;
    state.peakMarkerObjects = Math.max(state.peakMarkerObjects, batch.length);
    state.timings.markerUpdateMs = Math.round(performance.now() - t0);
    return batch;
  }

  function buildListCard(e) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'event-item';
    button.dataset.id = e.id;

    const top = document.createElement('span');
    top.className = 'item-top';
    appendText(top, 'span', `${e.categoryMeta.emoji} ${e.categoryMeta.label}`, 'item-source');
    const tags = document.createElement('span');
    tags.className = 'item-tags';
    appendText(tags, 'span', e.isReview ? 'REVIEW' : 'LIVE', reviewTagClass(e.isReview));
    if (!e.mapReady) {
      appendText(tags, 'span', 'LIST ONLY', 'item-tag nycif-list-only');
    }
    if (e.isMajor) {
      appendText(tags, 'span', 'MAJOR', 'item-tag');
    }
    const dist = milesBetween(state.userLocation, e);
    if (Number.isFinite(dist)) {
      appendText(tags, 'span', formatDistanceLabel(dist), 'item-tag near');
    }
    top.appendChild(tags);
    button.appendChild(top);
    appendText(button, 'strong', e.title);
    appendText(button, 'span', e.dateKey || 'Date unavailable');
    appendText(button, 'small', [e.borough, e.location, e.nycif?.event_type].filter(Boolean).join(' • '));
    if (e.mapReady) {
      const actions = document.createElement('span');
      actions.className = 'quick-actions';
      appendSafeLink(actions, mapsUrl('apple', e), 'Directions');
      button.appendChild(actions);
    }
    button.addEventListener('click', ev => {
      if (ev.target.closest('a')) {
        return;
      }
      focusEvent(e.id);
    });
    return button;
  }

  function countForMode(mode) {
    const { today, end } = dayRange();
    return state.events.filter(e => {
      if (!e.dateKey || e.dateKey < today || e.dateKey > end) {
        return false;
      }
      if (mode === 'major') {
        return e.isMajor && !e.isReview;
      }
      return true;
    }).length;
  }

  function updateModeButtons() {
    if (els.modeMajor) {
      els.modeMajor.textContent = `Major Events (${countForMode('major').toLocaleString()})`;
      els.modeMajor.classList.toggle('active', state.viewMode === 'major');
      els.modeMajor.setAttribute('aria-pressed', String(state.viewMode === 'major'));
    }
    if (els.modeAll) {
      els.modeAll.textContent = `All Events (${countForMode('all').toLocaleString()})`;
      els.modeAll.classList.toggle('active', state.viewMode === 'all');
      els.modeAll.setAttribute('aria-pressed', String(state.viewMode === 'all'));
    }
    if (els.sourceFilter) {
      els.sourceFilter.hidden = state.viewMode !== 'all';
    }
  }

  function applyZeroMajorFallback(visible) {
    if (state.viewMode !== 'major' || state.userChangedFilters || visible.length) {
      return visible;
    }
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

  function updateIndexLabel() {
    if (state.indexComplete) {
      setIndexStatus('Full event index loaded');
      return;
    }
    setIndexStatus('Indexing more events…');
  }

  function render() {
    const t0 = performance.now();
    updateModeButtons();
    updateIndexLabel();
    let visible = state.events.filter(eventMatches).sort(sortEvents);
    visible = applyZeroMajorFallback(visible);
    const drawn = renderMarkers(visible);
    const shown = Math.min(state.listShown, visible.length);
    const listOnly = visible.filter(e => !e.mapReady).length;
    let indexNote = state.indexComplete ? 'full index loaded' : 'index still loading pages';
    els.listMeta.textContent = `${state.events.length.toLocaleString()} loaded · ${visible.length.toLocaleString()} match filters · ${drawn.length.toLocaleString()} markers in view · showing ${shown.toLocaleString()} of ${visible.length.toLocaleString()} list results · ${indexNote}${listOnlySuffix(listOnly)}`;
    clearChildren(els.eventList);
    if (!visible.length) {
      appendText(els.eventList, 'div', 'No events match this view. Try Show All Events or Reset Filters.', 'empty');
    } else {
      visible.slice(0, shown).forEach(e => els.eventList.appendChild(buildListCard(e)));
    }
    if (els.loadMoreBtn) {
      els.loadMoreBtn.hidden = shown >= visible.length;
      els.loadMoreBtn.textContent = `Load 100 more (${Math.max(0, visible.length - shown).toLocaleString()} remaining)`;
    }
    if (els.brandCount) {
      els.brandCount.textContent = `${visible.length.toLocaleString()} ${viewModeNoun()} · ${dateModeLabel()}`;
    }
    status(`${viewModeTitle()} · ${visible.length.toLocaleString()} match · ${drawn.length.toLocaleString()} markers · v${VERSION}`);
    state.timings.listRenderMs = Math.round(performance.now() - t0);
    if (debug && els.debugPanel) {
      els.debugPanel.hidden = false;
      els.debugPanel.textContent = JSON.stringify({
        version: VERSION,
        viewMode: state.viewMode,
        total: state.events.length,
        filtered: visible.length,
        markers: drawn.length,
        peakMarkerObjects: state.peakMarkerObjects,
        indexComplete: state.indexComplete,
        pagesLoaded: state.pagesLoaded,
        pagesTotal: state.pagesTotal,
        cluster: useCluster,
        timings: state.timings,
        errors: state.errors.slice(-8)
      }, null, 2);
    }
    return visible;
  }

  function scheduleRender() {
    clearTimeout(renderTimer);
    renderTimer = setTimeout(() => render(), 40);
  }

  function focusEvent(id) {
    const e = state.byId.get(id);
    if (!e) {
      return;
    }
    if (!e.mapReady) {
      status(`${e.title}: coordinate pending; list-only record.`);
      setDesk(true);
      return;
    }
    const marker = ensureMarker(e);
    if (marker && !markers.hasLayer(marker)) {
      markers.addLayer(marker);
    }
    map.flyTo([e.lat, e.lng], Math.max(map.getZoom(), 15), { duration: 0.55 });
    setTimeout(() => marker?.openPopup(), 420);
    setDesk(false);
  }

  function setLayers(open) {
    if (!els.layersPanel || !els.layersBtn) {
      return;
    }
    els.layersPanel.hidden = !open;
    els.layersBtn.setAttribute('aria-expanded', String(open));
    setTimeout(() => map.invalidateSize(), 100);
  }

  function setDesk(open) {
    if (!els.deskDrawer || !els.deskBtn) {
      return;
    }
    els.deskDrawer.hidden = !open;
    els.deskBtn.setAttribute('aria-expanded', String(open));
    setTimeout(() => map.invalidateSize(), 100);
  }

  function setActiveBoroughButton(activeButton) {
    if (!els.boroughs) {
      return;
    }
    els.boroughs.querySelectorAll('button').forEach(btn => {
      btn.classList.toggle('active', btn === activeButton);
    });
  }

  function onBoroughSelected(value, button) {
    state.userChangedFilters = true;
    state.borough = value;
    setActiveBoroughButton(button);
    savePrefs();
    scheduleRender();
  }

  function buildBoroughs() {
    if (!els.boroughs) {
      return;
    }
    clearChildren(els.boroughs);
    BOROUGHS.forEach(b => {
      const value = b === 'All' ? 'all' : b;
      const button = document.createElement('button');
      button.type = 'button';
      button.dataset.borough = value;
      button.textContent = b;
      if (state.borough === value) {
        button.classList.add('active');
      }
      button.addEventListener('click', () => onBoroughSelected(value, button));
      els.boroughs.appendChild(button);
    });
  }

  function onDateChipSelected(mode) {
    state.userChangedFilters = true;
    state.dateMode = mode;
    state.listShown = LIST_PAGE;
    savePrefs();
    buildDateChips();
    scheduleRender();
    loadPagesForCurrentWindow(state.loadToken);
  }

  function appendDateChip(track, mode, label) {
    const button = document.createElement('button');
    button.type = 'button';
    button.dataset.dateMode = mode;
    button.textContent = label;
    if (state.dateMode === mode) {
      button.classList.add('active');
    }
    button.addEventListener('click', () => onDateChipSelected(mode));
    track.appendChild(button);
  }

  function buildDateChips() {
    if (!els.dateChips) {
      return;
    }
    clearChildren(els.dateChips);
    const track = document.createElement('div');
    track.className = 'date-chip-track';
    const { today, end } = dayRange();
    const pool = state.events.filter(e => {
      if (state.viewMode === 'major') {
        return e.isMajor && !e.isReview;
      }
      if (state.sourceFilter === 'approved') {
        return !e.isReview;
      }
      if (state.sourceFilter === 'review') {
        return e.isReview;
      }
      return true;
    });
    const counts = {
      next7: pool.filter(e => e.dateKey && e.dateKey >= today && e.dateKey <= end).length,
      all: pool.filter(e => e.dateKey && e.dateKey >= today).length
    };
    const addChip = (mode, label) => appendDateChip(track, mode, label);
    addChip('next7', `Next 7 days (${counts.next7.toLocaleString()})`);
    for (let i = 0; i < 8; i += 1) {
      const d = addDays(new Date(), i);
      const key = dateKey(d);
      const n = pool.filter(e => e.dateKey === key).length;
      const label = i === 0 ? `Today (${n})` : `${DAY_NAMES[d.getDay()]} ${d.getMonth() + 1}/${d.getDate()} (${n})`;
      addChip(key, label);
    }
    addChip('all', `All upcoming (${counts.all.toLocaleString()})`);
    els.dateChips.appendChild(track);
  }

  function setUserLocation(lat, lng, accuracy) {
    const here = [lat, lng];
    state.userLocation = { lat, lng };
    if (userMarker) {
      userMarker.setLatLng(here);
    }
    else {
      userMarker = L.marker(here, {
        icon: L.divIcon({ className: 'user-location-shell', html: '<span class="user-location"></span>', iconSize: [36, 44], iconAnchor: [18, 42] }),
        zIndexOffset: 4000
      }).addTo(map);
      const shell = userMarker.getElement()?.querySelector('.user-location');
      if (shell) {
        shell.textContent = '🗽';
      }
      userMarker.bindPopup('Location updated');
    }
    if (userAccuracy) {
      userAccuracy.setLatLng(here);
      userAccuracy.setRadius(accuracy || 0);
    } else {
      userAccuracy = L.circle(here, { radius: accuracy || 0, color: '#d40000', weight: 2, fillColor: '#d40000', fillOpacity: 0.08 }).addTo(map);
    }
  }

  function locateUser(options = {}) {
    if (!navigator.geolocation) {
      status('Location is not available in this browser.');
      return;
    }
    status('Finding your location…');
    navigator.geolocation.getCurrentPosition(pos => {
      const { latitude, longitude, accuracy } = pos.coords;
      setUserLocation(latitude, longitude, accuracy);
      if (options.sortNear) {
        state.sort = 'near';
        if (els.sortSelect) {
          els.sortSelect.value = 'near';
        }
        savePrefs();
      }
      map.flyTo([latitude, longitude], Math.max(map.getZoom(), 14), { duration: 0.6 });
      userMarker?.openPopup();
      scheduleRender();
    }, () => status('Location failed.'), { enableHighAccuracy: true, timeout: 12000, maximumAge: 15000 });
  }

  function pageOverlapsWindow(page, today, end) {
    if (!page.earliest_date || !page.latest_date) {
      return true;
    }
    if (state.dateMode === 'all') {
      return page.latest_date >= today;
    }
    if (state.dateMode === 'today') {
      return page.earliest_date <= today && page.latest_date >= today;
    }
    if (/^\d{4}-\d{2}-\d{2}$/.test(state.dateMode)) {
      return page.earliest_date <= state.dateMode && page.latest_date >= state.dateMode;
    }
    return page.latest_date >= today && page.earliest_date <= end;
  }

  async function loadLayerPages(layer, manifest, token, prioritizeWindow) {
    if (!manifest?.pages?.length) {
      return;
    }
    state.pagesTotal[layer] = manifest.page_count || manifest.pages.length;
    const { today, end } = dayRange();
    const ordered = [...manifest.pages].sort((a, b) => {
      const aHit = pageOverlapsWindow(a, today, end) ? 0 : 1;
      const bHit = pageOverlapsWindow(b, today, end) ? 0 : 1;
      return aHit - bHit;
    });
    const urlFor = layer === 'approved' ? FEEDS.approvedPage : FEEDS.reviewPage;
    for (const page of ordered) {
      if (token !== state.loadToken) {
        return;
      }
      if (prioritizeWindow && !pageOverlapsWindow(page, today, end) && state.dateMode !== 'all') {
        // still load later for full search index
      }
      try {
        const json = await fetchJson(urlFor(page.cursor || page.page.replace('.json', '')), `${layer}-${page.page}`);
        if (token !== state.loadToken) {
          return;
        }
        const envelope = SCHEMA.projectEnvelope(json, layer === 'review' ? 'review_supplemental' : 'approved_staged', json.generated_at_utc);
        upsertEvents(envelope.events);
        state.pagesLoaded[layer] += 1;
        updateIndexLabel();
        scheduleRender();
      } catch (err) {
        state.errors.push(String(err.message || err));
      }
    }
  }

  async function loadPagesForCurrentWindow(token) {
    const needReview = state.viewMode === 'all' && (state.sourceFilter === 'all' || state.sourceFilter === 'review');
    const needApproved = state.viewMode === 'all' || true; // approved pages also enrich major flags/search
    if (needApproved && state.manifests.approved) {
      await loadLayerPages('approved', state.manifests.approved, token, true);
    }
    if (needReview && state.manifests.review) {
      await loadLayerPages('review', state.manifests.review, token, true);
    }
    if (token === state.loadToken) {
      state.indexComplete = state.pagesLoaded.approved >= (state.pagesTotal.approved || 0)
        && (
          !(state.viewMode === 'all' && (state.sourceFilter === 'all' || state.sourceFilter === 'review'))
          || state.pagesLoaded.review >= (state.pagesTotal.review || 0)
        );
      // Once approved fully loaded, search is globally complete for approved/major.
      if (state.pagesLoaded.approved >= (state.pagesTotal.approved || 0) && state.pagesLoaded.review >= (state.pagesTotal.review || 0)) {
        state.indexComplete = true;
      }
      updateIndexLabel();
      scheduleRender();
    }
  }

  async function bootFeeds() {
    const token = ++state.loadToken;
    state.errors = [];
    state.pagesLoaded = { approved: 0, review: 0 };
    state.indexComplete = false;
    status('Loading Major Events…');
    try {
      let majorJson;
      try {
        majorJson = await fetchJson(FEEDS.major, 'major');
      } catch {
        majorJson = await fetchJson(FEEDS.majorFallback, 'major-fallback');
        state.fallbackUsed = true;
      }
      if (token !== state.loadToken) {
        return;
      }
      const major = SCHEMA.projectEnvelope(majorJson, 'approved_staged', majorJson.generated_at_utc);
      major.events.forEach(e => {
        e.significance = 'major';
        e.nycif = { ...(e.nycif || {}), is_major: true, data_layer: 'approved_staged' };
      });
      state.byId.clear();
      upsertEvents(major.events);
      state.timings.timeToFirstMajorMs = state.timings.major?.fetchMs || 0;
      const visible = render();
      const mapReady = visible.filter(e => e.mapReady);
      if (mapReady.length) {
        map.fitBounds(mapReady.slice(0, 200).map(e => [e.lat, e.lng]), { padding: [44, 44], maxZoom: 12 });
      }
    } catch (err) {
      state.errors.push(String(err.message || err));
      setBanner('Major feed unavailable. Use Retry Feed or open All Events after recovery.');
      status('Major feed unavailable.');
    }

    try {
      status('Loading approved and review page manifests…');
      const [approvedManifest, reviewManifest] = await Promise.all([
        fetchJson(FEEDS.approvedManifest, 'approved-manifest'),
        fetchJson(FEEDS.reviewManifest, 'review-manifest')
      ]);
      if (token !== state.loadToken) {
        return;
      }
      state.manifests.approved = approvedManifest;
      state.manifests.review = reviewManifest;
      state.pagesTotal.approved = approvedManifest.page_count || approvedManifest.pages?.length || 0;
      state.pagesTotal.review = reviewManifest.page_count || reviewManifest.pages?.length || 0;
      await loadPagesForCurrentWindow(token);
    } catch (err) {
      state.errors.push(String(err.message || err));
      setBanner('Page manifests unavailable. Major Events may still work. All Events search may be incomplete.');
      state.indexComplete = false;
      updateIndexLabel();
    }
  }

  function syncUi() {
    if (els.photoOnly) {
      els.photoOnly.checked = state.photoOnly;
    }
    if (els.nypdOnly) {
      els.nypdOnly.checked = state.nypdOnly;
    }
    if (els.sortSelect) {
      els.sortSelect.value = state.sort;
    }
    if (els.sourceFilter) {
      els.sourceFilter.value = state.sourceFilter;
    }
    document.querySelectorAll('[data-cat]').forEach(input => {
      input.checked = !!state.categories[input.dataset.cat];
    });
    updateModeButtons();
  }

  function onToggleFilterChange(input) {
    state.userChangedFilters = true;
    state[input.id] = input.checked;
    savePrefs();
    scheduleRender();
  }

  function onCategoryFilterChange(input) {
    state.userChangedFilters = true;
    state.categories[input.dataset.cat] = input.checked;
    savePrefs();
    scheduleRender();
  }

  function onSearchInput() {
    state.userChangedFilters = true;
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      state.search = norm(els.searchInput.value);
      state.listShown = LIST_PAGE;
      scheduleRender();
    }, SEARCH_DEBOUNCE_MS);
  }

  function onSortSelectChange() {
    state.userChangedFilters = true;
    state.sort = els.sortSelect.value;
    savePrefs();
    if (state.sort === 'near' && !state.userLocation) {
      locateUser({ sortNear: true });
    }
    else {
      scheduleRender();
    }
  }

  function onMapMoveEnd() {
    if (popupCentering) {
      return;
    }

    clearTimeout(moveTimer);
    moveTimer = setTimeout(() => {
      if (state.viewMode === 'all') {
        scheduleRender();
      }
    }, 120);
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
      loadPagesForCurrentWindow(state.loadToken);
    });
    els.sourceFilter?.addEventListener('change', () => {
      state.userChangedFilters = true;
      state.sourceFilter = els.sourceFilter.value;
      state.listShown = LIST_PAGE;
      savePrefs();
      scheduleRender();
      loadPagesForCurrentWindow(state.loadToken);
    });
    [els.photoOnly, els.nypdOnly].filter(Boolean).forEach(input => {
      input.addEventListener('change', () => onToggleFilterChange(input));
    });
    document.querySelectorAll('[data-cat]').forEach(input => {
      input.addEventListener('change', () => onCategoryFilterChange(input));
    });
    els.searchInput?.addEventListener('input', onSearchInput);
    els.sortSelect?.addEventListener('change', onSortSelectChange);
    els.loadMoreBtn?.addEventListener('click', () => {
      state.listShown += LIST_PAGE;
      scheduleRender();
    });
    els.resetFiltersBtn?.addEventListener('click', () => {
      const keepEvents = state.events;
      const keepById = state.byId;
      const keepMeta = { timings: state.timings, manifests: state.manifests, pagesLoaded: state.pagesLoaded, pagesTotal: state.pagesTotal, indexComplete: state.indexComplete };
      Object.assign(state, publicDefaults(), keepMeta, { events: keepEvents, byId: keepById, listShown: LIST_PAGE, userChangedFilters: false, search: '' });
      setBanner('');
      if (els.searchInput) {
        els.searchInput.value = '';
      }
      syncUi();
      savePrefs();
      buildDateChips();
      scheduleRender();
    });
    els.retryFeedBtn?.addEventListener('click', () => bootFeeds());
    map.on('moveend', onMapMoveEnd);
  }

  async function boot() {
    loadPrefs();
    syncUi();
    bindUi();
    buildBoroughs();
    buildDateChips();
    if ('serviceWorker' in navigator && !swRegistered) {
      swRegistered = true;
      navigator.serviceWorker.register('./service-worker.js').catch(() => { /* optional */ });
    }
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
        peakMarkerObjects: state.peakMarkerObjects,
        cluster: useCluster,
        indexComplete: state.indexComplete,
        pagesLoaded: state.pagesLoaded,
        pagesTotal: state.pagesTotal,
        fullDumpDownloaded: false,
        timings: state.timings
      })
    };
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot, { once: true });
  }
  else boot();
})();
