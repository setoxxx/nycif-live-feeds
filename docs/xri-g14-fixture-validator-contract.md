# XRI-G14 Fixture Validator Contract

## Phase

XRI-G14

## Source

- Source phase: XRI-G13
- Source PR: #18
- Source merge commit SHA: `10509fb463a18a3fadb0ba39f29857981543ecc1`

## Mode

Non-production fixture validator only.

XRI-G14 defines the validation contract for fixture-only manual-review schema examples introduced by XRI-G13. It does not enable approval, geocoding, promotion, publishing, registry import, database creation, runtime behavior, public map behavior, or production feed behavior.

## Allowed in XRI-G14

XRI-G14 may define validation rules for:

- Required field presence.
- Required identity fields.
- Required source fields.
- Required display and location text fields.
- Required reviewer decision fields.
- Required audit fields.
- Required blocking fields.
- Allowed review decision values only.
- Forbidden review decision values absent.
- Blocking fields remaining true.
- Coordinate absence.
- Production path absence.
- Runtime/importer/database behavior absence.
- Deterministic fixture ordering.
- Fixture-only input/output behavior.
- Fail-closed behavior for unexpected fields or forbidden decisions.

## Not allowed in XRI-G14

XRI-G14 must not:

- Modify production feeds.
- Modify public map runtime.
- Modify WordPress.
- Modify `nycinfocus.com/map`.
- Modify iframe or embed settings.
- Modify scheduled workflows.
- Touch `data/location_cache.json`.
- Run live staging.
- Fetch SODA or other live data.
- Geocode.
- Approve candidates.
- Promote candidates.
- Create registry database behavior.
- Create importer behavior.
- Add runtime publishing behavior.
- Publish anything.
- Start XRI-G15.

## Required field groups

A fixture validator should require the field groups defined by XRI-G13.

### Identity fields

- `review_record_id`
- `candidate_identity_key`
- `group_key`
- `source_dataset_id`
- `source_record_id`

### Source fields

- `source_name`
- `source_url`
- `source_observed_at`
- `source_phase`
- `source_pr`

### Display and location text fields

- `title`
- `display_location`
- `location_text_raw`
- `location_confidence`
- `location_notes`

### Reviewer decision fields

- `review_decision`
- `review_reason`
- `review_notes`
- `needs_more_context_reason`

### Audit fields

- `reviewer_id`
- `reviewed_at`
- `review_batch_id`
- `schema_version`
- `created_at`
- `updated_at`

### Blocking fields

- `production_blocked`
- `geocode_blocked`
- `promotion_blocked`
- `publishing_blocked`
- `registry_import_blocked`

## Allowed review decision values

The validator should allow only:

- `hold`
- `reject`
- `needs_more_context`
- `eligible_for_future_review`

## Forbidden review decision values

The validator should reject:

- `approved`
- `geocoded`
- `promoted`
- `published`

## Blocking-field requirements

The validator should require these fields to remain true:

- `production_blocked`
- `geocode_blocked`
- `promotion_blocked`
- `publishing_blocked`
- `registry_import_blocked`

## Coordinate prohibition

The validator should fail closed if coordinate fields are present, including but not limited to:

- `latitude`
- `longitude`
- `lat`
- `lon`
- `lng`
- `coordinates`
- `geometry`

## Production path prohibition

The validator should fail closed if fixture records target production or runtime output paths.

## Runtime/importer/database prohibition

The validator should fail closed if fixture records or validator metadata imply runtime publishing, registry import, database writes, production feed writes, public map behavior, WordPress behavior, geocoding, approval, or promotion.

## Deterministic fixture ordering

The validator should require deterministic ordering by stable identity fields, preferably:

1. `source_dataset_id`
2. `group_key`
3. `candidate_identity_key`
4. `review_record_id`

## Fixture-only input/output behavior

Inputs and outputs must remain fixture-only. Output may be a validation report or summary, but must not be consumed by production runtime, public map runtime, registry import, scheduled workflows, WordPress, geocoding, approval, or promotion.

## Fail-closed behavior

The validator should fail closed when:

- Required fields are missing.
- Allowed decision values are violated.
- Forbidden decision values appear.
- Blocking fields are false or missing.
- Coordinates appear.
- Production paths appear.
- Runtime/importer/database behavior appears.
- Unexpected fields imply production, geocoding, approval, promotion, publishing, registry import, database creation, scheduled workflows, WordPress, or public map behavior.

## Proposed XRI-G15 gate

XRI-G15 should execute the non-production fixture validator against fixture examples only. It may produce a fixture-only validation report.

XRI-G15 must not start from this PR. It requires a separate explicit prompt after XRI-G14 is reviewed and merged.

## Review gate

Open a PR only. Do not merge. Do not start XRI-G15.
