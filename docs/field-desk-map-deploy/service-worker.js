const CACHE_NAME = 'nycif-v015-emergency-map-restore';
const APP_SHELL = [
  './',
  './index.html',
  './style.css',
  './fielddesk-v02.css',
  './weekstrip-v06-safe.css',
  './staged-map-mode-v01.css',
  './public-map-v01.css',
  './data-window-v08-safe.css',
  './truth-panel-v09-safe.css',
  './live-test-v010-safe.css',
  './public-approved-overlays-capture-v01.js',
  './public-map-defaults-v01.js',
  './public-approved-overlays-v01.js',
  './boot-today-v073-safe.js',
  './date-normalizer-v073-safe.js',
  './event-significance-v01.js',
  './map-date-key-v01.js',
  './app-v06-safe.js',
  './stats-v05-safe.js',
  './data-window-v08-safe.js',
  './truth-panel-v09-safe.js',
  './live-test-v011-safe.js',
  './manifest.json',
  './icons/icon-192.svg',
  './icons/icon-512.svg'
];

const NETWORK_FIRST_RE = /\/(?:index\.html|app-v06-safe\.js|public-map-defaults-v01\.js|event-significance-v01\.js|map-date-key-v01\.js|service-worker\.js|public-approved-overlays-v01\.js|public-approved-overlays-capture-v01\.js)$/;

function isNetworkFirstRequest(url) {
  if (url.hostname === 'raw.githubusercontent.com') return true;
  return url.origin === location.origin && NETWORK_FIRST_RE.test(url.pathname);
}

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE_NAME).then(c => c.addAll(APP_SHELL)).catch(() => undefined));
  self.skipWaiting();
});

self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))));
  self.clients.claim();
});

self.addEventListener('fetch', e => {
  const u = new URL(e.request.url);
  if (u.origin !== location.origin && u.hostname !== 'raw.githubusercontent.com') return;

  if (isNetworkFirstRequest(u)) {
    e.respondWith(
      fetch(e.request, { cache: 'no-store' })
        .then(r => {
          if (r && r.ok && e.request.method === 'GET' && u.origin === location.origin) {
            const copy = r.clone();
            caches.open(CACHE_NAME).then(c => c.put(e.request, copy)).catch(() => undefined);
          }
          return r;
        })
        .catch(() => caches.match(e.request))
    );
    return;
  }

  e.respondWith(
    fetch(e.request)
      .then(r => {
        if (r && r.ok && e.request.method === 'GET') {
          const copy = r.clone();
          caches.open(CACHE_NAME).then(c => c.put(e.request, copy)).catch(() => undefined);
        }
        return r;
      })
      .catch(() => caches.match(e.request))
  );
});
