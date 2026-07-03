# XRI-G15 Validator Execution Contract

## Phase

XRI-G15

## Source

- Source phase: XRI-G14
- Source PR: #20
- Source merge commit SHA: `e68576971ba54b6e2cbf4a978db76b060a5f6380`

## Mode

Non-production validator execution only.

XRI-G15 defines or records execution of the XRI-G14 fixture validator against fixture examples only. It does not enable production behavior, registry database behavior, registry importer behavior, public map runtime behavior, WordPress behavior, geocoding, approval, promotion, publishing, scheduled workflow behavior, or runtime publishing behavior.

## Allowed in XRI-G15

XRI-G15 may define or record fixture-only execution checks for:

- XRI-G14 fixture validator scope remaining non-production only.
- Fixture inputs remaining non-production only.
- Fixture outputs remaining non-production only.
- Required field presence validation.
- Required identity fields validation.
- Required source fields validation.
- Required display and location text fields validation.
- Required reviewer decision fields validation.
- Required audit fields validation.
- Required blocking fields validation.
- Allowed review decision values only.
- Forbidden review decision values absent.
- Blocking fields remaining true.
- Coordinate fields absent.
- Production paths absent.
- Runtime/importer/database behavior absent.
- Deterministic fixture ordering.
- Fixture-only input/output behavior.
- Fail-closed behavior.
- Proposed XRI-G16 gate, without starting XRI-G16.

## Not allowed in XRI-G15

XRI-G15 must not:

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
- Start XRI-G16.

## Fixture execution boundary

The execution gate must remain fixture-only. Inputs may be described as fixture examples, and outputs may be described as a fixture-only validation result or report. No fixture result may be consumed by production runtime, public map runtime, registry import, scheduled workflows, WordPress, geocoding, approval, promotion, publishing, or database behavior.

## Execution checks

The execution gate should confirm that the XRI-G14 validator expectations are represented for fixture examples only.

### Required field validation represented

The execution gate should represent validation for all required field groups from the XRI-G13/XRI-G14 schema chain.

### Identity fields validation represented

- `review_record_id`
- `candidate_identity_key`
- `group_key`
- `source_dataset_id`
- `source_record_id`

### Source fields validation represented

- `source_name`
- `source_url`
- `source_observed_at`
- `source_phase`
- `source_pr`

### Display and location text fields validation represented

- `title`
- `display_location`
- `location_text_raw`
- `location_confidence`
- `location_notes`

### Reviewer decision fields validation represented

- `review_decision`
- `review_reason`
- `review_notes`
- `needs_more_context_reason`

### Audit fields validation represented

- `reviewer_id`
- `reviewed_at`
- `review_batch_id`
- `schema_version`
- `created_at`
- `updated_at`

### Blocking fields validation represented

- `production_blocked`
- `geocode_blocked`
- `promotion_blocked`
- `publishing_blocked`
- `registry_import_blocked`

## Allowed review decision values

Fixture execution may treat these as the only allowed decision values:

- `hold`
- `reject`
- `needs_more_context`
- `eligible_for_future_review`

## Forbidden review decision values

Fixture execution must keep these values absent:

- `approved`
- `geocoded`
- `promoted`
- `published`

## Blocking-field requirements

Fixture execution must represent these fields as true:

- `production_blocked`
- `geocode_blocked`
- `promotion_blocked`
- `publishing_blocked`
- `registry_import_blocked`

## Coordinate prohibition

Fixture execution must represent coordinate absence. It must not introduce or depend on coordinate fields such as:

- `latitude`
- `longitude`
- `lat`
- `lon`
- `lng`
- `coordinates`
- `geometry`

## Production path prohibition

Fixture execution must represent that no fixture input or output targets production paths.

## Runtime/importer/database prohibition

Fixture execution must represent that no runtime, importer, database, public map, WordPress, geocoding, approval, promotion, publishing, production feed, or scheduled workflow behavior is introduced.

## Deterministic fixture ordering

Fixture execution must represent deterministic fixture ordering by stable identity fields, preferably:

1. `source_dataset_id`
2. `group_key`
3. `candidate_identity_key`
4. `review_record_id`

## Fail-closed behavior

Fixture execution must represent fail-closed behavior for missing required fields, forbidden review decisions, false or missing blockers, coordinates, production paths, runtime behavior, importer behavior, database behavior, approval behavior, promotion behavior, publishing behavior, and unexpected production-implying fields.

## Proposed XRI-G16 gate

XRI-G16 should define non-production validator failure-case fixtures only.

XRI-G16 must not start from this PR. It requires a separate explicit prompt after XRI-G15 is reviewed and merged.

## Review gate

Open a PR only. Do not merge. Do not start XRI-G16.
