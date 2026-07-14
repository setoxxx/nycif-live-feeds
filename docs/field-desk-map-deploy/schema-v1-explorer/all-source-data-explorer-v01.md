# NYCIF all-source data explorer v01

## Purpose

This change preserves the restored public map while adding a separate **All Data** explorer for the event data already produced by `nycif-live-feeds`.

Explorer rows are projected through **event feed schema v1.0** before UI use:

- `schema_version`, `generated_at_utc`, `total`, `next_cursor`
- event fields: `id`, `title`, `category`, `start_date_time`, `end_date_time`, `timezone`, `borough`, `location`, `latitude`, `longitude`, `significance`, nested `source`

See `docs/event_feed_schema_v1.md` in `nycif-live-feeds` for the contract.

## Source separation

The explorer loads and clearly separates:

1. **Approved/staged schema projection** — prefers `data/events_schema_v1_staged.json`, falls back to `data/nycif_staged_live_events.json` and projects client-side.
2. **Expanded review schema projection** — prefers `data/events_schema_v1_supplemental_review.json`, falls back to `data/supplemental_events_staging_feed.json` and projects client-side.

Expanded review records are visibly marked `REVIEW`. They are not written back to the approved feed and are not described as production-approved.

The current supplemental manifest reports 4,032 records: 2,502 citywide-calendar-only records and 1,530 Parks-only records. Of those, 2,961 currently have proposed coordinates and 1,071 remain without coordinates.

## Access model

- Search runs across every loaded record, not only the first rendered rows.
- The list initially renders 100 records and provides **Load 100 more** access.
- Records without usable NYC coordinates remain searchable and visible as `LIST ONLY` (`latitude`/`longitude` null).
- Clicking a map-ready result focuses it on the existing Leaflet map.
- The restored main event map, geolocation, Near Me, directions, date controls, and existing overlays remain unchanged.

## Display categories

Schema category slugs:

- `sports`, `fitness`, `parks`, `arts`, `market`, `civic`, `government`, `education`, `family`, `services`, `environment`, `volunteer`, `jobs`, `housing`, `general`

## Safety boundaries

- `data/location_cache.json` is not modified.
- No supplemental record is promoted into the approved production feed.
- Existing 5PM, legal cannabis, and correlation overlays are preserved.
- WordPress remains an iframe wrapper around the GitHub Pages viewer.
- The existing restored runtime is not replaced.

## Validation

- `node --check event-feed-schema-v1.js` passed on the authored file.
- `node --check all-source-data-explorer-v01.js` passed on the authored file.
- `node --check service-worker.js` passed on the authored update.
- Backend `scripts/project_events_schema_v1.py` writes `data/events_schema_v1_validation_report.json`.
- Interactive browser validation remains required after GitHub Pages deploy.
