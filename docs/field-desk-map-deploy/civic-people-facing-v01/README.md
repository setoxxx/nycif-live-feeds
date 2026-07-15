# Civic people-facing v01 — Field Desk package

Staged **Review / Help Places** wiring for Jobs, Volunteer, OAC activities, farmers markets, and benefits/help directories.

Does **not** publish to the public map. Does **not** modify Approved permit feeds or `location_cache.json`.

## Lanes

| Lane | Source | Field Desk filter |
|------|--------|-------------------|
| Approved | existing `schema-v1-discovery` approved (permits) | Approved |
| Review | discovery review (calendar / Parks) **UNION** `schema-v1-civic-review/review` | Review |
| Help Places | `schema-v1-civic-review/help` (markets + benefits/SNAP/drop-in/Homebase/aging/NYCHA) | Help Places / Markets |

Major default + Next 7 days remain. **Show All Upcoming** is still the Ouija control.

List cards show **source dataset**, **date/schedule**, and **coordinate_status** (`map_ready` / `LIST ONLY` / `PROPOSED`).

## Feeds (live-feeds repo)

| Artifact | Path |
|----------|------|
| Combined staging | `data/civic_people_facing_staging_feed.json` |
| Civic review pages | `data/schema-v1-civic-review/review/` |
| Help pages | `data/schema-v1-civic-review/help/` |
| QA | `data/civic_people_facing_date_time_location_qa.json` |
| Continuity | `data/civic_people_facing_continuity_report.json` |
| Food-access gap | `data/civic_food_access_gap_note.json` |

## Howard Pages push checklist (`nycif-field-desk`)

`cursor[bot]` **cannot** push `setoxxx/nycif-field-desk`. Howard must copy:

| Copy from live-feeds | Into field-desk |
|----------------------|-----------------|
| `docs/field-desk-map-deploy/civic-people-facing-v01/index.html` | `index.html` (or civic review path) |
| `docs/field-desk-map-deploy/civic-people-facing-v01/civic-patch-v01.js` | `./civic-patch-v01.js` |
| `docs/field-desk-map-deploy/civic-people-facing-v01/public-map-defaults-v01.js` | `./public-map-defaults-v01.js` (civic-specific; not a discovery copy) |
| `docs/field-desk-map-deploy/civic-people-facing-v01/service-worker.js` | `./service-worker.js` (thin civic shell SW) |
| `docs/field-desk-map-deploy/schema-v1-major-all-v01/app-schema-v1-major-all-v01.js` | `./app-schema-v1-major-all-v01.js` (**required** — civic feed hooks) |
| `docs/field-desk-map-deploy/schema-v1-major-all-v01/event-feed-schema-v1.js` | `./event-feed-schema-v1.js` |
| CSS/overlay siblings from `discovery-taxonomy-v02/` if not already on Pages | local `./` copies |

After copy, change any `../schema-v1-major-all-v01/` or `../discovery-taxonomy-v02/` script `src` values to local `./` paths as needed.

Preview:

```text
?v=civic-people-facing-v01&resetFilters=1&feeds=cursor/civic-people-facing-intake-da92
```

Checklist after Pages deploy:

1. Major default + Next 7 days
2. All Events → Review shows calendar/Parks **and** civic rows (OAC / volunteer)
3. Help Places / Markets shows directories; pins only when `map_ready`
4. List item shows dataset id + coordinate status
5. Approved permit lane unchanged
6. Incognito + mobile smoke

## Safety

- `promotion_allowed: false` on all civic rows
- `manual_review_status: pending`
- `public_map_modified` / `location_cache_modified` / `staged_feed_modified`: false
- Soup-kitchen citywide live pin feed remains a **known gap** (see `data/civic_food_access_gap_note.json`)
