# Events source inventory v02

Generated: `2026-07-14T05:11:43Z`

- Source files discovered in catalog: **16**
- Raw intake event-like rows: **39873**
- Generated output rows (excluded from raw intake): **108261**
- Duplicative source rows: **66168**
- Historical-only rows: **23693**

## Sources

- `raw-nyc-open-data-street-events` — `data/raw_nyc_open_data_snapshot.json` — status=`used` — rows=35438
- `nyc-citywide-events-calendar` — `data/nyc_citywide_events_calendar_snapshot.json` — status=`review_only` — rows=2781
- `nyc-parks-bigapps-events` — `data/nyc_parks_bigapps_events_snapshot.json` — status=`review_only` — rows=1654
- `nycif-staged-live-events` — `data/nycif_staged_live_events.json` — status=`used` — rows=32845
- `supplemental-events-staging-feed` — `data/supplemental_events_staging_feed.json` — status=`review_only` — rows=4032
- `nycif-all-radar-map-events` — `nycif_all_radar_map_events.json` — status=`duplicative_source` — rows=33084
- `nycif-live-test-enriched-events` — `data/nycif_live_test_enriched_events.json` — status=`duplicative_source` — rows=33084
- `previous-staged-live-events-snapshot` — `data/previous_staged_live_events_snapshot.json` — status=`historical_only` — rows=23111
- `nycif-major-radar-map-events-legacy` — `nycif_major_radar_map_events.json` — status=`historical_only` — rows=582
- `row-disposition-events` — `data/row_disposition_events.json` — status=`generated_output` — rows=34075
- `events-schema-v1-staged` — `data/events_schema_v1_staged.json` — status=`generated_output` — rows=32845
- `events-schema-v1-supplemental-review` — `data/events_schema_v1_supplemental_review.json` — status=`generated_output` — rows=4032
- `events-schema-v1-major` — `data/events_schema_v1_major.json` — status=`generated_output` — rows=432
- `schema-v1-approved-pages` — `data/schema-v1/approved/manifest.json` — status=`generated_output` — rows=32845
- `schema-v1-review-pages` — `data/schema-v1/review/manifest.json` — status=`generated_output` — rows=4032
- `location-cache` — `data/location_cache.json` — status=`historical_only` — rows=0
