# XRI-G31 Non-Production Manual Review Export Readiness Checkpoint Gate Contract

Phase: XRI-G31

## Source phases

* XRI-G27
* XRI-G28
* XRI-G29
* XRI-G30

## Source pull requests

* XRI-G27: #37
* XRI-G28: #38
* XRI-G29: #39
* XRI-G30: #40

## Source merge commit SHAs

* XRI-G27: f5c6a4a71063565f4b634e683e44c42fdabdf520
* XRI-G28: 64f3c5b46336498495e598258024378148f774e1
* XRI-G29: 3111d20302d7b4bd6a5c22b39ae6aad31c2a03cf
* XRI-G30: 5612fc8969b8db48a3b74f41bd17a099fde3abf9

## Source artifacts checked

* docs/xri-g27-non-production-manual-review-export-contract-gate-contract.md
* data/reports/xri_g27_non_production_manual_review_export_contract_gate_report.json
* docs/xri-g28-non-production-manual-review-export-sample-gate-contract.md
* data/reports/xri_g28_non_production_manual_review_export_sample_gate_report.json
* data/fixtures/xri-g28-non-production-manual-review-export.sample.json
* docs/xri-g29-non-production-manual-review-export-sample-validation-gate-contract.md
* data/reports/xri_g29_non_production_manual_review_export_sample_validation_gate_report.json
* docs/xri-g30-non-production-manual-review-export-validation-summary-gate-contract.md
* data/reports/xri_g30_non_production_manual_review_export_validation_summary_gate_report.json

## Purpose

Define a non-production manual review export readiness checkpoint gate only.

This gate summarizes, in contract/report form only, whether the completed XRI-G27 through XRI-G30 non-production manual-review export chain is ready for a future production-boundary design phase. It remains readiness-only, checkpoint-only, contract-only/report-only, non-production only, and not a production artifact.

## Allowed files

* docs/xri-g31-non-production-manual-review-export-readiness-checkpoint-gate-contract.md
* data/reports/xri_g31_non_production_manual_review_export_readiness_checkpoint_gate_report.json

No optional fixture is required for this phase.

## Readiness boundary

The readiness checkpoint must enforce:

* readiness-only
* checkpoint-only
* contract-only / report-only
* non-production only
* evaluates XRI-G27/XRI-G28/XRI-G29/XRI-G30 contract chain only
* readiness is only for future production-boundary design
* readiness is not production deployment readiness
* readiness is not live-map readiness
* readiness is not publishing readiness
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

## Required manual-review export fields checked

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

## Required readiness checkpoint constraints

The readiness checkpoint must declare:

* source XRI-G27 pull request must be recorded
* source XRI-G28 pull request must be recorded
* source XRI-G29 pull request must be recorded
* source XRI-G30 pull request must be recorded
* source XRI-G27 merge SHA must be recorded
* source XRI-G28 merge SHA must be recorded
* source XRI-G29 merge SHA must be recorded
* source XRI-G30 merge SHA must be recorded
* source artifacts must be listed
* expected sample fixture record count must be 2
* stable identity basis must be group_key, display_location, candidate_identity
* review_rank must not be used as identity
* review_rank may appear only as ordering/display metadata
* export_mode must be non_production_manual_review_export_contract
* production_artifact must be false
* allowed sample review_status values must be needs_review or correction_needed
* forbidden sample review_status values must be approved, promoted, or published
* production-boundary design must be future-only
* production deployment must not be declared ready
* live map publish must not be declared ready
* publishing must not be declared ready

## Required readiness checkpoint pass cases

The readiness checkpoint must define pass coverage for:

* source XRI-G27 export contract gate identified
* source XRI-G28 sample gate identified
* source XRI-G29 sample validation gate identified
* source XRI-G30 validation summary gate identified
* source XRI-G27 merge SHA recorded
* source XRI-G28 merge SHA recorded
* source XRI-G29 merge SHA recorded
* source XRI-G30 merge SHA recorded
* source artifacts checked
* readiness boundary summarized
* stable identity basis checked
* review_rank identity prohibition checked
* review_rank ordering/display use checked
* required manual-review export fields checked
* sample record count expectation checked
* allowed review_status values checked
* forbidden review_status values checked
* future production-boundary design limitation checked
* production deployment not-ready status checked
* live-map not-ready status checked
* publishing not-ready status checked
* no production validator execution confirmed
* no production validator wiring confirmed
* no production export behavior confirmed
* no-write/no-import confirmation summarized
* fail-closed expectations summarized

## Required readiness checkpoint fail-closed cases

The readiness checkpoint must fail closed for:

* missing_source_xri_g27
* missing_source_xri_g28
* missing_source_xri_g29
* missing_source_xri_g30
* missing_source_xri_g27_pull_request
* missing_source_xri_g28_pull_request
* missing_source_xri_g29_pull_request
* missing_source_xri_g30_pull_request
* missing_source_xri_g27_merge_sha
* missing_source_xri_g28_merge_sha
* missing_source_xri_g29_merge_sha
* missing_source_xri_g30_merge_sha
* missing_source_artifact_check
* missing_readiness_boundary
* missing_future_production_boundary_limitation
* production_deployment_marked_ready
* live_map_marked_ready
* publishing_marked_ready
* missing_stable_identity_check
* missing_review_rank_identity_prohibition_check
* missing_review_rank_ordering_display_check
* missing_required_field_check
* missing_sample_record_count_check
* sample_record_count_not_2
* missing_allowed_review_status_check
* missing_forbidden_review_status_check
* review_rank_used_as_identity
* identity_drift
* export_mode_not_non_production
* production_artifact_true
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

Manual review export readiness checkpoint output is readiness-only, checkpoint-only, contract-only/report-only, non-production only, and not a production artifact.

## Hard prohibitions

No production feeds, public map runtime, WordPress, nycinfocus.com/map, iframe/embed settings, scheduled workflows, data/location_cache.json, live staging, SODA/live fetch, geocoding, candidate approval, candidate promotion, production registry database/importer, production export behavior, production validator execution, production validator wiring, registry writes, registry imports, runtime publishing behavior, production runtime input, public output, WordPress output, executable production behavior, production fixture wiring, production summary wiring, production readiness wiring, publishing, or XRI-G32 start.

## Review gate

Open a pull request only. Do not merge. Do not start XRI-G32.
