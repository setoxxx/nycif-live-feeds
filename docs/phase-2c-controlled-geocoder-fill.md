# NYCIF Phase 2C Controlled Geocoder Fill

Phase 2C creates a filled proposal artifact for unresolved GPS groups without publishing anything.

## Safety rule

Phase 2C must not modify:

- `data/location_cache.json`
- `data/nycif_staged_live_events.json`
- the public map

Phase 2C writes filled proposals only.

## Script

- `scripts/build_gps_geocoding_filled_proposals.py`

## Inputs

Required:

- `data/gps_review_geocoding_proposals.json`

Optional local reference files:

- `data/manual_gps_reference.json`
- `data/nyc_parks_facility_reference.json`

Existing conservative fallback:

- broad place-name memory from `data/location_cache.json`

## Outputs

- `data/gps_review_geocoding_filled_proposals.json`
- `data/gps_review_geocoding_fill_report.json`

## Current fill order

1. Local manual GPS reference file, if present.
2. Local NYC Parks/facility reference file, if present.
3. Conservative existing NYCIF location-cache broad place-name memory.
4. Leave unresolved rows pending with null coordinates.

## Promotion rule

Phase 2C never sets `promotion_allowed` to true.

Every filled coordinate remains:

- `manual_review_status: pending`
- `promotion_allowed: false`

A later promotion script may only promote a row if it has valid NYC coordinates, documented source, confidence reason, manual approval, and explicit promotion permission.

## Next phase

Phase 2D should inspect filled proposals and create a manual approval workflow.

No public map change should happen before that approval workflow exists.
