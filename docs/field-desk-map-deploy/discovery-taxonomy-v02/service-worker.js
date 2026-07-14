const CACHE_NAME = 'nycif-v019-discovery-taxonomy-v02';
const APP_SHELL = [
  './',
  './index.html',
  './style.css',
  './fielddesk-v02.css',
  './weekstrip-v06-safe.css',
  './public-map-v01.css',
  './public-approved-overlays-capture-v01.js',
  './public-map-defaults-v01.js',
  './public-approved-overlays-v01.js',
  './boot-today-v073-safe.js',
  './date-normalizer-v073-safe.js',
  './event-feed-schema-v1.js',
  './app-discovery-taxonomy-v02.js',
  './manifest.json',
  './icons/icon-192.svg',
  './icons/icon-512.svg'
];

const NETWORK_FIRST_RE = /\/(?:index\.html|app-discovery-taxonomy-v02\.js|event-feed-schema-v1\.js|public-map-defaults-v01\.js|service-worker\.js|public-approved-overlays-v01\.js|public-approved-overlays-capture-v01\.js)$/;

function isNetworkFirst(url) {
  return (url.origin === location.origin && NETWORK_FIRST_RE.test(url.pathname)) || url.hostname === 'raw.githubusercontent.com';
}

self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE_NAME).then(cache => cache.addAll(APP_SHELL)));
  self.skipWaiting();
});

self.addEventListener('activate', event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key !== CACHE_NAME).map(key => caches.delete(key)))));
  self.clients.claim();
});

self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);
  if (url.origin !== location.origin && url.hostname !== 'raw.githubusercontent.com') return;

  if (isNetworkFirst(url)) {
    event.respondWith(
      fetch(event.request).then(response => {
        const copy = response.clone();
        caches.open(CACHE_NAME).then(cache => cache.put(event.request, copy));
        return response;
      }).catch(() => caches.match(event.request))
    );
    return;
  }

  event.respondWith(
    caches.match(event.request).then(cached => cached || fetch(event.request).then(response => {
      const copy = response.clone();
      caches.open(CACHE_NAME).then(cache => cache.put(event.request, copy));
      return response;
    }))
  );
});
