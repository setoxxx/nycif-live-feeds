# XRI-G36 Non-Production Source Ingestion Sample Validation Gate Contract

Phase: XRI-G36

## Source phases

* XRI-G27
* XRI-G28
* XRI-G29
* XRI-G30
* XRI-G31
* XRI-G32
* XRI-G33
* XRI-G34
* XRI-G35

## Source pull requests

* XRI-G27: #37
* XRI-G28: #38
* XRI-G29: #39
* XRI-G30: #40
* XRI-G31: #41
* XRI-G32: #42
* XRI-G33: #43
* XRI-G34: #44
* XRI-G35: #45

## Source merge commit SHAs

* XRI-G27: f5c6a4a71063565f4b634e683e44c42fdabdf520
* XRI-G28: 64f3c5b46336498495e598258024378148f774e1
* XRI-G29: 3111d20302d7b4bd6a5c22b39ae6aad31c2a03cf
* XRI-G30: 5612fc8969b8db48a3b74f41bd17a099fde3abf9
* XRI-G31: 0511419a0c0120677dfcf192e5d0a54ac4b7b3d2
* XRI-G32: ce4bf0e8a8054a4a828ba5eedd9dac9ec077a641
* XRI-G33: b589a59ace787e897fe8726284dd2439780fcf57
* XRI-G34: 7f56aae80be31429103bc5c3ea78d4e08dbc12ea
* XRI-G35: fd16bff1fd58bdaedb6099bb548f546982a0dde0

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
* docs/xri-g34-source-ingestion-contract-today-weekend-events-gate-contract.md
* data/reports/xri_g34_source_ingestion_contract_today_weekend_events_gate_report.json
* docs/xri-g35-non-production-source-ingestion-sample-contract-gate-contract.md
* data/reports/xri_g35_non_production_source_ingestion_sample_contract_gate_report.json
* data/fixtures/xri-g35-non-production-source-ingestion-sample.json

## Purpose

Define a non-production source ingestion sample validation gate for the XRI-G35 static non-production sample fixture. This gate is contract-only and report-only. It declares expected validation checks without executable validation code, fixture mutation, ingestion, live fetch, public output, or production behavior.

## Allowed files

* docs/xri-g36-non-production-source-ingestion-sample-validation-gate-contract.md
* data/reports/xri_g36_non_production_source_ingestion_sample_validation_gate_report.json

The XRI-G35 sample fixture must not be modified.

## Boundary status

The XRI-G36 gate is validation contract only, validation design only, report-only output, non-production validation only, static fixture validation only, fake/manual/test-data validation only, and not executable validation code.

The XRI-G36 gate is not source ingestion execution, live-data fetch, SODA/API call, NYC Open Data call, website scraping, candidate creation, production candidate data, registry database/importer/exporter implementation, registry write/import, live registry/table creation, production deployment, live-map publishing, runtime wiring, production export, production validation execution/wiring, geocoding, approval, promotion, publishing, scheduled workflow, location_cache access, or executable production behavior.

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

## Required validation declaration

XRI-G36 declares that the XRI-G35 fixture is expected to validate the following without executing code:

* fixture file exists at data/fixtures/xri-g35-non-production-source-ingestion-sample.json
* fixture top-level schema is present
* fixture phase is XRI-G35
* fixture production_artifact is false
* fixture non_production_sample is true
* fixture generated_from_live_data is false
* fixture live_fetch_performed is false
* fixture api_call_performed is false
* fixture soda_call_performed is false
* fixture nyc_open_data_call_performed is false
* fixture website_scrape_performed is false
* fixture geocoding_performed is false
* fixture runtime_wired is false
* fixture source_records exists
* fixture source_records count is exactly 3
* every source_record_id starts with xri-g35-sample-source-
* every source record sample_record is true
* every source record production_artifact is false
* every source record public_output is false
* every source record manual_review_required is true
* every source record latitude is null
* every source record longitude is null
* every geocoding_status is not_attempted or blocked_in_this_gate
* every source_freshness_status is sample_current_window, sample_weekend_window, or sample_needs_review
* every review_status is needs_review, correction_needed, or rejected
* review_rank is present only as ordering/display metadata
* review_rank is not used as source_record_id
* review_rank is not used as candidate_identity
* review_rank is not used as dedupe_key
* no record claims approved, promoted, published, public, live, or production status
* no record includes private email, private message, private calendar, rumor, or unsourced submission source
* all required sample, source attribution, event time, location, and audit/rollback fields are present
* no production artifact is produced
* no runtime wiring is declared
* no executable validation is declared
* no sample fixture mutation is performed

## Required validation pass cases

* xri_g35_fixture_exists
* xri_g35_fixture_schema_present
* xri_g35_fixture_phase_is_xri_g35
* fixture_production_artifact_false
* fixture_non_production_sample_true
* fixture_generated_from_live_data_false
* fixture_live_fetch_performed_false
* fixture_api_call_performed_false
* fixture_soda_call_performed_false
* fixture_nyc_open_data_call_performed_false
* fixture_website_scrape_performed_false
* fixture_geocoding_performed_false
* fixture_runtime_wired_false
* fixture_source_records_present
* fixture_source_record_count_exactly_three
* all_source_record_ids_use_xri_g35_sample_prefix
* all_sample_record_true
* all_record_production_artifact_false
* all_record_public_output_false
* all_record_manual_review_required_true
* all_record_latitude_null
* all_record_longitude_null
* all_geocoding_status_values_allowed
* all_source_freshness_status_values_allowed
* all_review_status_values_allowed
* review_rank_display_only
* review_rank_not_source_record_id
* review_rank_not_candidate_identity
* review_rank_not_dedupe_key
* no_approved_status
* no_promoted_status
* no_published_status
* no_public_status
* no_live_status
* no_production_status
* no_private_email_source
* no_private_message_source
* no_private_calendar_source
* no_rumor_source
* no_unsourced_submission_source
* all_required_sample_fields_present
* all_source_attribution_fields_present
* all_event_time_fields_present
* all_location_fields_present
* all_audit_rollback_fields_present
* no_production_artifact_produced
* no_runtime_wiring_declared
* no_executable_validation_declared
* no_sample_fixture_mutation_performed

## Required validation fail-closed cases

* missing_xri_g35_fixture
* missing_fixture_schema
* fixture_phase_not_xri_g35
* fixture_production_artifact_true
* fixture_non_production_sample_false
* fixture_generated_from_live_data_true
* fixture_live_fetch_performed_true
* fixture_api_call_performed_true
* fixture_soda_call_performed_true
* fixture_nyc_open_data_call_performed_true
* fixture_website_scrape_performed_true
* fixture_geocoding_performed_true
* fixture_runtime_wired_true
* missing_source_records
* source_record_count_not_three
* source_record_id_missing_prefix
* sample_record_not_true
* record_production_artifact_true
* record_public_output_true
* manual_review_required_false
* record_latitude_not_null
* record_longitude_not_null
* geocoding_status_unallowed
* source_freshness_status_unallowed
* review_status_unallowed
* review_rank_used_as_identity
* review_rank_used_as_candidate_identity
* review_rank_used_as_dedupe_key
* approved_status_present
* promoted_status_present
* published_status_present
* public_status_present
* live_status_present
* production_status_present
* private_email_source_present
* private_message_source_present
* private_calendar_source_present
* rumor_source_present
* unsourced_submission_source_present
* required_sample_field_missing
* source_attribution_field_missing
* event_time_field_missing
* location_field_missing
* audit_rollback_field_missing
* production_artifact_produced
* runtime_wiring_declared
* executable_validation_declared
* sample_fixture_mutated
* attempted_live_data_fetch
* attempted_soda_api_call
* attempted_nyc_open_data_call
* attempted_api_call
* attempted_website_scrape
* attempted_geocoding
* attempted_candidate_creation
* attempted_production_candidate_creation
* attempted_registry_write
* attempted_registry_import
* attempted_live_registry_data_creation
* attempted_production_runtime_implementation
* attempted_public_map_runtime_implementation
* attempted_wordpress_output
* attempted_scheduled_workflow
* attempted_location_cache_access
* attempted_xri_g37_start

## Carried-forward allowed source categories

* NYC agency event calendars
* NYC public meeting calendars
* NYC permitted event records
* NYC parks and recreation events
* NYC street activity / permitted activity records
* NYC transportation / street closure notices
* NYC emergency or service disruption notices only when relevant to map display
* NYC public-school closure or calendar events only when relevant to public civic map context
* manually reviewed newsroom entries

## Carried-forward disallowed source categories

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

## Carried-forward policies

* date-window policy
* source-attribution policy
* freshness policy
* dedupe policy
* location policy
* manual-review handoff policy
* audit/rollback policy
* fail-closed behavior
* stable identity behavior
* review_rank identity prohibition

## Output rule

XRI-G36 output is non-production validation design only, contract-only, report-only, and not a production artifact.

## Hard prohibitions

No production feeds, public map runtime, WordPress, nycinfocus.com/map, iframe/embed settings, scheduled workflows, data/location_cache.json, live staging, SODA/live fetch, NYC Open Data calls, API calls, website scraping, geocoding, candidate creation, production candidate data, live registry data, candidate approval, candidate promotion, production registry database/importer/exporter behavior, live registry/table creation, production export behavior, production validator execution, production validator wiring, executable validation code, registry writes, registry imports, runtime publishing behavior, production runtime input, public output, WordPress output, executable production behavior, sample fixture mutation, validation runtime wiring, production fixture wiring, production summary wiring, production readiness wiring, production boundary wiring, candidate schema wiring, source ingestion wiring, publishing, or XRI-G37 start.

## Review gate

Open a pull request only. Do not merge. Do not start XRI-G37.
