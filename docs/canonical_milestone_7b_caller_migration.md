# Canonical Milestone 7-B Caller Migration

Canonical Milestone 7-B migrates active GPS identity callers to the shared
helper introduced in Canonical Milestone 7-A:

- `scripts.gps_identity.normalize_text_legacy`
- `scripts.gps_identity.normalize_text_with_ampersand`
- `scripts.gps_identity.build_group_key`
- `scripts.gps_identity.build_stable_identity_key`
- `scripts.gps_identity.build_stable_event_identity`
- `scripts.gps_identity.row_location`
- `scripts.gps_identity.event_cemsids`
- `scripts.gps_identity.build_repository_candidate_keys`

## Migrated Callers

The migration removes duplicated active-pipeline identity helper copies from:

- `scripts/build_gps_repository.py`
- `scripts/build_gps_review_groups.py`
- `scripts/build_gps_geocoding_filled_proposals.py`
- `scripts/build_gps_manual_approval_staging.py`
- `scripts/generate_gps_staged_feed_integration_match_diagnostic.py`
- `scripts/apply_gps_staged_feed_integration_update.py`
- `scripts/audit_feed_anomalies.py`
- `scripts/audit_row_disposition.py`
- `scripts/build_location_cache.py`
- `scripts/build_staged_production_feed.py`
- `scripts/build_test_enriched_feed.py`
- `scripts/sync_nyc_open_data.py`

Each caller keeps its existing non-identity behavior. Date parsing, source ID
splitting, GPS payload construction, geocoder fill logic, fuzzy staged-feed
matching, feed fetching, report writing, and promotion gates are not changed by
this milestone.

## Compatibility Contract

The M7-A helper oracle tests remain the compatibility baseline. M7-B adds
caller-migration checks that verify:

- authorized callers import the shared helper;
- documented duplicate helper definitions are removed;
- active callers are bound to the canonical helper functions;
- repository cache keys match the helper output bit for bit;
- staged-feed identity remains independent of CEMSID ordering;
- `review_rank` remains informational and is not used as identity.

## Safety Boundary

This milestone does not authorize or implement:

- duplicate-key enforcement;
- positional review-array changes;
- APIs;
- website runtime changes;
- accounts;
- notifications;
- mobile development;
- production changes;
- deployment;
- public-map changes;
- WordPress changes;
- geocoding;
- promotion or publishing.

Protected production data files remain protected. This milestone is source,
tests, and documentation only.
