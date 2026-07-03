# XRI-G12 Planning Gate Contract

## Phase

XRI-G12

## Source

- Source phase: XRI-G11
- Source PR: #15
- Source merge commit SHA: `1718a1d2e93eadbe71f498f050ec88cb272d4a3c`

## Mode

Planning gate only.

XRI-G12 defines the next safe bridge from fixture-only grouped review validation toward a future manual-review workflow. It does not implement production behavior.

## Allowed in XRI-G12

XRI-G12 may define documentation and reports for:

- Manual review workflow boundaries.
- Required preconditions from XRI-G10 and XRI-G11.
- Required human decision points.
- Required audit fields for a future manual-review workflow.
- Blocking conditions that must remain in force until a later explicit production phase.
- A proposed XRI-G13 gate, without starting XRI-G13.

## Not allowed in XRI-G12

XRI-G12 must not:

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
- Publish anything.
- Start XRI-G13.

## Preconditions from XRI-G10

XRI-G10 must have produced a fixture-only grouped review export with:

- `production_allowed: false`.
- Deterministic grouped sections.
- Review-only rows.
- Supporting reference rows kept non-public.
- No coordinate inference.
- No production/map/WordPress/runtime side effects.

## Preconditions from XRI-G11

XRI-G11 must have validated that the grouped export remains:

- Fixture-only.
- Deterministic.
- Review-only.
- Blocked from approval and promotion.
- Free of coordinates.
- Protected by fail-closed output path guards.
- Isolated from production feeds, public map runtime, WordPress, scheduled workflows, `data/location_cache.json`, SODA/live fetch, geocoding, registry DB/importer creation, and XRI-G12+ production behavior.

## Manual review workflow boundaries

Future manual-review work must remain separate from production publication. A future workflow may prepare review records, but it must not automatically approve, geocode, promote, publish, or alter public-facing data.

A reviewer may inspect candidate rows and assign review intent, but those review decisions must remain non-production until a later explicit phase authorizes a controlled bridge.

## Required human decision points

A future manual-review workflow must require explicit human decisions for:

- Candidate accept/reject/hold status.
- Location confidence classification.
- Whether a row needs additional source context.
- Whether a supporting reference row remains support-only.
- Whether a candidate is eligible for future geocoding consideration.
- Whether a candidate is eligible for future promotion consideration.

None of these decisions may trigger production changes in XRI-G12.

## Required audit fields for future manual review

A later manual-review artifact should include audit fields such as:

- `reviewer_id`
- `reviewed_at`
- `review_decision`
- `review_reason`
- `source_dataset_id`
- `candidate_identity_key`
- `group_key`
- `display_location`
- `location_confidence`
- `supporting_reference_only`
- `public_event_candidate`
- `geocode_eligible_future`
- `promotion_eligible_future`
- `production_blocked`
- `audit_notes`

## Still blocked until later explicit production phase

The following remain blocked after XRI-G12:

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

## Proposed XRI-G13 gate

XRI-G13 should be a non-production manual-review schema prototype. It may define review record fields and fixture-only examples. It must not start production behavior, geocoding, promotion, registry DB/importer creation, public map runtime changes, WordPress changes, scheduled workflow changes, or `data/location_cache.json` access.

XRI-G13 must not start from this PR. It requires a separate explicit prompt after XRI-G12 is reviewed and merged.

## Review gate

Open a PR only. Do not merge. Do not start XRI-G13.
