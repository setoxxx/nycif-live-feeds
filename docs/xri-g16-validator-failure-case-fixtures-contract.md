# XRI-G16 Validator Failure-Case Fixtures Contract

## Phase

XRI-G16

## Source

- Source phase: XRI-G15
- Source PR: #22
- Source merge commit SHA: `700662c7e72b6e547df3283cce82efa2aeae1800`

## Mode

Non-production validator failure-case fixtures only.

XRI-G16 defines fixture-only failure cases proving that the non-production validator should fail closed when XRI-G14/XRI-G15 expectations are violated. These fixtures are examples only and must not be consumed by production runtime, public map runtime, registry import, scheduled workflows, WordPress, geocoding, approval, promotion, publishing, database behavior, or runtime behavior.

## Allowed in XRI-G16

XRI-G16 may define fixture-only failure cases for:

- Missing required fields.
- Missing identity fields.
- Missing source fields.
- Missing display and location text fields.
- Missing reviewer decision fields.
- Missing audit fields.
- Missing blocking fields.
- Invalid review decision values.
- Forbidden review decision values.
- Blocking fields set false.
- Coordinate fields present.
- Production paths present.
- Runtime/importer/database behavior implied.
- Public map behavior implied.
- WordPress behavior implied.
- Scheduled workflow behavior implied.
- Geocoding behavior implied.
- Approval behavior implied.
- Promotion behavior implied.
- Publishing behavior implied.
- Non-deterministic fixture ordering.
- Unexpected production-implying fields.
- Any fixture that would not fail closed under the XRI-G14/XRI-G15 contract.

## Not allowed in XRI-G16

XRI-G16 must not:

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
- Start XRI-G17.

## Fixture boundary

Failure-case fixtures must remain non-production examples only. They may be referenced by a future non-production validator execution gate, but they must not be wired into production runtime, public map runtime, registry import, scheduled workflows, WordPress, geocoding, approval, promotion, publishing, database behavior, or runtime behavior.

## Required failure-case categories

### Missing required fields

Fixtures should represent missing required fields and demonstrate expected fail-closed behavior.

### Missing identity fields

Fixtures should represent missing identity fields such as:

- `review_record_id`
- `candidate_identity_key`
- `group_key`
- `source_dataset_id`
- `source_record_id`

### Missing source fields

Fixtures should represent missing source fields such as:

- `source_name`
- `source_url`
- `source_observed_at`
- `source_phase`
- `source_pr`

### Missing display and location text fields

Fixtures should represent missing display/location fields such as:

- `title`
- `display_location`
- `location_text_raw`
- `location_confidence`
- `location_notes`

### Missing reviewer decision fields

Fixtures should represent missing reviewer decision fields such as:

- `review_decision`
- `review_reason`
- `review_notes`
- `needs_more_context_reason`

### Missing audit fields

Fixtures should represent missing audit fields such as:

- `reviewer_id`
- `reviewed_at`
- `review_batch_id`
- `schema_version`
- `created_at`
- `updated_at`

### Missing blocking fields

Fixtures should represent missing blocking fields such as:

- `production_blocked`
- `geocode_blocked`
- `promotion_blocked`
- `publishing_blocked`
- `registry_import_blocked`

### Invalid review decisions

Fixtures should represent review decisions outside the allowed values:

- `hold`
- `reject`
- `needs_more_context`
- `eligible_for_future_review`

### Forbidden review decisions

Fixtures should represent forbidden values that must fail closed:

- `approved`
- `geocoded`
- `promoted`
- `published`

### Blocking fields false

Fixtures should represent false blocking fields that must fail closed:

- `production_blocked`
- `geocode_blocked`
- `promotion_blocked`
- `publishing_blocked`
- `registry_import_blocked`

### Coordinate fields present

Fixtures should represent coordinate fields that must fail closed:

- `latitude`
- `longitude`
- `lat`
- `lon`
- `lng`
- `coordinates`
- `geometry`

### Production paths present

Fixtures should represent any fixture input or output targeting production paths.

### Runtime/importer/database behavior implied

Fixtures should represent fields or metadata implying runtime, importer, or database behavior.

### Public map behavior implied

Fixtures should represent fields or metadata implying public map behavior.

### WordPress behavior implied

Fixtures should represent fields or metadata implying WordPress behavior.

### Scheduled workflow behavior implied

Fixtures should represent fields or metadata implying scheduled workflow behavior.

### Geocoding behavior implied

Fixtures should represent fields or metadata implying geocoding behavior.

### Approval behavior implied

Fixtures should represent fields or metadata implying approval behavior.

### Promotion behavior implied

Fixtures should represent fields or metadata implying promotion behavior.

### Publishing behavior implied

Fixtures should represent fields or metadata implying publishing behavior.

### Non-deterministic fixture ordering

Fixtures should represent ordering that is unstable or lacks stable identity sort keys.

### Unexpected production-implying fields

Fixtures should represent unexpected fields that imply production, geocoding, approval, promotion, publishing, registry import, database behavior, scheduled workflow behavior, WordPress behavior, or public map behavior.

## Passing fixture control behavior

Passing fixtures may be referenced only as a control example if needed. Passing fixtures must remain fixture-only and must not create approval, geocoding, promotion, publishing, registry import, database, runtime, public map, WordPress, scheduled workflow, or production behavior.

## Proposed XRI-G17 gate

XRI-G17 should execute non-production failure-case validator checks against the failure-case fixtures only.

XRI-G17 must not start from this PR. It requires a separate explicit prompt after XRI-G16 is reviewed and merged.

## Review gate

Open a PR only. Do not merge. Do not start XRI-G17.
