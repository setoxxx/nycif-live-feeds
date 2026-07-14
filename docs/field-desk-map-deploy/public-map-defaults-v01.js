(function () {
  const STORAGE_KEY = 'nycif-field-desk-state-v06-safe';
  const DEFAULT_VERSION = 'staged-live-v02';
  const defaults = {
    borough: 'all',
    sort: 'priority',
    dateMode: 'today',
    categories: {
      sports: true,
      parade: true,
      market: true,
      arts: true,
      parks: true,
      general: true,
      fitness: false
    },
    majorOnly: false,
    photoOnly: false,
    nypdOnly: false,
    newOnly: false
  };

  function applyDefaults(forceReset) {
    if (forceReset) {
      localStorage.removeItem(STORAGE_KEY);
    }

    const existing = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');
    if (forceReset || !existing || existing.nycifDefaultVersion !== DEFAULT_VERSION) {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({
        ...defaults,
        nycifDefaultVersion: DEFAULT_VERSION
      }));
    }
  }

  try {
    const url = new URL(window.location.href);
    const versionFlag = url.searchParams.get('v');
    const forceReset = url.searchParams.get('resetFilters') === '1'
      || versionFlag === 'major-default-qa-01'
      || versionFlag === 'ui-defaults-02'
      || versionFlag === 'c5p-postpublish-02'
      || versionFlag === 'm10-staged-live'
      || versionFlag === 'staged-live-v01'
      || versionFlag === 'staged-live-v02';
    applyDefaults(forceReset);
  } catch {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({
      ...defaults,
      nycifDefaultVersion: DEFAULT_VERSION
    }));
  }
})();
