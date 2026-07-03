# XRI-G13 Manual-Review Schema Prototype Contract

## Phase

XRI-G13

## Source

- Source phase: XRI-G12
- Source PR: #16
- Source merge commit SHA: `dd8eb2ae1d782db33fbdbda36ed954343cdde1f1`

## Mode

Non-production manual-review schema prototype only.

XRI-G13 defines a fixture-only manual-review record schema and example records that could support future human review. It does not enable approval, geocoding, promotion, publishing, registry database behavior, or importer behavior.

## Allowed in XRI-G13

XRI-G13 may define:

- Manual-review record fields.
- Required identity fields.
- Required source fields.
- Required display and location text fields.
- Required reviewer decision fields.
- Required audit fields.
- Required blocking fields.
- Allowed future review decisions.
- Explicitly forbidden decisions.
- Fixture-only example records.
- Validation expectations.
- A proposed XRI-G14 gate, without starting XRI-G14.

## Not allowed in XRI-G13

XRI-G13 must not:

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
- Start XRI-G14.

## Manual-review record schema

A future manual-review record should include the following field groups.

### Required identity fields

- `review_record_id`
- `candidate_identity_key`
- `group_key`
- `source_dataset_id`
- `source_record_id`

### Required source fields

- `source_name`
- `source_url`
- `source_observed_at`
- `source_phase`
- `source_pr`

### Required display and location text fields

- `title`
- `display_location`
- `location_text_raw`
- `location_confidence`
- `location_notes`

### Required reviewer decision fields

- `review_decision`
- `review_reason`
- `review_notes`
- `needs_more_context_reason`

### Required audit fields

- `reviewer_id`
- `reviewed_at`
- `review_batch_id`
- `schema_version`
- `created_at`
- `updated_at`

### Required blocking fields

- `production_blocked`
- `geocode_blocked`
- `promotion_blocked`
- `publishing_blocked`
- `registry_import_blocked`

## Allowed future review decisions

The only allowed prototype review decisions are:

- `hold`
- `reject`
- `needs_more_context`
- `eligible_for_future_review`

These decisions are review-only and must not trigger geocoding, approval, promotion, publishing, runtime changes, or importer/database behavior.

## Explicitly forbidden decisions

The following decisions are forbidden in XRI-G13:

- `approved`
- `geocoded`
- `promoted`
- `published`

## Fixture-only example records

Example records must remain fixture-only and non-production. They may demonstrate shape and validation expectations but must not be loaded by runtime code.

Example decision mix:

- One `hold` fixture.
- One `reject` fixture.
- One `needs_more_context` fixture.
- One `eligible_for_future_review` fixture.

Every fixture must preserve these blockers:

- `production_blocked: true`
- `geocode_blocked: true`
- `promotion_blocked: true`
- `publishing_blocked: true`
- `registry_import_blocked: true`

## Validation expectations

A later validator may check:

- Required field presence.
- Allowed decision values only.
- Forbidden decision values absent.
- Blocking fields remain true.
- No coordinates are present.
- No production paths are targeted.
- No runtime/importer/database behavior is introduced.
- Deterministic fixture ordering.

## Still blocked until later explicit production phase

The following remain blocked after XRI-G13:

- Production feed writes.
- Public map runtime changes.
- WordPress changes.
- `nycinfocus.com/map` changes.
- Iframe/embed changes.
- Scheduled workflow changes.
- `data/location_cache.json` reads or writes.
- Live staging.
- SODA/live data fetch.
- Geocoding.
- Candidate approval.
- Candidate promotion.
- Registry database/importer creation.
- Runtime publishing behavior.

## Proposed XRI-G14 gate

XRI-G14 should be a non-production fixture validator for the manual-review schema prototype. It may validate required fields, allowed decision values, forbidden decision absence, blocker fields, deterministic fixture ordering, and path isolation.

XRI-G14 must not start from this PR. It requires a separate explicit prompt after XRI-G13 is reviewed and merged.

## Review gate

Open a PR only. Do not merge. Do not start XRI-G14.
