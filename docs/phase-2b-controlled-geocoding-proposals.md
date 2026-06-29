# NYCIF Phase 2B Controlled Geocoding Proposals

Phase 2B prepares GPS review candidates for geocoding without publishing anything.

## Safety rule

Phase 2B must not modify:

- `data/location_cache.json`
- `data/nycif_staged_live_events.json`
- the public map

Phase 2B writes proposal files only.

## Scripts

- `scripts/build_gps_review_groups.py`
- `scripts/build_gps_geocoding_proposals.py`

## Outputs

- `data/gps_review_group_report.json`
- `data/gps_review_location_groups.json`
- `data/gps_review_geocoding_queue.json`
- `data/gps_review_geocoding_proposals.json`
- `data/gps_review_geocoding_proposal_report.json`

## Location group fix

`gps_review_location_groups.json` is intentionally compact and readable:

- maximum 3 sample events per group
- top title/type/agency counts only
- simplified geocoder query included
- no full repeated event dump per group

## Proposal file behavior

`gps_review_geocoding_proposals.json` contains only the top safe review candidates.

Every proposal starts with:

- `proposed_lat: null`
- `proposed_lng: null`
- `geocoder_source: null`
- `geocoder_confidence: null`
- `manual_review_status: pending`
- `promotion_allowed: false`

## Promotion rule

No proposal may be promoted unless a later promotion script confirms:

- valid NYC latitude/longitude
- named geocoder source
- confidence reason
- manual review approved
- promotion allowed

Promotion is intentionally not part of Phase 2B.

## Next step after Phase 2B

Run the workflow, inspect the proposal report, then decide which geocoder to use:

- manual review
- Google Places
- Foursquare Places
- NYC Parks reference data

The next phase should be `Phase 2C: geocoder integration or manual coordinate fill`, not public release.
