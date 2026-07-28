# City Engine protected staging feed

## Purpose

Convert the existing NYCIF staged-event snapshot into the City Engine GeoJSON schema for editor-only WordPress review.

The adapter reads `data/nycif_staged_live_events.json` but never modifies it. Its output is a separate review artifact and does not authorize publication, public-map use, feed promotion, WordPress upload, or replacement of `/map/`.

## Eligibility

A source row is included only when all of these are true:

- `staged_feed` is exactly `true`
- `production_ready` is exactly `true`
- `needs_review` is exactly `false`
- the event has a stable non-empty ID and title
- the date is inside the requested review window
- latitude and longitude are inside conservative NYC bounds
- the eligible ID is unique

Every converted feature sets:

- `public_display_eligible: false`
- `staging_display_eligible: true`
- `review_status: protected-staging`

This keeps the artifact usable in the authenticated draft preview without treating it as a public feed.

## Freshness gate

The adapter reads `feed-metadata.json` and compares `generated_at_utc` with the review time. A normal build writes a feed only when:

- the source age is within `--max-source-age-hours`; and
- at least one eligible event falls inside the requested window.

A stale source writes a diagnostic report but no feed. `--report-only` can be used for diagnostics without producing a GeoJSON artifact.

## Outputs

The adapter writes only beneath the explicitly supplied output directory:

- `city-engine-staging-feed-report.json`
- `city-engine-staging-feed.geojson` only when all gates pass and `--report-only` is not used

## Example review command

```bash
python3 scripts/build_city_engine_staging_feed.py \
  --input data/nycif_staged_live_events.json \
  --metadata feed-metadata.json \
  --output-dir /tmp/nycif-city-engine-staging-feed-review \
  --window-start 2026-07-27 \
  --window-days 8 \
  --max-source-age-hours 36 \
  --report-only
```

## Current blocker

The committed feed metadata reports `generated_at_utc` as July 14, 2026. That snapshot is stale for a July 27, 2026 staging review, so the adapter must fail closed until the existing feed refresh workflow produces a current reviewed snapshot.

## Explicit non-actions

This work does not:

- edit `data/nycif_staged_live_events.json`
- edit `data/location_cache.json`
- change the public map feed
- change `/map/`
- change the existing WordPress public map plugin
- publish or promote any event
- upload or replace the City Engine staging plugin
