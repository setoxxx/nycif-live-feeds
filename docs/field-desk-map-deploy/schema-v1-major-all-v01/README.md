# Unified Major + All Events viewer (schema-v1)

Apply these files onto `setoxxx/nycif-field-desk` (successor to PR #106).

This agent cannot push to Field Desk (GitHub 403 for cursor[bot]).

## Runtime

- Cache token: `schema-v1-major-all-v01`
- Default mode: Major Events, Next 7 days
- Marker strategy: Leaflet.markercluster (cap 2500 added layers)
- List: 100 + Load 100 more; search covers full loaded dataset
- Feeds (after live-feeds merge):
  - `data/events_schema_v1_major.json`
  - `data/events_schema_v1_staged.json`
  - `data/events_schema_v1_supplemental_review.json`

## Zero-major fallback

1. Try Major / next 7 days
2. If empty, jump to next future major date with banner
3. If no upcoming major at all, switch to All Events next 7 with banner

## Next 7 days definition

`today` through `today + 7` inclusive.
