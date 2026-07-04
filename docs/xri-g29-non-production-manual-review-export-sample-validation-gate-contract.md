# XRI-G29 Non-Production Manual Review Export Sample Validation Gate Contract

Phase: XRI-G29

Source phase: XRI-G28
Source pull request: #38
Source merge commit SHA: 64f3c5b46336498495e598258024378148f774e1
Source sample fixture: data/fixtures/xri-g28-non-production-manual-review-export.sample.json

## Purpose

Define a non-production manual review export sample validation gate for the XRI fixture/manual-review prototype path.

This gate validates, in contract/report form only, that the XRI-G28 sample fixture follows the XRI-G27 manual review export contract shape. It remains non-production, validation-only, contract-only/report-only, and not a production artifact.

## Allowed files

* docs/xri-g29-non-production-manual-review-export-sample-validation-gate-contract.md
* data/reports/xri_g29_non_production_manual_review_export_sample_validation_gate_report.json

No optional expected fixture is required for this gate.

## Validation boundaries

The validation gate must enforce:

* validation-only
* contract-only / report-only
* non-production only
* validates sample fixture contract shape only
* no production validator execution
* no production validator wiring
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

## Required sample-validation target fields

Validation target fields are:

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

## Required validation constraints

The validation gate must declare:

* sample fixture must exist as XRI-G28 source artifact reference
* sample fixture record count must be 2
* group_key must be present
* display_location must be present
* candidate_identity must be present
* review_status must be present
* review_reason must be present
* review_notes must be present
* review_rank must be present
* source_phase must be present
* export_mode must be non_production_manual_review_export_contract
* production_artifact must be false
* review_rank must not be used as identity
* review_rank may appear only as ordering/display metadata
* review_status must be needs_review or correction_needed
* review_status must not be approved, promoted, or published

## Required sample-validation pass cases

The validation gate must define pass coverage for:

* source XRI-G28 sample gate identified
* source XRI-G28 merge SHA recorded
* source XRI-G28 sample fixture referenced
* validation boundaries summarized
* sample record count requirement summarized
* required fields validation summarized
* stable identity validation summarized
* review_rank identity prohibition summarized
* review_rank ordering/display use summarized
* allowed review_status validation summarized
* forbidden review_status validation summarized
* no production validator execution confirmed
* no production validator wiring confirmed
* no production export behavior confirmed
* no-write/no-import confirmation summarized
* fail-closed expectations summarized

## Required sample-validation fail-closed cases

The validation gate must fail closed for:

* missing source phase
* missing source pull request
* missing source merge commit SHA
* missing source sample fixture reference
* missing validation boundary summary
* missing sample record count requirement
* sample record count not 2
* missing required sample field
* missing group_key
* missing display_location
* missing candidate_identity
* missing review_status
* missing review_reason
* missing review_notes
* missing review_rank
* missing source_phase
* review_rank used as identity
* identity drift
* export_mode not non-production
* production_artifact true
* unsupported_review_status
* approved_status_present
* promoted_status_present
* published_status_present
* attempted_production_validator_execution
* attempted_production_validator_wiring
* attempted_production_export_behavior
* attempted_registry_write_target
* attempted_registry_import_target
* attempted_geocode_target
* attempted_approval_state
* attempted_promotion_state
* attempted_publishing_state
* attempted_public_map_target
* attempted_wordpress_target
* attempted_scheduled_workflow_target
* attempted_location_cache_access
* attempted_executable_production_behavior

## Output rule

Manual review export sample validation output is validation-only, contract-only/report-only, non-production only, and not a production artifact.

## Hard prohibitions

No production feeds, public map runtime, WordPress, nycinfocus.com/map, iframe/embed settings, scheduled workflows, data/location_cache.json, live staging, SODA/live fetch, geocoding, candidate approval, candidate promotion, production registry database/importer, production export behavior, production validator execution, production validator wiring, registry writes, registry imports, runtime publishing behavior, production runtime input, public output, WordPress output, executable production behavior, production fixture wiring, publishing, or XRI-G30 start.

## Review gate

Open a pull request only. Do not merge. Do not start XRI-G30.
