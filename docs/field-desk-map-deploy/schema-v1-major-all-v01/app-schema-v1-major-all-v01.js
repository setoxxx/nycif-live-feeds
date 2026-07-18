(() => {
  const DISCOVERY = window.NYCIF_DISCOVERY_V02 || null;
  const VERSION = (DISCOVERY && DISCOVERY.version) || 'schema-v1-major-all-v01';
  const STORAGE_KEY = 'nycif-field-desk-state-v06-safe';
  const DEFAULT_VERSION = VERSION;
  const LIST_PAGE = 100;
  const VIEWPORT_BUFFER = 0.15;
  const MARKER_SOFT_CAP = 600;
  const SEARCH_DEBOUNCE_MS = 180;
  const DAY_WINDOW = 7; // today plus seven more calendar days = eight choices
  const NYC_CENTER = [40.7128, -74.006];
  const SCHEMA = window.NYCIF_EVENT_FEED_SCHEMA_V1;
  const FEED_ROOT = (DISCOVERY && DISCOVERY.feedRoot) || 'schema-v1';
  const BUG_REPORT_EMAIL = 'howard@nycinfocus.com';
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
    // Primary: current live discovery feed used by the authoritative runtime.
    major: FEED_HOST + `/data/${FEED_ROOT}/major/events.json`,
    // Fallback: full current/future feed at the same authorized ref.
    majorFallback: FEED_HOST + (
      DISCOVERY
        ? '/data/events_discovery_v02_major.json'
        : '/data/events_schema_v1_major.json'
    ),
    // Emergency: major-only feed maintained on the backend main branch.
    majorEmergency: 'https://raw.githubusercontent.com/setoxxx/nycif-live-feeds/main/nycif_major_radar_map_events.json',
    approvedManifest: FEED_HOST + `/data/${FEED_ROOT}/approved/manifest.json`,
    approvedPage: cursor => pageUrl('approved', cursor),
    reviewManifest: FEED_HOST + `/data/${FEED_ROOT}/review/manifest.json`,
    reviewPage: cursor => pageUrl('review', cursor)
  };
  // News Desk operator lanes (money shots + viral magnets), same feed ref.
  const NEWS_DESK_DATA = {
    money: FEED_HOST + '/data/photographer_assignment_calendar_2mo.json',
    viral: FEED_HOST + '/data/photographer_viral_recurrence_matches.json'
  };
  // Editor's Picks / medal engine (pure module). Falls back to inert stubs if
  // the script is missing, so the map never breaks over the ranking layer.
  const ED = window.NYCIF_EDITORIAL || {
    editorialScore: () => 0, medalOf: () => '', sourceKey: () => '',
    extractReturningKeys: () => new Set(), extractNewsDeskRows: () => [],
    MEDAL_META: {}
  };
  const CATEGORY_META = {
    sports: { emoji: '🏟️', label: 'Sports' },
    fitness: { emoji: '💪', label: 'Fitness / wellness' },
    parks: { emoji: '🌳', label: 'Parks / recreation' },
    arts: { emoji: '🎭', label: 'Arts / culture' },
    market: { emoji: '🛍️', label: 'Markets / fairs' },
    civic: { emoji: '📣', label: 'Civic / neighborhood' },
    media: { emoji: '🎬', label: 'Film / production' },
    government: { emoji: '🏛️', label: 'Government / meetings' },
    education: { emoji: '📚', label: 'Classes / workshops' },
    family: { emoji: '👨‍👩‍👧', label: 'Kids / family' },
    services: { emoji: '🤝', label: 'Health / benefits' },
    environment: { emoji: '🌎', label: 'Environment / nature' },
    volunteer: { emoji: '🙋', label: 'Volunteer opportunities' },
    jobs: { emoji: '💼', label: 'Jobs / career' },
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
  // Event-specific emoji: pick a glyph that looks like what the event IS
  // ("food looks like food") from the title/tags, falling back to the category
  // emoji. First match wins, so put specific patterns before generic ones.
  const EVENT_EMOJI_RULES = [
    [/\bfeast\b|giglio|san gennaro/i, '🍝'],
    [/food|culinary|taste of|restaurant|eats|foodie|chili|pizza|bbq|barbecue|cook ?out|grill/i, '🍽️'],
    [/farmers? market|greenmarket|green market|produce|harvest|hhfm/i, '🛍️🥬'],
    [/night market|bazaar|flea|vendor|sidewalk sale|craft fair|makers/i, '🛍️'],
    [/wine|beer|brew|cocktail|spirits/i, '🍷'],
    [/ice cream|dessert|sweet|bake/i, '🍦'],
    [/coffee/i, '☕'],
    [/parade/i, '🎊'],
    [/carnival|mardi gras/i, '🎡'],
    [/fireworks/i, '🎆'],
    [/marathon|\b\d+ ?k\b|road race|run\b|running|jog|triathlon|duathlon|cycl|bike ride|criterium/i, '🏃'],
    [/yoga|zumba|pilates|fitness|workout|aerobic|bootcamp|tai chi|wellness/i, '🧘'],
    [/concert|music|jazz|band|dj\b|symphony|orchestra|hip ?hop|salsa|reggae|summerstage/i, '🎵'],
    [/danc(e|ing)/i, '💃'],
    [/theater|theatre|shakespeare|drama/i, '🎭'],
    [/film|movie|cinema|screening|shoot|production|red carpet/i, '🎬'],
    [/art|gallery|exhibit|mural|paint|sculpture/i, '🎨'],
    [/book|story ?time|read|poetry|author|literary/i, '📖'],
    [/religious|church|mass|procession|prayer|vigil|worship|faith/i, '⛪'],
    [/health|clinic|screening|vaccine|medical|blood drive|wellness fair/i, '🏥'],
    [/block party|street festival|festival|fair\b|fest\b|celebration|party/i, '🎉'],
    [/rally|march|protest|demonstration|vigil/i, '✊'],
    [/clean ?-?up|garden|tree|nature|environment|compost|recycl/i, '🌳'],
    // Sport-specific glyphs before kids so e.g. "Football - Youth" stays 🏈.
    [/basketball/i, '🏀'],
    [/baseball|little league/i, '⚾'],
    [/softball/i, '🥎'],
    [/soccer/i, '⚽'],
    [/flag football|american football|\bfootball\b/i, '🏈'],
    [/tennis/i, '🎾'],
    [/volleyball/i, '🏐'],
    [/hockey/i, '🏒'],
    [/cricket/i, '🏏'],
    [/lacrosse/i, '🥍'],
    [/rugby/i, '🏉'],
    [/track and field|track\b/i, '🏃'],
    [/skate|skating/i, '🛹'],
    [/golf\b/i, '⛳'],
    [/boxing|kickbox|martial arts|karate|judo|taekwondo/i, '🥊'],
    [/kids|children|family|playground|storytime/i, '🧒'],
    [/job|career|hiring|workforce/i, '💼'],
    [/beach|boardwalk|pool|swim/i, '🏖️'],
  ];
  function eventEmoji(title, tags, categoryKey) {
    const hay = `${title || ''} ${(tags || []).join(' ')}`;
    for (const [re, glyph] of EVENT_EMOJI_RULES) {
      if (re.test(hay)) return glyph;
    }
    return (CATEGORY_META[categoryKey] || CATEGORY_META.general).emoji;
  }
  const BOROUGHS = ['All', 'Manhattan', 'Brooklyn', 'Queens', 'Bronx', 'Staten Island'];
  const debug = (() => {
    try { return new URL(location.href).searchParams.get('debugMap') === '1'; }
    catch { return false; }
  })();

  const state = {
    events: [],
    byId: new Map(),
    search: '',
    borough: 'all',
    sort: 'priority',
    dateMode: 'today',
    categories: Object.fromEntries(ALL_CATEGORY_KEYS.map(k => [k, true])),
    newsDeskOn: true,          // 📰 News Desk category (money shots + viral magnets)
    medalFilter: 'all',        // 'all' | 'medaled' | 'gold' — Editor's Picks focus
    returningKeys: new Set(),  // source keys with proven past presence
    moneyKeys: new Set(),      // source keys flagged as money-day shots
    moneyScoreByKey: new Map(),// source key -> money-day assignment score
    newsDeskLoaded: false,
    userLocation: null,
    listShown: LIST_PAGE,
    banner: '',
    // 'loading' | 'ok' | 'error' — lets the UI distinguish an honest empty
    // day from a feed failure. A failure must never present as zero events.
    feedPhase: 'loading',
    feedSource: '',
    lastGoodLoadAt: null,
    hasFitBounds: false,
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
    bugBtn: document.getElementById('bugBtn'),
    deskBtn: document.getElementById('deskBtn'),
    deskDrawer: document.getElementById('deskDrawer'),
    closeDeskBtn: document.getElementById('closeDeskBtn'),
    banner: document.getElementById('viewBanner'),
    searchInput: document.getElementById('searchInput'),
    sortSelect: document.getElementById('sortSelect'),
    dateChips: document.getElementById('dateChips'),
    boroughs: document.getElementById('boroughs'),
    listMeta: document.getElementById('listMeta'),
    eventList: document.getElementById('eventList'),
    loadMoreBtn: document.getElementById('loadMoreBtn'),
    enableAllBtn: document.getElementById('enableAllCategoriesBtn'),
    resetFiltersBtn: document.getElementById('resetFiltersBtn'),
    retryFeedBtn: document.getElementById('retryFeedBtn'),
    newsDeskToggle: document.getElementById('newsDeskToggle'),
    editorsPicks: document.getElementById('editorsPicksSelect'),
    debugPanel: document.getElementById('debugPanel'),
    indexStatus: document.getElementById('indexStatus')
  };

  if (!els.map || !SCHEMA) {
    if (els.status) {
      els.status.textContent = 'The map could not start. Please refresh the page.';
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

  map.on('popupclose', event => {
    document.body.classList.remove('nycif-popup-open');
    const source = event.popup && event.popup._source;
    if (source && source.__nycifStack) {
      source.__nycifStack.selected = null;
    }
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

  const norm = v => String(v ?? '').toLowerCase().replace(/\s+/g, ' ').trim();
  const dateKey = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  const todayKey = () => dateKey(new Date());
  const addDays = (d, n) => { const x = new Date(d); x.setDate(x.getDate() + n); return x; };
  const dayRange = () => ({ today: todayKey(), end: dateKey(addDays(new Date(), DAY_WINDOW)) });
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

  // The selected calendar date. 'today' is a sentinel so the default always
  // tracks the real current day, even across midnight or stale storage.
  function selectedDateKey() {
    if (state.dateMode === 'today') {
      return todayKey();
    }
    const valid = SCHEMA.validCalendarDate(state.dateMode);
    if (valid && valid >= todayKey()) {
      return valid;
    }
    return todayKey();
  }

  // Preference order: schema event date, then row.date, then a date derived
  // from start_date_time. Impossible dates like 2026-02-31 are rejected and
  // the event is excluded from date-specific public results.
  function eventDate(row) {
    const nycifDate = SCHEMA.validCalendarDate(row?.nycif?.event_date);
    if (nycifDate) {
      return nycifDate;
    }
    const direct = SCHEMA.validCalendarDate(String(row.date || '').slice(0, 10));
    if (direct) {
      return direct;
    }
    const start = String(row.start_date_time || '');
    const match = /^(\d{4}-\d{2}-\d{2})/.exec(start);
    if (match) {
      return SCHEMA.validCalendarDate(match[1]) || '';
    }
    return '';
  }

  // The last day a multi-day event (feast / festival / installation) runs, so
  // it shows on EVERY day it is active — not only its start date. Absurdly long
  // spans (season-long permits) are capped so they don't flood every day.
  const MAX_SPAN_DAYS = 21;
  function eventEndDay(row, startDay) {
    if (!startDay) return startDay || '';
    const raw = /^(\d{4}-\d{2}-\d{2})/.exec(String(row.end_date_time || ''));
    const endDay = raw ? SCHEMA.validCalendarDate(raw[1]) : '';
    if (!endDay || endDay <= startDay) {
      return startDay;
    }
    const cap = dateKey(addDays(new Date(`${startDay}T12:00:00`), MAX_SPAN_DAYS));
    return endDay > cap ? cap : endDay;
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
    const startDay = eventDate(schemaEvent);
    const e = {
      ...schemaEvent,
      lat: schemaEvent.latitude,
      lng: schemaEvent.longitude,
      dateKey: startDay,
      startDay,
      endDay: eventEndDay(schemaEvent, startDay),
      // Past = the event's end time has already elapsed (wall clock). Computed
      // live against the viewer's current moment so an event that ended earlier
      // today grays out too ("what's happening now" reads at a glance), not just
      // events on prior days. Falls back to end-of-day when only a date exists.
      isPast: (() => {
        const raw = schemaEvent.end_date_time || schemaEvent.start_date_time || '';
        if (!raw) return false;
        const hasTime = /T\d{2}:\d{2}/.test(raw);
        const when = new Date(hasTime ? raw : `${String(raw).slice(0, 10)}T23:59:59`);
        return !Number.isNaN(when.getTime()) && when.getTime() < Date.now();
      })(),
      categoryKey: catKey,
      categoryMeta: CATEGORY_META[catKey],
      displayEmoji: eventEmoji(title, tags, catKey),
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
      marqueeText: norm([title, nycif.event_type, nycif.major_reason, nycif.classification_reason].filter(Boolean).join(' ')),
      marker: null
    };
    e.priority = Number(e.major_score || 0) + (e.isMajor ? 500 : 0) + (e.photoPick ? 120 : 0);
    e.crowdScore = Number(nycif.expected_crowd_score || 0);
    applyEditorial(e);
    return e;
  }

  // Compute (or recompute) an event's editorial score, medal tier, and News
  // Desk flags. Called at build time and again once the News Desk signals load.
  function applyEditorial(e) {
    const key = ED.sourceKey(e);
    e.returning = state.returningKeys.has(key);
    e.marquee = typeof ED.isMarquee === 'function' && ED.isMarquee(e.marqueeText);
    const money = state.moneyKeys.has(key) || e.kind === 'money';
    e.editorialScore = ED.editorialScore({
      isMajor: e.isMajor,
      crowdScore: e.crowdScore,
      photoPick: e.photoPick,
      returning: e.returning,
      marquee: e.marquee,
      moneyScore: state.moneyScoreByKey.get(key) || (e.kind === 'money' ? e.major_score : 0)
    });
    e.medal = ED.medalOf(e.editorialScore);
    // News Desk = the curated standouts: money shots, viral magnets, marquee
    // types (FIFA/festival/parade/feast), and anything that earned a medal.
    e.newsDesk = e.returning || money || e.kind === 'viral' || e.marquee || !!e.medal;
    return e;
  }

  function medalMatch(e) {
    if (state.medalFilter === 'gold') return e.medal === 'gold';
    if (state.medalFilter === 'medaled') return !!e.medal;
    return true;
  }

  function categoryFilterMatch(e) {
    // News Desk is an additive highlight: when on, money shots + viral magnets
    // show regardless of their category selection.
    if (state.newsDeskOn && e.newsDesk) {
      return true;
    }
    if (state.categories[e.categoryKey]) {
      return true;
    }
    if (!DISCOVERY) {
      return false;
    }
    return (e.interests || []).some(interest => !!state.categories[interest]);
  }

  // Operator desk (?desk=1 / ?assignment=1) uses the same media pin rule as
  // the public map; list visibility is handled via sourceMatches/eventMatches.
  function isOperatorDesk() {
    try {
      const p = new URL(location.href).searchParams;
      return p.get('desk') === '1' || p.get('assignment') === '1';
    } catch {
      return false;
    }
  }

  function markerEligible(e) {
    if (!e.mapReady) {
      return false;
    }
    if (!DISCOVERY) {
      return true;
    }
    // Money-shot exception: film/production pins even when TVPP roles them as
    // street_closure / supporting_permit. Never pin maintenance_or_closure.
    if (e.categoryKey === 'media') {
      const role = e.event_role;
      if (role === 'maintenance_or_closure') {
        return false;
      }
      if (role === 'public_event' || role === 'street_closure' || role === 'supporting_permit') {
        return true;
      }
      return false;
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
      dateMode: 'today',
      categories: Object.fromEntries(ALL_CATEGORY_KEYS.map(k => [k, true])),
      newsDeskOn: true,
      medalFilter: 'all',
      nycifDefaultVersion: DEFAULT_VERSION
    };
  }

  function forceReset() {
    try {
      return new URL(location.href).searchParams.get('resetFilters') === '1';
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
        categories: { ...defaults.categories, ...(parsed.categories || {}) }
      };
      if (use.categories.parade != null && use.categories.civic == null) {
        use.categories.civic = !!use.categories.parade;
      }
      Object.assign(state, {
        borough: use.borough,
        sort: use.sort === 'near' ? 'priority' : use.sort,
        // Today is always the default date after a normal load.
        dateMode: 'today',
        categories: Object.fromEntries(ALL_CATEGORY_KEYS.map(k => [k, use.categories[k] !== false])),
        newsDeskOn: use.newsDeskOn !== false,
        medalFilter: (use.medalFilter === 'gold' || use.medalFilter === 'medaled') ? use.medalFilter : 'all'
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
      categories: { ...state.categories },
      newsDeskOn: state.newsDeskOn,
      medalFilter: state.medalFilter,
      nycifDefaultVersion: DEFAULT_VERSION
    }));
  }

  function dateMatches(e) {
    const start = e.startDay || e.dateKey;
    if (!start) {
      return false;
    }
    const end = e.endDay || start;
    const sel = selectedDateKey();
    // Multi-day events (feasts, festivals, installations) show on every day
    // they run. selectedDateKey() is always today or later, so a finished
    // event (end < today) can never match — no historical events appear.
    return start <= sel && sel <= end;
  }

  function sourceMatches(e) {
    // Approved + review_supplemental public_event rows are both list-visible.
    // Non-public roles stay hidden except media money-shot roles (A4).
    // isReview can still style markers subtly; it no longer hides the row.
    // Operator desk (?desk=1 / ?assignment=1) uses this same list rule.
    if (e.event_role === 'maintenance_or_closure') {
      return false;
    }
    if (e.event_role === 'public_event') {
      return true;
    }
    if (e.categoryKey === 'media'
      && (e.event_role === 'street_closure' || e.event_role === 'supporting_permit')) {
      return true;
    }
    return false;
  }

  function eventMatches(e) {
    return sourceMatches(e)
      && dateMatches(e)
      && categoryFilterMatch(e)
      && medalMatch(e)
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

  function formatDistanceLabel(dist) {
    if (dist < 0.1) {
      return 'nearby';
    }
    const digits = dist < 10 ? 1 : 0;
    return `${dist.toFixed(digits)} mi`;
  }

  function friendlyDateLabel(key) {
    const today = todayKey();
    if (key === today) {
      return 'today';
    }
    if (key === dateKey(addDays(new Date(), 1))) {
      return 'tomorrow';
    }
    if (SCHEMA.validCalendarDate(key)) {
      return `${Number(key.slice(5, 7))}/${Number(key.slice(8, 10))}`;
    }
    return key;
  }

  const shortDate = key => (SCHEMA.validCalendarDate(key)
    ? `${key.slice(5, 7)}/${key.slice(8, 10)}/${key.slice(2, 4)}`
    : '');

  function meaningfulTime(value) {
    const text = String(value || '');
    const match24 = text.match(/T(\d{2}):(\d{2})/);
    if (match24 && !(match24[1] === '00' && match24[2] === '00')) {
      return true;
    }
    return /T(\d{1,2}):(\d{2})\s*(am|pm)/i.test(text);
  }

  function formatClock(value) {
    const text = String(value || '');
    let date = null;
    const match12 = text.match(/T(\d{1,2}):(\d{2})\s*(am|pm)/i);
    if (match12) {
      let hour = Number(match12[1]);
      const minute = match12[2];
      const ampm = String(match12[3]).toLowerCase();
      if (ampm === 'pm' && hour < 12) {
        hour += 12;
      }
      if (ampm === 'am' && hour === 12) {
        hour = 0;
      }
      const day = text.slice(0, 10);
      date = new Date(`${day}T${String(hour).padStart(2, '0')}:${minute}:00-04:00`);
    } else if (meaningfulTime(text)) {
      date = new Date(text);
    }
    if (!date || Number.isNaN(date.getTime())) {
      return '';
    }
    return new Intl.DateTimeFormat('en-US', {
      hour: 'numeric',
      minute: '2-digit',
      timeZone: 'America/New_York'
    }).format(date);
  }

  function formatTimeRange(e) {
    const start = formatClock(e && e.start_date_time);
    const end = formatClock(e && e.end_date_time);
    if (start && end && start !== end) {
      return `${start}–${end}`;
    }
    return start || end || 'Time not listed';
  }

  function eventSortTime(e) {
    const raw = String(e?.start_date_time || '');
    const match12 = raw.match(/T(\d{1,2}):(\d{2})\s*(am|pm)/i);
    if (match12) {
      let hour = Number(match12[1]);
      const minute = Number(match12[2]);
      const ampm = String(match12[3]).toLowerCase();
      if (ampm === 'pm' && hour < 12) {
        hour += 12;
      }
      if (ampm === 'am' && hour === 12) {
        hour = 0;
      }
      return hour * 60 + minute;
    }
    const match24 = raw.match(/T(\d{2}):(\d{2})/);
    if (match24) {
      return Number(match24[1]) * 60 + Number(match24[2]);
    }
    return Number.MAX_SAFE_INTEGER;
  }

  // "07/16/26" for a single day, "07/16 – 07/19" for a multi-day run.
  function formatDateSpan(e) {
    const start = e.startDay || e.dateKey;
    if (!SCHEMA.validCalendarDate(start)) {
      return 'Date unavailable';
    }
    const end = e.endDay || start;
    if (SCHEMA.validCalendarDate(end) && end > start) {
      return `${start.slice(5, 7)}/${start.slice(8, 10)} – ${end.slice(5, 7)}/${end.slice(8, 10)}`;
    }
    return shortDate(start);
  }

  function coordKeyFor(lat, lng) {
    return `${Number(lat).toFixed(5)},${Number(lng).toFixed(5)}`;
  }

  function groupEventsByCoord(eventList) {
    const groups = new Map();
    for (const e of eventList) {
      const key = coordKeyFor(e.lat, e.lng);
      if (!groups.has(key)) {
        groups.set(key, []);
      }
      groups.get(key).push(e);
    }
    for (const group of groups.values()) {
      group.sort((a, b) => b.priority - a.priority || String(a.title).localeCompare(String(b.title)));
    }
    return groups;
  }

  function stackDotsHtml(extraCount) {
    if (extraCount <= 0) {
      return '';
    }
    const shown = Math.min(extraCount, 3);
    let html = '<span class="stack-dots" aria-hidden="true">';
    for (let i = 0; i < shown; i += 1) {
      html += '<span class="stack-dot"></span>';
    }
    if (extraCount > 3) {
      html += `<span class="stack-more">+${extraCount - 3}</span>`;
    }
    html += '</span>';
    return html;
  }

  function markerClassList(e, stackCount) {
    const cls = ['marker', `marker--${e.categoryKey}`];
    if (e.isPast) {
      cls.push('marker--past');
    }
    if (e.isReview) {
      cls.push('marker--review');
    }
    if (e.photoPick) {
      cls.push('marker--photo');
    }
    if (e.isMajor) {
      cls.push('marker--major');
    }
    if (e.medal) {
      cls.push(`marker--medal-${e.medal}`);
    }
    if (stackCount > 1) {
      cls.push('marker--stacked');
    }
    if (e.displayEmoji === '🛍️🥬') {
      cls.push('marker--produce');
    }
    return cls;
  }

  function popupPicker(events, marker) {
    const root = document.createElement('article');
    root.className = 'popup-card popup-card--picker';
    const locationLabel = events[0]?.location || 'this location';
    appendText(root, 'p', `${events.length} events`, 'popup-picker-label');
    appendText(root, 'h2', locationLabel);
    const scroll = document.createElement('div');
    scroll.className = 'popup-stack-scroll';
    scroll.setAttribute('role', 'listbox');
    scroll.setAttribute('aria-label', `Events at ${locationLabel}`);
    const sorted = [...events].sort((a, b) => eventSortTime(a) - eventSortTime(b)
      || String(a.title).localeCompare(String(b.title)));
    sorted.forEach(ev => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'popup-stack-item';
      btn.setAttribute('role', 'option');
      btn.setAttribute('aria-label', `${ev.title}, ${formatTimeRange(ev)}`);
      appendText(btn, 'span', ev.displayEmoji, 'popup-stack-emoji');
      const copy = document.createElement('span');
      copy.className = 'popup-stack-copy';
      appendText(copy, 'span', ev.title, 'popup-stack-title');
      appendText(copy, 'span', formatTimeRange(ev), 'popup-stack-time');
      btn.appendChild(copy);
      btn.addEventListener('click', evt => {
        evt.preventDefault();
        evt.stopPropagation();
        openStackDetail(marker, events, ev);
      });
      scroll.appendChild(btn);
    });
    root.appendChild(scroll);
    return root;
  }

  function openStackPicker(marker, events) {
    if (!marker || !events?.length) {
      return;
    }
    marker.__nycifStack = { events, selected: null };
    marker.setPopupContent(events.length === 1 ? popupRoot(events[0]) : popupPicker(events, marker));
    if (marker.isPopupOpen()) {
      marker.getPopup().update();
      syncPopupBackButton(marker);
    } else {
      marker.openPopup();
    }
  }

  function openStackDetail(marker, events, selected) {
    if (!marker || !selected) {
      return;
    }
    marker.__nycifStack = { events, selected };
    marker.setPopupContent(popupRoot(selected));
    if (marker.isPopupOpen()) {
      marker.getPopup().update();
      syncPopupBackButton(marker);
    } else {
      marker.openPopup();
    }
  }

  function syncStackPopupPlacement(marker) {
    const stack = marker?.__nycifStack;
    const popup = marker?.getPopup();
    const el = popup?.getElement();
    if (!stack || stack.events.length <= 1 || !el || !map) {
      return;
    }
    const markerPoint = map.latLngToContainerPoint(marker.getLatLng());
    const mapWidth = map.getSize().x;
    const popupWidth = el.offsetWidth || 320;
    const roomRight = mapWidth - markerPoint.x;
    const roomLeft = markerPoint.x;
    const preferRight = roomRight >= popupWidth + 24 || roomRight >= roomLeft;
    const sideClass = preferRight ? 'nycif-event-popup--side-right' : 'nycif-event-popup--side-left';
    el.classList.remove('nycif-event-popup--side-right', 'nycif-event-popup--side-left');
    el.classList.add(sideClass);
    const offsetX = preferRight ? 20 : -(popupWidth * 0.38);
    popup.options.offset = L.point(offsetX, -6);
    popup.update();
  }

  function syncPopupBackButton(marker) {
    const popup = marker.getPopup();
    const wrapper = popup?.getElement()?.querySelector('.leaflet-popup-content-wrapper');
    if (!wrapper) {
      return;
    }
    wrapper.querySelector('.nycif-popup-back')?.remove();
    const stack = marker.__nycifStack;
    if (!stack?.selected || stack.events.length <= 1) {
      return;
    }
    const back = document.createElement('button');
    back.type = 'button';
    back.className = 'nycif-popup-back';
    back.setAttribute('aria-label', 'Back to events at this location');
    back.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M12 4a8 8 0 1 0 0 16 8 8 0 0 0 0-16zm1 4v2.17l2.59 2.59L14 14.83 9.17 10 14 5.17 15.59 6.76 13 9.35V8h2z"/></svg>';
    back.addEventListener('click', evt => {
      evt.preventDefault();
      evt.stopPropagation();
      openStackPicker(marker, stack.events);
    });
    wrapper.appendChild(back);
  }

  function popupRoot(e) {
    const root = document.createElement('article');
    root.className = 'popup-card';

    const cat = appendText(root, 'div', '', 'popup-category');
    appendText(cat, 'span', e.displayEmoji);
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
    addRow('Date', formatDateSpan(e));
    addRow('Time', formatTimeRange(e));
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
      appendText(root, 'div', 'Location being confirmed.', 'popup-pending');
    }
    return root;
  }

  function makeStackMarker(events) {
    const primary = events[0];
    const count = events.length;
    const medalEmoji = primary.medal && ED.MEDAL_META[primary.medal] ? ED.MEDAL_META[primary.medal].emoji : '';
    const cls = markerClassList(primary, count);
    const marker = L.marker([primary.lat, primary.lng], {
      icon: L.divIcon({
        className: 'marker-shell',
        html: `<span class="${cls.join(' ')}"><span class="emoji"></span>${medalEmoji ? '<span class="medal"></span>' : ''}${stackDotsHtml(count - 1)}</span>`,
        iconSize: [38, count > 1 ? 46 : 38],
        iconAnchor: [19, count > 1 ? 23 : 19],
        popupAnchor: [0, count > 1 ? -28 : -24]
      }),
      title: count > 1 ? `${count} events here` : primary.title,
      riseOnHover: true
    });
    marker.__nycifStack = { events, selected: null };
    marker.on('add', () => {
      const root = marker.getElement();
      const emoji = root?.querySelector('.emoji');
      if (emoji) {
        emoji.textContent = primary.displayEmoji;
      }
      const medal = root?.querySelector('.medal');
      if (medal && medalEmoji) {
        medal.textContent = medalEmoji;
      }
    });
    marker.bindPopup(() => {
      const stack = marker.__nycifStack || { events, selected: null };
      if (stack.selected || stack.events.length === 1) {
        return popupRoot(stack.selected || stack.events[0]);
      }
      return popupPicker(stack.events, marker);
    }, {
      maxWidth: 360,
      minWidth: 300,
      autoPan: false,
      autoPanPadding: [28, 28],
      closeButton: true,
      autoClose: true,
      closeOnClick: true,
      offset: count > 1 ? L.point(22, -8) : L.point(0, 0),
      className: count > 1 ? 'nycif-event-popup nycif-event-popup--stack' : 'nycif-event-popup'
    });
    marker.on('popupopen', () => {
      syncStackPopupPlacement(marker);
      syncPopupBackButton(marker);
    });
    return marker;
  }

  const stackMarkerCache = new Map();

  function ensureStackMarker(events) {
    if (!events.length) {
      return null;
    }
    const key = coordKeyFor(events[0].lat, events[0].lng);
    if (stackMarkerCache.has(key)) {
      const marker = stackMarkerCache.get(key);
      events.forEach(e => {
        e.marker = marker;
      });
      marker.__nycifStack = { events, selected: marker.__nycifStack?.selected || null };
      return marker;
    }
    const marker = makeStackMarker(events);
    events.forEach(e => {
      e.marker = marker;
    });
    stackMarkerCache.set(key, marker);
    return marker;
  }

  function ensureMarker(e) {
    if (!markerEligible(e)) {
      return null;
    }
    if (e.marker) {
      return e.marker;
    }
    const key = coordKeyFor(e.lat, e.lng);
    const stack = state.events.filter(ev => markerEligible(ev)
      && eventMatches(ev)
      && coordKeyFor(ev.lat, ev.lng) === key);
    stack.sort((a, b) => b.priority - a.priority || String(a.title).localeCompare(String(b.title)));
    return ensureStackMarker(stack.length ? stack : [e]);
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
    stackMarkerCache.clear();
    if (markers.clearLayers) {
      markers.clearLayers();
    }
    const mapReady = visible.filter(e => markerEligible(e));
    const bounds = expandedBounds();
    const inView = bounds ? mapReady.filter(e => bounds.contains([e.lat, e.lng])) : mapReady;
    const candidates = (inView.length ? inView : mapReady).slice(0, MARKER_SOFT_CAP);
    candidates.forEach(e => {
      e.marker = null;
    });
    const groups = groupEventsByCoord(candidates);
    const batch = [];
    for (const group of groups.values()) {
      const marker = ensureStackMarker(group);
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
    button.className = e.isPast ? 'event-item event-item--past' : 'event-item';
    button.dataset.id = e.id;

    const top = document.createElement('span');
    top.className = 'item-top';
    appendText(top, 'span', `${e.displayEmoji} ${e.categoryMeta.label}`, 'item-source');
    const tags = document.createElement('span');
    tags.className = 'item-tags';
    if (e.isPast) {
      appendText(tags, 'span', '✓ Ended', 'item-tag ended');
    }
    if (e.medal && ED.MEDAL_META[e.medal]) {
      appendText(tags, 'span', `${ED.MEDAL_META[e.medal].emoji} ${ED.MEDAL_META[e.medal].label}`, `item-tag medal medal-${e.medal}`);
    }
    if (e.newsDesk) {
      appendText(tags, 'span', '📰 News Desk', 'item-tag newsdesk');
    }
    if (e.endDay && e.startDay && e.endDay > e.startDay) {
      appendText(tags, 'span', '📅 Multi-day', 'item-tag multiday');
    }
    if (e.isMajor && !e.medal) {
      appendText(tags, 'span', '⭐ Featured', 'item-tag featured');
    }
    if (!e.mapReady) {
      appendText(tags, 'span', 'Location being confirmed', 'item-tag pending');
    }
    const dist = milesBetween(state.userLocation, e);
    if (Number.isFinite(dist)) {
      appendText(tags, 'span', formatDistanceLabel(dist), 'item-tag near');
    }
    top.appendChild(tags);
    button.appendChild(top);
    appendText(button, 'strong', e.title);
    appendText(button, 'span', formatDateSpan(e));
    appendText(button, 'small', [e.borough, e.location].filter(Boolean).join(' • '));
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

  function updateIndexLabel() {
    if (state.indexComplete) {
      setIndexStatus('');
      return;
    }
    setIndexStatus('Finding more events…');
  }

  function emptyStateMessage() {
    if (state.feedPhase === 'error' && !state.events.length) {
      return 'Events could not be loaded right now. Please use Retry Events in the Filters panel, or check back in a few minutes.';
    }
    const anyCategoryOn = ALL_CATEGORY_KEYS.some(k => state.categories[k]);
    if (!anyCategoryOn) {
      return 'No categories are selected. Use Enable All in the Filters panel to see events.';
    }
    if (state.search || state.borough !== 'all') {
      return 'No events match your current search or borough. Try widening your filters.';
    }
    const otherDayHint = categoryOtherDayHint();
    if (otherDayHint) {
      return otherDayHint;
    }
    return `No events found for ${friendlyDateLabel(selectedDateKey())} yet. Try another day or check back soon.`;
  }

  function categoryKeysForEvent(e) {
    const keys = new Set();
    if (e.categoryKey && (CATEGORY_META[e.categoryKey] || state.categories[e.categoryKey] != null)) {
      keys.add(e.categoryKey);
    }
    for (const interest of e.interests || []) {
      if (CATEGORY_META[interest] || state.categories[interest] != null) {
        keys.add(interest);
      }
    }
    return keys;
  }

  function categoryOtherDayHint() {
    const active = ALL_CATEGORY_KEYS.filter(k => state.categories[k]);
    if (active.length !== 1) {
      return '';
    }
    const key = active[0];
    const label = (CATEGORY_META[key] || {}).label || key;
    let otherDays = 0;
    for (const e of state.events) {
      if (!sourceMatches(e) || dateMatches(e)) {
        continue;
      }
      if (categoryKeysForEvent(e).has(key)) {
        otherDays += 1;
      }
    }
    if (!otherDays) {
      return '';
    }
    return `No ${label.toLowerCase()} events on ${friendlyDateLabel(selectedDateKey())}, but ${otherDays.toLocaleString()} on other days in this feed — try another date chip.`;
  }

  // Gray out category filters that have no events for the selected date, and
  // show a live count on the ones that do. Recomputes when the loaded event set
  // or selected date changes.
  let _catAvailKey = '';
  function updateCategoryAvailability() {
    const cacheKey = `${state.events.length}|${selectedDateKey()}`;
    if (_catAvailKey === cacheKey) return;
    _catAvailKey = cacheKey;
    const dateCounts = {};
    const totalCounts = {};
    const pinCounts = {};
    for (const e of state.events) {
      if (!sourceMatches(e)) {
        continue;
      }
      const keys = categoryKeysForEvent(e);
      for (const key of keys) {
        totalCounts[key] = (totalCounts[key] || 0) + 1;
        if (dateMatches(e)) {
          dateCounts[key] = (dateCounts[key] || 0) + 1;
          if (markerEligible(e)) {
            pinCounts[key] = (pinCounts[key] || 0) + 1;
          }
        }
      }
    }
    document.querySelectorAll('[data-cat]').forEach(input => {
      const key = input.getAttribute('data-cat');
      const onDate = dateCounts[key] || 0;
      const inFeed = totalCounts[key] || 0;
      const pins = pinCounts[key] || 0;
      const label = input.closest('.check');
      if (label) {
        label.classList.toggle('check--empty', inFeed === 0);
        let badge = label.querySelector('.check-count');
        if (!badge) {
          badge = document.createElement('small');
          badge.className = 'check-count';
          label.appendChild(badge);
        }
        if (inFeed === 0) {
          badge.textContent = 'not ready';
          badge.title = '';
        } else if (onDate === 0) {
          badge.textContent = `0 · ${inFeed.toLocaleString()} other days`;
          badge.title = `${inFeed.toLocaleString()} ${(CATEGORY_META[key] || {}).label || key} events on other days in this feed`;
        } else if (pins < onDate) {
          badge.textContent = `${onDate.toLocaleString()} · ${pins.toLocaleString()} on map`;
          badge.title = `${onDate.toLocaleString()} list-visible today; ${pins.toLocaleString()} with map pins (${onDate - pins} list-only)`;
        } else {
          badge.textContent = onDate.toLocaleString();
          badge.title = inFeed > onDate
            ? `${onDate.toLocaleString()} today · ${inFeed.toLocaleString()} total in feed`
            : '';
        }
      }
      // Empty lanes are non-interactive; enabling one would just show nothing.
      input.disabled = inFeed === 0;
    });
  }

  function render() {
    const t0 = performance.now();
    updateIndexLabel();
    updateCategoryAvailability();
    const visible = state.events.filter(eventMatches).sort(sortEvents);
    const drawn = renderMarkers(visible);
    const shown = Math.min(state.listShown, visible.length);
    const mapEligibleCount = visible.filter(e => markerEligible(e)).length;
    const dateLabel = friendlyDateLabel(selectedDateKey());
    let meta = `${visible.length.toLocaleString()} event${visible.length === 1 ? '' : 's'} ${dateLabel === 'today' || dateLabel === 'tomorrow' ? dateLabel : `on ${dateLabel}`}`;
    if (drawn.length < mapEligibleCount) {
      meta += ' · move or zoom the map to see more pins';
    }
    els.listMeta.textContent = meta;
    clearChildren(els.eventList);
    if (!visible.length) {
      appendText(els.eventList, 'div', emptyStateMessage(), 'empty');
    } else {
      visible.slice(0, shown).forEach(e => els.eventList.appendChild(buildListCard(e)));
    }
    if (els.loadMoreBtn) {
      els.loadMoreBtn.hidden = shown >= visible.length;
      els.loadMoreBtn.textContent = `Show 100 more (${Math.max(0, visible.length - shown).toLocaleString()} remaining)`;
    }
    if (els.brandCount) {
      els.brandCount.textContent = `${visible.length.toLocaleString()} event${visible.length === 1 ? '' : 's'} · ${dateLabel}`;
    }
    if (state.feedPhase === 'error' && !state.events.length) {
      status('Events are temporarily unavailable. Open Filters and choose Retry Events.');
    } else if (state.feedPhase === 'error') {
      status('Events could not be refreshed. Showing the most recent available information.');
    } else {
      status(`${visible.length.toLocaleString()} event${visible.length === 1 ? '' : 's'} · ${dateLabel}`);
    }
    state.timings.listRenderMs = Math.round(performance.now() - t0);
    if (debug && els.debugPanel) {
      els.debugPanel.hidden = false;
      els.debugPanel.textContent = JSON.stringify({
        version: VERSION,
        total: state.events.length,
        filtered: visible.length,
        markers: drawn.length,
        peakMarkerObjects: state.peakMarkerObjects,
        indexComplete: state.indexComplete,
        pagesLoaded: state.pagesLoaded,
        pagesTotal: state.pagesTotal,
        cluster: useCluster,
        feedPhase: state.feedPhase,
        feedSource: state.feedSource,
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
      status(`${e.title}: location being confirmed.`);
      setDesk(true);
      return;
    }
    const marker = ensureMarker(e);
    if (marker && !markers.hasLayer(marker)) {
      markers.addLayer(marker);
    }
    map.flyTo([e.lat, e.lng], Math.max(map.getZoom(), 15), { duration: 0.55 });
    setTimeout(() => {
      if (!marker) {
        return;
      }
      const stack = marker.__nycifStack?.events || [e];
      if (stack.length > 1) {
        openStackDetail(marker, stack, e);
      } else {
        marker.openPopup();
      }
    }, 420);
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
    state.dateMode = mode;
    state.listShown = LIST_PAGE;
    buildDateChips();
    scheduleRender();
    loadPagesForCurrentWindow(state.loadToken);
  }

  function buildDateChips() {
    if (!els.dateChips) {
      return;
    }
    clearChildren(els.dateChips);
    const track = document.createElement('div');
    track.className = 'date-chip-track';
    const activeKey = selectedDateKey();
    SCHEMA.dateChipModel(new Date()).forEach(chip => {
      const mode = chip.offset === 0 ? 'today' : chip.key;
      const button = document.createElement('button');
      button.type = 'button';
      button.dataset.dateMode = mode;
      button.dataset.dateKey = chip.key;
      button.textContent = chip.label;
      if (chip.key === activeKey) {
        button.classList.add('active');
      }
      button.addEventListener('click', () => onDateChipSelected(mode));
      track.appendChild(button);
    });
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
        icon: L.divIcon({ className: 'user-location-shell', html: '<span class="user-location" aria-hidden="true"></span>', iconSize: [24, 24], iconAnchor: [12, 12] }),
        zIndexOffset: 4000
      }).addTo(map);
      userMarker.bindPopup('You are here');
    }
    if (userAccuracy) {
      userAccuracy.setLatLng(here);
      userAccuracy.setRadius(accuracy || 0);
    } else {
      userAccuracy = L.circle(here, { radius: accuracy || 0, color: '#1677ff', weight: 2, fillColor: '#1677ff', fillOpacity: 0.08 }).addTo(map);
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
    }, () => {
      status('We could not access your location. Please check your browser location permission and try again.');
    }, { enableHighAccuracy: true, timeout: 12000, maximumAge: 15000 });
  }

  function pageOverlapsWindow(page, start, end) {
    if (!page.earliest_date || !page.latest_date) {
      return true;
    }
    return page.latest_date >= start && page.earliest_date <= end;
  }

  async function loadLayerPages(layer, manifest, token) {
    if (!manifest?.pages?.length) {
      return;
    }
    const { today, end } = dayRange();
    // Look back one span-length so multi-day events (feasts, festivals) that
    // started before today but are still running are still downloaded — their
    // manifest page is dated by start, not by end. dateMatches still hides
    // anything already finished, so no past events are shown.
    const lookbackStart = dateKey(addDays(new Date(), -MAX_SPAN_DAYS));
    const windowPages = [...manifest.pages].filter(page => pageOverlapsWindow(page, lookbackStart, end));
    state.pagesTotal[layer] = windowPages.length;
    const urlFor = layer === 'review' ? FEEDS.reviewPage : FEEDS.approvedPage;
    const dataLayer = layer === 'review' ? 'review_supplemental' : 'approved_staged';
    for (const page of windowPages) {
      if (token !== state.loadToken) {
        return;
      }
      try {
        const json = await fetchJson(urlFor(page.cursor || page.page.replace('.json', '')), `${layer}-${page.page}`);
        if (token !== state.loadToken) {
          return;
        }
        const envelope = SCHEMA.projectEnvelope(json, dataLayer, json.generated_at_utc);
        upsertEvents(envelope.events);
        state.pagesLoaded[layer] += 1;
        updateIndexLabel();
        scheduleRender();
      } catch (err) {
        state.errors.push(String(err.message || err));
        console.error('[NYCIF] page load failed:', layer, page.page, err);
      }
    }
  }

  async function loadPagesForCurrentWindow(token) {
    if (state.manifests.approved) {
      await loadLayerPages('approved', state.manifests.approved, token);
    }
    if (state.manifests.review) {
      await loadLayerPages('review', state.manifests.review, token);
    }
    if (token === state.loadToken) {
      state.indexComplete = state.pagesLoaded.approved >= (state.pagesTotal.approved || 0)
        && state.pagesLoaded.review >= (state.pagesTotal.review || 0);
      updateIndexLabel();
      scheduleRender();
    }
  }

  async function loadMajorWithFallbacks() {
    const chain = [
      { url: FEEDS.major, label: 'major', source: 'primary' },
      { url: FEEDS.majorFallback, label: 'major-fallback', source: 'fallback' },
      { url: FEEDS.majorEmergency, label: 'major-emergency', source: 'emergency' }
    ];
    const failures = [];
    for (const step of chain) {
      try {
        const json = await fetchJson(step.url, step.label);
        console.info(`[NYCIF] events loaded from ${step.source} feed`, step.url);
        return { json, source: step.source };
      } catch (err) {
        failures.push(`${step.label}: ${err.message || err}`);
        console.error(`[NYCIF] ${step.source} feed failed:`, step.url, err);
      }
    }
    throw new Error(failures.join(' | '));
  }

  async function bootFeeds() {
    const token = ++state.loadToken;
    state.errors = [];
    state.pagesLoaded = { approved: 0, review: 0 };
    state.pagesTotal = { approved: 0, review: 0 };
    state.indexComplete = false;
    state.feedPhase = state.events.length ? state.feedPhase : 'loading';
    status('Loading NYC events…');
    try {
      const { json: majorJson, source } = await loadMajorWithFallbacks();
      if (token !== state.loadToken) {
        return;
      }
      const major = SCHEMA.projectEnvelope(majorJson, 'approved_staged', majorJson.generated_at_utc);
      major.events.forEach(e => {
        e.significance = 'major';
        e.nycif = { ...(e.nycif || {}), is_major: true, data_layer: 'approved_staged' };
      });
      // Replace inventory only after a feed has succeeded. A failed refresh
      // must never clear events that are already on screen.
      state.byId.clear();
      upsertEvents(major.events);
      state.feedPhase = 'ok';
      state.feedSource = source;
      state.lastGoodLoadAt = new Date().toISOString();
      setBanner('');
      state.timings.timeToFirstMajorMs = state.timings.major?.fetchMs || 0;
      const visible = render();
      if (!state.hasFitBounds) {
        const mapReady = visible.filter(e => e.mapReady);
        if (mapReady.length) {
          map.fitBounds(mapReady.slice(0, 200).map(e => [e.lat, e.lng]), { padding: [44, 44], maxZoom: 12 });
          state.hasFitBounds = true;
        }
      }
    } catch (err) {
      state.errors.push(String(err.message || err));
      console.error('[NYCIF] all event feeds failed:', err);
      state.feedPhase = 'error';
      if (state.events.length) {
        setBanner('Events could not be refreshed. Showing the most recent available information.');
      } else {
        setBanner('Events could not be loaded. Open Filters and choose Retry Events.');
      }
      render();
    }

    try {
      const approvedManifest = await fetchJson(FEEDS.approvedManifest, 'approved-manifest');
      if (token !== state.loadToken) {
        return;
      }
      state.manifests.approved = approvedManifest;
    } catch (err) {
      state.errors.push(String(err.message || err));
      console.error('[NYCIF] approved manifest failed:', err);
      state.manifests.approved = null;
    }

    // Review supplemental is fail-soft: map still works on approved alone.
    try {
      const reviewManifest = await fetchJson(FEEDS.reviewManifest, 'review-manifest');
      if (token !== state.loadToken) {
        return;
      }
      state.manifests.review = reviewManifest;
    } catch (err) {
      state.errors.push(String(err.message || err));
      console.error('[NYCIF] review manifest failed (fail-soft):', err);
      state.manifests.review = null;
    }

    if (token !== state.loadToken) {
      return;
    }
    if (state.manifests.approved || state.manifests.review) {
      await loadPagesForCurrentWindow(token);
    } else {
      state.indexComplete = false;
      updateIndexLabel();
    }
  }

  // Load the News Desk signals (money shots + viral magnets), tag matching
  // events, add certified pins not already in the feed, and recompute medals.
  // Non-blocking and failure-tolerant: the public map works without it.
  async function loadNewsDeskSignals() {
    try {
      const [moneyJson, viralJson] = await Promise.all([
        fetchJson(NEWS_DESK_DATA.money, 'newsdesk-money').catch(() => null),
        fetchJson(NEWS_DESK_DATA.viral, 'newsdesk-viral').catch(() => null)
      ]);
      state.returningKeys = ED.extractReturningKeys(viralJson);
      const rows = ED.extractNewsDeskRows(moneyJson, viralJson);
      state.moneyKeys = new Set(
        rows.filter(r => r.kind === 'money' && r.key).map(r => r.key)
      );
      state.moneyScoreByKey = new Map(
        rows.filter(r => r.kind === 'money' && r.key).map(r => [r.key, r.majorScore])
      );
      // Add certified News Desk pins that are not already in the loaded feed
      // window, so today's money shots always appear. Deduped by source key.
      const known = new Set([...state.byId.values()].map(e => ED.sourceKey(e)).filter(Boolean));
      let added = 0;
      rows.forEach(r => {
        if (!r.key || known.has(r.key)) return;
        known.add(r.key);
        const catKey = CATEGORY_META[r.category] ? r.category : 'general';
        const e = {
          id: r.id,
          title: r.title,
          lat: r.lat,
          lng: r.lng,
          latitude: r.lat,
          longitude: r.lng,
          borough: r.borough,
          location: r.location,
          dateKey: SCHEMA.validCalendarDate(r.date) || '',
          startDay: SCHEMA.validCalendarDate(r.date) || '',
          endDay: eventEndDay(r, SCHEMA.validCalendarDate(r.date) || ''),
          start_date_time: r.start_date_time,
          end_date_time: r.end_date_time,
          categoryKey: catKey,
          categoryMeta: CATEGORY_META[catKey],
          interests: [],
          tags: [],
          source: r.source,
          event_role: 'public_event',
          parent_event_id: null,
          mapReady: true,
          isReview: false,
          isMajor: true,
          photoPick: false,
          major_score: r.majorScore,
          crowdScore: 0,
          kind: r.kind,
          nycif: { coordinate_status: 'map_ready', display_disposition: 'standalone_public_event' },
          searchText: norm([r.title, r.location, r.borough, catKey, 'news desk'].filter(Boolean).join(' ')),
          marqueeText: norm(r.title || ''),
          priority: r.majorScore + 500,
          marker: null
        };
        applyEditorial(e);
        state.byId.set(e.id, e);
        added += 1;
      });
      // Re-tag + re-score everything now that the signals are known.
      state.events = [...state.byId.values()];
      state.events.forEach(applyEditorial);
      state.newsDeskLoaded = true;
      console.info(`[NYCIF] News Desk loaded: ${state.returningKeys.size} returning, ${state.moneyKeys.size} money, ${added} supplemental pins.`);
      scheduleRender();
    } catch (err) {
      console.error('[NYCIF] News Desk signals failed:', err);
    }
  }

  function syncUi() {
    if (els.sortSelect) {
      els.sortSelect.value = state.sort;
    }
    if (els.newsDeskToggle) {
      els.newsDeskToggle.checked = state.newsDeskOn;
    }
    if (els.editorsPicks) {
      els.editorsPicks.value = state.medalFilter;
    }
    document.querySelectorAll('[data-cat]').forEach(input => {
      input.checked = !!state.categories[input.dataset.cat];
    });
  }

  function onCategoryFilterChange(input) {
    state.categories[input.dataset.cat] = input.checked;
    savePrefs();
    scheduleRender();
  }

  function onNewsDeskToggle() {
    state.newsDeskOn = !!els.newsDeskToggle?.checked;
    savePrefs();
    scheduleRender();
  }

  function onEditorsPicksChange() {
    const v = els.editorsPicks?.value;
    state.medalFilter = (v === 'gold' || v === 'medaled') ? v : 'all';
    state.listShown = LIST_PAGE;
    savePrefs();
    scheduleRender();
  }

  function onSearchInput() {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      state.search = norm(els.searchInput.value);
      state.listShown = LIST_PAGE;
      scheduleRender();
    }, SEARCH_DEBOUNCE_MS);
  }

  function onSortSelectChange() {
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
      scheduleRender();
    }, 120);
  }

  function enableAllCategories() {
    ALL_CATEGORY_KEYS.forEach(k => { state.categories[k] = true; });
    state.newsDeskOn = true;
    syncUi();
    savePrefs();
    scheduleRender();
  }

  function clearFilters() {
    ALL_CATEGORY_KEYS.forEach(k => { state.categories[k] = false; });
    state.newsDeskOn = false;
    state.medalFilter = 'all';
    state.search = '';
    state.borough = 'all';
    state.sort = 'priority';
    state.dateMode = 'today';
    state.listShown = LIST_PAGE;
    if (els.searchInput) {
      els.searchInput.value = '';
    }
    syncUi();
    buildBoroughs();
    buildDateChips();
    savePrefs();
    scheduleRender();
  }

  function bugReportMailto() {
    const categoriesOn = ALL_CATEGORY_KEYS.filter(k => state.categories[k]);
    const categorySummary = categoriesOn.length === ALL_CATEGORY_KEYS.length
      ? 'All'
      : (categoriesOn.join(', ') || 'None');
    const center = map.getCenter();
    const lines = [
      `Map URL: ${location.href}`,
      `Selected date: ${selectedDateKey()}`,
      `Categories: ${categorySummary}`,
      `Borough: ${state.borough}`,
      `Sort: ${state.sort}`,
      `Feed state: ${state.feedPhase}${state.feedSource ? ` (${state.feedSource})` : ''}`,
      `Browser: ${navigator.userAgent}`,
      `Screen: ${window.innerWidth}x${window.innerHeight}`,
      `Timestamp: ${new Date().toISOString()}`,
      `App version: ${VERSION}`,
      `Map center: ${center.lat.toFixed(4)}, ${center.lng.toFixed(4)}`,
      `Map zoom: ${map.getZoom()}`,
      '',
      'What happened?',
      ''
    ];
    return `mailto:${BUG_REPORT_EMAIL}?subject=${encodeURIComponent('Bug Found')}&body=${encodeURIComponent(lines.join('\n'))}`;
  }

  function bindUi() {
    els.layersBtn?.addEventListener('click', () => setLayers(els.layersPanel.hidden));
    els.deskBtn?.addEventListener('click', () => setDesk(els.deskDrawer.hidden));
    els.closeDeskBtn?.addEventListener('click', () => setDesk(false));
    els.locateBtn?.addEventListener('click', () => locateUser());
    els.nearMeBtn?.addEventListener('click', () => locateUser({ sortNear: true }));
    window.addEventListener('nycif:display-mode', (event) => {
      if (event.detail?.mobile) {
        setDesk(false);
        setLayers(false);
      }
    });
    els.bugBtn?.addEventListener('click', () => {
      window.location.href = bugReportMailto();
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
    els.enableAllBtn?.addEventListener('click', enableAllCategories);
    els.resetFiltersBtn?.addEventListener('click', clearFilters);
    els.retryFeedBtn?.addEventListener('click', () => bootFeeds());
    els.newsDeskToggle?.addEventListener('change', onNewsDeskToggle);
    els.editorsPicks?.addEventListener('change', onEditorsPicksChange);
    map.on('moveend', onMapMoveEnd);
  }

  async function boot() {
    loadPrefs();
    syncUi();
    bindUi();
    buildBoroughs();
    buildDateChips();
    await bootFeeds();
    // News Desk + Editor's Picks signals load after the core feed (non-blocking).
    loadNewsDeskSignals();
    window.NYCIF_UNIFIED_VIEWER = {
      version: VERSION,
      getSummary: () => ({
        total: state.events.length,
        major: state.events.filter(e => e.isMajor && !e.isReview).length,
        approved: state.events.filter(e => !e.isReview).length,
        review: state.events.filter(e => e.isReview).length,
        operatorDesk: isOperatorDesk(),
        mapReady: state.events.filter(e => e.mapReady).length,
        listOnly: state.events.filter(e => !e.mapReady).length,
        markerObjects: state.markerObjects,
        peakMarkerObjects: state.peakMarkerObjects,
        cluster: useCluster,
        indexComplete: state.indexComplete,
        pagesLoaded: state.pagesLoaded,
        pagesTotal: state.pagesTotal,
        feedPhase: state.feedPhase,
        feedSource: state.feedSource,
        lastGoodLoadAt: state.lastGoodLoadAt,
        selectedDate: selectedDateKey(),
        newsDeskLoaded: state.newsDeskLoaded,
        newsDeskCount: state.events.filter(e => e.newsDesk).length,
        medals: {
          gold: state.events.filter(e => e.medal === 'gold').length,
          silver: state.events.filter(e => e.medal === 'silver').length,
          bronze: state.events.filter(e => e.medal === 'bronze').length
        },
        timings: state.timings
      })
    };
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot, { once: true });
  }
  else boot();
})();
