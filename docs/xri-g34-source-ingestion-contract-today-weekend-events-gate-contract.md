# XRI-G34 Source Ingestion Contract for Today/Weekend Events Gate Contract

Phase: XRI-G34

## Source phases

* XRI-G27
* XRI-G28
* XRI-G29
* XRI-G30
* XRI-G31
* XRI-G32
* XRI-G33

## Source pull requests

* XRI-G27: #37
* XRI-G28: #38
* XRI-G29: #39
* XRI-G30: #40
* XRI-G31: #41
* XRI-G32: #42
* XRI-G33: #43

## Source merge commit SHAs

* XRI-G27: f5c6a4a71063565f4b634e683e44c42fdabdf520
* XRI-G28: 64f3c5b46336498495e598258024378148f774e1
* XRI-G29: 3111d20302d7b4bd6a5c22b39ae6aad31c2a03cf
* XRI-G30: 5612fc8969b8db48a3b74f41bd17a099fde3abf9
* XRI-G31: 0511419a0c0120677dfcf192e5d0a54ac4b7b3d2
* XRI-G32: ce4bf0e8a8054a4a828ba5eedd9dac9ec077a641
* XRI-G33: b589a59ace787e897fe8726284dd2439780fcf57

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
* docs/xri-g33-candidate-event-registry-schema-gate-contract.md
* data/reports/xri_g33_candidate_event_registry_schema_gate_report.json

## Purpose

Define a source ingestion contract for today/weekend events gate only. This is contract-only, design-only, and report-only output. It defines future source-ingestion rules and fail-closed requirements before any later controlled candidate registry, production map-feed, or publishing path can be implemented.

## Allowed files

* docs/xri-g34-source-ingestion-contract-today-weekend-events-gate-contract.md
* data/reports/xri_g34_source_ingestion_contract_today_weekend_events_gate_report.json

No optional fixture is required for this phase.

## Boundary status

The source ingestion contract gate is:

* contract-only
* design-only
* report-only output
* not source ingestion execution
* not live-data fetch
* not SODA/API call
* not NYC Open Data call
* not website scraping
* not candidate creation
* not registry database implementation
* not registry importer implementation
* not registry exporter implementation
* not registry write/import
* not live registry/table creation
* not production deployment
* not live-map publishing
* not runtime wiring
* not production export
* not production validation execution
* not production validation wiring
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

## Future allowed source categories for today/weekend events

* NYC agency event calendars
* NYC public meeting calendars
* NYC permitted event records
* NYC parks and recreation events
* NYC street activity / permitted activity records
* NYC transportation / street closure notices
* NYC emergency or service disruption notices only when relevant to map display
* NYC public-school closure or calendar events only when relevant to public civic map context
* manually reviewed newsroom entries

## Future disallowed source categories

* unsourced user submissions
* private messages
* private emails
* private calendars
* rumors
* social media posts without official or verified source backing
* stale source records outside the configured date window
* malformed source records
* source records without minimum event time/location/source attribution fields
* source records requiring geocoding before manual review
* source records that cannot be deduped

## Required future date-window policy

* today window required
* weekend window required
* explicit timezone required
* event_start_at required
* event_end_at required when known
* all-day event handling required
* stale event exclusion required
* future lookahead limit required
* date-window calculation must be deterministic
* date-window calculation must not rely on review_rank

## Required future source attribution policy

* source_name required
* source_url required when public URL exists
* source_type required
* source_event_id required when available
* source_retrieved_at required
* source_date_published required when available
* source_last_modified required when available
* attribution must survive candidate/review/approval/publishing handoff

## Required future freshness policy

* source_retrieved_at required
* source freshness threshold required
* stale sources must fail closed
* missing retrieved timestamp must fail closed
* source clock/timezone assumptions must be explicit

## Required future dedupe policy

* dedupe_key required
* duplicate_of supported
* stable identity required before candidate creation
* review_rank forbidden as dedupe identity
* title-only dedupe forbidden
* location-only dedupe forbidden
* source-only dedupe forbidden
* ambiguous duplicates must go to manual review

## Required future location policy

* display_location required
* normalized_location required when available
* borough required when known
* latitude/longitude optional until geocoding policy allows them
* location_confidence required
* geocoding_status required
* geocoding must not execute in this gate
* low-confidence locations must fail closed or require manual review

## Required future manual-review handoff policy

* raw source records are not public output
* ingested candidate records are not public output
* reviewed records are not public output
* approved records may become eligible for later controlled production output
* promoted records may become eligible for later publication staging
* published records may become public only after future explicit production workflow
* rejected records must not become public output
* correction_needed records must not become public output

## Required future audit/rollback policy

* audit_trail_reference required
* source_snapshot_reference required when available
* ingestion_run_id required in future implementation
* public_disable required
* rollback_reference required
* unpublished_at supported
* rejection reason supported
* correction reason supported

## Required source ingestion contract pass cases

* source XRI-G27 export contract gate identified
* source XRI-G28 sample gate identified
* source XRI-G29 sample validation gate identified
* source XRI-G30 validation summary gate identified
* source XRI-G31 readiness checkpoint gate identified
* source XRI-G32 production-boundary design gate identified
* source XRI-G33 candidate event registry schema gate identified
* source XRI-G27 merge SHA recorded
* source XRI-G28 merge SHA recorded
* source XRI-G29 merge SHA recorded
* source XRI-G30 merge SHA recorded
* source XRI-G31 merge SHA recorded
* source XRI-G32 merge SHA recorded
* source XRI-G33 merge SHA recorded
* source artifacts checked
* contract-only boundary declared
* today/weekend event-source ingestion design declared
* production deployment not-ready status declared
* live-map not-ready status declared
* publishing not-ready status declared
* source ingestion execution not-ready status declared
* live-data fetch not-ready status declared
* SODA/API calls not-ready status declared
* stable identity basis checked
* review_rank identity prohibition checked
* review_rank ordering/display use checked
* allowed source categories declared
* disallowed source categories declared
* date-window policy declared
* source-attribution policy declared
* freshness policy declared
* dedupe policy declared
* location policy declared
* manual-review handoff policy declared
* audit/rollback policy declared
* no live ingestion implementation confirmed
* no SODA/API implementation confirmed
* no candidate creation confirmed
* no registry database implementation confirmed
* no registry importer implementation confirmed
* no registry exporter implementation confirmed
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

## Required source ingestion contract fail-closed cases

* missing_source_xri_g27
* missing_source_xri_g28
* missing_source_xri_g29
* missing_source_xri_g30
* missing_source_xri_g31
* missing_source_xri_g32
* missing_source_xri_g33
* missing_source_xri_g27_pull_request
* missing_source_xri_g28_pull_request
* missing_source_xri_g29_pull_request
* missing_source_xri_g30_pull_request
* missing_source_xri_g31_pull_request
* missing_source_xri_g32_pull_request
* missing_source_xri_g33_pull_request
* missing_source_xri_g27_merge_sha
* missing_source_xri_g28_merge_sha
* missing_source_xri_g29_merge_sha
* missing_source_xri_g30_merge_sha
* missing_source_xri_g31_merge_sha
* missing_source_xri_g32_merge_sha
* missing_source_xri_g33_merge_sha
* missing_source_artifact_check
* missing_contract_only_boundary
* source_ingestion_execution_marked_ready
* live_data_fetch_marked_ready
* soda_api_call_marked_ready
* nyc_open_data_call_marked_ready
* website_scrape_marked_ready
* candidate_creation_marked_ready
* production_deployment_marked_ready
* live_map_marked_ready
* publishing_marked_ready
* runtime_wiring_marked_ready
* production_export_marked_ready
* production_validator_execution_marked_ready
* production_validator_wiring_marked_ready
* registry_database_marked_ready
* registry_importer_marked_ready
* registry_exporter_marked_ready
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
* missing_allowed_source_categories
* missing_disallowed_source_categories
* missing_date_window_policy
* missing_source_attribution_policy
* missing_freshness_policy
* missing_dedupe_policy
* missing_location_policy
* missing_manual_review_handoff_policy
* missing_audit_rollback_policy
* stale_source_allowed
* private_source_allowed
* source_without_attribution_allowed
* missing_source_retrieved_at_allowed
* ambiguous_duplicate_allowed_without_review
* low_confidence_location_allowed_without_review
* raw_source_record_marked_public
* candidate_record_marked_public
* production_artifact_true
* attempted_source_ingestion_implementation
* attempted_live_data_fetch
* attempted_soda_api_call
* attempted_nyc_open_data_call
* attempted_website_scrape
* attempted_candidate_creation
* attempted_registry_database_implementation
* attempted_registry_importer_implementation
* attempted_registry_exporter_implementation
* attempted_production_runtime_implementation
* attempted_public_map_runtime_implementation
* attempted_wordpress_implementation
* attempted_scheduled_workflow_implementation
* attempted_location_cache_access
* attempted_live_staging
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

Source ingestion contract output is contract-only, design-only, report-only, and not a production artifact.

## Hard prohibitions

No production feeds, public map runtime, WordPress, nycinfocus.com/map, iframe/embed settings, scheduled workflows, data/location_cache.json, live staging, SODA/live fetch, NYC Open Data calls, API calls, website scraping, geocoding, candidate creation, candidate approval, candidate promotion, production registry database/importer/exporter behavior, live registry/table creation, production export behavior, production validator execution, production validator wiring, registry writes, registry imports, runtime publishing behavior, production runtime input, public output, WordPress output, executable production behavior, production fixture wiring, production summary wiring, production readiness wiring, production boundary wiring, candidate schema wiring, source ingestion wiring, publishing, or XRI-G35 start.

## Review gate

Open a pull request only. Do not merge. Do not start XRI-G35.
