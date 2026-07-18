(function () {
  'use strict';
  try {
    var params = new URL(location.href).searchParams;
    if (params.get('previewExport') !== '1' || params.get('deskOverlay') === '1') {
      return;
    }
    var target = new URL('approved-export-preview.html', location.href);
    ['exportFeed', 'exportPins', 'localExport', 'distExport'].forEach(function (key) {
      var value = params.get(key);
      if (value) {
        target.searchParams.set(key, value);
      }
    });
    location.replace(String(target));
  } catch (e) {
    /* ignore */
  }
})();
