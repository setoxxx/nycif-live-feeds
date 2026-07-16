/**
 * NYCIF Discovery Taxonomy live runtime repair v03.
 * Loads before event-feed-schema-v1.js and app-schema-v1-major-all-v01.js.
 */
(() => {
  'use strict';

  const VERSION = 'public-map-v05';
  // Feed source ref on the backend repo (setoxxx/nycif-live-feeds).
  // Points at `main`, which already serves data/schema-v1-discovery/** and is
  // kept current by the backend Discovery Feed Refresh workflow (daily rebuild
  // + commit). This replaces the old pinned commit that could not refresh and
  // would break if its branch were deleted. If the primary/full feeds are ever
  // unavailable, the app still degrades to the major-only emergency feed.
  const DEFAULT_FEED_REF = 'main';
  const FEED_ROOT = 'schema-v1-discovery';
  const LIVE_FEED_HOST = 'raw.githubusercontent.com';
  const successfulPageUrls = new Set();
  const eventRegistry = new Map();
  const titleIndex = new Map();
  let lastBootResetAt = 0;

  function normalizedTitle(value) {
    return String(value || '').toLowerCase().replace(/\s+/g, ' ').trim();
  }

  function normalizeUrl(value) {
    try {
      const url = new URL(String(value), location.href);
      url.searchParams.delete('cache');
      url.hash = '';
      return url.toString();
    } catch {
      return String(value || '');
    }
  }

  function isLocalHost() {
    return location.hostname === 'localhost' || location.hostname === '127.0.0.1';
  }

  function ensureProductionFeedRef() {
    if (isLocalHost()) {
      return;
    }
    try {
      const url = new URL(location.href);
      let changed = false;
      if (!url.searchParams.get('feeds')) {
        url.searchParams.set('feeds', DEFAULT_FEED_REF);
        changed = true;
      }
      if (!url.searchParams.get('v')) {
        url.searchParams.set('v', VERSION);
        changed = true;
      }
      if (changed) {
        history.replaceState(history.state, '', url.toString());
      }
    } catch {
      // The app still has its normal main-branch fallback.
    }
  }

  ensureProductionFeedRef();

  window.NYCIF_DISCOVERY_V02 = {
    version: VERSION,
    feedRoot: FEED_ROOT,
    defaultFeedRef: DEFAULT_FEED_REF,
    categoryMeta: {
      sports: { emoji: '🏟️', label: 'Sports' },
      civic: { emoji: '📣', label: 'Parades / civic' },
      market: { emoji: '🛍️', label: 'Street fairs / markets' },
      arts: { emoji: '🎭', label: 'Arts / performance' },
      parks: { emoji: '🌳', label: 'Parks / outdoors' },
      fitness: { emoji: '💪', label: 'Fitness / wellness' },
      family: { emoji: '👨‍👩‍👧', label: 'Kids / family' },
      education: { emoji: '📚', label: 'Classes / workshops' },
      volunteer: { emoji: '🙋', label: 'Volunteer opportunities' },
      general: { emoji: '📍', label: 'General' },
      tours: { emoji: '🗺️', label: 'Tours / history' },
      government: { emoji: '🏛️', label: 'Government / meetings' },
      services: { emoji: '🤝', label: 'Health / benefits' },
      jobs: { emoji: '💼', label: 'Jobs / career' },
      housing: { emoji: '🏠', label: 'Housing / tenant help' },
      environment: { emoji: '🌎', label: 'Environment / nature' },
      media: { emoji: '🎬', label: 'Film / production' }
    }
  };

  function isLiveFeedUrl(value) {
    try {
      return new URL(String(value), location.href).hostname === LIVE_FEED_HOST;
    } catch {
      return false;
    }
  }

  function isMajorFeedUrl(value) {
    const normalized = normalizeUrl(value);
    return /\/data\/(?:schema-v1-discovery\/major\/events|events_discovery_v02_major)\.json$/i.test(normalized);
  }

  function isRetryableStatus(status) {
    return status === 408 || status === 425 || status === 429 || status >= 500;
  }

  function delay(ms) {
    return new Promise(resolve => window.setTimeout(resolve, ms));
  }

  const nativeFetch = window.fetch.bind(window);
  window.fetch = async function nycifFetchWithRetry(input, init) {
    const requestUrl = typeof input === 'string' ? input : input && input.url;
    const liveFeed = isLiveFeedUrl(requestUrl);

    if (liveFeed && isMajorFeedUrl(requestUrl)) {
      const now = Date.now();
      if (now - lastBootResetAt > 1000) {
        successfulPageUrls.clear();
        lastBootResetAt = now;
      }
    }

    const attempts = liveFeed ? 5 : 1;
    let lastError = null;
    let lastResponse = null;

    for (let attempt = 0; attempt < attempts; attempt += 1) {
      try {
        const response = await nativeFetch(input, init);
        lastResponse = response;
        if (!liveFeed || response.ok || !isRetryableStatus(response.status) || attempt === attempts - 1) {
          return response;
        }
      } catch (error) {
        lastError = error;
        if (!liveFeed || attempt === attempts - 1) {
          throw error;
        }
      }
      await delay(250 * (2 ** attempt));
    }

    if (lastResponse) {
      return lastResponse;
    }
    throw lastError || new Error('NYCIF feed request failed');
  };

  function pageUrlFromManifest(manifestUrl, page) {
    const base = normalizeUrl(manifestUrl).replace(/\/manifest\.json$/i, '/pages/');
    const name = String((page && (page.cursor || page.page)) || '').replace(/\.json$/i, '');
    return `${base}${name}.json`;
  }

  function wrapManifestPages(data, manifestUrl) {
    if (!data || !Array.isArray(data.pages) || data.pages.__nycifRuntimeRepairProxy) {
      return data;
    }
    const originalPages = data.pages;
    const proxy = new Proxy(originalPages, {
      get(target, property, receiver) {
        if (property === '__nycifRuntimeRepairProxy') {
          return true;
        }
        if (property === Symbol.iterator) {
          return function* nycifRemainingPages() {
            for (const page of target) {
              if (!successfulPageUrls.has(pageUrlFromManifest(manifestUrl, page))) {
                yield page;
              }
            }
          };
        }
        return Reflect.get(target, property, receiver);
      }
    });
    data.pages = proxy;
    return data;
  }

  const nativeResponseJson = Response.prototype.json;
  Response.prototype.json = async function nycifResponseJson() {
    const data = await nativeResponseJson.call(this);
    const url = normalizeUrl(this.url || '');

    if (/\/data\/schema-v1-discovery\/(approved|review)\/pages\/[^/]+\.json$/i.test(url)) {
      successfulPageUrls.add(url);
    }

    if (/\/data\/schema-v1-discovery\/(approved|review)\/manifest\.json$/i.test(url)) {
      return wrapManifestPages(data, url);
    }

    return data;
  };

  function registerEvents(events) {
    if (!Array.isArray(events)) {
      return;
    }
    events.forEach(event => {
      if (!event || !event.id) {
        return;
      }
      eventRegistry.set(String(event.id), event);
      const key = normalizedTitle(event.title);
      if (!key) {
        return;
      }
      const ids = titleIndex.get(key) || [];
      if (!ids.includes(String(event.id))) {
        ids.push(String(event.id));
        titleIndex.set(key, ids);
      }
    });
  }

  function wrapSchema(schema) {
    if (!schema || typeof schema.projectEnvelope !== 'function' || schema.__nycifRuntimeRepairV03) {
      return schema;
    }
    const originalProjectEnvelope = schema.projectEnvelope.bind(schema);
    return {
      ...schema,
      __nycifRuntimeRepairV03: true,
      projectEnvelope(...args) {
        const envelope = originalProjectEnvelope(...args);
        registerEvents(envelope && envelope.events);
        return envelope;
      }
    };
  }

  let schemaValue = wrapSchema(window.NYCIF_EVENT_FEED_SCHEMA_V1);
  try {
    Object.defineProperty(window, 'NYCIF_EVENT_FEED_SCHEMA_V1', {
      configurable: true,
      enumerable: true,
      get() {
        return schemaValue;
      },
      set(value) {
        schemaValue = wrapSchema(value);
      }
    });
  } catch {
    // The schema remains usable even if the property cannot be wrapped.
  }

  function meaningfulTime(value) {
    const text = String(value || '');
    const match = text.match(/T(\d{2}):(\d{2})/);
    return !!match && !(match[1] === '00' && match[2] === '00');
  }

  function formatClock(value) {
    if (!meaningfulTime(value)) {
      return '';
    }
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
      return '';
    }
    return new Intl.DateTimeFormat('en-US', {
      hour: 'numeric',
      minute: '2-digit',
      timeZone: 'America/New_York'
    }).format(date);
  }

  function formatDate(value) {
    const text = String(value || '').slice(0, 10);
    const match = text.match(/^(\d{4})-(\d{2})-(\d{2})$/);
    return match ? `${match[2]}/${match[3]}/${match[1].slice(2)}` : text;
  }

  function formatTimeRange(event) {
    const start = formatClock(event && event.start_date_time);
    const end = formatClock(event && event.end_date_time);
    if (start && end && start !== end) {
      return `${start}–${end}`;
    }
    return start || end || 'Time not listed';
  }

  function safeUrl(value) {
    try {
      const url = new URL(String(value || ''));
      return url.protocol === 'https:' || url.protocol === 'http:' ? url.toString() : '';
    } catch {
      return '';
    }
  }

  function eventForPopup(content, markerTitle) {
    const ids = titleIndex.get(normalizedTitle(markerTitle)) || [];
    if (!ids.length) {
      return null;
    }
    if (ids.length === 1) {
      return eventRegistry.get(ids[0]) || null;
    }
    const text = content && content.textContent ? normalizedTitle(content.textContent) : '';
    return ids.map(id => eventRegistry.get(id)).find(event => event && event.location && text.includes(normalizedTitle(event.location)))
      || eventRegistry.get(ids[0])
      || null;
  }

  function appendPopupLink(actions, href, label) {
    const url = safeUrl(href);
    if (!url || Array.from(actions.querySelectorAll('a')).some(link => link.href === url || link.textContent === label)) {
      return;
    }
    const link = document.createElement('a');
    link.className = 'field-action';
    link.href = url;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    link.textContent = label;
    actions.appendChild(link);
  }

  function enhancePopup(content, markerTitle) {
    if (!(content instanceof HTMLElement) || content.dataset.nycifRuntimeEnhanced === '1') {
      return;
    }
    const event = eventForPopup(content, markerTitle);
    if (!event) {
      return;
    }

    const dl = content.querySelector('dl');
    if (dl && !dl.querySelector('[data-nycif-time-row]')) {
      const row = document.createElement('div');
      row.dataset.nycifTimeRow = '1';
      const dt = document.createElement('dt');
      dt.textContent = 'Time';
      const dd = document.createElement('dd');
      dd.textContent = formatTimeRange(event);
      row.append(dt, dd);
      const first = dl.firstElementChild;
      if (first && first.nextSibling) {
        dl.insertBefore(row, first.nextSibling);
      } else {
        dl.appendChild(row);
      }
    }

    let actions = content.querySelector('.field-actions');
    if (!actions) {
      actions = document.createElement('div');
      actions.className = 'field-actions';
      content.appendChild(actions);
    }

    const officialUrl = event.source && event.source.source_url;
    appendPopupLink(actions, officialUrl, 'Official page');
    const searchQuery = [event.title, event.date || event.start_date_time, event.borough, event.location]
      .filter(Boolean)
      .join(' ');
    appendPopupLink(actions, `https://www.google.com/search?q=${encodeURIComponent(searchQuery)}`, 'Search event');
    content.dataset.nycifRuntimeEnhanced = '1';
  }

  if (window.L && L.Marker && L.Marker.prototype && typeof L.Marker.prototype.bindPopup === 'function') {
    const nativeBindPopup = L.Marker.prototype.bindPopup;
    L.Marker.prototype.bindPopup = function nycifBindPopup(content, options) {
      try {
        enhancePopup(content, this.options && this.options.title);
      } catch {
        // Keep normal Leaflet popup binding if enhancement fails.
      }
      return nativeBindPopup.call(this, content, options);
    };
  }

  function enhanceListCard(card) {
    if (!(card instanceof HTMLElement) || card.dataset.nycifRuntimeEnhanced === '1') {
      return;
    }
    const event = eventRegistry.get(String(card.dataset.id || ''));
    if (!event) {
      return;
    }
    const directChildren = Array.from(card.children);
    const strongIndex = directChildren.findIndex(child => child.tagName === 'STRONG');
    const dateLine = strongIndex >= 0 ? directChildren.slice(strongIndex + 1).find(child => child.tagName === 'SPAN') : null;
    if (dateLine) {
      const dateText = formatDate(event.date || event.start_date_time || event.nycif && event.nycif.event_date);
      dateLine.textContent = `${dateText || 'Date unavailable'} · ${formatTimeRange(event)}`;
    }
    card.dataset.nycifRuntimeEnhanced = '1';
  }

  function enhanceNode(node) {
    if (!(node instanceof HTMLElement)) {
      return;
    }
    if (node.matches('.event-item[data-id]')) {
      enhanceListCard(node);
    }
    node.querySelectorAll('.event-item[data-id]').forEach(enhanceListCard);
  }

  const observer = new MutationObserver(records => {
    records.forEach(record => record.addedNodes.forEach(enhanceNode));
  });
  observer.observe(document.documentElement, { childList: true, subtree: true });
  document.querySelectorAll('.event-item[data-id]').forEach(enhanceListCard);

  window.NYCIF_RUNTIME_REPAIR_V03 = {
    version: VERSION,
    feedRef: DEFAULT_FEED_REF,
    successfulPageUrls,
    eventRegistry
  };
})();
