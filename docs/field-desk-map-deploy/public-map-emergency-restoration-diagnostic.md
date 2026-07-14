# Public map emergency restoration — pre-fix diagnostic

Generated: 2026-07-14 (UTC) during emergency repair for Howard Weiss.

## Backend health (nycif-live-feeds dashboard)

Source: `status/nycif-live-pipeline-dashboard.json` (`generated_at_utc`: 2026-07-14T02:02:16Z)

| Metric | Count |
| --- | ---: |
| staged_feed_events | 32,845 |
| classified_permit_rows / current_future_raw_rows | 33,084 |
| fitness | 192 |
| parks | 4,461 |
| sports | 27,020 |
| market | 930 |
| arts | 218 |
| general | 24 |

Staged feed file `data/nycif_staged_live_events.json` was inspected locally:

- 32,845 events, all with valid NYC coordinates
- Date range begins `2026-07-14` through `2026-12-27`
- 1,125 events on local calendar date 2026-07-14
- Categories present include `fitness`

## Live Field Desk (GitHub Pages + local main checkout)

Served local main checkout at `http://127.0.0.1:8765/` and compared with `https://setoxxx.github.io/nycif-field-desk/`.

| Observation | Value |
| --- | --- |
| App version string | `0.6-staged-03-new-admin-filter` |
| `PUBLIC_DEFAULT_VERSION` | `major-only-v04` |
| Boot feed request | `nycif_major_radar_map_events.json` only |
| Status line | `10 assignments · Fast major feed · v0.6-...` |
| Event list items | 10 |
| Parks / General checkboxes | unchecked / absent fitness control |
| Major events only | checked (`true`) |
| localStorage prefs version | `major-only-v04` with `majorOnly: true`, parks/general false, fitness missing |
| Active service-worker cache | `nycif-v014-category-defaults-fix` |
| Fatal console errors | none observed |
| Staged / full feed fetch on boot | **not requested** |

## Root cause

The public map boots the **major** assignment feed (~582 rows) with **major-only** public defaults, parks/general disabled, and no fitness category. Ordinary staged live events (~32k) are never loaded on first paint. Overlay scripts (`public-approved-overlays-v01.js`) still load separately, so 5PM / cannabis / correlation pins can appear while the ordinary event population looks empty or near-empty.

Secondary risks confirmed in source:

1. Strict `dateMode: 'today'` with no next-date fallback can blank the map when the browser date precedes the earliest feed date.
2. `makeEvent` derives `dateKey` primarily from `Date.parse(start_date_time)`, which can shift calendar days under UTC offsets; `row.date` should be primary.
3. Service worker + old `?v=` query strings keep serving the major-only shell after code updates.

## M10 mirror note

`nycif-live-feeds/docs/field-desk-map-deploy/` contains a partial repair (staged boot, fitness classifier stub, parks/general in defaults file, marker cap 2000) that was **not** deployed to `nycif-field-desk` main. That mirror still leaves fitness default `false` in app state and lacks resilient multi-feed fallback, today→next-date fallback, significance UI, and SW bust — so it is a reference, not a blind overwrite target.

## Safety check for this diagnostic

- Did not modify `data/location_cache.json`
- Did not alter GPS review / approval artifacts
- Did not publish to WordPress or GitHub Pages
