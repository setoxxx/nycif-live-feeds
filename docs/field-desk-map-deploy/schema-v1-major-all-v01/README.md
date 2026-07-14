# Unified Major + All Events viewer (schema-v1)

Canonical Field Desk runtime for schema-v1 Major Events / All Events.

Apply the files in this directory onto `setoxxx/nycif-field-desk` (supersedes the disconnected explorer on PR #106).

Do not keep a second copy of normalization/rendering logic elsewhere in this repo.

## Runtime

- Cache token: `schema-v1-major-all-v01`
- Default mode: Major Events, Next 7 days
- Marker strategy: Leaflet.markercluster with viewport-focused marker instantiation (not a full dump load)
- List: 100 + Load 100 more; search status reports when page indexing is incomplete
- Progressive feeds (after live-feeds merge to `main`, or `?feeds=<branch>` for preview):
  - `data/schema-v1/major/events.json`
  - `data/schema-v1/approved/manifest.json` + `pages/page-XXXX.json`
  - `data/schema-v1/review/manifest.json` + `pages/page-XXXX.json` (All Sources / Review only)
- Security: event strings use `textContent`; source URLs validated as absolute `http:`/`https:` only

## Zero-major fallback

1. Try Major / next 7 days
2. If empty, jump to next future major date with banner
3. If no upcoming major at all, switch to All Events next 7 with banner

## Next 7 days definition

`today` through `today + 7` inclusive.

## WordPress

Do not ship plugin 1.4.0 from this mirror. Keep plugin 1.3.1 / PR #164 as rollback until live Pages pass.
