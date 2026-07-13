# Canonical Milestone 8-B — GPS Review Tail Reduction at Scale

Milestone: **Canonical Milestone 8-B**
Parent: Canonical Milestone 8
Status: **complete (Phase 2C/2D staging)** — manual approval and Phase 2E not authorized

## Objective

Expand Phase 2C geocoder fill from the top-50 proposal batch to the full safe review queue (292 proposals) using `nyc_parks_facility_reference.json`.

## Results (2026-07-13)

| Metric | Top-50 (8) | At scale (8-B) |
|--------|------------|----------------|
| Proposals processed | 50 | **292** |
| Filled | 47 | **233** |
| Unfilled | 3 | **59** |
| From `nyc_parks_bigapps` | 40 | **179** |
| From location cache memory | 7 | **54** |
| Manual approval queue | 47 | **233** |
| Validation `qa_pass` | true | **true** |

Fill rate: **79.8%** (233/292) of safe proposal batch.

## Commands run

```bash
python3 scripts/build_gps_review_groups.py
GPS_PROPOSAL_LIMIT=292 python3 scripts/build_gps_geocoding_proposals.py
python3 scripts/build_gps_geocoding_filled_proposals.py
python3 scripts/build_gps_manual_approval_queue.py
python3 scripts/build_gps_manual_review_sheet.py
python3 scripts/validate_gps_manual_approvals.py
python3 scripts/generate_live_pipeline_dashboard_status.py
```

## Artifacts updated

- `data/gps_review_geocoding_proposals.json`
- `data/gps_review_geocoding_filled_proposals.json`
- `data/gps_review_geocoding_fill_report.json`
- `data/gps_manual_approval_queue.json`
- `data/gps_manual_approval_review_sheet.json` / `.csv`
- `data/gps_manual_approval_validation_report.json`

## Next steps (gated)

1. Human review of 233 pending rows in approval queue / review sheet
2. Set `manual_review_status=approved` only for verified rows (separate explicit commit)
3. Phase 2E promotion **only** with explicit publish authorization
4. Remaining ~59 unfilled proposals: manual geocoding or reference expansion

## Safety

- `location_cache_modified`: false
- `staged_feed_modified`: false
- `public_map_modified`: false
- `promotion_allowed`: false on all queue rows
