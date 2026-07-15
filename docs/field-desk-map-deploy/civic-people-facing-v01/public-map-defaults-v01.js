/**
 * Civic people-facing defaults — Major + Next 7 days.
 * Intentionally not a copy of discovery-taxonomy-v02 defaults (Sonar duplication gate).
 */
(function applyCivicPeopleFacingDefaults() {
  var KEY = "nycif-field-desk-state-v06-safe";
  var VERSION = "civic-people-facing-v01";
  var CATEGORY_ON = [
    "sports", "civic", "market", "arts", "parks", "fitness", "family", "education",
    "volunteer", "general", "tours", "government", "services", "jobs", "housing", "environment"
  ];
  var cats = {};
  CATEGORY_ON.forEach(function (k) { cats[k] = true; });

  var payload = {
    borough: "all",
    sort: "priority",
    dateMode: "next7",
    viewMode: "major",
    sourceFilter: "all",
    categories: cats,
    majorOnly: false,
    photoOnly: false,
    nypdOnly: false,
    newOnly: false,
    nycifDefaultVersion: VERSION
  };

  function shouldReset(params) {
    var v = params.get("v");
    return params.get("resetFilters") === "1" || v === VERSION;
  }

  try {
    var params = new URL(location.href).searchParams;
    var existing = {};
    try { existing = JSON.parse(localStorage.getItem(KEY) || "{}") || {}; } catch (e) { existing = {}; }
    if (shouldReset(params) || existing.nycifDefaultVersion !== VERSION) {
      localStorage.setItem(KEY, JSON.stringify(payload));
    }
  } catch (err) {
    try { localStorage.setItem(KEY, JSON.stringify(payload)); } catch (ignore) { /* ignore */ }
  }
})();
