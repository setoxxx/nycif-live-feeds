(() => {
  const KEYS = ['nycif-field-desk-state-v06-safe', 'nycif-field-desk-state-v03'];
  for (const key of KEYS) {
    try {
      const raw = localStorage.getItem(key);
      if (!raw) continue;
      const prefs = JSON.parse(raw);
      if (!prefs || typeof prefs !== 'object') continue;
      // Keep next7 / exact dates / all upcoming. Only normalize legacy "weekend"/"tomorrow"
      // when somehow stuck without a public default version.
      if (!prefs.nycifDefaultVersion && (prefs.dateMode === 'weekend' || prefs.dateMode === 'tomorrow')) {
        prefs.dateMode = 'next7';
        localStorage.setItem(key, JSON.stringify(prefs));
      }
    } catch {}
  }
})();
