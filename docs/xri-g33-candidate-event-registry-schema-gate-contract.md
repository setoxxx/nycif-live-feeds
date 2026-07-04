# XRI-G33 Candidate Event Registry Schema Gate Contract

Phase: XRI-G33

## Source phases

* XRI-G27
* XRI-G28
* XRI-G29
* XRI-G30
* XRI-G31
* XRI-G32

## Source pull requests

* XRI-G27: #37
* XRI-G28: #38
* XRI-G29: #39
* XRI-G30: #40
* XRI-G31: #41
* XRI-G32: #42

## Source merge commit SHAs

* XRI-G27: f5c6a4a71063565f4b634e683e44c42fdabdf520
* XRI-G28: 64f3c5b46336498495e598258024378148f774e1
* XRI-G29: 3111d20302d7b4bd6a5c22b39ae6aad31c2a03cf
* XRI-G30: 5612fc8969b8db48a3b74f41bd17a099fde3abf9
* XRI-G31: 0511419a0c0120677dfcf192e5d0a54ac4b7b3d2
* XRI-G32: ce4bf0e8a8054a4a828ba5eedd9dac9ec077a641

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
* docs/xri-g32-production-boundary-design-gate-contract.md
* data/reports/xri_g32_production_boundary_design_gate_report.json

## Purpose

Define a candidate event registry schema gate only.

This gate defines, in contract/report form only, the required future candidate-event record schema for a later controlled map-feed production path. It may declare future candidate schema design and future candidate registry design ready. It must not declare production deployment ready, live-map publishing ready, or publishing ready.

## Allowed files

* docs/xri-g33-candidate-event-registry-schema-gate-contract.md
* data/reports/xri_g33_candidate_event_registry_schema_gate_report.json

No optional fixture is required for this phase.

## Boundary status

The candidate event registry schema gate is:

* schema-only
* design-only
* contract-only / report-only
* not production deployment
* not live-map publishing
* not runtime wiring
* not production export
* not production validation execution
* not production validation wiring
* not registry database implementation
* not registry importer implementation
* not registry export implementation
* not registry write/import
* not live registry/table creation
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

## Future candidate event registry required minimum schema fields

* candidate_id
* candidate_identity
* group_key
* display_location
* normalized_location
* borough
* latitude
* longitude
* location_confidence
* geocoding_status
* source_name
* source_url
* source_type
* source_retrieved_at
* source_event_id
* event_title
* event_description
* event_category
* event_start_at
* event_end_at
* event_timezone
* event_all_day
* event_status
* review_status
* review_reason
* review_notes
* review_rank
* reviewed_by
* reviewed_at
* approval_status
* approved_by
* approved_at
* promotion_status
* promoted_by
* promoted_at
* publication_status
* published_at
* unpublished_at
* public_disable
* rollback_reference
* dedupe_key
* duplicate_of
* created_at
* updated_at
* audit_trail_reference
* schema_version
* production_artifact

## Required allowed candidate lifecycle statuses

* candidate
* needs_review
* correction_needed
* reviewed
* approved
* promoted
* published
* unpublished
* rejected

## Required future status separation

* candidate records are not public output
* reviewed records are not public output
* approved records may become eligible for future production output
* promoted records may become eligible for future publication staging
* published records may become public only after future explicit production workflow
* rejected records must not become public output
* unpublished records must not remain public output

## Required future schema controls

* candidate identity required
* stable identity basis required
* review_rank forbidden as identity
* review_rank allowed only for ordering/display
* event time fields required
* source attribution fields required
* location confidence fields required
* geocoding status field required but no geocoding execution
* dedupe fields required
* audit trail reference required
* approval/promotion/publication separation required
* public disable field required
* rollback reference required
* production_artifact false required for this gate

## Required candidate schema pass cases

* source XRI-G27 export contract gate identified
* source XRI-G28 sample gate identified
* source XRI-G29 sample validation gate identified
* source XRI-G30 validation summary gate identified
* source XRI-G31 readiness checkpoint gate identified
* source XRI-G32 production-boundary design gate identified
* source XRI-G27 merge SHA recorded
* source XRI-G28 merge SHA recorded
* source XRI-G29 merge SHA recorded
* source XRI-G30 merge SHA recorded
* source XRI-G31 merge SHA recorded
* source XRI-G32 merge SHA recorded
* source artifacts checked
* schema-only boundary declared
* production deployment not-ready status declared
* live-map not-ready status declared
* publishing not-ready status declared
* stable identity basis checked
* review_rank identity prohibition checked
* review_rank ordering/display use checked
* required minimum schema fields declared
* candidate lifecycle statuses declared
* candidate/reviewed/approved/promoted/published separation declared
* source attribution fields declared
* event time fields declared
* location confidence fields declared
* geocoding status declared without geocoding execution
* dedupe fields declared
* audit trail reference declared
* public disable field declared
* rollback reference declared
* production_artifact false declared
* no registry database implementation confirmed
* no registry importer implementation confirmed
* no registry export implementation confirmed
* no live registry/table creation confirmed
* no production runtime implementation confirmed
* no production export implementation confirmed
* no production validator implementation confirmed
* no registry write/import implementation confirmed
* no geocoding implementation confirmed
* no approval/promotion/publishing implementation confirmed
* no scheduled workflow implementation confirmed
* no location_cache access confirmed
* fail-closed expectations summarized

## Required candidate schema fail-closed cases

* missing_source_xri_g27
* missing_source_xri_g28
* missing_source_xri_g29
* missing_source_xri_g30
* missing_source_xri_g31
* missing_source_xri_g32
* missing_source_xri_g27_pull_request
* missing_source_xri_g28_pull_request
* missing_source_xri_g29_pull_request
* missing_source_xri_g30_pull_request
* missing_source_xri_g31_pull_request
* missing_source_xri_g32_pull_request
* missing_source_xri_g27_merge_sha
* missing_source_xri_g28_merge_sha
* missing_source_xri_g29_merge_sha
* missing_source_xri_g30_merge_sha
* missing_source_xri_g31_merge_sha
* missing_source_xri_g32_merge_sha
* missing_source_artifact_check
* missing_schema_only_boundary
* production_deployment_marked_ready
* live_map_marked_ready
* publishing_marked_ready
* runtime_wiring_marked_ready
* production_export_marked_ready
* production_validator_execution_marked_ready
* production_validator_wiring_marked_ready
* registry_database_marked_ready
* registry_importer_marked_ready
* registry_export_marked_ready
* registry_write_marked_ready
* registry_import_marked_ready
* live_registry_table_created
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
* missing_required_minimum_schema_fields
* missing_candidate_id
* missing_candidate_identity
* missing_group_key
* missing_display_location
* missing_event_time_fields
* missing_source_attribution_fields
* missing_location_confidence_fields
* missing_geocoding_status_field
* geocoding_execution_added
* missing_dedupe_fields
* missing_audit_trail_reference
* missing_public_disable_field
* missing_rollback_reference
* missing_candidate_reviewed_approved_promoted_published_separation
* production_artifact_true
* attempted_registry_database_implementation
* attempted_registry_importer_implementation
* attempted_registry_export_implementation
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

Candidate event registry schema output is schema-only, design-only, contract-only/report-only, and not a production artifact.

## Hard prohibitions

No production feeds, public map runtime, WordPress, nycinfocus.com/map, iframe/embed settings, scheduled workflows, data/location_cache.json, live staging, SODA/live fetch, geocoding, candidate approval, candidate promotion, production registry database/importer/exporter behavior, live registry/table creation, production export behavior, production validator execution, production validator wiring, registry writes, registry imports, runtime publishing behavior, production runtime input, public output, WordPress output, executable production behavior, production fixture wiring, production summary wiring, production readiness wiring, production boundary wiring, candidate schema wiring, publishing, or XRI-G34 start.

## Review gate

Open a pull request only. Do not merge. Do not start XRI-G34.
