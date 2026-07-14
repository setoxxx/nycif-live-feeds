# NYCIF Project Bookmark — Full State & Continuation Prompt

**Bookmark date:** 2026-07-14  
**Purpose:** Single copy-paste reference for any agent or operator — everything done, current data, map URLs, and where the project is moving.

Copy everything below the line into a new Cursor Cloud Agent session to continue work.

---

## Mission snapshot

NYC In Focus (NYCIF) live-event intelligence: ingest NYC permit Open Data + supplemental citywide calendar + Parks BigApps, resolve GPS via tiered public resolver, stage for human review, serve on field desk + public map.

**Prime directive:** Do not publish bad data. Supplemental and resolver-derived rows stay pending until explicitly approved.

---

## Repositories

| Repo | Role | Default branch |
|------|------|----------------|
| `setoxxx/nycif-live-feeds` | Backend feeds, GPS pipeline, QA, status JSON | `main` |
| `setoxxx/nycif-field-desk` | Public Leaflet map (GitHub Pages) + admin dashboard | `main` |
| WordPress (`nycinfocus.com/map/`) | iframe shell → GitHub Pages map | external |

Read **both** `AGENTS.md` files before editing.

---

## Milestone completion log

| Milestone | Status | Key outcome |
|-----------|--------|-------------|
| M8 Live admin dashboard | ✅ merged | Live pipeline panel, multi-source coverage |
| M8-B GPS tail at scale | ✅ merged | Parks facility reference, Phase 2C fill |
| **M9 Coverage gaps** | ✅ merged PR #161 | Supplemental review queues, tiered resolver in test feed, GeoSearch fill |
| **M10 Productionize resolver** | ✅ merged PR #162 | Resolver in `sync_nyc_open_data.py`, supplemental staging feed (4,032 rows) |
| **Schema-v1 Field Desk mirror** | ✅ merged PR #166 | Unified Major/All Field Desk mirror + schema-v1 QA |
| **Discovery Taxonomy v02** | ✅ merged PR #167 | Source-to-map handshake; Sonar Reliability-D fixed; filter counts; Green Market demotion |
| **M7-B.2 self-hash remediation** | ✅ merged PR #148 | `gps-adjudication-self-hash-v1` producer/validator lifecycle |
| **WP map plugin restore package** | ✅ merged PR #164 | Canonical packaging (`map-restore-v02`); live site install still human-only |
| **M10b Live map refresh** | 🔄 human follow-through | Field-desk push, optional WP install from #164, live-sync-qa dispatch |
| M11 Supplemental merge | ⏳ next | Human-approved calendar+Parks → map layer; optional Phase 2E cache promotion (unauthorized until explicit) |
| M7-C duplicate-key enforcement | 🚫 unauthorized | Not started |

---

## Current backend numbers (2026-07-14 QA)

| Metric | Value |
|--------|-------|
| Raw NYC Open Data rows | 35,438 |
| Current/future permit rows | 33,084 |
| Test enriched `needs_review` | **0** |
| Test enriched `gps_ready` | **33,084** (100%) |
| Live sync `matched_with_gps` | **33,084** (resolver in sync) |
| Staged production feed (deduped) | ~32,845 |
| Backend reliability gate | **PASS** |
| GPS review queue | **0** |
| Supplemental staging feed | **4,032** (2,502 calendar + 1,530 Parks) |
| Unit tests | **430+ passed** |

### Resolver tier breakdown (test feed)

- event_id: 21,900 · location_cache: 9,932 · tier_1_gazetteer: 849 · tier_2_midpoint: 285 · tier_2_cache: 1 · text_date_location: 117

---

## Public map & feed URLs (live contract)

### What the map should load (post M10b)

| Feed | URL | Role |
|------|-----|------|
| **Staged (canonical public)** | `https://raw.githubusercontent.com/setoxxx/nycif-live-feeds/main/data/nycif_staged_live_events.json` | Default boot — QA-validated, deduped permit events |
| **Full (Show more)** | `https://raw.githubusercontent.com/setoxxx/nycif-live-feeds/main/nycif_all_radar_map_events.json` | All GPS-ready permit rows from resolver pipeline |
| **Major (legacy curated)** | `https://raw.githubusercontent.com/setoxxx/nycif-live-feeds/main/nycif_major_radar_map_events.json` | Smaller curated subset — stale until rebuilt |
| **Delta** | `https://raw.githubusercontent.com/setoxxx/nycif-live-feeds/main/data/live_delta_report.json` | Newly added highlighting |

### Map entrypoints

| Surface | URL |
|---------|-----|
| GitHub Pages map | https://setoxxx.github.io/nycif-field-desk/ |
| Staged review mode | `?staged=1` or `?feed=staged` |
| Field-desk admin | https://setoxxx.github.io/nycif-field-desk/admin/index.html |
| WordPress wrapper | https://nycinfocus.com/map/ |
| Live pipeline dashboard JSON | https://raw.githubusercontent.com/setoxxx/nycif-live-feeds/main/status/nycif-live-pipeline-dashboard.json |

### QA-only (never public default)

- `data/nycif_live_test_enriched_events.json`
- `data/supplemental_events_staging_feed.json`
- All `gps_review_*`, `gps_manual_approval_*`, resolver unresolved queues

---

## Scripts pipeline (run order)

```bash
# Full backend + map feed refresh
NYCIF_ALLOW_LIVE_GEOSEARCH=yes python3 scripts/sync_nyc_open_data.py
NYCIF_ALLOW_LIVE_GEOSEARCH=yes python3 scripts/build_test_enriched_feed.py
python3 scripts/build_staged_production_feed.py
python3 scripts/build_public_map_feeds.py
python3 scripts/build_supplemental_events_staging_feed.py
python3 scripts/generate_live_pipeline_dashboard_status.py
python3 scripts/backend_reliability_gate.py
```

CI: `gh workflow run live-sync-qa.yml -f allow_live_fetch=yes -f allow_email=no`

---

## Deploy packages (human push when bot 403)

| Package | Source in live-feeds | Target |
|---------|---------------------|--------|
| Admin panel | `docs/field-desk-admin-deploy/admin/` | `nycif-field-desk/admin/` |
| Map live staged | `docs/field-desk-map-deploy/` | `nycif-field-desk/` root |
| WordPress plugin | `docs/wordpress-plugin-deploy/nycif-events-map/` | `nycif-web-platform/wordpress-plugins/` or WP install |

---

## Protected files (do not edit without explicit authorization)

**Backend:** `data/location_cache.json`, `data/nycif_staged_live_events.json`, `data/staged_live_manifest.json`, public feed outputs when not running publish pipeline.

**Frontend:** `app-v06-safe.js`, public map entrypoints, feed URL constants — unless human says publish/update public map.

**Phase 2E:** ~16.5k resolver keys proven in QA but **not** promoted to `location_cache.json`.

---

## Open PRs / branches

| Item | URL / branch |
|------|----------------|
| M10 backend | https://github.com/setoxxx/nycif-live-feeds/pull/162 — `cursor/milestone-10-productionize-resolver-5215` |
| M10b map (field-desk) | branch `cursor/live-staged-map-m10-5215` (after push) |

---

## What remains unpromoted / unapproved

1. Supplemental 4,032 rows — manual review only (`promotion_allowed: false`)
2. Resolver cache → `location_cache.json` — Phase 2E blocked
3. WordPress plugin activation on production — human deploy
4. Field-desk GitHub Pages — verify after map deploy push

---

## Milestone 11 preview (next agent prompt seed)

1. Human review top 100 from `data/supplemental_calendar_only_priority_review.csv`
2. Optional approved supplemental layer on map (separate from permit staged feed)
3. Phase 2E only if human says: **"promote approved resolver rows to location_cache.json"**
4. Rebuild `nycif_major_radar_map_events.json` from priority/major rules if curated default desired

---

## Hard rules (repeat)

- No publish/promote without explicit language
- Admin dashboard: read-only
- Map consumes **staged + all** feeds only — never GPS review artifacts
- Preserve safety fields on all GPS rows

---

## Key artifact index

```
status/nycif-project-status.json
status/nycif-live-pipeline-dashboard.json
status/nycif-milestone-10-productionize-resolver.json
status/nycif-coverage-roadmap.json
data/backend_reliability_gate_report.json
data/test_enriched_feed_manifest.json
data/staged_live_manifest.json
data/supplemental_events_staging_report.json
data/public_map_feed_publish_report.json
docs/nyc-tiered-location-resolver.md
docs/nycif-next-agent-prompt-milestone-10.md
docs/nycif-project-bookmark-prompt.md   ← this file
```

---

*End bookmark — paste above into new agent session to continue.*
