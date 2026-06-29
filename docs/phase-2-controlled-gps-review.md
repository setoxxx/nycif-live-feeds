# NYCIF Phase 2 Controlled GPS Review

Phase 2 reduces the GPS review queue without risking bad public map pins.

## Goal

Take unresolved events from:

- `data/gps_needs_review_events.json`

Group them into repeated unresolved locations, then create a staging-only geocoding queue.

## Important safety rule

Phase 2 must not directly publish coordinates to the public map.

The Phase 2 grouping step does not modify:

- `data/location_cache.json`
- `data/nycif_staged_live_events.json`
- public WordPress map

## Script

- `scripts/build_gps_review_groups.py`

## Outputs

- `data/gps_review_group_report.json`
- `data/gps_review_location_groups.json`
- `data/gps_review_geocoding_queue.json`

## What the grouping script does

1. Reads GPS review events.
2. Groups repeated unresolved locations by borough + normalized location text.
3. Counts how many events each unresolved location affects.
4. Classifies location complexity:
   - `single_place_or_block`
   - `street_between_pair`
   - `park_or_facility_subsite`
   - `multi_segment_corridor`
   - `missing_location`
5. Creates a geocoding queue with blank proposed coordinate fields.
6. Marks every item as not public and not promoted.

## Geocoding queue fields

Each queue item includes:

- `group_key`
- `priority_score`
- `event_count`
- `borough`
- `display_location`
- `geocoder_query`
- `confidence_hint`
- `location_complexity`
- `proposed_lat`
- `proposed_lng`
- `geocoder_source`
- `geocoder_confidence`
- `manual_review_status`
- `promotion_allowed`

## Promotion rule

No proposed coordinate may be promoted to `location_cache.json` unless all of these are true:

- `proposed_lat` exists
- `proposed_lng` exists
- `geocoder_source` is documented
- `geocoder_confidence` is high enough
- `manual_review_status` is `approved`
- `promotion_allowed` is `true`

Promotion will require a separate script in a later step.

## Recommended Phase 2 order

1. Run the normal `NYCIF Live Sync QA` workflow.
2. Inspect `data/gps_review_group_report.json`.
3. Identify top repeated unresolved locations.
4. Decide whether to geocode using Google Places, Foursquare Places, or manual lookup.
5. Fill proposed coordinates only in the staging geocoding queue.
6. Add a separate approval/promote script later.

## Completion criteria

Phase 2 grouping is complete when:

- `gps_review_group_report.json` exists.
- `gps_review_location_groups.json` exists.
- `gps_review_geocoding_queue.json` exists.
- The public map is unchanged.
- `location_cache.json` is unchanged by the grouping step.
- The top unresolved location groups are visible and prioritized.
