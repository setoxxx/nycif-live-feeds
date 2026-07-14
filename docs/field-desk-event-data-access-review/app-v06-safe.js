const VERSION = '0.8-event-data-access-v01';
const NYC_CENTER = [40.7128, -74.0060];
const STORAGE_KEY = 'nycif-field-desk-state-v06-safe';
const PUBLIC_DEFAULT_VERSION = 'staged-live-v04';
/** Soft safety for rare non-viewport paths; viewport rendering is preferred. */
const PUBLIC_MARKER_CAP = 12000;
const VIEW_MARKER_CAP = 700;
const LIST_PAGE_SIZE = 80;
const FEEDS = {
  staged: 'https://raw.githubusercontent.com/setoxxx/nycif-live-feeds/main/data/nycif_staged_live_events.json',
  full: 'https://raw.githubusercontent.com/setoxxx/nycif-live-feeds/main/nycif_all_radar_map_events.json',
  major: 'https://raw.githubusercontent.com/setoxxx/nycif-live-feeds/main/nycif_major_radar_map_events.json'
};
const DELTA_REPORT_URL = 'https://raw.githubusercontent.com/setoxxx/nycif-live-feeds/main/data/live_delta_report.json';
const BOROUGHS = ['All', 'Manhattan', 'Brooklyn', 'Queens', 'Bronx', 'Staten Island'];
const DAY_NAMES = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const SUPPORTED_CATS = ['sports', 'parade', 'market', 'arts', 'parks', 'fitness', 'general'];
const DEBUG_MAP = (() => {
  try { return new URL(location.href).searchParams.get('debugMap') === '1'; }
  catch { return false; }
})();

const state = {
  feed: 'staged',
  events: [],
  feedRawRows: 0,
  feedRejected: { missingCoords: 0, outsideBounds: 0, invalidShape: 0 },
  search: '',
  borough: 'all',
  sort: 'priority',
  dateMode: 'next7',
  userLocation: null,
  categories: { sports: true, parade: true, market: true, arts: true, parks: true, fitness: true, general: true },
  majorOnly: false,
  photoOnly: false,
  nypdOnly: false,
  newOnly: false,
  newlyAddedKeys: new Set(),
  deltaAddedCount: 0,
  maxMarkers: PUBLIC_MARKER_CAP,
  userChangedFilters: false,
  feedLoadError: '',
  listLimit: LIST_PAGE_SIZE,
  lastVisible: [],
  markersInView: 0
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
  loadAllBtn: document.getElementById('loadAllBtn'),
  majorOnly: document.getElementById('majorOnly'),
  photoOnly: document.getElementById('photoOnly'),
  nypdOnly: document.getElementById('nypdOnly'),
  newOnly: document.getElementById('newOnly'),
  newOnlyText: document.getElementById('newOnlyText'),
  searchInput: document.getElementById('searchInput'),
  sortSelect: document.getElementById('sortSelect'),
  dateChips: document.getElementById('dateChips'),
  boroughs: document.getElementById('boroughs'),
  listMeta: document.getElementById('listMeta'),
  eventList: document.getElementById('eventList'),
  emptyState: document.getElementById('emptyState')
};

const map = L.map(els.map, { zoomControl: true, closePopupOnClick: false, tap: false }).setView(NYC_CENTER, 11);
window.NYCIF_MAIN_MAP = map;
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { attribution: '&copy; OpenStreetMap contributors' }).addTo(map);
const markers = L.layerGroup().addTo(map);
let userMarker = null;
let userAccuracy = null;
let moveTimer = null;

function status(t) { if (els.status) els.status.textContent = t; }
function esc(v) { return String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])); }
function norm(v) { return String(v ?? '').toLowerCase().replace(/\s+/g, ' ').trim(); }
function parseDate(v) { const t = v ? Date.parse(v) : NaN; return Number.isFinite(t) ? new Date(t) : null; }
function dateKey(d) { return d ? `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}` : ''; }
function todayKey() { return dateKey(new Date()); }
function addDays(d, n) { const x = new Date(d); x.setDate(x.getDate() + n); return x; }
function isNYCoord(lat, lng) { return Number.isFinite(lat) && Number.isFinite(lng) && lat >= 40.4774 && lat <= 40.9176 && lng >= -74.2591 && lng <= -73.7004; }
function eventDateKey(row) {
  const direct = String(row.date || '').slice(0, 10);
  if (/^\d{4}-\d{2}-\d{2}$/.test(direct)) return direct;
  const d = parseDate(row.start_date_time || row.start || row.start_time);
  return dateKey(d);
}
function milesBetween(a, b) {
  if (!a || !b) return null;
  const R = 3958.8, toRad = x => x * Math.PI / 180;
  const dLat = toRad(b.lat - a.lat), dLng = toRad(b.lng - a.lng);
  const lat1 = toRad(a.lat), lat2 = toRad(b.lat);
  const x = Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLng / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(x));
}
function distanceLabel(e) { const m = milesBetween(state.userLocation, e); return Number.isFinite(m) ? (m < .1 ? 'nearby' : `${m.toFixed(m < 10 ? 1 : 0)} mi`) : ''; }
function appleMapsUrl(e) { return `https://maps.apple.com/?daddr=${e.lat},${e.lng}&q=${encodeURIComponent(e.title)}`; }
function googleMapsUrl(e) { return `https://www.google.com/maps/dir/?api=1&destination=${e.lat},${e.lng}&travelmode=driving`; }

function category(row) {
  const preset = norm(row.category);
  if (SUPPORTED_CATS.includes(preset)) {
    return {
      key: preset,
      emoji: { sports: '🏟️', parade: '📣', market: '🛍️', arts: '🎭', parks: '🌳', fitness: '💪', general: '📍' }[preset],
      label: { sports: 'Sports', parade: 'Parades / civic', market: 'Street fairs / markets', arts: 'Arts / performance', parks: 'Parks / family', fitness: 'Fitness / wellness', general: 'General' }[preset]
    };
  }
  const text = norm([row.title, row.event_type, row.type, row.location, row.display_location, row.lane, row.nypd_notice, row.verification_status, row.icon].join(' '));
  const icon = row.icon || '';
  const sport = /\b(softball|baseball|basketball|soccer|football|hockey|tennis|lacrosse|cricket|volleyball|kickball|rugby|little league|athletic race|sport - youth|sport - adult)\b/.test(text);
  if (icon === '🌈' || /pride/.test(text)) return { key: 'parade', emoji: '🌈', label: 'Pride / parade' };
  if (sport || icon === '🏟️' || /world cup|fifa|fan zone|race|marathon|yankee|citi field/.test(text)) return { key: 'sports', emoji: icon || '🏟️', label: 'Sports' };
  if (/yoga|zumba|pilates|fitness|workout|aerobics|exercise|calisthenics|boot camp|bootcamp|barre|spin class|spinning|tai chi|qigong|wellness class|movement class|stretching|shape up nyc|bodyweight/.test(text)) return { key: 'fitness', emoji: '💪', label: 'Fitness / wellness' };
  if (icon === '📣' || /parade|march|rally|vigil|ceremony|memorial|civic|street event|block party/.test(text)) return { key: 'parade', emoji: icon || '📣', label: 'Parades / civic' };
  if (icon === '🛍️' || /market|food|vendor|feast|fair|merchandise|pop[- ]?up/.test(text)) return { key: 'market', emoji: icon || '🛍️', label: 'Street fairs / markets' };
  if (icon === '🎭' || /music|concert|arts|dance|theater|theatre|film|production|performance/.test(text)) return { key: 'arts', emoji: icon || '🎭', label: 'Arts / performance' };
  if (icon === '🌳' || /park|family|kids|children|beach|garden|nature/.test(text)) return { key: 'parks', emoji: icon || '🌳', label: 'Parks / family' };
  return { key: 'general', emoji: icon || '📍', label: 'General' };
}

function isNypd(e) { return e.verification_status === 'nypd_field_intel' || /nypd/i.test(e.source_file || '') || e._manual_priority === 'NYPD' || /NYPD Field Intel/i.test(e.title || ''); }
function isPhotoPick(e) { return e.photo_pick === true || e.photoPick === true || /world cup|fan zone|pride|parade|march|street fair|festival|market|rally|vigil|ceremony|waterfront|dumbo|rockefeller|hudson yards|citi field|yankee|criterium/.test(e.searchText); }
function priority(e) {
  let s = Number.parseInt(e.expected_crowd_score || e.priority_score || 0, 10) || 0;
  if (isNypd(e)) s += 1000;
  if (e.photoPick) s += 250;
  if (e.crowd_level === 'very_high') s += 400;
  if (e.crowd_level === 'high') s += 260;
  if (e.crowd_level === 'medium_high') s += 160;
  if (e.category.key === 'parade') s += 75;
  if (e.category.key === 'market') s += 45;
  return s;
}
function crowdLabel(e) { return [String(e.crowd_level || '').replace('_', ' '), e.major_reason || ''].filter(Boolean).join(' — '); }
function photoPriority(e) {
  if (isNypd(e) || e.crowd_level === 'very_high' || e.priority >= 1100) return 'Must shoot';
  if (e.photoPick || e.crowd_level === 'high' || e.crowd_level === 'medium_high') return 'Good if nearby';
  return 'Optional';
}
function deltaKey(row) {
  const d = String(row.id || row.source_event_id || '').trim();
  return d || [row.title, row.borough, row.display_location || row.location, row.date, row.start_date_time].map(v => String(v || '').trim().toLowerCase()).join('|');
}

function makeEvent(row, i) {
  if (!row || typeof row !== 'object') {
    state.feedRejected.invalidShape += 1;
    return null;
  }
  const lat = Number.parseFloat(row.lat ?? row.latitude);
  const lng = Number.parseFloat(row.lng ?? row.longitude);
  if (!Number.isFinite(lat) || !Number.isFinite(lng)) {
    state.feedRejected.missingCoords += 1;
    return null;
  }
  if (!isNYCoord(lat, lng)) {
    state.feedRejected.outsideBounds += 1;
    return null;
  }
  const cat = category(row);
  const dk = eventDateKey(row);
  const start = parseDate(row.start_date_time || row.start || row.date);
  const title = row.title || row.name || 'Untitled event';
  const location = row.display_location || row.location || row.address || '';
  const e = {
    ...row,
    id: String(row.id || row.source_event_id || `event-${i}`),
    title,
    location,
    borough: row.borough || '',
    type: row.event_type || row.type || '',
    lat,
    lng,
    start,
    dateKey: dk,
    category: cat,
    searchText: norm([title, location, row.borough, row.event_type, row.type, row.lane, row.nypd_notice, row.verification_status, row.source_file, row.major_reason, row.crowd_level, cat.label].join(' ')),
    marker: null
  };
  if (row.staged_feed && !e.assignment_feed) e.assignment_feed = 'staged';
  e.photoPick = isPhotoPick(e);
  e.priority = priority(e);
  e.newlyAdded = state.newlyAddedKeys.has(deltaKey(row));
  return e;
}

function timeLabel(d) { return d ? d.toLocaleString([], { weekday: 'short', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }) : 'Time not listed'; }
function assignmentText(e) {
  return ['NYCIF FIELD ASSIGNMENT', e.title, `Time: ${timeLabel(e.start)}`, e.borough ? `Borough: ${e.borough}` : '', e.location ? `Location: ${e.location}` : '', distanceLabel(e) ? `Distance: ${distanceLabel(e)}` : '', `Photo priority: ${photoPriority(e)}`, crowdLabel(e) ? `Assignment read: ${crowdLabel(e)}` : '', isNypd(e) ? 'NYPD intel item' : '', `Apple Maps: ${appleMapsUrl(e)}`, `Google Maps: ${googleMapsUrl(e)}`].filter(Boolean).join('\n');
}
async function copyAssignment(e) {
  try { await navigator.clipboard.writeText(assignmentText(e)); status('Assignment copied.'); }
  catch { window.prompt('Copy assignment:', assignmentText(e)); }
}
function popupHtml(e) {
  const src = isNypd(e) ? 'NYPD Field Intel' : e.assignment_feed === 'staged' ? 'Live feed' : e.assignment_feed === 'major' ? 'Major feed' : 'NYCIF live feed';
  const dist = distanceLabel(e), crowd = crowdLabel(e), url = e.source_url || e.url || e.event_url || '';
  return `<article class="popup-card"><div class="popup-source ${isNypd(e) ? 'is-nypd' : ''}">${esc(src)}${e.newlyAdded ? ' · NEW' : ''}</div><div class="popup-category"><span>${esc(e.category.emoji)}</span> ${esc(e.category.label)}</div><div class="photo-priority ${photoPriority(e).toLowerCase().replaceAll(' ', '-')}">${esc(photoPriority(e))}</div><h2>${esc(e.title)}</h2><dl><div><dt>Time</dt><dd>${esc(timeLabel(e.start))}</dd></div>${dist ? `<div><dt>Distance</dt><dd>${esc(dist)}</dd></div>` : ''}${e.borough ? `<div><dt>Borough</dt><dd>${esc(e.borough)}</dd></div>` : ''}${e.location ? `<div><dt>Location</dt><dd>${esc(e.location)}</dd></div>` : ''}${crowd ? `<div><dt>Assignment read</dt><dd>${esc(crowd)}</dd></div>` : ''}</dl>${e.photoPick ? '<div class="popup-photo">📸 Camera-friendly assignment</div>' : ''}<div class="field-actions"><a class="field-action" target="_blank" rel="noopener" href="${esc(appleMapsUrl(e))}">Apple Maps</a><a class="field-action" target="_blank" rel="noopener" href="${esc(googleMapsUrl(e))}">Google Maps</a><button class="field-action" type="button" data-copy-id="${esc(e.id)}">Copy</button></div>${url ? `<a class="popup-link" target="_blank" rel="noopener" href="${esc(url)}">Source</a>` : ''}</article>`;
}
function makeMarker(e) {
  const cls = ['marker', `marker--${e.category.key}`, e.photoPick ? 'marker--photo' : '', isNypd(e) ? 'marker--nypd' : '', e.newlyAdded ? 'marker--new' : '', e.crowd_level ? `marker--${e.crowd_level}` : ''].filter(Boolean).join(' ');
  return L.marker([e.lat, e.lng], {
    icon: L.divIcon({ className: 'marker-shell', html: `<span class="${cls}"><span class="emoji">${e.category.emoji}</span></span>`, iconSize: [38, 38], iconAnchor: [19, 19], popupAnchor: [0, -24] }),
    title: e.title,
    alt: e.title,
    riseOnHover: true,
    bubblingMouseEvents: false
  }).bindPopup(popupHtml(e), { maxWidth: 330, minWidth: 240, autoPan: true, keepInView: true, closeButton: true, autoClose: false, closeOnClick: false, closeOnEscapeKey: false });
}
function ensureMarker(e) { if (!e.marker) e.marker = makeMarker(e); return e.marker; }

/** Next 7 days = today through today+7 inclusive (8 calendar dates). */
function dayRange() {
  const today = todayKey();
  const end = dateKey(addDays(new Date(), 7));
  return { today, end };
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
function eventMatches(e) {
  return dateMatches(e)
    && !!state.categories[e.category.key]
    && (!state.majorOnly || e.assignment_feed === 'major' || e.field_default || e.photoPick || isNypd(e))
    && (!state.photoOnly || e.photoPick)
    && (!state.nypdOnly || isNypd(e))
    && (!state.newOnly || e.newlyAdded)
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
  if (state.sort === 'type') return (a.type || 'zz').localeCompare(b.type || 'zz') || b.priority - a.priority;
  if (state.sort === 'time') return (a.start?.getTime() || 9999999999999) - (b.start?.getTime() || 9999999999999);
  return b.priority - a.priority || ((a.start?.getTime() || 9999999999999) - (b.start?.getTime() || 9999999999999));
}

function publicDefaults() {
  return {
    borough: 'all', sort: 'priority', dateMode: 'next7',
    categories: { sports: true, parade: true, market: true, arts: true, parks: true, fitness: true, general: true },
    majorOnly: false, photoOnly: false, nypdOnly: false, newOnly: false,
    nycifDefaultVersion: PUBLIC_DEFAULT_VERSION
  };
}
function forceReset() {
  try {
    const u = new URL(location.href);
    return u.searchParams.get('resetFilters') === '1' || u.searchParams.get('v') === 'map-restore-v02' || u.searchParams.get('v') === 'map-access-v01';
  } catch { return false; }
}
function loadPrefs() {
  try {
    if (forceReset()) localStorage.removeItem(STORAGE_KEY);
    const p = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');
    const d = publicDefaults();
    const use = (forceReset() || p.nycifDefaultVersion !== PUBLIC_DEFAULT_VERSION)
      ? d
      : { ...d, ...p, categories: { ...d.categories, ...(p.categories || {}) } };
    Object.assign(state, {
      borough: use.borough, sort: use.sort, dateMode: use.dateMode, categories: use.categories,
      majorOnly: !!use.majorOnly, photoOnly: !!use.photoOnly, nypdOnly: !!use.nypdOnly, newOnly: !!use.newOnly
    });
    savePrefs();
  } catch { Object.assign(state, publicDefaults()); }
}
function savePrefs() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify({
    borough: state.borough,
    sort: state.sort === 'near' && !state.userLocation ? 'priority' : state.sort,
    dateMode: state.dateMode,
    categories: { ...state.categories },
    majorOnly: state.majorOnly, photoOnly: state.photoOnly, nypdOnly: state.nypdOnly, newOnly: state.newOnly,
    nycifDefaultVersion: PUBLIC_DEFAULT_VERSION
  }));
}

function countByDateMode(mode) {
  const prev = state.dateMode;
  state.dateMode = mode;
  const n = state.events.filter(dateMatches).length;
  state.dateMode = prev;
  return n;
}

function updateChrome(visible) {
  const newCount = visible.filter(e => e.newlyAdded).length;
  const nypdCount = visible.filter(isNypd).length;
  const photoCount = visible.filter(e => e.photoPick).length;
  if (els.brandCount) {
    els.brandCount.textContent = `${visible.length.toLocaleString()} live${newCount ? ` · ${newCount.toLocaleString()} new` : ''}${nypdCount ? ` · ${nypdCount.toLocaleString()} NYPD` : ''}${photoCount ? ` · ${photoCount.toLocaleString()} photo` : ''}`;
  }
  const dateLabel = state.dateMode === 'next7' ? 'Next 7 days' : state.dateMode === 'all' ? 'All upcoming' : state.dateMode;
  status(`${state.events.length.toLocaleString()} feed · ${visible.length.toLocaleString()} match · ${state.markersInView.toLocaleString()} markers in view · ${state.feed} · ${dateLabel} · v${VERSION}`);
}

function paddedBounds() {
  const b = map.getBounds().pad(0.15);
  return b;
}

function eventsInViewport(visible) {
  if (!visible.length) return [];
  let bounds;
  try { bounds = paddedBounds(); } catch { return visible.slice(0, VIEW_MARKER_CAP); }
  const inView = [];
  for (const e of visible) {
    if (bounds.contains([e.lat, e.lng])) {
      inView.push(e);
      if (inView.length >= VIEW_MARKER_CAP) break;
    }
  }
  // If zoomed out so far that few/no markers match quickly, fall back to top-priority sample.
  if (inView.length < 40 && visible.length > inView.length) {
    const extras = visible.filter(e => !inView.includes(e)).slice(0, Math.min(VIEW_MARKER_CAP - inView.length, 200));
    return inView.concat(extras);
  }
  return inView;
}

function drawMarkers(visible) {
  markers.clearLayers();
  const draw = eventsInViewport(visible);
  draw.forEach(e => markers.addLayer(ensureMarker(e)));
  state.markersInView = draw.length;
  return draw;
}

function emptyActionsHtml() {
  return `<div class="empty empty--filters" role="status">
    <p>Events exist, but this date/filter/search combination shows none.</p>
    <div class="empty-actions">
      <button type="button" data-empty-action="all-categories">Enable all categories</button>
      <button type="button" data-empty-action="next7">Return to next 7 days</button>
      <button type="button" data-empty-action="all-dates">Show all upcoming</button>
      <button type="button" data-empty-action="reset">Reset filters</button>
      <button type="button" data-empty-action="reload">Reload feed</button>
    </div>
  </div>`;
}

function bindEmptyActions(root) {
  root.querySelectorAll('[data-empty-action]').forEach(btn => {
    btn.addEventListener('click', () => {
      const a = btn.dataset.emptyAction;
      if (a === 'all-categories') Object.keys(state.categories).forEach(k => { state.categories[k] = true; });
      if (a === 'next7') state.dateMode = 'next7';
      if (a === 'all-dates') state.dateMode = 'all';
      if (a === 'reset') Object.assign(state, publicDefaults());
      if (a === 'reload') { bootFeeds(); return; }
      state.userChangedFilters = true;
      state.search = '';
      if (els.searchInput) els.searchInput.value = '';
      state.listLimit = LIST_PAGE_SIZE;
      syncUiFromState();
      buildDateChips();
      savePrefs();
      render();
    });
  });
}

function renderList(visible) {
  const shown = visible.slice(0, state.listLimit);
  const remaining = Math.max(0, visible.length - shown.length);
  if (!visible.length) {
    els.eventList.innerHTML = state.feedLoadError
      ? `<div class="empty empty--error" role="alert"><p>${esc(state.feedLoadError)}</p><div class="empty-actions"><button type="button" data-empty-action="reload">Reload feed</button></div></div>`
      : emptyActionsHtml();
    bindEmptyActions(els.eventList);
    return;
  }
  const rows = shown.map(e => {
    const dist = distanceLabel(e);
    return `<button type="button" class="event-item" data-id="${esc(e.id)}"><span class="item-top"><span class="item-source">${esc(e.category.emoji)} ${esc(e.category.label)}</span><span class="item-tags">${e.newlyAdded ? '<span class="item-tag danger">NEW</span>' : ''}${dist ? `<span class="item-tag near">${esc(dist)}</span>` : ''}<span class="item-tag priority-${photoPriority(e).toLowerCase().replaceAll(' ', '-')}">${esc(photoPriority(e))}</span>${e.photoPick ? '<span class="item-tag">📸</span>' : ''}${isNypd(e) ? '<span class="item-tag danger">NYPD</span>' : ''}</span></span><strong>${esc(e.title)}</strong><span>${esc(timeLabel(e.start))}</span><small>${esc([e.borough, e.location, crowdLabel(e)].filter(Boolean).join(' • '))}</small><span class="quick-actions"><a href="${esc(appleMapsUrl(e))}" target="_blank" rel="noopener">Directions</a><button type="button" data-copy-id="${esc(e.id)}">Copy</button></span></button>`;
  }).join('');
  const more = remaining
    ? `<div class="list-more"><button type="button" id="loadMoreEvents">Load more (${Math.min(LIST_PAGE_SIZE, remaining).toLocaleString()} of ${remaining.toLocaleString()} remaining)</button></div>`
    : '';
  els.eventList.innerHTML = rows + more;
  els.eventList.querySelectorAll('[data-id]').forEach(b => b.addEventListener('click', ev => {
    if (ev.target.closest('a,button[data-copy-id]')) return;
    const e = state.events.find(x => x.id === b.dataset.id);
    if (!e) return;
    map.flyTo([e.lat, e.lng], Math.max(map.getZoom(), 15), { duration: .55 });
    setTimeout(() => { ensureMarker(e).setPopupContent(popupHtml(e)); ensureMarker(e).openPopup(); if (!markers.hasLayer(e.marker)) markers.addLayer(e.marker); }, 420);
    setDesk(false);
  }));
  els.eventList.querySelectorAll('[data-copy-id]').forEach(b => b.addEventListener('click', ev => {
    ev.stopPropagation();
    const e = state.events.find(x => x.id === b.dataset.copyId);
    if (e) copyAssignment(e);
  }));
  const moreBtn = document.getElementById('loadMoreEvents');
  if (moreBtn) moreBtn.addEventListener('click', () => {
    state.listLimit += LIST_PAGE_SIZE;
    renderList(state.lastVisible);
    els.listMeta.textContent = `Showing ${Math.min(state.listLimit, state.lastVisible.length).toLocaleString()} of ${state.lastVisible.length.toLocaleString()} matching events · ${state.markersInView.toLocaleString()} markers in view`;
  });
}

function logDebugPipeline(visible) {
  if (!DEBUG_MAP) return;
  const cats = {};
  state.events.forEach(e => { cats[e.category.key] = (cats[e.category.key] || 0) + 1; });
  const table = {
    rawRows: state.feedRawRows,
    accepted: state.events.length,
    rejectedMissingCoords: state.feedRejected.missingCoords,
    rejectedOutsideBounds: state.feedRejected.outsideBounds,
    rejectedInvalidShape: state.feedRejected.invalidShape,
    today: countByDateMode('today'),
    next7: countByDateMode('next7'),
    allUpcoming: countByDateMode('all'),
    filteredMatch: visible.length,
    listRendered: Math.min(state.listLimit, visible.length),
    markersInView: state.markersInView,
    categoryCounts: cats
  };
  console.table(table);
  window.NYCIF_MAP_DEBUG = table;
}

function render() {
  let visible = state.events.filter(eventMatches).sort(sortEvents);
  if (!visible.length && !state.userChangedFilters && state.events.length) {
    const next = state.events.filter(e => e.dateKey >= todayKey() && state.categories[e.category.key]).sort((a, b) => a.dateKey.localeCompare(b.dateKey))[0];
    if (next && state.dateMode === 'today') {
      state.dateMode = 'next7';
      savePrefs();
      buildDateChips();
      visible = state.events.filter(eventMatches).sort(sortEvents);
    }
  }
  state.lastVisible = visible;
  drawMarkers(visible);
  const newCount = visible.filter(e => e.newlyAdded).length;
  const photoCount = visible.filter(e => e.photoPick).length;
  const nypdCount = visible.filter(isNypd).length;
  els.listMeta.textContent = `Showing ${Math.min(state.listLimit, visible.length).toLocaleString()} of ${visible.length.toLocaleString()} matching events · ${state.markersInView.toLocaleString()} markers in view · ${newCount.toLocaleString()} newly added · ${photoCount.toLocaleString()} photo · ${nypdCount.toLocaleString()} NYPD`;
  renderList(visible);
  updateChrome(visible);
  logDebugPipeline(visible);
  return visible;
}

async function loadDeltaReport() {
  try {
    const r = await fetch(`${DELTA_REPORT_URL}?cache=${Date.now()}`, { headers: { Accept: 'application/json' }, cache: 'no-store' });
    if (!r.ok) throw new Error(`delta HTTP ${r.status}`);
    const j = await r.json();
    const added = Array.isArray(j.added_events) ? j.added_events : [];
    const keys = new Set();
    added.forEach(row => [row.id, row.source_event_id, deltaKey(row)].forEach(v => { const k = String(v || '').trim(); if (k) keys.add(k); }));
    state.newlyAddedKeys = keys;
    state.deltaAddedCount = Number(j.added_count ?? added.length) || added.length;
    if (els.newOnlyText) els.newOnlyText.textContent = `🆕 Newly added only (${state.deltaAddedCount.toLocaleString()})`;
  } catch { state.newlyAddedKeys = new Set(); }
}

async function loadFeed(kind) {
  const url = FEEDS[kind];
  status(`Loading ${kind} feed…`);
  const t0 = performance.now();
  const r = await fetch(`${url}?cache=${Date.now()}`, { headers: { Accept: 'application/json' }, cache: 'no-store' });
  if (!r.ok) throw new Error(`${kind} feed HTTP ${r.status}`);
  const j = await r.json();
  const rows = Array.isArray(j) ? j : (j.events || []);
  state.feedRawRows = rows.length;
  state.feedRejected = { missingCoords: 0, outsideBounds: 0, invalidShape: 0 };
  const tParse = performance.now();
  state.events = rows.map(makeEvent).filter(Boolean);
  const tClass = performance.now();
  state.feed = kind;
  state.feedLoadError = '';
  state.maxMarkers = PUBLIC_MARKER_CAP;
  state.listLimit = LIST_PAGE_SIZE;
  const visible = render();
  if (visible.length) {
    try { map.fitBounds(visible.slice(0, 250).map(e => [e.lat, e.lng]), { padding: [44, 44], maxZoom: 12 }); } catch {}
  }
  setTimeout(() => map.invalidateSize(), 120);
  if (DEBUG_MAP) {
    console.log('NYCIF feed timings ms', {
      fetchParse: Math.round(tParse - t0),
      classify: Math.round(tClass - tParse),
      total: Math.round(performance.now() - t0)
    });
  }
}

async function bootFeeds() {
  for (const kind of ['staged', 'full', 'major']) {
    try {
      await loadFeed(kind);
      return;
    } catch (e) {
      state.feedLoadError = `${kind} feed failed: ${e.message}`;
      status(state.feedLoadError);
    }
  }
  state.events = [];
  state.feedLoadError = `All map feeds failed. ${state.feedLoadError}`;
  render();
}

function syncUiFromState() {
  if (els.majorOnly) els.majorOnly.checked = state.majorOnly;
  if (els.photoOnly) els.photoOnly.checked = state.photoOnly;
  if (els.nypdOnly) els.nypdOnly.checked = state.nypdOnly;
  if (els.newOnly) els.newOnly.checked = state.newOnly;
  if (els.sortSelect) els.sortSelect.value = state.sort;
  document.querySelectorAll('[data-cat]').forEach(i => { i.checked = !!state.categories[i.dataset.cat]; });
}
function setLayers(open) { els.layersPanel.hidden = !open; els.layersBtn.setAttribute('aria-expanded', String(open)); setTimeout(() => map.invalidateSize(), 100); }
function setDesk(open) { els.deskDrawer.hidden = !open; els.deskBtn.setAttribute('aria-expanded', String(open)); setTimeout(() => map.invalidateSize(), 100); }
function buildBoroughs() {
  els.boroughs.innerHTML = BOROUGHS.map(b => {
    const v = b === 'All' ? 'all' : b;
    return `<button type="button" class="${state.borough === v ? 'active' : ''}" data-borough="${esc(v)}">${esc(b)}</button>`;
  }).join('');
  els.boroughs.addEventListener('click', ev => {
    const b = ev.target.closest('[data-borough]');
    if (!b) return;
    state.userChangedFilters = true;
    state.borough = b.dataset.borough;
    state.listLimit = LIST_PAGE_SIZE;
    els.boroughs.querySelectorAll('button').forEach(x => x.classList.toggle('active', x === b));
    savePrefs();
    render();
  });
}
function chipText(d) { return `${DAY_NAMES[d.getDay()]} ${d.getMonth() + 1}/${d.getDate()}`; }
function buildDateChips() {
  const days = Array.from({ length: 8 }, (_, i) => addDays(new Date(), i));
  const next7Count = state.events.length ? countByDateMode('next7') : null;
  const allCount = state.events.length ? countByDateMode('all') : null;
  const todayCount = state.events.length ? countByDateMode('today') : null;
  const labelCount = (label, n) => (n == null ? label : `${label} (${n.toLocaleString()})`);
  els.dateChips.innerHTML = `<div class="date-chip-track"><button type="button" data-date-mode="next7" class="${state.dateMode === 'next7' ? 'active' : ''}">${esc(labelCount('Next 7 days', next7Count))}</button>${days.map((d, i) => {
    const k = dateKey(d);
    const n = state.events.length ? state.events.filter(e => e.dateKey === k).length : null;
    const label = i === 0 ? labelCount('Today', todayCount ?? n) : (n == null ? chipText(d) : `${chipText(d)} (${n.toLocaleString()})`);
    return `<button type="button" data-date-mode="${esc(k)}" data-date-key="${esc(k)}" class="${state.dateMode === k ? 'active' : ''}">${esc(label)}</button>`;
  }).join('')}<button type="button" data-date-mode="all" class="${state.dateMode === 'all' ? 'active' : ''}">${esc(labelCount('All upcoming', allCount))}</button></div>`;
  if (!els.dateChips.dataset.bound) {
    els.dateChips.dataset.bound = '1';
    els.dateChips.addEventListener('click', ev => {
      const b = ev.target.closest('[data-date-mode]');
      if (!b) return;
      state.userChangedFilters = true;
      state.dateMode = b.dataset.dateMode;
      state.listLimit = LIST_PAGE_SIZE;
      savePrefs();
      render();
      buildDateChips();
    });
  }
}
function setUserLocation(lat, lng, accuracy) {
  const here = [lat, lng];
  state.userLocation = { lat, lng };
  if (userMarker) userMarker.setLatLng(here);
  else userMarker = L.marker(here, { icon: L.divIcon({ className: 'user-location-shell', html: '<span class="user-location">🗽</span>', iconSize: [36, 44], iconAnchor: [18, 42], popupAnchor: [0, -38] }), zIndexOffset: 4000 }).addTo(map).bindPopup(`<strong>You are here</strong><br>Accuracy: ${Math.round(accuracy || 0)} meters`);
  if (userAccuracy) { userAccuracy.setLatLng(here); userAccuracy.setRadius(accuracy || 0); }
  else userAccuracy = L.circle(here, { radius: accuracy || 0, color: '#d40000', weight: 2, fillColor: '#d40000', fillOpacity: .08 }).addTo(map);
}
function locateUser(options = {}) {
  if (!navigator.geolocation) { status('Location is not available in this browser.'); return; }
  status('Finding your location…');
  navigator.geolocation.getCurrentPosition(pos => {
    const { latitude, longitude, accuracy } = pos.coords;
    setUserLocation(latitude, longitude, accuracy);
    if (options.sortNear) { state.sort = 'near'; els.sortSelect.value = 'near'; savePrefs(); }
    map.flyTo([latitude, longitude], Math.max(map.getZoom(), 14), { duration: .6 });
    userMarker.openPopup();
    render();
  }, err => status(`Location failed: ${err.message}`), { enableHighAccuracy: true, timeout: 12000, maximumAge: 15000 });
}

function bindUi() {
  els.layersBtn.addEventListener('click', () => setLayers(els.layersPanel.hidden));
  els.deskBtn.addEventListener('click', () => setDesk(els.deskDrawer.hidden));
  els.closeDeskBtn.addEventListener('click', () => setDesk(false));
  els.locateBtn.addEventListener('click', () => locateUser());
  els.nearMeBtn.addEventListener('click', () => locateUser({ sortNear: true }));
  if (els.loadAllBtn) els.loadAllBtn.addEventListener('click', () => loadFeed('full').catch(e => status(`Full feed failed: ${e.message}`)));
  [els.majorOnly, els.photoOnly, els.nypdOnly, els.newOnly].filter(Boolean).forEach(i => i.addEventListener('change', () => {
    state.userChangedFilters = true;
    state[i.id] = i.checked;
    state.listLimit = LIST_PAGE_SIZE;
    savePrefs();
    render();
  }));
  document.querySelectorAll('[data-cat]').forEach(i => i.addEventListener('change', () => {
    state.userChangedFilters = true;
    state.categories[i.dataset.cat] = i.checked;
    state.listLimit = LIST_PAGE_SIZE;
    savePrefs();
    render();
  }));
  els.searchInput.addEventListener('input', () => {
    state.userChangedFilters = true;
    state.search = norm(els.searchInput.value);
    state.listLimit = LIST_PAGE_SIZE;
    render();
  });
  els.sortSelect.addEventListener('change', () => {
    state.userChangedFilters = true;
    state.sort = els.sortSelect.value;
    savePrefs();
    if (state.sort === 'near' && !state.userLocation) locateUser({ sortNear: true });
    else render();
  });
  document.addEventListener('click', ev => {
    const b = ev.target.closest('[data-copy-id]');
    if (!b) return;
    const e = state.events.find(x => x.id === b.dataset.copyId);
    if (e) copyAssignment(e);
  });
  map.on('moveend zoomend', () => {
    clearTimeout(moveTimer);
    moveTimer = setTimeout(() => {
      if (!state.lastVisible.length) return;
      drawMarkers(state.lastVisible);
      updateChrome(state.lastVisible);
      els.listMeta.textContent = `Showing ${Math.min(state.listLimit, state.lastVisible.length).toLocaleString()} of ${state.lastVisible.length.toLocaleString()} matching events · ${state.markersInView.toLocaleString()} markers in view`;
    }, 120);
  });
}

async function boot() {
  loadPrefs();
  await loadDeltaReport();
  syncUiFromState();
  bindUi();
  buildBoroughs();
  buildDateChips();
  if ('serviceWorker' in navigator) navigator.serviceWorker.register('./service-worker.js').catch(() => {});
  await bootFeeds();
  buildDateChips();
}
boot();
