# XRI-G17 Failure-Case Validator Execution Contract

## Phase

XRI-G17

## Source

- Source phase: XRI-G16
- Source PR: #23
- Source merge commit SHA: `b7a1ac08bbd19d77dffde6c9535a59054b07e03e`

## Mode

Non-production failure-case validator execution only.

XRI-G17 defines execution of the non-production validator against XRI-G16 failure-case fixtures only. The resulting failure-case validation report is fixture-only and must not be consumed by production runtime, public map runtime, registry import, scheduled workflows, WordPress, geocoding, approval, promotion, publishing, database behavior, importer behavior, or runtime publishing behavior.

## Allowed in XRI-G17

XRI-G17 may define or record fixture-only execution checks confirming that failure-case fixtures fail closed when they violate the XRI-G14/XRI-G15/XRI-G16 chain.

## Not allowed in XRI-G17

XRI-G17 must not:

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
- Start XRI-G18.

## Failure-case execution boundary

The execution gate must remain failure-case fixture-only. Inputs must be XRI-G16 failure-case fixtures or fixture descriptions only. Outputs must be a fixture-only failure-case validation result or report only.

No execution result may be consumed by:

- Production runtime.
- Public map runtime.
- Registry import.
- Scheduled workflows.
- WordPress.
- Geocoding.
- Approval.
- Promotion.
- Publishing.
- Database behavior.
- Runtime behavior.
- Importer behavior.

## Required failure-case execution confirmations

The execution gate must confirm:

- XRI-G16 failure-case fixtures remain non-production only.
- Failure-case inputs are fixture-only.
- Failure-case outputs are fixture-only.
- Validator execution is failure-case execution only.
- Missing required fields fail closed.
- Missing identity fields fail closed.
- Missing source fields fail closed.
- Missing display/location text fields fail closed.
- Missing reviewer decision fields fail closed.
- Missing audit fields fail closed.
- Missing blocking fields fail closed.
- Invalid review decision values fail closed.
- Forbidden review decision values fail closed.
- Blocking fields false fail closed.
- Coordinate fields present fail closed.
- Production paths present fail closed.
- Runtime/importer/database behavior implied fails closed.
- Public map behavior implied fails closed.
- WordPress behavior implied fails closed.
- Scheduled workflow behavior implied fails closed.
- Geocoding behavior implied fails closed.
- Approval behavior implied fails closed.
- Promotion behavior implied fails closed.
- Publishing behavior implied fails closed.
- Non-deterministic fixture ordering fails closed or is reported as invalid.
- Unexpected production-implying fields fail closed.
- Any fixture that would not fail closed under the XRI-G14/XRI-G15/XRI-G16 chain is reported as a failure.
- XRI-G18 is not started.

## Forbidden review decision values

These forbidden review decision values must fail closed:

- `approved`
- `geocoded`
- `promoted`
- `published`

## Blocking fields false

These false blocking fields must fail closed:

- `production_blocked`
- `geocode_blocked`
- `promotion_blocked`
- `publishing_blocked`
- `registry_import_blocked`

## Coordinate fields present

These coordinate fields must fail closed if present:

- `latitude`
- `longitude`
- `lat`
- `lon`
- `lng`
- `coordinates`
- `geometry`

## Execution result expectations

The validator execution report should record expected failures as expected outcomes.

Expected failure cases count as successful validation behavior only when they fail closed.

Any failure case that passes validation must be treated as a failed execution result.

Any production-linked behavior must be treated as a failed execution result.

Any missing safety confirmation must be treated as a failed execution result.

## Failure-case execution categories

The execution report must represent execution categories for:

- Missing required fields.
- Missing identity fields.
- Missing source fields.
- Missing display/location text fields.
- Missing reviewer decision fields.
- Missing audit fields.
- Missing blocking fields.
- Invalid review decision values.
- Forbidden review decision values.
- Blocking fields false.
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

## Proposed XRI-G18 gate

XRI-G18 should create a non-production validator summary and handoff gate only.

XRI-G18 must not start from this PR. It requires a separate explicit prompt after XRI-G17 is reviewed and merged.

## Review gate

Open a PR only. Do not merge. Do not start XRI-G18.
