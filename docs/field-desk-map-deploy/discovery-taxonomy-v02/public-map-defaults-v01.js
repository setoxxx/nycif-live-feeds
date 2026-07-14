(function () {
  const STORAGE_KEY = 'nycif-field-desk-state-v06-safe';
  const DEFAULT_VERSION = 'discovery-taxonomy-v02';
  const defaults = {
    borough: 'all',
    sort: 'priority',
    dateMode: 'next7',
    viewMode: 'major',
    sourceFilter: 'all',
    categories: {
      sports: true,
      civic: true,
      market: true,
      arts: true,
      parks: true,
      fitness: true,
      family: true,
      education: true,
      volunteer: true,
      general: true,
      tours: true,
      government: true,
      services: true,
      jobs: true,
      housing: true,
      environment: true
    },
    majorOnly: false,
    photoOnly: false,
    nypdOnly: false,
    newOnly: false
  };

  function applyDefaults(forceReset) {
    if (forceReset) localStorage.removeItem(STORAGE_KEY);
    const existing = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');
    if (forceReset || existing?.nycifDefaultVersion !== DEFAULT_VERSION) {
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
      || versionFlag === 'discovery-taxonomy-v02'
      || versionFlag === 'schema-v1-major-all-v01'
      || versionFlag === 'map-restore-v02'
      || versionFlag === 'data-explorer-v01'
      || versionFlag === 'major-default-qa-01'
      || versionFlag === 'ui-defaults-02'
      || versionFlag === 'c5p-postpublish-02';
    applyDefaults(forceReset);
  } catch {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({
      ...defaults,
      nycifDefaultVersion: DEFAULT_VERSION
    }));
  }
})();
