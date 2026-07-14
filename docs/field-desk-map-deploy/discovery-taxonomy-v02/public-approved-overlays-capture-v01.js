(function () {
  if (!window.L || window.NYCIF_APPROVED_OVERLAYS_CAPTURED) return;

  const originalMap = window.L.map;
  window.L.map = function patchedNycifMapFactory(...args) {
    const map = originalMap.apply(this, args);
    window.NYCIF_MAIN_MAP = map;
    window.dispatchEvent(new CustomEvent('nycif:main-map-ready', { detail: { map } }));
    return map;
  };

  window.NYCIF_APPROVED_OVERLAYS_CAPTURED = true;
})();
