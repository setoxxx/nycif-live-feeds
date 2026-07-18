(function () {
  'use strict';

  /** Matches public-map-v01.css mobile rules (@media max-width: 720px). */
  var MOBILE_MQ = '(max-width: 720px)';
  var mq = window.matchMedia(MOBILE_MQ);
  var MODES = { MOBILE: 'mobile', DESKTOP: 'desktop' };

  function currentMode() {
    return mq.matches ? MODES.MOBILE : MODES.DESKTOP;
  }

  function isMobile() {
    return currentMode() === MODES.MOBILE;
  }

  function syncExploreMoreDefault(mobile) {
    var btn = document.getElementById('explore-more-toggle');
    var panel = document.getElementById('explore-more-panel');
    if (!btn || !panel) {
      return;
    }
    panel.hidden = mobile;
    btn.setAttribute('aria-expanded', mobile ? 'false' : 'true');
  }

  function applyDisplayMode() {
    var mode = currentMode();
    var mobile = mode === MODES.MOBILE;
    var html = document.documentElement;
    var body = document.body;

    html.dataset.nycifDisplay = mode;
    html.classList.toggle('nycif-display-mobile', mobile);
    html.classList.toggle('nycif-display-desktop', !mobile);
    if (body) {
      body.classList.toggle('nycif-display-mobile', mobile);
      body.classList.toggle('nycif-display-desktop', !mobile);
    }

    syncExploreMoreDefault(mobile);

    window.dispatchEvent(new CustomEvent('nycif:display-mode', {
      detail: { mode: mode, mobile: mobile, desktop: !mobile }
    }));

    return mode;
  }

  function bindExploreMoreToggle() {
    var btn = document.getElementById('explore-more-toggle');
    var panel = document.getElementById('explore-more-panel');
    if (!btn || !panel || btn.dataset.nycifDisplayBound === '1') {
      return;
    }
    btn.dataset.nycifDisplayBound = '1';
    btn.addEventListener('click', function () {
      var open = panel.hidden;
      panel.hidden = !open;
      btn.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
  }

  function init() {
    applyDisplayMode();
    bindExploreMoreToggle();
  }

  if (typeof mq.addEventListener === 'function') {
    mq.addEventListener('change', applyDisplayMode);
  } else if (typeof mq.addListener === 'function') {
    mq.addListener(applyDisplayMode);
  }

  window.NYCIF_DISPLAY_MODE = {
    MODES: MODES,
    MOBILE_MQ: MOBILE_MQ,
    get: currentMode,
    isMobile: isMobile,
    isDesktop: function () { return !isMobile(); },
    apply: applyDisplayMode
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init, { once: true });
  } else {
    init();
  }
})();
