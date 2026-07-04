# XRI-G30 Non-Production Manual Review Export Validation Summary Gate Contract

Phase: XRI-G30

## Source phases

* XRI-G27
* XRI-G28
* XRI-G29

## Source pull requests

* XRI-G27: #37
* XRI-G28: #38
* XRI-G29: #39

## Source merge commit SHAs

* XRI-G27: f5c6a4a71063565f4b634e683e44c42fdabdf520
* XRI-G28: 64f3c5b46336498495e598258024378148f774e1
* XRI-G29: 3111d20302d7b4bd6a5c22b39ae6aad31c2a03cf

## Source artifacts summarized

* docs/xri-g27-non-production-manual-review-export-contract-gate-contract.md
* data/reports/xri_g27_non_production_manual_review_export_contract_gate_report.json
* docs/xri-g28-non-production-manual-review-export-sample-gate-contract.md
* data/reports/xri_g28_non_production_manual_review_export_sample_gate_report.json
* data/fixtures/xri-g28-non-production-manual-review-export.sample.json
* docs/xri-g29-non-production-manual-review-export-sample-validation-gate-contract.md
* data/reports/xri_g29_non_production_manual_review_export_sample_validation_gate_report.json

## Purpose

Define a non-production manual review export validation summary gate only.

This gate summarizes, in contract/report form only, the completed non-production manual-review export chain from XRI-G27 through XRI-G29. It remains summary-only, validation-summary-only, contract-only/report-only, non-production only, and not a production artifact.

## Allowed files

* docs/xri-g30-non-production-manual-review-export-validation-summary-gate-contract.md
* data/reports/xri_g30_non_production_manual_review_export_validation_summary_gate_report.json

No optional fixture is required for this phase.

## Summary boundaries

The summary gate must enforce:

* summary-only
* validation-summary-only
* contract-only / report-only
* non-production only
* summarizes XRI-G27/XRI-G28/XRI-G29 contract chain only
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

## Required manual-review export fields summarized

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

## Required validation-summary constraints

The validation summary must declare:

* source XRI-G27 pull request must be recorded
* source XRI-G28 pull request must be recorded
* source XRI-G29 pull request must be recorded
* source XRI-G27 merge SHA must be recorded
* source XRI-G28 merge SHA must be recorded
* source XRI-G29 merge SHA must be recorded
* source artifacts must be listed
* expected sample fixture record count must be 2
* stable identity basis must be group_key, display_location, candidate_identity
* review_rank must not be used as identity
* review_rank may appear only as ordering/display metadata
* export_mode must be non_production_manual_review_export_contract
* production_artifact must be false
* allowed sample review_status values must be needs_review or correction_needed
* forbidden sample review_status values must be approved, promoted, or published

## Required validation-summary pass cases

The validation summary must define pass coverage for:

* source XRI-G27 export contract gate identified
* source XRI-G28 sample gate identified
* source XRI-G29 sample validation gate identified
* source XRI-G27 merge SHA recorded
* source XRI-G28 merge SHA recorded
* source XRI-G29 merge SHA recorded
* source artifacts summarized
* summary boundaries summarized
* stable identity basis summarized
* review_rank identity prohibition summarized
* review_rank ordering/display use summarized
* required manual-review export fields summarized
* sample record count expectation summarized
* allowed review_status values summarized
* forbidden review_status values summarized
* no production validator execution confirmed
* no production validator wiring confirmed
* no production export behavior confirmed
* no-write/no-import confirmation summarized
* fail-closed expectations summarized

## Required validation-summary fail-closed cases

The validation summary must fail closed for:

* missing_source_xri_g27
* missing_source_xri_g28
* missing_source_xri_g29
* missing_source_xri_g27_pull_request
* missing_source_xri_g28_pull_request
* missing_source_xri_g29_pull_request
* missing_source_xri_g27_merge_sha
* missing_source_xri_g28_merge_sha
* missing_source_xri_g29_merge_sha
* missing_source_artifact_summary
* missing_summary_boundary_summary
* missing_stable_identity_summary
* missing_review_rank_identity_prohibition_summary
* missing_review_rank_ordering_display_summary
* missing_required_field_summary
* missing_sample_record_count_summary
* sample_record_count_not_2
* missing_allowed_review_status_summary
* missing_forbidden_review_status_summary
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

Manual review export validation summary output is summary-only, validation-summary-only, contract-only/report-only, non-production only, and not a production artifact.

## Hard prohibitions

No production feeds, public map runtime, WordPress, nycinfocus.com/map, iframe/embed settings, scheduled workflows, data/location_cache.json, live staging, SODA/live fetch, geocoding, candidate approval, candidate promotion, production registry database/importer, production export behavior, production validator execution, production validator wiring, registry writes, registry imports, runtime publishing behavior, production runtime input, public output, WordPress output, executable production behavior, production fixture wiring, production summary wiring, publishing, or XRI-G31 start.

## Review gate

Open a pull request only. Do not merge. Do not start XRI-G31.
