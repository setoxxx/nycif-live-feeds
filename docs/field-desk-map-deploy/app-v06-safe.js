const VERSION = '0.7-staged-live-m10';
const NYC_CENTER = [40.7128, -74.0060];
const STORAGE_KEY = 'nycif-field-desk-state-v06-safe';
const PUBLIC_DEFAULT_VERSION = 'staged-live-v02';

const FEEDS = {
  major: 'https://raw.githubusercontent.com/setoxxx/nycif-live-feeds/main/nycif_major_radar_map_events.json',
  full: 'https://raw.githubusercontent.com/setoxxx/nycif-live-feeds/main/nycif_all_radar_map_events.json',
  staged: 'https://raw.githubusercontent.com/setoxxx/nycif-live-feeds/main/data/nycif_staged_live_events.json'
};
const DELTA_REPORT_URL = 'https://raw.githubusercontent.com/setoxxx/nycif-live-feeds/main/data/live_delta_report.json';

const BOROUGHS = ['All', 'Manhattan', 'Brooklyn', 'Queens', 'Bronx', 'Staten Island'];
const DAY_NAMES = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

const state = {
  feed: 'major',
  events: [],
  fullLoaded: false,
  stagedLoaded: false,
  search: '',
  borough: 'all',
  sort: 'priority',
  dateMode: 'today',
  userLocation: null,
  categories: { sports: true, parade: true, market: true, arts: true, parks: false, general: false, fitness: false },
  majorOnly: false,
  photoOnly: false,
  nypdOnly: false,
  newOnly: false,
  newlyAddedKeys: new Set(),
  deltaAddedCount: 0,
  deltaGeneratedAt: null,
  maxMarkers: 650
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
  stagedFeedBtn: null,
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
  eventList: document.getElementById('eventList')
};

const map = L.map(els.map, { zoomControl: true, closePopupOnClick: false, tap: false }).setView(NYC_CENTER, 11);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { attribution: '&copy; OpenStreetMap contributors' }).addTo(map);

const markers = L.layerGroup().addTo(map);
let userMarker = null;
let userAccuracy = null;

function status(text) { els.status.textContent = text; }
function esc(value) { return String(value ?? '').replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch])); }
function normalize(value) { return String(value ?? '').toLowerCase().replace(/\s+/g, ' ').trim(); }
function parseDate(value) { const t = value ? Date.parse(value) : NaN; return Number.isFinite(t) ? new Date(t) : null; }
function dateKey(date) { if (!date) return ''; return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`; }
function todayKey() { return dateKey(new Date()); }
function tomorrowKey() { const d = new Date(); d.setDate(d.getDate() + 1); return dateKey(d); }
function addDays(date, days) { const d = new Date(date); d.setDate(d.getDate() + days); return d; }
function weekStartSunday(date) { const d = new Date(date); d.setHours(0, 0, 0, 0); d.setDate(d.getDate() - d.getDay()); return d; }
function isWeekendDate(date) { return !!date && (date.getDay() === 0 || date.getDay() === 6); }
function timeLabel(date) { return date ? date.toLocaleString([], { weekday: 'short', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }) : 'Time not listed'; }
function isNYCoord(lat, lng) { return Number.isFinite(lat) && Number.isFinite(lng) && lat >= 40.4774 && lat <= 40.9176 && lng >= -74.2591 && lng <= -73.7004; }

function milesBetween(a, b) {
  if (!a || !b) return null;
  const R = 3958.8;
  const toRad = deg => deg * Math.PI / 180;
  const dLat = toRad(b.lat - a.lat);
  const dLng = toRad(b.lng - a.lng);
  const lat1 = toRad(a.lat);
  const lat2 = toRad(b.lat);
  const x = Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLng / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(x));
}

function distanceLabel(event) {
  if (!state.userLocation) return '';
  const miles = milesBetween(state.userLocation, event);
  if (!Number.isFinite(miles)) return '';
  return miles < 0.1 ? 'nearby' : `${miles.toFixed(miles < 10 ? 1 : 0)} mi`;
}

function appleMapsUrl(event) { return `https://maps.apple.com/?daddr=${event.lat},${event.lng}&q=${encodeURIComponent(event.title)}`; }
function googleMapsUrl(event) { return `https://www.google.com/maps/dir/?api=1&destination=${event.lat},${event.lng}&travelmode=driving`; }

function category(row) {
  const preset = String(row.category || '').toLowerCase();
  if (preset === 'sports') return { key: 'sports', emoji: '🏟️', label: 'Sports / World Cup' };
  if (preset === 'parade') return { key: 'parade', emoji: '📣', label: 'Parade / civic' };
  if (preset === 'market') return { key: 'market', emoji: '🛍️', label: 'Market / street fair' };
  if (preset === 'arts') return { key: 'arts', emoji: '🎭', label: 'Arts / production' };
  if (preset === 'parks') return { key: 'parks', emoji: '🌳', label: 'Parks / family' };
  if (preset === 'fitness') return { key: 'fitness', emoji: '💪', label: 'Fitness / wellness' };
  const text = normalize([row.title, row.event_type, row.type, row.location, row.display_location, row.lane, row.nypd_notice, row.verification_status, row.icon].join(' '));
  const icon = row.icon || '';
  if (icon === '🌈' || /pride/.test(text)) return { key: 'parade', emoji: '🌈', label: 'Pride / parade' };
  if (icon === '🚴' || /criterium|cycling|bike/.test(text)) return { key: 'sports', emoji: '🚴', label: 'Cycling / sports' };
  if (icon === '🏟️' || /world cup|fifa|fan zone|sport|soccer|race|marathon|run|walk|yankee|citi field/.test(text)) return { key: 'sports', emoji: icon || '🏟️', label: 'Sports / World Cup' };
  if (icon === '📣' || /parade|march|rally|vigil|ceremony|memorial|civic|street event|block party/.test(text)) return { key: 'parade', emoji: icon || '📣', label: 'Parade / civic' };
  if (icon === '🛍️' || /market|food|vendor|feast|fair|merchandise|pop[- ]?up/.test(text)) return { key: 'market', emoji: icon || '🛍️', label: 'Market / street fair' };
  if (icon === '🎭' || /music|concert|arts|dance|theater|theatre|film|production|performance/.test(text)) return { key: 'arts', emoji: icon || '🎭', label: 'Arts / production' };
  if (/yoga|zumba|fitness|workout|pilates|crossfit|aerobic|exercise|calisthenics|boot camp|bootcamp|barre|spin class|spinning|tai chi|qigong|wellness class|movement class|stretching|training session/.test(text)) {
    return { key: 'fitness', emoji: '💪', label: 'Fitness / wellness' };
  }
  if (icon === '🌳' || /park|family|kids|children|beach|garden|nature/.test(text)) return { key: 'parks', emoji: icon || '🌳', label: 'Parks / family' };
  return { key: 'general', emoji: icon || '📍', label: 'General event' };
}

function isNypd(event) { return event.verification_status === 'nypd_field_intel' || /nypd/i.test(event.source_file || '') || event._manual_priority === 'NYPD' || /NYPD Field Intel/i.test(event.title || ''); }
function isPhotoPick(event) { return event.photo_pick === true || event.photoPick === true || /world cup|fan zone|pride|parade|march|street fair|festival|market|rally|vigil|ceremony|waterfront|dumbo|rockefeller|hudson yards|citi field|yankee|criterium/.test(event.searchText); }

function priority(event) {
  let score = Number.parseInt(event.expected_crowd_score || event.priority_score || 0, 10) || 0;
  if (isNypd(event)) score += 1000;
  if (event.photoPick) score += 250;
  if (event.crowd_level === 'very_high') score += 400;
  if (event.crowd_level === 'high') score += 260;
  if (event.crowd_level === 'medium_high') score += 160;
  if (event.category.key === 'parade') score += 75;
  if (event.category.key === 'market') score += 45;
  return score;
}

function crowdLabel(event) {
  const level = event.crowd_level || '';
  const reason = event.major_reason || '';
  if (!level && !reason) return '';
  return [level.replace('_', ' '), reason].filter(Boolean).join(' — ');
}

function photoPriority(event) {
  if (isNypd(event) || event.crowd_level === 'very_high' || event.priority >= 1100) return 'Must shoot';
  if (event.photoPick || event.crowd_level === 'high' || event.crowd_level === 'medium_high') return 'Good if nearby';
  return 'Optional';
}

function deltaKey(row) {
  const direct = String(row.id || row.source_event_id || '').trim();
  if (direct) return direct;
  return [row.title, row.borough, row.display_location || row.location, row.date, row.start_date_time].map(value => String(value || '').trim().toLowerCase()).join('|');
}

function isNewlyAdded(event) {
  return state.newlyAddedKeys.has(deltaKey(event)) || state.newlyAddedKeys.has(String(event.id || '').trim()) || state.newlyAddedKeys.has(String(event.source_event_id || '').trim());
}

function makeEvent(row, index) {
  const lat = Number.parseFloat(row.lat);
  const lng = Number.parseFloat(row.lng);
  if (!isNYCoord(lat, lng)) return null;
  const cat = category(row);
  const start = parseDate(row.start_date_time || row.start || row.date);
  const title = row.title || row.name || 'Untitled event';
  const location = row.display_location || row.location || row.address || '';
  const event = { ...row, id: String(row.id || `event-${index}`), title, location, borough: row.borough || '', type: row.event_type || row.type || '', lat, lng, start, dateKey: dateKey(start) || (row.date || row.start_date_time || '').slice(0, 10), category: cat, searchText: normalize([title, location, row.borough, row.event_type, row.type, row.lane, row.nypd_notice, row.verification_status, row.source_file, row.major_reason, row.crowd_level].join(' ')) };
  if (row.staged_feed && !event.assignment_feed) event.assignment_feed = 'staged';
  event.photoPick = isPhotoPick(event);
  event.priority = priority(event);
  event.newlyAdded = isNewlyAdded(event);
  event.marker = null;
  return event;
}

function assignmentText(event) {
  const lines = ['NYCIF FIELD ASSIGNMENT', event.title, `Time: ${timeLabel(event.start)}`, event.borough ? `Borough: ${event.borough}` : '', event.location ? `Location: ${event.location}` : '', distanceLabel(event) ? `Distance: ${distanceLabel(event)}` : '', `Photo priority: ${photoPriority(event)}`, crowdLabel(event) ? `Assignment read: ${crowdLabel(event)}` : '', isNypd(event) ? 'NYPD intel item' : '', event.nypd_notice ? `NYPD note: ${event.nypd_notice}` : '', `Apple Maps: ${appleMapsUrl(event)}`, `Google Maps: ${googleMapsUrl(event)}`, (event.source_url || event.url || event.event_url) ? `Source: ${event.source_url || event.url || event.event_url}` : ''];
  return lines.filter(Boolean).join('\n');
}

async function copyAssignment(event) {
  const text = assignmentText(event);
  try { await navigator.clipboard.writeText(text); status('Assignment copied.'); }
  catch { window.prompt('Copy assignment:', text); status('Copy box opened.'); }
}

function feedLabel() {
  if (state.feed === 'major') return 'Fast major feed';
  if (state.feed === 'full') return 'Full feed';
  if (state.feed === 'staged') return 'Staged deduped feed';
  return 'Live feed';
}

function popupHtml(event) {
  const source = isNypd(event) ? 'NYPD Field Intel' : (event.assignment_feed === 'staged' ? 'Staged Deduped Feed' : event.assignment_feed === 'major' ? 'Major Assignment Feed' : 'NYCIF Live Feed');
  const crowd = crowdLabel(event);
  const nypd = event.nypd_notice || '';
  const sourceUrl = event.source_url || event.url || event.event_url || '';
  const distance = distanceLabel(event);
  return `<article class="popup-card"><div class="popup-source ${isNypd(event) ? 'is-nypd' : ''}">${esc(source)}${event.newlyAdded ? ' · NEW' : ''}</div><div class="popup-category"><span>${esc(event.category.emoji)}</span> ${esc(event.category.label)}</div><div class="photo-priority ${photoPriority(event).toLowerCase().replaceAll(' ', '-')}">${esc(photoPriority(event))}</div><h2>${esc(event.title)}</h2>${isNypd(event) ? '<div class="popup-priority">High-priority field item</div>' : ''}<dl><div><dt>Time</dt><dd>${esc(timeLabel(event.start))}</dd></div>${distance ? `<div><dt>Distance</dt><dd>${esc(distance)}</dd></div>` : ''}${event.borough ? `<div><dt>Borough</dt><dd>${esc(event.borough)}</dd></div>` : ''}${event.location ? `<div><dt>Location</dt><dd>${esc(event.location)}</dd></div>` : ''}${crowd ? `<div><dt>Assignment read</dt><dd>${esc(crowd)}</dd></div>` : ''}</dl>${event.photoPick ? '<div class="popup-photo">📸 Camera-friendly assignment</div>' : ''}${nypd ? `<div class="popup-nypd"><b>NYPD Field Intel:</b> ${esc(nypd)}</div>` : ''}<div class="field-actions"><a class="field-action" target="_blank" rel="noopener" href="${esc(appleMapsUrl(event))}">Apple Maps</a><a class="field-action" target="_blank" rel="noopener" href="${esc(googleMapsUrl(event))}">Google Maps</a><button class="field-action" type="button" data-copy-id="${esc(event.id)}">Copy</button></div>${sourceUrl ? `<a class="popup-link" target="_blank" rel="noopener" href="${esc(sourceUrl)}">Source</a>` : ''}</article>`;
}

function makeMarker(event) {
  const classes = ['marker', `marker--${event.category.key}`, event.photoPick ? 'marker--photo' : '', isNypd(event) ? 'marker--nypd' : '', event.newlyAdded ? 'marker--new' : '', event.crowd_level ? `marker--${event.crowd_level}` : ''].filter(Boolean).join(' ');
  const marker = L.marker([event.lat, event.lng], { icon: L.divIcon({ className: 'marker-shell', html: `<span class="${classes}"><span class="emoji">${event.category.emoji}</span></span>`, iconSize: [38, 38], iconAnchor: [19, 19], popupAnchor: [0, -24] }), title: event.title, alt: event.title, riseOnHover: true, bubblingMouseEvents: false }).bindPopup(popupHtml(event), { maxWidth: 330, minWidth: 240, autoPan: true, keepInView: true, closeButton: true, autoClose: false, closeOnClick: false, closeOnEscapeKey: false });
  marker.on('click tap', ev => { if (ev?.originalEvent) { L.DomEvent.preventDefault(ev.originalEvent); L.DomEvent.stop(ev.originalEvent); } marker.setPopupContent(popupHtml(event)); marker.openPopup(); });
  marker.on('popupopen', ev => { const el = ev?.popup?.getElement?.(); if (!el) return; L.DomEvent.disableClickPropagation(el); L.DomEvent.disableScrollPropagation(el); });
  return marker;
}

function ensureMarker(event) {
  if (!event.marker) event.marker = makeMarker(event);
  return event.marker;
}

function isExactDateMode(value) { return /^\d{4}-\d{2}-\d{2}$/.test(value); }
function dateMatches(event) { if (state.dateMode === 'all') return true; if (!event.dateKey) return false; if (state.dateMode === 'today') return event.dateKey === todayKey(); if (state.dateMode === 'tomorrow') return event.dateKey === tomorrowKey(); if (state.dateMode === 'weekend') return isWeekendDate(event.start); if (isExactDateMode(state.dateMode)) return event.dateKey === state.dateMode; return true; }
function eventMatches(event) { if (!dateMatches(event)) return false; if (!state.categories[event.category.key]) return false; if (state.majorOnly && !(event.assignment_feed === 'major' || event.assignment_feed === 'staged' || event.field_default || event.photoPick || isNypd(event))) return false; if (state.photoOnly && !event.photoPick) return false; if (state.nypdOnly && !isNypd(event)) return false; if (state.newOnly && !event.newlyAdded) return false; if (state.borough !== 'all' && event.borough !== state.borough) return false; if (state.search && !event.searchText.includes(state.search)) return false; return true; }

function sortEvents(a, b) {
  if (state.newOnly) return Number(b.newlyAdded) - Number(a.newlyAdded) || ((a.start?.getTime() || 9999999999999) - (b.start?.getTime() || 9999999999999));
  if (state.sort === 'near') { const da = milesBetween(state.userLocation, a) ?? 999999; const db = milesBetween(state.userLocation, b) ?? 999999; return da - db || b.priority - a.priority; }
  if (state.sort === 'borough') return (a.borough || 'zz').localeCompare(b.borough || 'zz') || b.priority - a.priority;
  if (state.sort === 'type') return (a.type || 'zz').localeCompare(b.type || 'zz') || b.priority - a.priority;
  if (state.sort === 'time') return (a.start?.getTime() || 9999999999999) - (b.start?.getTime() || 9999999999999);
  return b.priority - a.priority || ((a.start?.getTime() || 9999999999999) - (b.start?.getTime() || 9999999999999));
}

function isPublicMapPage() {
  return document.body.classList.contains('public-map-page');
}

function getPublicDefaultPrefs() {
  return {
    borough: 'all',
    sort: 'priority',
    dateMode: 'today',
    categories: { sports: true, parade: true, market: true, arts: true, parks: false, general: false, fitness: false },
    majorOnly: true,
    photoOnly: false,
    nypdOnly: false,
    newOnly: false,
    nycifDefaultVersion: PUBLIC_DEFAULT_VERSION
  };
}

function shouldForcePublicDefaultReset() {
  try {
    const url = new URL(window.location.href);
    const resetFlag = url.searchParams.get('resetFilters');
    const versionFlag = url.searchParams.get('v');
    return resetFlag === '1'
      || versionFlag === 'major-default-qa-01'
      || versionFlag === 'ui-defaults-02'
      || versionFlag === 'c5p-postpublish-02'
      || versionFlag === 'staged-live-v02';
  } catch {
    return false;
  }
}

function applyPublicDefaultPrefsToState() {
  const defaults = getPublicDefaultPrefs();
  state.borough = defaults.borough;
  state.sort = defaults.sort;
  state.dateMode = defaults.dateMode;
  state.categories = { ...defaults.categories };
  state.majorOnly = defaults.majorOnly;
  state.photoOnly = defaults.photoOnly;
  state.nypdOnly = defaults.nypdOnly;
  state.newOnly = defaults.newOnly;
}

function applyPublicPrefsToState(prefs) {
  if (prefs.borough) state.borough = prefs.borough;
  if (prefs.sort) state.sort = prefs.sort;
  if (prefs.dateMode) state.dateMode = prefs.dateMode;
  state.categories = {
    sports: !!prefs.categories?.sports,
    parade: !!prefs.categories?.parade,
    market: !!prefs.categories?.market,
    arts: !!prefs.categories?.arts,
    parks: !!prefs.categories?.parks,
    general: !!prefs.categories?.general,
    fitness: !!prefs.categories?.fitness
  };
  state.majorOnly = !!prefs.majorOnly;
  state.photoOnly = !!prefs.photoOnly;
  state.nypdOnly = !!prefs.nypdOnly;
  state.newOnly = !!prefs.newOnly;
}

function applyLegacyPrefsToState(prefs) {
  if (prefs.borough) state.borough = prefs.borough;
  if (prefs.sort) state.sort = prefs.sort;
  if (prefs.dateMode) state.dateMode = prefs.dateMode;
  if (prefs.categories) state.categories = { ...state.categories, ...prefs.categories };
  state.majorOnly = !!prefs.majorOnly;
  state.photoOnly = !!prefs.photoOnly;
  state.nypdOnly = !!prefs.nypdOnly;
  state.newOnly = !!prefs.newOnly;
}

function loadPublicMapPrefs() {
  const forceReset = shouldForcePublicDefaultReset();
  if (forceReset) localStorage.removeItem(STORAGE_KEY);

  const prefs = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');
  if (forceReset || prefs.nycifDefaultVersion !== PUBLIC_DEFAULT_VERSION) {
    applyPublicDefaultPrefsToState();
    savePrefs();
    return;
  }

  applyPublicPrefsToState(prefs);
}

function savePrefs() {
  const prefs = {
    borough: state.borough,
    sort: state.sort === 'near' && !state.userLocation ? 'priority' : state.sort,
    dateMode: state.dateMode,
    categories: { ...state.categories },
    majorOnly: state.majorOnly,
    photoOnly: state.photoOnly,
    nypdOnly: state.nypdOnly,
    newOnly: state.newOnly
  };
  if (isPublicMapPage()) prefs.nycifDefaultVersion = PUBLIC_DEFAULT_VERSION;
  localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs));
}

function loadPrefs() {
  try {
    if (isPublicMapPage()) {
      loadPublicMapPrefs();
      return;
    }

    applyLegacyPrefsToState(JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}'));
  } catch {}
}

function updateChrome(visible) {
  const nypdCount = visible.filter(isNypd).length;
  const photoCount = visible.filter(e => e.photoPick).length;
  const newCount = visible.filter(e => e.newlyAdded).length;
  const nearNote = state.userLocation && state.sort === 'near' ? ' · near me' : '';
  if (els.brandCount) els.brandCount.textContent = `${visible.length} live${newCount ? ` · ${newCount} new` : ''}${nypdCount ? ` · ${nypdCount} NYPD` : ''}${photoCount ? ` · ${photoCount} photo` : ''}`;
  status(`${visible.length} assignment${visible.length === 1 ? '' : 's'} · ${feedLabel()}${state.newOnly ? ' · newly added only' : ''}${nearNote} · v${VERSION}`);
}

function render() {
  markers.clearLayers();
  const visible = state.events.filter(eventMatches).sort(sortEvents);
  const draw = visible.slice(0, state.maxMarkers);
  draw.forEach(event => markers.addLayer(ensureMarker(event)));
  const photoCount = visible.filter(e => e.photoPick).length;
  const nypdCount = visible.filter(isNypd).length;
  const newCount = visible.filter(e => e.newlyAdded).length;
  const nearMode = state.userLocation && state.sort === 'near';
  els.listMeta.textContent = `${draw.length < visible.length ? `${draw.length} shown of ${visible.length}` : `${visible.length} visible`} assignments · ${newCount} newly added · ${photoCount} photo picks · ${nypdCount} NYPD${nearMode ? ' · sorted near you' : ''}`;
  els.eventList.innerHTML = visible.slice(0, 60).map(event => { const distance = distanceLabel(event); return `<button type="button" class="event-item" data-id="${esc(event.id)}"><span class="item-top"><span class="item-source">${esc(event.category.emoji)} ${esc(event.category.label)}</span><span class="item-tags">${event.newlyAdded ? '<span class="item-tag danger">NEW</span>' : ''}${distance ? `<span class="item-tag near">${esc(distance)}</span>` : ''}<span class="item-tag priority-${photoPriority(event).toLowerCase().replaceAll(' ', '-')}">${esc(photoPriority(event))}</span>${event.assignment_feed === 'staged' ? '<span class="item-tag">STAGED</span>' : ''}${event.photoPick ? '<span class="item-tag">📸</span>' : ''}${isNypd(event) ? '<span class="item-tag danger">NYPD</span>' : ''}</span></span><strong>${esc(event.title)}</strong><span>${esc(timeLabel(event.start))}</span><small>${esc([event.borough, event.location, crowdLabel(event)].filter(Boolean).join(' • '))}</small><span class="quick-actions"><a href="${esc(appleMapsUrl(event))}" target="_blank" rel="noopener">Directions</a><button type="button" data-copy-id="${esc(event.id)}">Copy</button></span></button>`; }).join('') || '<div class="empty">No assignments match this view.</div>';
  els.eventList.querySelectorAll('[data-id]').forEach(button => button.addEventListener('click', ev => { if (ev.target.closest('a,button[data-copy-id]')) return; const event = state.events.find(e => e.id === button.dataset.id); if (!event) return; map.flyTo([event.lat, event.lng], Math.max(map.getZoom(), 15), { duration: 0.55 }); setTimeout(() => { const marker = ensureMarker(event); marker.setPopupContent(popupHtml(event)); marker.openPopup(); if (!markers.hasLayer(marker)) markers.addLayer(marker); }, 420); setDesk(false); }));
  els.eventList.querySelectorAll('[data-copy-id]').forEach(button => button.addEventListener('click', ev => { ev.stopPropagation(); const event = state.events.find(e => e.id === button.dataset.copyId); if (event) copyAssignment(event); }));
  updateChrome(visible);
  return visible;
}

async function loadDeltaReport() {
  if (!els.newOnly && !document.body.classList.contains('admin-map-page')) return;
  try {
    const response = await fetch(`${DELTA_REPORT_URL}?cache=${Date.now()}`, { headers: { Accept: 'application/json' }, cache: 'no-store' });
    if (!response.ok) throw new Error(`delta HTTP ${response.status}`);
    const report = await response.json();
    const added = Array.isArray(report.added_events) ? report.added_events : [];
    const keys = new Set();
    added.forEach(row => {
      [row.id, row.source_event_id, deltaKey(row)].forEach(value => {
        const key = String(value || '').trim();
        if (key) keys.add(key);
      });
    });
    state.newlyAddedKeys = keys;
    state.deltaAddedCount = Number(report.added_count ?? added.length) || added.length;
    state.deltaGeneratedAt = report.generated_at_utc || null;
    if (els.newOnlyText) els.newOnlyText.textContent = `🆕 Newly added only (${state.deltaAddedCount.toLocaleString()})`;
  } catch (error) {
    state.newlyAddedKeys = new Set();
    state.deltaAddedCount = 0;
    if (els.newOnlyText) els.newOnlyText.textContent = '🆕 Newly added only (delta unavailable)';
    console.warn('NYCIF delta report unavailable', error);
  }
}

async function loadFeed(kind) {
  const url = FEEDS[kind];
  const label = kind === 'major' ? 'major field assignments' : kind === 'full' ? 'full event database' : 'staged deduped feed';
  status(`Loading ${label}…`);
  const response = await fetch(`${url}?cache=${Date.now()}`, { headers: { Accept: 'application/json' }, cache: 'no-store' });
  if (!response.ok) throw new Error(`${kind} feed HTTP ${response.status}`);
  const json = await response.json();
  const rows = Array.isArray(json) ? json : (json.events || []);
  const events = rows.map(makeEvent).filter(Boolean);
  if (kind === 'major') {
    state.maxMarkers = 650;
    state.events = events;
    state.feed = 'major';
  } else if (kind === 'staged') {
    state.maxMarkers = 2000;
    state.events = events;
    state.feed = 'staged';
    state.stagedLoaded = true;
    state.fullLoaded = false;
    if (els.stagedFeedBtn) {
      els.stagedFeedBtn.textContent = 'Staged feed loaded';
      els.stagedFeedBtn.disabled = true;
    }
  } else {
    state.maxMarkers = 650;
    const existing = new Map(state.events.map(e => [e.id, e]));
    events.forEach(event => existing.set(event.id, event));
    state.events = [...existing.values()];
    state.feed = 'full';
    state.fullLoaded = true;
  }
  const visible = render();
  if (visible.length && kind !== 'staged') map.fitBounds(visible.slice(0, 200).map(e => [e.lat, e.lng]), { padding: [44, 44], maxZoom: 12 });
  if (visible.length && kind === 'staged') status(`${visible.length} assignments · Staged deduped feed loaded · first ${Math.min(visible.length, state.maxMarkers)} markers drawn · v${VERSION}`);
  setTimeout(() => map.invalidateSize(), 120);
}

function syncUiFromState() {
  els.majorOnly.checked = state.majorOnly;
  els.photoOnly.checked = state.photoOnly;
  els.nypdOnly.checked = state.nypdOnly;
  if (els.newOnly) els.newOnly.checked = state.newOnly;
  els.sortSelect.value = state.sort;
  document.querySelectorAll('[data-cat]').forEach(input => { input.checked = !!state.categories[input.dataset.cat]; });
}

function setLayers(open) { els.layersPanel.hidden = !open; els.layersBtn.setAttribute('aria-expanded', String(open)); setTimeout(() => map.invalidateSize(), 100); }
function setDesk(open) { els.deskDrawer.hidden = !open; els.deskBtn.setAttribute('aria-expanded', String(open)); setTimeout(() => map.invalidateSize(), 100); }

function buildBoroughs() {
  els.boroughs.innerHTML = BOROUGHS.map(b => { const value = b === 'All' ? 'all' : b; return `<button type="button" class="${state.borough === value ? 'active' : ''}" data-borough="${esc(value)}">${esc(b)}</button>`; }).join('');
  els.boroughs.addEventListener('click', ev => { const button = ev.target.closest('[data-borough]'); if (!button) return; state.borough = button.dataset.borough; els.boroughs.querySelectorAll('button').forEach(b => b.classList.toggle('active', b === button)); savePrefs(); render(); });
}

function chipModeForDate(date) { return dateKey(date) === todayKey() ? 'today' : dateKey(date); }
function chipText(date) { return `${DAY_NAMES[date.getDay()]} ${date.getMonth() + 1}/${date.getDate()}`; }
function buildDateChips() {
  if (!els.dateChips) return;
  const start = weekStartSunday(new Date());
  const days = Array.from({ length: 14 }, (_, index) => addDays(start, index));
  els.dateChips.innerHTML = `<div class="date-chip-track">${days.map(date => { const mode = chipModeForDate(date); const label = dateKey(date) === todayKey() ? 'Today' : chipText(date); return `<button type="button" data-date-mode="${esc(mode)}" data-date-key="${esc(dateKey(date))}" class="${state.dateMode === mode ? 'active' : ''}">${esc(label)}</button>`; }).join('')}<button type="button" data-date-mode="all" class="${state.dateMode === 'all' ? 'active' : ''}">All</button></div>`;
  const active = els.dateChips.querySelector('button.active');
  if (active) setTimeout(() => active.scrollIntoView({ inline: 'center', block: 'nearest' }), 50);
  els.dateChips.addEventListener('click', ev => { const button = ev.target.closest('[data-date-mode]'); if (!button) return; state.dateMode = button.dataset.dateMode; els.dateChips.querySelectorAll('[data-date-mode]').forEach(b => b.classList.toggle('active', b === button)); savePrefs(); render(); });
}

function setUserLocation(latitude, longitude, accuracy) {
  const here = [latitude, longitude];
  state.userLocation = { lat: latitude, lng: longitude };
  if (userMarker) userMarker.setLatLng(here); else { const icon = L.divIcon({ className: 'user-location-shell', html: '<span class="user-location">🗽</span>', iconSize: [36, 44], iconAnchor: [18, 42], popupAnchor: [0, -38] }); userMarker = L.marker(here, { icon, zIndexOffset: 4000 }).addTo(map).bindPopup(`<strong>You are here</strong><br>Accuracy: ${Math.round(accuracy || 0)} meters`); }
  if (userAccuracy) { userAccuracy.setLatLng(here); userAccuracy.setRadius(accuracy || 0); } else { userAccuracy = L.circle(here, { radius: accuracy || 0, color: '#d40000', weight: 2, fillColor: '#d40000', fillOpacity: 0.08 }).addTo(map); }
}

function locateUser(options = {}) {
  if (!navigator.geolocation) { status('Location is not available in this browser.'); return; }
  status('Finding your location…');
  navigator.geolocation.getCurrentPosition(pos => { const { latitude, longitude, accuracy } = pos.coords; setUserLocation(latitude, longitude, accuracy); if (options.sortNear) { state.sort = 'near'; els.sortSelect.value = 'near'; savePrefs(); } map.flyTo([latitude, longitude], Math.max(map.getZoom(), 14), { duration: 0.6 }); userMarker.openPopup(); render(); status(options.sortNear ? 'Sorted assignments near you.' : 'Location updated.'); }, err => status(`Location failed: ${err.message}`), { enableHighAccuracy: true, timeout: 12000, maximumAge: 15000 });
}

function ensureStagedButton() {
  if (!els.layersPanel || document.getElementById('loadStagedBtn')) return;
  const button = document.createElement('button');
  button.id = 'loadStagedBtn';
  button.className = 'load-all staged-feed-test';
  button.type = 'button';
  button.textContent = 'Load staged feed';
  els.loadAllBtn.insertAdjacentElement('afterend', button);
  els.stagedFeedBtn = button;
}

function bindUi() {
  ensureStagedButton();
  els.layersBtn.addEventListener('click', () => setLayers(els.layersPanel.hidden));
  els.deskBtn.addEventListener('click', () => setDesk(els.deskDrawer.hidden));
  els.closeDeskBtn.addEventListener('click', () => setDesk(false));
  els.locateBtn.addEventListener('click', () => locateUser());
  els.nearMeBtn.addEventListener('click', () => locateUser({ sortNear: true }));
  els.loadAllBtn.addEventListener('click', async () => { if (state.fullLoaded) { status('Full feed already loaded.'); return; } els.loadAllBtn.disabled = true; els.loadAllBtn.textContent = 'Loading all events…'; try { await loadFeed('full'); els.loadAllBtn.textContent = 'All events loaded'; } catch (error) { els.loadAllBtn.disabled = false; els.loadAllBtn.textContent = 'Load all events'; status(`Full feed failed: ${error.message}`); } });
  if (els.stagedFeedBtn) els.stagedFeedBtn.addEventListener('click', async () => { if (state.stagedLoaded) { status('Staged feed already loaded.'); return; } els.stagedFeedBtn.disabled = true; els.stagedFeedBtn.textContent = 'Loading staged feed…'; try { await loadFeed('staged'); } catch (error) { els.stagedFeedBtn.disabled = false; els.stagedFeedBtn.textContent = 'Load staged feed'; status(`Staged feed failed: ${error.message}`); } });
  els.majorOnly.addEventListener('change', () => { state.majorOnly = els.majorOnly.checked; savePrefs(); render(); });
  els.photoOnly.addEventListener('change', () => { state.photoOnly = els.photoOnly.checked; savePrefs(); render(); });
  els.nypdOnly.addEventListener('change', () => { state.nypdOnly = els.nypdOnly.checked; savePrefs(); render(); });
  if (els.newOnly) els.newOnly.addEventListener('change', async () => { state.newOnly = els.newOnly.checked; savePrefs(); if (state.newOnly && !state.stagedLoaded) { if (els.stagedFeedBtn) els.stagedFeedBtn.click(); else await loadFeed('staged'); } else render(); });
  document.querySelectorAll('[data-cat]').forEach(input => input.addEventListener('change', () => { state.categories[input.dataset.cat] = input.checked; savePrefs(); render(); }));
  els.searchInput.addEventListener('input', () => { state.search = normalize(els.searchInput.value); render(); });
  els.sortSelect.addEventListener('change', () => { state.sort = els.sortSelect.value; savePrefs(); if (state.sort === 'near' && !state.userLocation) locateUser({ sortNear: true }); else render(); });
  document.addEventListener('click', ev => { const button = ev.target.closest('[data-copy-id]'); if (!button) return; const event = state.events.find(e => e.id === button.dataset.copyId); if (event) copyAssignment(event); });
  map.on('click tap', ev => { if (ev?.originalEvent) L.DomEvent.stopPropagation(ev.originalEvent); });
}

async function boot() {
  loadPrefs();
  await loadDeltaReport();
  syncUiFromState();
  bindUi();
  buildBoroughs();
  buildDateChips();
  if ('serviceWorker' in navigator) navigator.serviceWorker.register('./service-worker.js').catch(() => {});
  try { await loadFeed('staged'); } catch (error) { status(`Staged feed failed: ${error.message}`); }
}

boot();
