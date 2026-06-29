# NYCIF Phase 1 Backend Reliability

Phase 1 is complete only when the backend can run without manual intervention and prove that every current/future NYC Open Data permit row is accounted for.

## Source

Primary city source:

- Dataset: NYC Permitted Event Information
- Dataset ID: tvpp-9vvx
- SODA2 endpoint: https://data.cityofnewyork.us/resource/tvpp-9vvx.json

## Automated workflow

Workflow:

- `.github/workflows/live-sync-qa.yml`

Triggers:

- Manual dispatch
- Hourly schedule
- Pushes to `main` that affect scripts/workflow/source feed files

## Pipeline contract

Every current/future incoming row must end in exactly one disposition:

1. `staged_with_valid_gps`
2. `matched_known_gps_memory`
3. `gps_review_queue`
4. `rejected_with_reason`

No row may silently disappear.

## Required artifacts

The workflow must create or refresh these files:

- `data/raw_nyc_open_data_snapshot.json`
- `data/live_sync_report.json`
- `data/nycif_live_test_enriched_events.json`
- `data/test_enriched_feed_manifest.json`
- `data/nycif_staged_live_events.json`
- `data/staged_live_manifest.json`
- `data/location_cache.json`
- `data/gps_repository_report.json`
- `data/gps_needs_review_events.json`
- `data/live_delta_report.json`
- `data/remainder_year_coverage_report.json`
- `data/row_disposition_report.json`
- `data/row_disposition_events.json`
- `data/feed_anomaly_report.json`
- `data/backend_reliability_gate_report.json`

## Reliability gate

Script:

- `scripts/backend_reliability_gate.py`

The gate passes when:

- Required artifacts exist and are not empty.
- Raw city snapshot has rows.
- Test feed has events.
- Staged feed has events.
- `row_disposition_report.json` has `qa_pass: true`.
- `unclassified_rows` is `0`.
- Classified row count equals current/future raw row count.
- GPS cache has entries.

The gate allows warnings for legitimate GPS review work. A non-empty GPS review queue is not a failure. It means the backend caught rows that need coordinate work instead of silently publishing bad pins.

## Success criteria

Phase 1 is complete when one full automatic workflow run produces:

- `backend_reliability_gate_report.json` with `gate_pass: true`
- `row_disposition_report.json` with `qa_pass: true`
- `row_disposition_report.json` with `unclassified_rows: 0`
- A valid staged feed consumed by the public map
- A valid GPS review queue for unresolved coordinates
- No admin-only controls exposed on the public map

## Public map boundary

Public map should consume only staged/public-safe feed data.

Admin/testing controls remain on:

- `https://setoxxx.github.io/nycif-field-desk/desk.html`

Public reader map remains:

- `https://nycinfocus.com/map/`

## Next phases

Only after Phase 1 passes:

1. Add controlled geocoding for `gps_needs_review_events.json`.
2. Add partner/API event sources.
3. Add branding refinements.
4. Add monetization/ads.
5. Update the public launch article.
