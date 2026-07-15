/**
 * Civic people-facing Field Desk config — load before app-schema-v1-major-all-v01.js.
 * Approved stay on discovery feeds; Review unions discovery review + civic review;
 * Help Places load from schema-v1-civic-review/help.
 */
window.NYCIF_DISCOVERY_V02 = Object.assign({}, window.NYCIF_DISCOVERY_V02 || {}, {
  version: "civic-people-facing-v01",
  feedRoot: "schema-v1-discovery",
  extraReviewRoots: ["schema-v1-civic-review"],
  helpFeedRoot: "schema-v1-civic-review",
  categoryMeta: Object.assign({}, (window.NYCIF_DISCOVERY_V02 && window.NYCIF_DISCOVERY_V02.categoryMeta) || {}, {
    volunteer: { emoji: "🙋", label: "Volunteer opportunities" },
    jobs: { emoji: "💼", label: "Jobs / career" },
    services: { emoji: "🤝", label: "Health / benefits / help" },
    housing: { emoji: "🏠", label: "Housing / tenant help" },
    market: { emoji: "🛍️", label: "Street fairs / markets" },
  }),
});
