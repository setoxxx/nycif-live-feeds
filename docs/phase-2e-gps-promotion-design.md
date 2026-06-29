# Phase 2E - GPS Promotion Design

## Purpose

Phase 2E is the future controlled promotion step that may take reviewed and approved GPS rows from:

- `data/gps_reviewed_approval_artifact.json`

and prepare them for a later update to:

- `data/location_cache.json`

This document is design-only. Phase 2E promotion is not authorized by default.

## Current status

Phase 2D produced a reviewed approval artifact with:

- 25 approved rows
- 17 excluded/correction-needed rows carried forward
- `promotion_allowed: true` only inside the reviewed approval artifact
- no modification to `data/location_cache.json`
- no modification to the staged event feed
- no public map publication

## Phase 2E safety contract

Phase 2E must not run unless Howard explicitly instructs promotion.

Before promotion, a separate readiness validator must pass.

A promotion script must never:

- promote rows from the review sheet directly
- promote rows from the staging candidates directly
- promote rows from the manual approval queue directly
- promote rows whose `promotion_scope` is not `reviewed_approval_artifact_only`
- promote rows that overlap with excluded/correction-needed rows
- modify the public map directly
- modify the staged event feed directly

Phase 2E may eventually modify only:

- `data/location_cache.json`

and only after explicit approval.

## Required input

The only valid Phase 2E input is:

- `data/gps_reviewed_approval_artifact.json`

The paired report must also be present:

- `data/gps_reviewed_approval_artifact_report.json`

The report must say:

- `qa_pass: true`
- `phase: phase_2d_reviewed_approval_artifact`
- `approved_count: 25`
- `excluded_carried_forward_count: 17`
- `invalid_approved_count: 0`
- `missing_required_count: 0`
- `overlap_with_excluded_count: 0`
- `phase_2e_promotion_performed: false`

## Required approved-row fields

Each promoted row must contain:

- `stable_identity_key`
- `group_key`
- `display_location`
- `borough`
- `proposed_lat`
- `proposed_lng`
- `geocoder_source`
- `geocoder_confidence`
- `confidence_reason`
- `manual_review_status: approved`
- `manual_reviewer`
- `manual_reviewed_at_utc`
- `approval_decision_reason`
- `promotion_allowed: true`
- `promotion_scope: reviewed_approval_artifact_only`
- `location_cache_modified: false` before promotion
- `staged_feed_modified: false`
- `public_map_modified: false`
- `phase_2e_promotion_performed: false`

## Coordinate validation

Coordinates must be numeric and within NYC operating bounds:

- latitude: `40.0 <= lat <= 41.0`
- longitude: `-75.0 <= lng <= -73.0`

Rows outside these bounds must fail readiness.

## Exclusion validation

The following rows must remain excluded from immediate promotion:

- all 17 `excluded_rows_carried_forward`
- any row that requires corrected coordinates
- any hard-error row
- any row with `approval_candidate: false`

A future correction pipeline may create new approved rows for corrected coordinates, but that must be a separate phase.

## Design-only readiness validator

Validator script:

- `scripts/validate_gps_phase2e_promotion_readiness.py`

Validator output:

- `data/gps_phase2e_promotion_readiness_report.json`

This validator is not a promotion script.

The validator must:

1. read `data/gps_reviewed_approval_artifact.json`
2. read `data/gps_reviewed_approval_artifact_report.json`
3. confirm the reviewed approval artifact passed QA
4. confirm exactly 25 approved rows
5. confirm 17 exclusions are carried forward
6. confirm no overlap between approved and excluded stable identity keys
7. validate all approved coordinates
8. validate all required approval metadata
9. confirm `promotion_allowed` is true only in approved rows
10. confirm `location_cache_modified`, `staged_feed_modified`, and `public_map_modified` are false
11. write a readiness report only

The validator must not modify `data/location_cache.json`.

The validator must not be treated as permission to promote.

## Proposed future promotion output

When Phase 2E is explicitly authorized, the promotion script should write:

- updated `data/location_cache.json`
- `data/gps_phase2e_promotion_report.json`
- optionally `data/gps_phase2e_promoted_rows.json`

The report must include:

- source artifact path
- source artifact timestamp
- promoted row count
- skipped row count
- before/after location cache counts
- exact keys written
- duplicate/overwrite behavior
- safety flags
- confirmation that staged feed and public map were not modified

## Location cache insertion model

The promotion script should create deterministic cache entries using stable keys such as:

- `phase2e:<borough>:<normalized-display-location>`
- or preserve an existing compatible `group_key` mapping if the cache schema supports it

Each inserted entry should preserve:

- lat/lng
- display location
- borough
- source: `phase_2d_reviewed_approval_artifact`
- original geocoder source
- confidence
- manual reviewer
- manual reviewed timestamp
- approval decision reason
- phase: `phase_2e`

## Duplicate handling

If a target cache key already exists:

1. If coordinates match exactly or are functionally equivalent, report as duplicate/no-op.
2. If coordinates differ, do not overwrite automatically.
3. Write the row to a conflict section in the promotion report.
4. Require human decision before overwrite.

## Workflow status

The readiness validator is design-only and should not be automatically wired into the live QA workflow until Howard asks for it.

Do not add a promotion script to the workflow.

Do not add `data/gps_phase2e_promotion_readiness_report.json` to automated public-feed publishing.

## Required human gate before promotion

Before any actual Phase 2E promotion, Howard must explicitly say something equivalent to:

> Promote the 25 approved Phase 2E GPS rows into location_cache.json.

Anything less specific, including `inspect`, `validate`, `design`, `prepare`, `stage`, or `ready`, is not permission to promote.

## Recommended next step

Inspect this design and the readiness validator.

After inspection, the validator may be run manually to produce a readiness report.

Do not create or run the actual promotion script until the readiness validator passes and Howard explicitly authorizes promotion.
