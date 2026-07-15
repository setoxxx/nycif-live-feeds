/**
 * Thin SW for civic-people-facing-v01 package preview.
 * Shell assets mostly live in sibling discovery-taxonomy-v02 / schema-v1-major-all-v01 folders.
 */
var CIVIC_CACHE = "nycif-civic-people-facing-v01-shell";
var CIVIC_SHELL = [
  "./index.html",
  "./civic-patch-v01.js",
  "./public-map-defaults-v01.js",
  "./service-worker.js"
];

self.addEventListener("install", function (event) {
  event.waitUntil(
    caches.open(CIVIC_CACHE).then(function (cache) {
      return cache.addAll(CIVIC_SHELL);
    }).then(function () {
      return self.skipWaiting();
    })
  );
});

self.addEventListener("activate", function (event) {
  event.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(keys.filter(function (k) { return k !== CIVIC_CACHE; }).map(function (k) {
        return caches.delete(k);
      }));
    }).then(function () {
      return self.clients.claim();
    })
  );
});

self.addEventListener("fetch", function (event) {
  var req = event.request;
  var url = new URL(req.url);
  var isFeedHost = url.hostname === "raw.githubusercontent.com";
  var isLocal = url.origin === self.location.origin;
  if (!isLocal && !isFeedHost) {
    return;
  }

  // Network-first for package JS/HTML and GitHub feed JSON; cache fallback offline.
  event.respondWith(
    fetch(req).then(function (res) {
      if (isLocal && res && res.ok) {
        var copy = res.clone();
        caches.open(CIVIC_CACHE).then(function (cache) { cache.put(req, copy); });
      }
      return res;
    }).catch(function () {
      return caches.match(req);
    })
  );
});
