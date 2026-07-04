# XRI-G28 Non-Production Manual Review Export Sample Gate Contract

Phase: XRI-G28

Source phase: XRI-G27
Source pull request: #37
Source merge commit SHA: f5c6a4a71063565f4b634e683e44c42fdabdf520

## Purpose

Define a non-production manual review export sample gate for the XRI fixture/manual-review prototype path.

This gate adds a sample-only fixture demonstrating the XRI-G27 manual review export contract shape. It is non-production, fixture-only/report-only, not a production artifact, and introduces no executable production behavior.

## Allowed files

* docs/xri-g28-non-production-manual-review-export-sample-gate-contract.md
* data/reports/xri_g28_non_production_manual_review_export_sample_gate_report.json
* data/fixtures/xri-g28-non-production-manual-review-export.sample.json

## Sample boundaries

The sample gate must enforce:

* sample-only
* report-only / fixture-only
* non-production only
* no production export behavior
* no production registry database writes
* no registry imports
* no public runtime output
* no public map output
* no WordPress output
* no scheduled workflow changes
* no geocoding
* no approval
* no promotion
* no publishing
* no data/location_cache.json access
* no executable production behavior

## Stable identity basis

Stable identity remains based only on:

* group_key
* display_location
* candidate_identity

## Forbidden identity basis

The following field must never be used as identity:

* review_rank

## Allowed ordering/display field

The following field may appear only as ordering or display metadata:

* review_rank

## Required manual-review export sample fields

Each sample row must include:

* group_key
* display_location
* candidate_identity
* review_status
* review_reason
* review_notes
* review_rank
* source_phase
* export_mode
* production_artifact

## Required field constraints

The sample gate must enforce:

* group_key must be present
* display_location must be present
* candidate_identity must be present
* review_status must be present
* review_reason must be present
* export_mode must be non_production_manual_review_export_contract
* production_artifact must be false
* review_rank must not be used as identity
* review_rank may appear only as ordering/display metadata

## Sample fixture requirements

The fixture must contain exactly 2 sample records.

Each sample record must be synthetic and non-production. review_status must be one of:

* needs_review
* correction_needed

The sample must not include approved, promoted, or published status values.

The sample must not imply real approval, promotion, publishing, registry import, registry write, geocoding, or public-map readiness.

## Required sample pass cases

The sample gate must define pass coverage for:

* source XRI-G27 export contract gate identified
* source XRI-G27 merge SHA recorded
* sample boundaries summarized
* required fields represented in sample rows
* stable identity basis represented
* review_rank identity prohibition represented
* review_rank ordering/display use represented
* no production export behavior confirmed
* no-write/no-import confirmation summarized
* fail-closed expectations summarized

## Required sample fail-closed cases

The sample gate must fail closed for:

* missing source phase
* missing source pull request
* missing source merge commit SHA
* missing sample boundary summary
* missing required sample field
* missing group_key
* missing display_location
* missing candidate_identity
* missing review_status
* missing review_reason
* review_rank used as identity
* identity drift
* export_mode not non-production
* production_artifact true
* approved status present
* promoted status present
* published status present
* attempted production export behavior
* attempted registry write target
* attempted registry import target
* attempted geocode target
* attempted approval state
* attempted promotion state
* attempted publishing state
* attempted public map target
* attempted WordPress target
* attempted scheduled workflow target
* attempted location_cache access
* attempted executable production behavior

## Output rule

Manual review export sample output is sample-only, fixture-only/report-only, non-production only, and not a production artifact.

## Hard prohibitions

No production feeds, public map runtime, WordPress, nycinfocus.com/map, iframe/embed settings, scheduled workflows, data/location_cache.json, live staging, SODA/live fetch, geocoding, candidate approval, candidate promotion, production registry database/importer, production export behavior, registry writes, registry imports, runtime publishing behavior, production runtime input, public output, WordPress output, executable production behavior, production validator execution, production validator wiring, production fixture wiring, publishing, or XRI-G29 start.

## Review gate

Open a pull request only. Do not merge. Do not start XRI-G29.
