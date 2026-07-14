# Complete NYCIF event-data access review

Branch: `cursor/review-complete-event-data-access`  
Reviewed against Field Desk `main` restore (`f272e16`, emergency map restore v02) plus focused access improvements in this PR.  
App version after fixes: `0.8-event-data-access-v01`  
Date of review: 2026-07-14

## Verdict

**The entire staged dataset is loaded and classified correctly.**  
No staged rows are rejected for coordinates or shape.

Remaining gaps before this PR were **access UX**, not data loss:

1. Event list rendered only the first **80** matching rows with no Load-more path.
2. Map attempted to draw up to **12,000** markers at once; on All upcoming that silently omitted **20,845** matching events from the map layer.
3. Status text did not clearly separate feed / match / currently drawn markers.

This PR keeps all **32,845** events in memory and makes them reachable via date chips, category filters, borough, search, and paginated list. Map markers now use **viewport-bounded rendering** (cap 700 in/near view) without adding a clustering dependency.

Gold/Silver/Bronze was intentionally **not** reintroduced.

## Current backend dashboard counts

Source: `nycif-live-feeds/status/nycif-live-pipeline-dashboard.json`

| Metric | Count |
| --- | ---: |
| staged_feed_events | 32,845 |
| classified / current_future | 33,084 |
| sports | 27,020 |
| parks | 4,461 |
| market | 930 |
| arts | 218 |
| fitness | 192 |
| general | 24 |

## Pipeline measurement (staged JSON)

| Stage | Count |
| --- | ---: |
| Raw staged rows (`object.events`) | 32,845 |
| Invalid JSON row shape | 0 |
| Missing / non-numeric lat/lng | 0 |
| Outside NYC bounds | 0 |
| Accepted into `state.events` | **32,845** |

NYC bounds used: lat `40.4774–40.9176`, lng `-74.2591–-73.7004`.  
No rejected bound samples were found for Staten Island / Rockaway / Bronx / waterfront.

### Category comparison

Backend category is preferred when supported. All 32,845 rows carried a supported backend category.

| Category | Backend | Frontend after classify |
| --- | ---: | ---: |
| sports | 27,020 | 27,020 |
| parks | 4,461 | 4,461 |
| market | 930 | 930 |
| arts | 218 | 218 |
| fitness | 192 | 192 |
| general | 24 | 24 |
| Keyword override of backend | — | **0** |

Softballs remain Sports. Yoga / tai chi / bootcamp remain Fitness when categorized by backend.

### Date window

**Standard used:** `next7` = today through today+7 inclusive (**8 calendar dates**).

| Window | Count |
| --- | ---: |
| Today (2026-07-14) | 1,125 |
| Next 7 days inclusive | 9,136 |
| All upcoming (`dateKey >= today`) | 32,845 |
| Past rows in staged feed | 0 |
| Invalid dates | 0 |
| Earliest / latest | 2026-07-14 / 2026-12-27 |

Events outside Next 7 days are **not deleted**; they remain available under **All upcoming** and single-day chips.

## Pre-fix live behavior (GitHub Pages + local main)

URL: `?v=map-restore-v02&resetFilters=1`

| Observation | Result |
| --- | --- |
| Boot feed | staged JSON 200 |
| Defaults | staged-live-v04, next7, all categories on, majorOnly off |
| Fitness control | present |
| Feed accepted | 32,845 (matches status when All upcoming) |
| Next 7 match | 9,136 |
| List rendered | **80 only**, no pagination |
| Softballs search | status updated to 2,440 (search covers full dataset) |
| All upcoming markers | **12,000** of 32,845 (cap silence) |
| SW cache | `nycif-v015-map-restore-v02` |
| Overlay controls | 5PM / cannabis / correlation present |
| Fatal console errors | none |

## Focused fixes in this PR

1. Status chrome: `feed · match · markers in view`
2. Event-list pagination: Load more, `Showing X of Y matching events`
3. Viewport-bounded marker drawing (`VIEW_MARKER_CAP=700`) on moveend/zoomend — avoids 12k DOM markers without a new clustering dependency
4. Date chips show counts (e.g. `Next 7 days (9,136)`)
5. Empty/filter recovery actions
6. `?debugMap=1` console.table pipeline diagnostics (`window.NYCIF_MAP_DEBUG`)
7. Service-worker cache bump to `nycif-v016-event-data-access`
8. Asset cache token `map-access-v01`

### Why no Leaflet.markercluster dependency

Viewport-bounded rendering is sufficient for this emergency access review: filtered result counts remain accurate, list pagination reaches every match, and in-view markers stay within a safe DOM budget. Clustering can be added later if product wants citywide dense clusters when zoomed out.

## Post-fix local browser results

URL: `http://127.0.0.1:8766/?v=map-access-v01&resetFilters=1&debugMap=1`

| Check | Result |
| --- | --- |
| Status | `32,845 feed · 9,136 match · 700 markers in view` |
| List | `Showing 80 of 9,136` + Load more |
| Load more | 80 → 160 |
| All upcoming | `32,845 match · 700 markers in view` (all remain searchable/listable) |
| Debug table | raw/accepted 32845, rejects 0, cats match backend |
| SW | `nycif-v016-event-data-access` |
| Overlays | controls present |
| `node --check app-v06-safe.js` | PASS |

## Service worker

- New cache name installed/activated locally after reload
- Network-first retained for index / app / defaults / SW / raw GitHub feeds
- Offline fallback via cache put after successful network response still present

## Overlays

Independent overlay controls remain in Filters. They load separate local JSON and are not counted in feed/match totals.

## Exact files changed

- `app-v06-safe.js`
- `index.html`
- `public-map-defaults-v01.js`
- `public-map-v01.css`
- `service-worker.js`
- `docs/complete-event-data-access-review.md`

## Remaining limitations

1. Markers in view are a viewport sample (≤700), not a 1:1 citywide pin for every match. All matches remain reachable via list pagination + search + filters.
2. Dense zoomed-out citywide overview without clustering may look sparse until the user zooms in.
3. Search may match substring hits across location text (not a correctness failure of feed access).
4. GitHub Pages will not show this access PR until it is merged/deployed.
5. WordPress iframe only reflects Pages; plugin packaging is outside this Field Desk PR scope (see live-feeds PR #164).
6. Significance tiers intentionally omitted from this review.

## Claim boundary

It is accurate to say:

> Every accepted staged event is loaded, classified, filterable, searchable, and reachable through the event list.

It is **not** accurate to say every accepted event is drawn as a Leaflet marker simultaneously.
