# XRI-G35 Non-Production Source Ingestion Sample Contract Gate Contract

Phase: XRI-G35

## Source phases

* XRI-G27
* XRI-G28
* XRI-G29
* XRI-G30
* XRI-G31
* XRI-G32
* XRI-G33
* XRI-G34

## Source pull requests

* XRI-G27: #37
* XRI-G28: #38
* XRI-G29: #39
* XRI-G30: #40
* XRI-G31: #41
* XRI-G32: #42
* XRI-G33: #43
* XRI-G34: #44

## Source merge commit SHAs

* XRI-G27: f5c6a4a71063565f4b634e683e44c42fdabdf520
* XRI-G28: 64f3c5b46336498495e598258024378148f774e1
* XRI-G29: 3111d20302d7b4bd6a5c22b39ae6aad31c2a03cf
* XRI-G30: 5612fc8969b8db48a3b74f41bd17a099fde3abf9
* XRI-G31: 0511419a0c0120677dfcf192e5d0a54ac4b7b3d2
* XRI-G32: ce4bf0e8a8054a4a828ba5eedd9dac9ec077a641
* XRI-G33: b589a59ace787e897fe8726284dd2439780fcf57
* XRI-G34: 7f56aae80be31429103bc5c3ea78d4e08dbc12ea

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

## Purpose

Define a non-production source ingestion sample contract gate only. This gate adds a contract/report-only boundary and a static non-production sample fixture showing the future source-ingestion record shape for today/weekend events. The sample fixture is fake/manual/test data only.

## Allowed files

* docs/xri-g35-non-production-source-ingestion-sample-contract-gate-contract.md
* data/reports/xri_g35_non_production_source_ingestion_sample_contract_gate_report.json
* data/fixtures/xri-g35-non-production-source-ingestion-sample.json

## Boundary status

The XRI-G35 gate is:

* non-production sample only
* static fixture only
* fake/manual/test data only
* contract-only
* design-only
* report-only output
* not source ingestion execution
* not live-data fetch
* not SODA/API call
* not NYC Open Data call
* not website scraping
* not candidate creation
* not production candidate data
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

## Required sample fixture shape

The fixture file must contain a top-level JSON object with:

* schema
* phase
* production_artifact
* non_production_sample
* generated_from_live_data
* live_fetch_performed
* api_call_performed
* soda_call_performed
* nyc_open_data_call_performed
* website_scrape_performed
* geocoding_performed
* runtime_wired
* source_records

The fixture must contain exactly 3 sample source records.

Each sample source record must include source_record_id, sample_record, source_name, source_type, source_url, source_event_id, source_retrieved_at, source_date_published, source_last_modified, source_timezone, source_freshness_status, source_window, event_title, event_description, event_category, event_start_at, event_end_at, event_timezone, event_all_day, event_status, display_location, normalized_location, borough, latitude, longitude, location_confidence, geocoding_status, group_key, candidate_identity, dedupe_key, duplicate_of, review_rank, manual_review_required, review_status, review_reason, public_output, production_artifact, ingestion_run_id, source_snapshot_reference, audit_trail_reference, public_disable, rollback_reference, and notes.

## Fixture record rules

* All source_record_id values must start with xri-g35-sample-source-
* sample_record must be true for every source record.
* production_artifact must be false for every source record.
* public_output must be false for every source record.
* manual_review_required must be true for every source record.
* generated_from_live_data must be false.
* live_fetch_performed must be false.
* api_call_performed must be false.
* soda_call_performed must be false.
* nyc_open_data_call_performed must be false.
* website_scrape_performed must be false.
* geocoding_performed must be false.
* runtime_wired must be false.
* latitude and longitude may be null only.
* geocoding_status must be not_attempted or blocked_in_this_gate.
* source_freshness_status must be sample_current_window, sample_weekend_window, or sample_needs_review.
* review_status must be needs_review, correction_needed, or rejected.
* review_rank may appear only as ordering/display metadata.
* review_rank must not be used as source_record_id.
* review_rank must not be used as candidate_identity.
* review_rank must not be used as dedupe_key.
* No record may claim approved, promoted, published, public, live, or production status.
* No record may include real private data.
* No record may be sourced from private email, private messages, private calendars, rumors, or unsourced submissions.

## Future allowed source categories

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

## Required future policies

Date-window policy requires today window, weekend window, explicit timezone, event_start_at, event_end_at when known, all-day handling, stale event exclusion, future lookahead limit, deterministic date-window calculation, and no review_rank dependency.

Source-attribution policy requires source_name, source_url when public URL exists, source_type, source_event_id when available, source_retrieved_at, source_date_published when available, source_last_modified when available, and attribution surviving candidate/review/approval/publishing handoff.

Freshness policy requires source_retrieved_at, source freshness threshold, stale sources fail closed, missing retrieved timestamp fail closed, and explicit source clock/timezone assumptions.

Dedupe policy requires dedupe_key, duplicate_of support, stable identity before candidate creation, review_rank forbidden as dedupe identity, title-only dedupe forbidden, location-only dedupe forbidden, source-only dedupe forbidden, and ambiguous duplicates sent to manual review.

Location policy requires display_location, normalized_location when available, borough when known, latitude/longitude optional until geocoding policy allows them, location_confidence, geocoding_status, no geocoding execution in this gate, and low-confidence locations fail closed or require manual review.

Manual-review handoff policy requires raw source records, ingested candidate records, and reviewed records to remain non-public output. Approved records may become eligible only for later controlled production output, promoted records may become eligible only for later publication staging, published records may become public only after future explicit production workflow, and rejected/correction_needed records must not become public output.

Audit/rollback policy requires audit_trail_reference, source_snapshot_reference when available, ingestion_run_id in future implementation, public_disable, rollback_reference, unpublished_at support, rejection reason support, and correction reason support.

## Required pass cases

* source XRI-G27 through XRI-G34 phases identified
* source pull requests #37 through #44 recorded
* source merge SHAs for XRI-G27 through XRI-G34 recorded
* source artifacts checked
* contract-only boundary declared
* non-production sample boundary declared
* static fixture boundary declared
* fake/manual/test-data boundary declared
* today/weekend event-source ingestion sample design declared
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
* fixture contains exactly 3 sample records
* fixture sample records marked non-production
* fixture sample records marked not public output
* fixture sample records marked manual review required
* fixture sample records marked not generated from live data
* fixture sample records marked no live fetch
* fixture sample records marked no SODA/API/NYC Open Data call
* fixture sample records marked no website scrape
* fixture sample records marked no geocoding
* fixture sample records marked no runtime wiring
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

## Required fail-closed cases

Missing source references, missing pull requests, missing merge SHAs, missing source artifacts, missing contract-only boundary, missing non-production sample boundary, missing static fixture boundary, missing fake/manual/test data boundary, source ingestion execution marked ready, live data fetch marked ready, SODA/API/NYC Open Data call marked ready, website scrape marked ready, candidate creation marked ready, production deployment marked ready, live map marked ready, publishing marked ready, runtime wiring marked ready, production export marked ready, production validator execution or wiring marked ready, registry database/importer/exporter/write/import marked ready, live registry table created, geocoding marked ready, approval/promotion/publishing control marked ready, scheduled workflow marked ready, location_cache access marked ready, review_rank used as identity/candidate_identity/dedupe_key, identity drift, missing required source policies, missing sample fixture, sample fixture with record count other than three, sample fixture marked production or public, fixture generated from live data, fixture live fetch/API/SODA/NYC Open Data/website scrape/geocoding/runtime wiring performed, sample record approved/promoted/published/public/production, sample record missing required fields, sample record with manual_review_required false, private source allowed, stale source allowed, missing source attribution allowed, ambiguous duplicate allowed without review, low-confidence location allowed without review, or any attempted production/runtime/public-map/WordPress/scheduled-workflow/location_cache behavior must fail closed.

## Output rule

Source ingestion sample output is non-production, static, fake/manual/test data, contract-only/report-only/sample-fixture-only, and not a production artifact.

## Hard prohibitions

No production feeds, public map runtime, WordPress, nycinfocus.com/map, iframe/embed settings, scheduled workflows, data/location_cache.json, live staging, SODA/live fetch, NYC Open Data calls, API calls, website scraping, geocoding, candidate creation, production candidate data, live registry data, candidate approval, candidate promotion, production registry database/importer/exporter behavior, live registry/table creation, production export behavior, production validator execution, production validator wiring, registry writes, registry imports, runtime publishing behavior, production runtime input, public output, WordPress output, executable production behavior, production fixture wiring, production summary wiring, production readiness wiring, production boundary wiring, candidate schema wiring, source ingestion wiring, publishing, or XRI-G36 start.

## Review gate

Open a pull request only. Do not merge. Do not start XRI-G36.
