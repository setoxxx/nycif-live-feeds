# XRI-G32 Production-Boundary Design Gate Contract

Phase: XRI-G32

## Source phases

* XRI-G27
* XRI-G28
* XRI-G29
* XRI-G30
* XRI-G31

## Source pull requests

* XRI-G27: #37
* XRI-G28: #38
* XRI-G29: #39
* XRI-G30: #40
* XRI-G31: #41

## Source merge commit SHAs

* XRI-G27: f5c6a4a71063565f4b634e683e44c42fdabdf520
* XRI-G28: 64f3c5b46336498495e598258024378148f774e1
* XRI-G29: 3111d20302d7b4bd6a5c22b39ae6aad31c2a03cf
* XRI-G30: 5612fc8969b8db48a3b74f41bd17a099fde3abf9
* XRI-G31: 0511419a0c0120677dfcf192e5d0a54ac4b7b3d2

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
* docs/xri-g31-non-production-manual-review-export-readiness-checkpoint-gate-contract.md
* data/reports/xri_g31_non_production_manual_review_export_readiness_checkpoint_gate_report.json

## Purpose

Define a production-boundary design gate only.

This gate defines, in contract/report form only, the required controls for a future transition from the completed non-production XRI manual-review/export chain to a later controlled production map-feed path.

This gate may mark future candidate registry design and future production path design ready. It must not mark production deployment, live-map publishing, runtime wiring, production export, production validation execution, production validation wiring, registry write/import, geocoding, approval, promotion, scheduled workflow, location_cache access, publishing, or executable production behavior ready.

## Allowed files

* docs/xri-g32-production-boundary-design-gate-contract.md
* data/reports/xri_g32_production_boundary_design_gate_report.json

No optional fixture is required for this phase.

## Boundary status

The production-boundary design gate is:

* design-only
* boundary-only
* contract-only / report-only
* not production deployment
* not live-map publishing
* not runtime wiring
* not production export
* not production validation execution
* not production validation wiring
* not registry write/import
* not geocoding
* not approval
* not promotion
* not publishing
* not scheduled workflow
* not location_cache access
* not executable production behavior

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

## Future production-boundary required controls

Any future production path must require:

* manual review required before public output
* explicit approval required before promotion
* rollback path required before public map output
* dry-run export required before production export
* source attribution policy required before public output
* date-window policy required before today/weekend event display
* dedupe policy required before public output
* geocoding policy required before coordinates enter production
* location confidence policy required before public map output
* public-map QA required before publishing
* emergency disable switch required before live publishing
* no automatic publish without human review
* audit trail required for reviewed/promoted/published records
* production outputs generated only from approved records
* separation required between candidate records, reviewed records, approved records, and published records

## Required production-boundary pass cases

The production-boundary design gate must define pass coverage for:

* source XRI-G27 export contract gate identified
* source XRI-G28 sample gate identified
* source XRI-G29 sample validation gate identified
* source XRI-G30 validation summary gate identified
* source XRI-G31 readiness checkpoint gate identified
* source XRI-G27 merge SHA recorded
* source XRI-G28 merge SHA recorded
* source XRI-G29 merge SHA recorded
* source XRI-G30 merge SHA recorded
* source XRI-G31 merge SHA recorded
* source artifacts checked
* design-only boundary declared
* production deployment not-ready status declared
* live-map not-ready status declared
* publishing not-ready status declared
* stable identity basis checked
* review_rank identity prohibition checked
* review_rank ordering/display use checked
* future manual-review control declared
* future explicit-approval control declared
* future rollback control declared
* future dry-run export control declared
* future source-attribution control declared
* future date-window control declared
* future dedupe control declared
* future geocoding policy control declared
* future location-confidence control declared
* future public-map QA control declared
* future emergency-disable control declared
* future no-automatic-publish control declared
* future audit-trail control declared
* future approved-record-only output control declared
* future candidate/reviewed/approved/published separation declared
* no production runtime implementation confirmed
* no production export implementation confirmed
* no production validator implementation confirmed
* no registry write/import implementation confirmed
* no geocoding implementation confirmed
* no approval/promotion/publishing implementation confirmed
* no scheduled workflow implementation confirmed
* no location_cache access confirmed
* fail-closed expectations summarized

## Required production-boundary fail-closed cases

The production-boundary design gate must fail closed for:

* missing_source_xri_g27
* missing_source_xri_g28
* missing_source_xri_g29
* missing_source_xri_g30
* missing_source_xri_g31
* missing_source_xri_g27_pull_request
* missing_source_xri_g28_pull_request
* missing_source_xri_g29_pull_request
* missing_source_xri_g30_pull_request
* missing_source_xri_g31_pull_request
* missing_source_xri_g27_merge_sha
* missing_source_xri_g28_merge_sha
* missing_source_xri_g29_merge_sha
* missing_source_xri_g30_merge_sha
* missing_source_xri_g31_merge_sha
* missing_source_artifact_check
* missing_design_only_boundary
* production_deployment_marked_ready
* live_map_marked_ready
* publishing_marked_ready
* runtime_wiring_marked_ready
* production_export_marked_ready
* production_validator_execution_marked_ready
* production_validator_wiring_marked_ready
* registry_write_marked_ready
* registry_import_marked_ready
* geocoding_marked_ready
* approval_marked_ready
* promotion_marked_ready
* publishing_control_marked_ready
* scheduled_workflow_marked_ready
* location_cache_access_marked_ready
* missing_stable_identity_check
* missing_review_rank_identity_prohibition_check
* missing_review_rank_ordering_display_check
* review_rank_used_as_identity
* identity_drift
* missing_manual_review_control
* missing_explicit_approval_control
* missing_rollback_control
* missing_dry_run_export_control
* missing_source_attribution_control
* missing_date_window_control
* missing_dedupe_control
* missing_geocoding_policy_control
* missing_location_confidence_control
* missing_public_map_qa_control
* missing_emergency_disable_control
* missing_no_automatic_publish_control
* missing_audit_trail_control
* missing_approved_record_only_output_control
* missing_candidate_reviewed_approved_published_separation
* attempted_production_runtime_implementation
* attempted_public_map_runtime_implementation
* attempted_wordpress_implementation
* attempted_scheduled_workflow_implementation
* attempted_location_cache_access
* attempted_live_staging
* attempted_soda_live_fetch
* attempted_geocoding
* attempted_candidate_approval
* attempted_candidate_promotion
* attempted_publishing
* attempted_registry_write
* attempted_registry_import
* attempted_production_export_behavior
* attempted_production_validator_execution
* attempted_production_validator_wiring
* attempted_executable_production_behavior

## Output rule

Production-boundary design output is design-only, boundary-only, contract-only/report-only, and not a production artifact.

## Hard prohibitions

No production feeds, public map runtime, WordPress, nycinfocus.com/map, iframe/embed settings, scheduled workflows, data/location_cache.json, live staging, SODA/live fetch, geocoding, candidate approval, candidate promotion, production registry database/importer behavior, production export behavior, production validator execution, production validator wiring, registry writes, registry imports, runtime publishing behavior, production runtime input, public output, WordPress output, executable production behavior, production fixture wiring, production summary wiring, production readiness wiring, production boundary wiring, publishing, or XRI-G33 start.

## Review gate

Open a pull request only. Do not merge. Do not start XRI-G33.
