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
| `docs/field-desk-map-deploy/civic-people-facing-v01/field-desk-operator-layer-v01.js` | `./field-desk-operator-layer-v01.js` |
| `docs/field-desk-map-deploy/civic-people-facing-v01/field-desk-news-desk-v01.js` | `./field-desk-news-desk-v01.js` |
| `docs/field-desk-admin-deploy/admin/news-desk-godview-panel-v01.js` | `admin/news-desk-godview-panel-v01.js` |
| `docs/field-desk-map-deploy/schema-v1-major-all-v01/app-schema-v1-major-all-v01.js` | `./app-schema-v1-major-all-v01.js` (**required** — civic feed hooks) |
| `docs/field-desk-map-deploy/schema-v1-major-all-v01/event-feed-schema-v1.js` | `./event-feed-schema-v1.js` |
| CSS/overlay siblings from `discovery-taxonomy-v02/` if not already on Pages | local `./` copies |

After copy, change any `../schema-v1-major-all-v01/` or `../discovery-taxonomy-v02/` script `src` values to local `./` paths as needed.

Preview (PR #171/#172 merged — use `main` feeds):

```text
?v=civic-people-facing-v01&resetFilters=1&feeds=main
```

Photographer calendar day deep-link (from God View “Map day”):

```text
?v=civic-people-facing-v01&resetFilters=1&feeds=main&mode=all&date=2026-07-20
```

**Assignment Mode** (Money-Day Desk v2 — curated pins/list only for that date):

```text
?v=civic-people-facing-v01&resetFilters=1&feeds=main&mode=all&date=2026-07-20&assignment=1
```

Optional borough chip (from God View Today/Tomorrow packs):

```text
?v=civic-people-facing-v01&resetFilters=1&feeds=main&mode=all&date=2026-07-20&assignment=1&borough=Brooklyn
```

**News Desk checklist + parade census** (staging overlay — operator/assignment mode only):

```text
?v=civic-people-facing-v01&resetFilters=1&feeds=main&mode=all&assignment=1
```

Loads `news_desk_assignment_checklist.json` + optional `citywide_parade_census_snapshot.json` pins in Filters panel. **Not** loaded on public map without `?assignment=1`.

ODB example (Jul 25 Brooklyn):

```text
?v=civic-people-facing-v01&resetFilters=1&feeds=main&mode=all&date=2026-07-25&assignment=1&borough=Brooklyn
```

Backend artifacts (after PR #179 merge): `data/news_desk_assignment_checklist.json`, `data/citywide_parade_census_snapshot.json`

Daily auto-pull workflow (live-feeds repo): `.github/workflows/daily-people-facing-desk-sync.yml`  
Artifacts: `data/photographer_assignment_calendar_2mo.json`, `data/photographer_money_day_quality_report.json`, `data/photographer_money_day_pack_today.json`, `data/photographer_money_day_pack_tomorrow.json`, `data/pin_integrity_gate_report.json`, `data/photographer_shoot_day_certified_pack.json`, `data/daily_people_facing_sync_report.json`

### Pin integrity (hard law)

Pins are integrity-gated via `scripts/pin_integrity.py` (NYC metro box lat 40.4774–40.9176, lng −74.2591–−73.7004). Ocean / Null Island / lat-lng swap / OOB cannot remain `map_ready` if the daily pin gate is green — bad rows demote to `list_only` with a clear reason and cleared coordinates. Field Desk Assignment Mode + money-day deep links refuse to plot non-certified pins; LIST ONLY stays visible in lists with the LIST ONLY badge.

Checklist after Pages deploy:

1. Major default + Next 7 days
2. All Events → Review shows calendar/Parks **and** civic rows (OAC / volunteer)
3. Help Places / Markets shows directories; pins only when `map_ready`
4. List item shows dataset id + coordinate status
5. Assignment Mode deep-link narrows to money-day ids for the date (fail soft if calendar missing)
6. News Desk panel appears in Filters when `?assignment=1` (staging checklist + optional census pins)
7. Public map without `?assignment=1` shows **no** News Desk / Operator Desk UI
8. Ocean / (0,0) / swapped / OOB pins never render as markers when pin gate is green
9. Approved permit lane unchanged
10. Incognito + mobile smoke

## Safety

- `promotion_allowed: false` on all civic rows
- `manual_review_status: pending`
- `public_map_modified` / `location_cache_modified` / `staged_feed_modified`: false
- Soup-kitchen citywide live pin feed remains a **known gap** (see `data/civic_food_access_gap_note.json`)
