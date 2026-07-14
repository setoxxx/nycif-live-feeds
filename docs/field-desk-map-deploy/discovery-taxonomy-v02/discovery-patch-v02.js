/**
 * Discovery Taxonomy v02 config — must load before app-schema-v1-major-all-v01.js.
 * Enables discovery feedRoot, interest OR matching, marker role gates, and labels.
 */
window.NYCIF_DISCOVERY_V02 = {
  version: "discovery-taxonomy-v02",
  feedRoot: "schema-v1-discovery",
  categoryMeta: {
    sports: { emoji: "🏟️", label: "Sports" },
    civic: { emoji: "📣", label: "Parades / civic" },
    market: { emoji: "🛍️", label: "Street fairs / markets" },
    arts: { emoji: "🎭", label: "Arts / performance" },
    parks: { emoji: "🌳", label: "Parks / outdoors" },
    fitness: { emoji: "💪", label: "Fitness / wellness" },
    family: { emoji: "👨‍👩‍👧", label: "Kids / family" },
    education: { emoji: "📚", label: "Classes / workshops" },
    volunteer: { emoji: "🙋", label: "Volunteer opportunities" },
    general: { emoji: "📍", label: "General" },
    tours: { emoji: "🗺️", label: "Tours / history" },
    government: { emoji: "🏛️", label: "Government / meetings" },
    services: { emoji: "🤝", label: "Health / benefits" },
    jobs: { emoji: "💼", label: "Jobs / career" },
    housing: { emoji: "🏠", label: "Housing / tenant help" },
    environment: { emoji: "🌎", label: "Environment / nature" },
  },
};
