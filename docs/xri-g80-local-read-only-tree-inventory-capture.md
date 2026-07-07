# XRI-G80 Local Read-Only Tree Inventory Capture

Status: inventory capture only
Baseline commit: 80e92d2418a7ebdb6f28ebfa85d2af9dabd9f30c
Captured HEAD: 80e92d2418a7ebdb6f28ebfa85d2af9dabd9f30c
Prior gate: XRI-G79 local read-only tree inventory output capture gate

## Safety

- Documentation/report only.
- Local read-only tree inventory capture only.
- No validation executed.
- No live fetch executed.
- No dry-run executed.
- No NYC Open Data/SODA/API call executed.
- No scraping executed.
- No geocoding executed.
- No data/location_cache.json change.
- No generated artifact change.
- No scripts/tools/tests/workflows changed.
- No public map/runtime files changed.
- No production write.

## Commands run

```text
git rev-parse HEAD
git status --short
git ls-tree -r --name-only HEAD
awk -F/ '{print $1}' committed file list | sort -u
grep fixture/test/manifest/workflow/script/validation filename patterns over committed file list
```

## Git status before commit

```text
?? tmp/
```

## Total committed files

```text
     269
```

## Top-level paths

```text
.github
AGENTS.md
data
docs
feed-metadata.json
major-feed-metadata.json
nycif_all_radar_map_events.json
nycif_major_radar_map_events.json
README.md
scripts
status
tests
tools
```

## Fixture-like paths

```text
data/fixtures/registry-candidate-extractor.sample.json
data/fixtures/xri-g23-prototype-fixture-manual-review-sample-set.sample.json
data/fixtures/xri-g28-non-production-manual-review-export.sample.json
data/fixtures/xri-g35-non-production-source-ingestion-sample.json
data/fixtures/xri-g5-source-field-mapping.sample.json
data/fixtures/xri-g6-mapping-validator.sample.json
data/fixtures/xri-g7-candidate-normalizer.sample.json
data/reports/xri_g10_fixture_grouped_review_export_report.json
data/reports/xri_g11_fixture_grouped_export_validation_report.json
data/reports/xri_g14_fixture_validator_report.json
data/reports/xri_g16_validator_failure_case_fixtures_report.json
data/reports/xri_g23_prototype_fixture_manual_review_sample_set_gate_report.json
data/reports/xri_g28_non_production_manual_review_export_sample_gate_report.json
data/reports/xri_g29_non_production_manual_review_export_sample_validation_gate_report.json
data/reports/xri_g35_non_production_source_ingestion_sample_contract_gate_report.json
data/reports/xri_g36_non_production_source_ingestion_sample_validation_gate_report.json
data/reports/xri_g40_non_production_fixture_only_implementation_scaffold_gate_report.json
data/reports/xri_g41_non_production_fixture_only_parser_normalizer_gate_report.json
data/reports/xri_g42_non_production_fixture_only_validation_execution_gate_report.json
data/reports/xri_g43_non_production_fixture_only_manual_review_handoff_gate_report.json
data/reports/xri_g44_non_production_fixture_only_audit_reporting_gate_report.json
data/reports/xri_g6_fixture_mapping_validator_report.json
data/reports/xri_g73_fixture_only_validation_authorization_gate_report.json
data/reports/xri_g74_fixture_only_validation_scope_command_gate_report.json
data/reports/xri_g75_fixture_inventory_gate_report.json
data/reports/xri_g76_fixture_inventory_results_gate_report.json
data/reports/xri_g7_fixture_candidate_normalizer_report.json
data/reports/xri_g8_fixture_candidate_preview_review_report.json
data/reports/xri_g9_fixture_review_sorting_grouping_report.json
docs/xri-g14-fixture-validator-contract.md
docs/xri-g16-validator-failure-case-fixtures-contract.md
docs/xri-g23-prototype-fixture-manual-review-sample-set-gate-contract.md
docs/xri-g28-non-production-manual-review-export-sample-gate-contract.md
docs/xri-g29-non-production-manual-review-export-sample-validation-gate-contract.md
docs/xri-g35-non-production-source-ingestion-sample-contract-gate-contract.md
docs/xri-g36-non-production-source-ingestion-sample-validation-gate-contract.md
docs/xri-g40-non-production-fixture-only-implementation-scaffold-gate-contract.md
docs/xri-g41-non-production-fixture-only-parser-normalizer-gate-contract.md
docs/xri-g42-non-production-fixture-only-validation-execution-gate-contract.md
docs/xri-g43-non-production-fixture-only-manual-review-handoff-gate-contract.md
docs/xri-g44-non-production-fixture-only-audit-reporting-gate-contract.md
docs/xri-g6-fixture-only-mapping-validator-contract.md
docs/xri-g7-fixture-only-candidate-normalization-contract.md
docs/xri-g73-fixture-only-validation-authorization-gate-contract.md
docs/xri-g74-fixture-only-validation-scope-command-gate-contract.md
docs/xri-g75-fixture-inventory-gate-contract.md
docs/xri-g76-fixture-inventory-results-gate-contract.md
docs/xri-g8-fixture-only-candidate-preview-review-report-contract.md
docs/xri-g9-fixture-only-review-sorting-grouping-contract.md
tests/registry/test_xri_g40_fixture_only_source_ingestion_scaffold.py
tests/registry/test_xri_g41_fixture_only_parser_normalizer.py
tests/registry/test_xri_g42_fixture_only_validation_execution.py
tests/registry/test_xri_g43_fixture_only_manual_review_handoff.py
tests/registry/test_xri_g44_fixture_only_audit_reporting.py
tools/registry/xri_g10_fixture_grouped_review_export.py
tools/registry/xri_g11_fixture_grouped_export_validator.py
tools/registry/xri_g40_fixture_only_source_ingestion_scaffold.py
tools/registry/xri_g41_fixture_only_parser_normalizer.py
tools/registry/xri_g42_fixture_only_validation_execution.py
tools/registry/xri_g43_fixture_only_manual_review_handoff.py
tools/registry/xri_g44_fixture_only_audit_reporting.py
tools/registry/xri_g6_fixture_mapping_validator.py
tools/registry/xri_g7_fixture_candidate_normalizer.py
tools/registry/xri_g8_fixture_candidate_preview_report.py
tools/registry/xri_g9_fixture_review_sorting_grouping.py
```

## Test-like paths

```text
tests/registry/test_xri_g40_fixture_only_source_ingestion_scaffold.py
tests/registry/test_xri_g41_fixture_only_parser_normalizer.py
tests/registry/test_xri_g42_fixture_only_validation_execution.py
tests/registry/test_xri_g43_fixture_only_manual_review_handoff.py
tests/registry/test_xri_g44_fixture_only_audit_reporting.py
```

## Manifest-like paths

```text
```

## Workflow-like paths

```text
.github/workflows/gps-staged-feed-integration-adjudication-summary.yml
.github/workflows/gps-staged-feed-integration-diagnostic.yml
.github/workflows/gps-staged-feed-integration-update.yml
.github/workflows/live-sync-qa.yml
```

## Script/tool-like paths

```text
scripts/apply_gps_staged_feed_integration_update.py
scripts/audit_feed_anomalies.py
scripts/audit_remainder_year_coverage.py
scripts/audit_row_disposition.py
scripts/backend_reliability_gate.py
scripts/build_gps_geocoding_filled_proposals.py
scripts/build_gps_geocoding_proposals.py
scripts/build_gps_manual_approval_queue.py
scripts/build_gps_manual_approval_staging.py
scripts/build_gps_manual_review_sheet.py
scripts/build_gps_repository.py
scripts/build_gps_review_groups.py
scripts/build_gps_reviewed_approval_artifact.py
scripts/build_live_delta_report.py
scripts/build_location_cache.py
scripts/build_staged_production_feed.py
scripts/build_test_enriched_feed.py
scripts/dry_run_gps_phase2e_promotion.py
scripts/generate_gps_staged_feed_integration_adjudication_summary.py
scripts/generate_gps_staged_feed_integration_match_diagnostic.py
scripts/publish_c5p_approved_major_event_row.mjs
scripts/send_live_delta_email.py
scripts/sync_nyc_open_data.py
scripts/validate_gps_manual_approvals.py
scripts/validate_gps_phase2e_promotion_readiness.py
tests/registry/test_xri_g40_fixture_only_source_ingestion_scaffold.py
tests/registry/test_xri_g41_fixture_only_parser_normalizer.py
tests/registry/test_xri_g42_fixture_only_validation_execution.py
tests/registry/test_xri_g43_fixture_only_manual_review_handoff.py
tests/registry/test_xri_g44_fixture_only_audit_reporting.py
tools/registry/registry_candidate_extractor_prototype.py
tools/registry/xri_g10_fixture_grouped_review_export.py
tools/registry/xri_g11_fixture_grouped_export_validator.py
tools/registry/xri_g40_fixture_only_source_ingestion_scaffold.py
tools/registry/xri_g41_fixture_only_parser_normalizer.py
tools/registry/xri_g42_fixture_only_validation_execution.py
tools/registry/xri_g43_fixture_only_manual_review_handoff.py
tools/registry/xri_g44_fixture_only_audit_reporting.py
tools/registry/xri_g6_fixture_mapping_validator.py
tools/registry/xri_g7_fixture_candidate_normalizer.py
tools/registry/xri_g8_fixture_candidate_preview_report.py
tools/registry/xri_g9_fixture_review_sorting_grouping.py
```

## Validation-related filename matches

```text
data/fixtures/registry-candidate-extractor.sample.json
data/fixtures/xri-g23-prototype-fixture-manual-review-sample-set.sample.json
data/fixtures/xri-g28-non-production-manual-review-export.sample.json
data/fixtures/xri-g35-non-production-source-ingestion-sample.json
data/fixtures/xri-g5-source-field-mapping.sample.json
data/fixtures/xri-g6-mapping-validator.sample.json
data/fixtures/xri-g7-candidate-normalizer.sample.json
data/gps_manual_approval_validation_report.json
data/location_cache.json
data/reports/production_feed_publish_report.json
data/reports/xri_g10_fixture_grouped_review_export_report.json
data/reports/xri_g11_fixture_grouped_export_validation_report.json
data/reports/xri_g14_fixture_validator_report.json
data/reports/xri_g15_validator_execution_report.json
data/reports/xri_g16_validator_failure_case_fixtures_report.json
data/reports/xri_g17_failure_case_validator_execution_report.json
data/reports/xri_g18_validator_summary_handoff_report.json
data/reports/xri_g21_prototype_scaffold_validator_gate_report.json
data/reports/xri_g22_prototype_scaffold_validator_execution_gate_report.json
data/reports/xri_g23_prototype_fixture_manual_review_sample_set_gate_report.json
data/reports/xri_g25_non_production_registry_dry_run_gate_report.json
data/reports/xri_g26_non_production_registry_dry_run_review_summary_gate_report.json
data/reports/xri_g27_non_production_manual_review_export_contract_gate_report.json
data/reports/xri_g28_non_production_manual_review_export_sample_gate_report.json
data/reports/xri_g29_non_production_manual_review_export_sample_validation_gate_report.json
data/reports/xri_g30_non_production_manual_review_export_validation_summary_gate_report.json
data/reports/xri_g31_non_production_manual_review_export_readiness_checkpoint_gate_report.json
data/reports/xri_g32_production_boundary_design_gate_report.json
data/reports/xri_g35_non_production_source_ingestion_sample_contract_gate_report.json
data/reports/xri_g36_non_production_source_ingestion_sample_validation_gate_report.json
data/reports/xri_g37_non_production_source_ingestion_validation_summary_gate_report.json
data/reports/xri_g40_non_production_fixture_only_implementation_scaffold_gate_report.json
data/reports/xri_g41_non_production_fixture_only_parser_normalizer_gate_report.json
data/reports/xri_g42_non_production_fixture_only_validation_execution_gate_report.json
data/reports/xri_g43_non_production_fixture_only_manual_review_handoff_gate_report.json
data/reports/xri_g44_non_production_fixture_only_audit_reporting_gate_report.json
data/reports/xri_g45_non_production_source_adapter_design_proposal_gate_report.json
data/reports/xri_g46_non_production_live_source_fetch_proposal_gate_report.json
data/reports/xri_g47_non_production_source_specific_adapter_proposal_gate_report.json
data/reports/xri_g48_non_production_controlled_live_fetch_implementation_authorization_gate_report.json
data/reports/xri_g49_non_production_controlled_live_fetch_plan_gate_report.json
data/reports/xri_g50_non_production_controlled_live_fetch_readiness_gate_report.json
data/reports/xri_g51_non_production_controlled_live_fetch_dry_run_authorization_gate_report.json
data/reports/xri_g52_non_production_controlled_live_fetch_dry_run_design_gate_report.json
data/reports/xri_g53_non_production_controlled_live_fetch_dry_run_manifest_gate_report.json
data/reports/xri_g54_non_production_controlled_live_fetch_dry_run_validation_gate_report.json
data/reports/xri_g55_non_production_controlled_live_fetch_dry_run_failure_stop_gate_report.json
data/reports/xri_g56_non_production_controlled_live_fetch_dry_run_audit_logging_gate_report.json
data/reports/xri_g57_non_production_controlled_live_fetch_dry_run_output_boundary_gate_report.json
data/reports/xri_g58_non_production_controlled_live_fetch_dry_run_input_boundary_gate_report.json
data/reports/xri_g59_non_production_controlled_live_fetch_dry_run_source_call_contract_gate_report.json
data/reports/xri_g60_non_production_controlled_live_fetch_dry_run_execution_authorization_gate_report.json
data/reports/xri_g61_non_production_controlled_live_fetch_dry_run_pre_execution_checklist_gate_report.json
data/reports/xri_g62_non_production_controlled_live_fetch_dry_run_read_only_harness_contract_gate_report.json
data/reports/xri_g63_non_production_controlled_live_fetch_dry_run_artifact_isolation_gate_report.json
data/reports/xri_g64_non_production_controlled_live_fetch_dry_run_audit_manifest_gate_report.json
data/reports/xri_g65_non_production_controlled_live_fetch_dry_run_review_package_gate_report.json
data/reports/xri_g6_fixture_mapping_validator_report.json
data/reports/xri_g73_fixture_only_validation_authorization_gate_report.json
data/reports/xri_g74_fixture_only_validation_scope_command_gate_report.json
data/reports/xri_g75_fixture_inventory_gate_report.json
data/reports/xri_g76_fixture_inventory_results_gate_report.json
data/reports/xri_g7_fixture_candidate_normalizer_report.json
data/reports/xri_g8_fixture_candidate_preview_review_report.json
data/reports/xri_g9_fixture_review_sorting_grouping_report.json
docs/phase-2c-controlled-geocoder-fill.md
docs/xri-g14-fixture-validator-contract.md
docs/xri-g15-validator-execution-contract.md
docs/xri-g16-validator-failure-case-fixtures-contract.md
docs/xri-g17-failure-case-validator-execution-contract.md
docs/xri-g18-validator-summary-handoff-contract.md
docs/xri-g21-prototype-scaffold-validator-gate-contract.md
docs/xri-g22-prototype-scaffold-validator-execution-gate-contract.md
docs/xri-g23-prototype-fixture-manual-review-sample-set-gate-contract.md
docs/xri-g25-non-production-registry-dry-run-gate-contract.md
docs/xri-g26-non-production-registry-dry-run-review-summary-gate-contract.md
docs/xri-g27-non-production-manual-review-export-contract-gate-contract.md
docs/xri-g28-non-production-manual-review-export-sample-gate-contract.md
docs/xri-g29-non-production-manual-review-export-sample-validation-gate-contract.md
docs/xri-g30-non-production-manual-review-export-validation-summary-gate-contract.md
docs/xri-g31-non-production-manual-review-export-readiness-checkpoint-gate-contract.md
docs/xri-g32-production-boundary-design-gate-contract.md
docs/xri-g35-non-production-source-ingestion-sample-contract-gate-contract.md
docs/xri-g36-non-production-source-ingestion-sample-validation-gate-contract.md
docs/xri-g37-non-production-source-ingestion-validation-summary-gate-contract.md
docs/xri-g40-non-production-fixture-only-implementation-scaffold-gate-contract.md
docs/xri-g41-non-production-fixture-only-parser-normalizer-gate-contract.md
docs/xri-g42-non-production-fixture-only-validation-execution-gate-contract.md
docs/xri-g43-non-production-fixture-only-manual-review-handoff-gate-contract.md
docs/xri-g44-non-production-fixture-only-audit-reporting-gate-contract.md
docs/xri-g45-non-production-source-adapter-design-proposal-gate-contract.md
docs/xri-g46-non-production-live-source-fetch-proposal-gate-contract.md
docs/xri-g47-non-production-source-specific-adapter-proposal-gate-contract.md
docs/xri-g48-non-production-controlled-live-fetch-implementation-authorization-gate-contract.md
docs/xri-g49-non-production-controlled-live-fetch-plan-gate-contract.md
docs/xri-g50-non-production-controlled-live-fetch-readiness-gate-contract.md
docs/xri-g51-non-production-controlled-live-fetch-dry-run-authorization-gate-contract.md
docs/xri-g52-non-production-controlled-live-fetch-dry-run-design-gate-contract.md
docs/xri-g53-non-production-controlled-live-fetch-dry-run-manifest-gate-contract.md
docs/xri-g54-non-production-controlled-live-fetch-dry-run-validation-gate-contract.md
docs/xri-g55-non-production-controlled-live-fetch-dry-run-failure-stop-gate-contract.md
docs/xri-g56-non-production-controlled-live-fetch-dry-run-audit-logging-gate-contract.md
docs/xri-g57-non-production-controlled-live-fetch-dry-run-output-boundary-gate-contract.md
docs/xri-g58-non-production-controlled-live-fetch-dry-run-input-boundary-gate-contract.md
docs/xri-g59-non-production-controlled-live-fetch-dry-run-source-call-contract-gate.md
docs/xri-g6-fixture-only-mapping-validator-contract.md
docs/xri-g60-non-production-controlled-live-fetch-dry-run-execution-authorization-gate.md
docs/xri-g61-non-production-controlled-live-fetch-dry-run-pre-execution-checklist-gate.md
docs/xri-g62-non-production-controlled-live-fetch-dry-run-read-only-harness-contract-gate.md
docs/xri-g63-non-production-controlled-live-fetch-dry-run-artifact-isolation-gate.md
docs/xri-g64-non-production-controlled-live-fetch-dry-run-audit-manifest-gate.md
docs/xri-g65-non-production-controlled-live-fetch-dry-run-review-package-gate.md
docs/xri-g7-fixture-only-candidate-normalization-contract.md
docs/xri-g73-fixture-only-validation-authorization-gate-contract.md
docs/xri-g74-fixture-only-validation-scope-command-gate-contract.md
docs/xri-g75-fixture-inventory-gate-contract.md
docs/xri-g76-fixture-inventory-results-gate-contract.md
docs/xri-g8-fixture-only-candidate-preview-review-report-contract.md
docs/xri-g9-fixture-only-review-sorting-grouping-contract.md
scripts/build_location_cache.py
scripts/build_staged_production_feed.py
scripts/validate_gps_manual_approvals.py
scripts/validate_gps_phase2e_promotion_readiness.py
tests/registry/test_xri_g40_fixture_only_source_ingestion_scaffold.py
tests/registry/test_xri_g41_fixture_only_parser_normalizer.py
tests/registry/test_xri_g42_fixture_only_validation_execution.py
tests/registry/test_xri_g43_fixture_only_manual_review_handoff.py
tests/registry/test_xri_g44_fixture_only_audit_reporting.py
tools/registry/xri_g10_fixture_grouped_review_export.py
tools/registry/xri_g11_fixture_grouped_export_validator.py
tools/registry/xri_g40_fixture_only_source_ingestion_scaffold.py
tools/registry/xri_g41_fixture_only_parser_normalizer.py
tools/registry/xri_g42_fixture_only_validation_execution.py
tools/registry/xri_g43_fixture_only_manual_review_handoff.py
tools/registry/xri_g44_fixture_only_audit_reporting.py
tools/registry/xri_g6_fixture_mapping_validator.py
tools/registry/xri_g7_fixture_candidate_normalizer.py
tools/registry/xri_g8_fixture_candidate_preview_report.py
tools/registry/xri_g9_fixture_review_sorting_grouping.py
```

## Full committed file list

```text
.github/workflows/gps-staged-feed-integration-adjudication-summary.yml
.github/workflows/gps-staged-feed-integration-diagnostic.yml
.github/workflows/gps-staged-feed-integration-update.yml
.github/workflows/live-sync-qa.yml
AGENTS.md
README.md
data/backend_reliability_gate_report.json
data/backups/nycif_all_radar_map_events.2026-07-01T19-55-07-881Z.json
data/backups/nycif_major_radar_map_events.2026-07-01T19-55-07-881Z.json
data/feed_anomaly_report.json
data/fixtures/registry-candidate-extractor.sample.json
data/fixtures/xri-g23-prototype-fixture-manual-review-sample-set.sample.json
data/fixtures/xri-g28-non-production-manual-review-export.sample.json
data/fixtures/xri-g35-non-production-source-ingestion-sample.json
data/fixtures/xri-g5-source-field-mapping.sample.json
data/fixtures/xri-g6-mapping-validator.sample.json
data/fixtures/xri-g7-candidate-normalizer.sample.json
data/gps_manual_approval_queue.json
data/gps_manual_approval_queue_report.json
data/gps_manual_approval_review_findings.json
data/gps_manual_approval_review_sheet.csv
data/gps_manual_approval_review_sheet.json
data/gps_manual_approval_review_sheet_report.json
data/gps_manual_approval_staging_candidates.json
data/gps_manual_approval_staging_report.json
data/gps_manual_approval_validation_report.json
data/gps_needs_review_events.json
data/gps_phase2e_post_promotion_qa_report.json
data/gps_phase2e_promotion_dry_run_report.json
data/gps_phase2e_promotion_readiness_report.json
data/gps_phase2e_promotion_report.json
data/gps_repository_report.json
data/gps_review_geocoding_fill_report.json
data/gps_review_geocoding_filled_proposals.json
data/gps_review_geocoding_proposal_report.json
data/gps_review_geocoding_proposals.json
data/gps_review_geocoding_queue.json
data/gps_review_group_report.json
data/gps_review_location_groups.json
data/gps_reviewed_approval_artifact.json
data/gps_reviewed_approval_artifact_report.json
data/gps_staged_feed_integration_adjudication_summary.json
data/gps_staged_feed_integration_dry_run_report.json
data/gps_staged_feed_integration_match_diagnostic.json
data/gps_staged_feed_integration_update_report.json
data/gps_staged_feed_post_update_qa_report.json
data/live_delta_report.json
data/live_sync_report.json
data/location_cache.json
data/nycif_live_test_enriched_events.json
data/nycif_staged_live_events.json
data/previous_staged_live_events_snapshot.json
data/raw_nyc_open_data_snapshot.json
data/remainder_year_coverage_report.json
data/reports/production_feed_publish_report.json
data/reports/registry_candidate_extractor_prototype_report.json
data/reports/xri_g10_fixture_grouped_review_export_report.json
data/reports/xri_g11_fixture_grouped_export_validation_report.json
data/reports/xri_g12_planning_gate_report.json
data/reports/xri_g13_manual_review_schema_prototype_report.json
data/reports/xri_g14_fixture_validator_report.json
data/reports/xri_g15_validator_execution_report.json
data/reports/xri_g16_validator_failure_case_fixtures_report.json
data/reports/xri_g17_failure_case_validator_execution_report.json
data/reports/xri_g18_validator_summary_handoff_report.json
data/reports/xri_g19_registry_implementation_planning_gate_report.json
data/reports/xri_g20_registry_manual_review_prototype_scaffold_report.json
data/reports/xri_g21_prototype_scaffold_validator_gate_report.json
data/reports/xri_g22_prototype_scaffold_validator_execution_gate_report.json
data/reports/xri_g23_prototype_fixture_manual_review_sample_set_gate_report.json
data/reports/xri_g24_stable_identity_matching_verification_gate_report.json
data/reports/xri_g25_non_production_registry_dry_run_gate_report.json
data/reports/xri_g26_non_production_registry_dry_run_review_summary_gate_report.json
data/reports/xri_g27_non_production_manual_review_export_contract_gate_report.json
data/reports/xri_g28_non_production_manual_review_export_sample_gate_report.json
data/reports/xri_g29_non_production_manual_review_export_sample_validation_gate_report.json
data/reports/xri_g30_non_production_manual_review_export_validation_summary_gate_report.json
data/reports/xri_g31_non_production_manual_review_export_readiness_checkpoint_gate_report.json
data/reports/xri_g32_production_boundary_design_gate_report.json
data/reports/xri_g33_candidate_event_registry_schema_gate_report.json
data/reports/xri_g34_source_ingestion_contract_today_weekend_events_gate_report.json
data/reports/xri_g35_non_production_source_ingestion_sample_contract_gate_report.json
data/reports/xri_g36_non_production_source_ingestion_sample_validation_gate_report.json
data/reports/xri_g37_non_production_source_ingestion_validation_summary_gate_report.json
data/reports/xri_g38_source_ingestion_readiness_checkpoint_gate_report.json
data/reports/xri_g39_controlled_implementation_planning_gate_report.json
data/reports/xri_g40_non_production_fixture_only_implementation_scaffold_gate_report.json
data/reports/xri_g41_non_production_fixture_only_parser_normalizer_gate_report.json
data/reports/xri_g42_non_production_fixture_only_validation_execution_gate_report.json
data/reports/xri_g43_non_production_fixture_only_manual_review_handoff_gate_report.json
data/reports/xri_g44_non_production_fixture_only_audit_reporting_gate_report.json
data/reports/xri_g45_non_production_source_adapter_design_proposal_gate_report.json
data/reports/xri_g46_non_production_live_source_fetch_proposal_gate_report.json
data/reports/xri_g47_non_production_source_specific_adapter_proposal_gate_report.json
data/reports/xri_g48_non_production_controlled_live_fetch_implementation_authorization_gate_report.json
data/reports/xri_g49_non_production_controlled_live_fetch_plan_gate_report.json
data/reports/xri_g50_non_production_controlled_live_fetch_readiness_gate_report.json
data/reports/xri_g51_non_production_controlled_live_fetch_dry_run_authorization_gate_report.json
data/reports/xri_g52_non_production_controlled_live_fetch_dry_run_design_gate_report.json
data/reports/xri_g53_non_production_controlled_live_fetch_dry_run_manifest_gate_report.json
data/reports/xri_g54_non_production_controlled_live_fetch_dry_run_validation_gate_report.json
data/reports/xri_g55_non_production_controlled_live_fetch_dry_run_failure_stop_gate_report.json
data/reports/xri_g56_non_production_controlled_live_fetch_dry_run_audit_logging_gate_report.json
data/reports/xri_g57_non_production_controlled_live_fetch_dry_run_output_boundary_gate_report.json
data/reports/xri_g58_non_production_controlled_live_fetch_dry_run_input_boundary_gate_report.json
data/reports/xri_g59_non_production_controlled_live_fetch_dry_run_source_call_contract_gate_report.json
data/reports/xri_g5_source_field_mapping_contract_report.json
data/reports/xri_g60_non_production_controlled_live_fetch_dry_run_execution_authorization_gate_report.json
data/reports/xri_g61_non_production_controlled_live_fetch_dry_run_pre_execution_checklist_gate_report.json
data/reports/xri_g62_non_production_controlled_live_fetch_dry_run_read_only_harness_contract_gate_report.json
data/reports/xri_g63_non_production_controlled_live_fetch_dry_run_artifact_isolation_gate_report.json
data/reports/xri_g64_non_production_controlled_live_fetch_dry_run_audit_manifest_gate_report.json
data/reports/xri_g65_non_production_controlled_live_fetch_dry_run_review_package_gate_report.json
data/reports/xri_g66_post_recovery_restart_authorization_gate_report.json
data/reports/xri_g67_post_recovery_continuation_scope_gate_report.json
data/reports/xri_g68_post_recovery_review_only_planning_gate_report.json
data/reports/xri_g69_post_g68_next_workstream_authorization_map_gate_report.json
data/reports/xri_g6_fixture_mapping_validator_report.json
data/reports/xri_g70_post_g69_lane_selection_gate_report.json
data/reports/xri_g71_post_g70_review_only_next_step_planning_gate_report.json
data/reports/xri_g72_review_only_evidence_requirements_gate_report.json
data/reports/xri_g73_fixture_only_validation_authorization_gate_report.json
data/reports/xri_g74_fixture_only_validation_scope_command_gate_report.json
data/reports/xri_g75_fixture_inventory_gate_report.json
data/reports/xri_g76_fixture_inventory_results_gate_report.json
data/reports/xri_g77_read_only_repository_tree_inventory_gate_report.json
data/reports/xri_g78_read_only_repository_tree_inventory_results_gate_report.json
data/reports/xri_g79_local_read_only_tree_inventory_output_capture_gate_report.json
data/reports/xri_g7_fixture_candidate_normalizer_report.json
data/reports/xri_g8_fixture_candidate_preview_review_report.json
data/reports/xri_g9_fixture_review_sorting_grouping_report.json
data/reports/xri_recovery_baseline_after_pr77_report.json
data/row_disposition_events.json
data/row_disposition_report.json
data/staged_feed_regeneration_report.json
data/staged_live_manifest.json
data/test_enriched_feed_manifest.json
data/tourist_categories_phase3a.json
docs/audits/live-sync-qa-autocommit-risk-after-pr76.md
docs/phase-1-backend-reliability.md
docs/phase-2-controlled-gps-review.md
docs/phase-2b-controlled-geocoding-proposals.md
docs/phase-2c-controlled-geocoder-fill.md
docs/phase-2e-gps-promotion-design.md
docs/phase-3a-tourist-mode-foundation.md
docs/read-only-candidate-extractor-prototype.md
docs/status-artifact-v1.md
docs/tourist_first_daily_event_layer_gate_spec.md
docs/xri-g12-planning-gate-contract.md
docs/xri-g13-manual-review-schema-prototype-contract.md
docs/xri-g14-fixture-validator-contract.md
docs/xri-g15-validator-execution-contract.md
docs/xri-g16-validator-failure-case-fixtures-contract.md
docs/xri-g17-failure-case-validator-execution-contract.md
docs/xri-g18-validator-summary-handoff-contract.md
docs/xri-g19-registry-implementation-planning-gate-contract.md
docs/xri-g20-registry-manual-review-prototype-scaffold-contract.md
docs/xri-g21-prototype-scaffold-validator-gate-contract.md
docs/xri-g22-prototype-scaffold-validator-execution-gate-contract.md
docs/xri-g23-prototype-fixture-manual-review-sample-set-gate-contract.md
docs/xri-g24-stable-identity-matching-verification-gate-contract.md
docs/xri-g25-non-production-registry-dry-run-gate-contract.md
docs/xri-g26-non-production-registry-dry-run-review-summary-gate-contract.md
docs/xri-g27-non-production-manual-review-export-contract-gate-contract.md
docs/xri-g28-non-production-manual-review-export-sample-gate-contract.md
docs/xri-g29-non-production-manual-review-export-sample-validation-gate-contract.md
docs/xri-g30-non-production-manual-review-export-validation-summary-gate-contract.md
docs/xri-g31-non-production-manual-review-export-readiness-checkpoint-gate-contract.md
docs/xri-g32-production-boundary-design-gate-contract.md
docs/xri-g33-candidate-event-registry-schema-gate-contract.md
docs/xri-g34-source-ingestion-contract-today-weekend-events-gate-contract.md
docs/xri-g35-non-production-source-ingestion-sample-contract-gate-contract.md
docs/xri-g36-non-production-source-ingestion-sample-validation-gate-contract.md
docs/xri-g37-non-production-source-ingestion-validation-summary-gate-contract.md
docs/xri-g38-source-ingestion-readiness-checkpoint-gate-contract.md
docs/xri-g39-controlled-implementation-planning-gate-contract.md
docs/xri-g40-non-production-fixture-only-implementation-scaffold-gate-contract.md
docs/xri-g41-non-production-fixture-only-parser-normalizer-gate-contract.md
docs/xri-g42-non-production-fixture-only-validation-execution-gate-contract.md
docs/xri-g43-non-production-fixture-only-manual-review-handoff-gate-contract.md
docs/xri-g44-non-production-fixture-only-audit-reporting-gate-contract.md
docs/xri-g45-non-production-source-adapter-design-proposal-gate-contract.md
docs/xri-g46-non-production-live-source-fetch-proposal-gate-contract.md
docs/xri-g47-non-production-source-specific-adapter-proposal-gate-contract.md
docs/xri-g48-non-production-controlled-live-fetch-implementation-authorization-gate-contract.md
docs/xri-g49-non-production-controlled-live-fetch-plan-gate-contract.md
docs/xri-g5-source-field-mapping-contract.md
docs/xri-g50-non-production-controlled-live-fetch-readiness-gate-contract.md
docs/xri-g51-non-production-controlled-live-fetch-dry-run-authorization-gate-contract.md
docs/xri-g52-non-production-controlled-live-fetch-dry-run-design-gate-contract.md
docs/xri-g53-non-production-controlled-live-fetch-dry-run-manifest-gate-contract.md
docs/xri-g54-non-production-controlled-live-fetch-dry-run-validation-gate-contract.md
docs/xri-g55-non-production-controlled-live-fetch-dry-run-failure-stop-gate-contract.md
docs/xri-g56-non-production-controlled-live-fetch-dry-run-audit-logging-gate-contract.md
docs/xri-g57-non-production-controlled-live-fetch-dry-run-output-boundary-gate-contract.md
docs/xri-g58-non-production-controlled-live-fetch-dry-run-input-boundary-gate-contract.md
docs/xri-g59-non-production-controlled-live-fetch-dry-run-source-call-contract-gate.md
docs/xri-g6-fixture-only-mapping-validator-contract.md
docs/xri-g60-non-production-controlled-live-fetch-dry-run-execution-authorization-gate.md
docs/xri-g61-non-production-controlled-live-fetch-dry-run-pre-execution-checklist-gate.md
docs/xri-g62-non-production-controlled-live-fetch-dry-run-read-only-harness-contract-gate.md
docs/xri-g63-non-production-controlled-live-fetch-dry-run-artifact-isolation-gate.md
docs/xri-g64-non-production-controlled-live-fetch-dry-run-audit-manifest-gate.md
docs/xri-g65-non-production-controlled-live-fetch-dry-run-review-package-gate.md
docs/xri-g66-post-recovery-restart-authorization-gate-contract.md
docs/xri-g67-post-recovery-continuation-scope-gate-contract.md
docs/xri-g68-post-recovery-review-only-planning-gate-contract.md
docs/xri-g69-post-g68-next-workstream-authorization-map-gate-contract.md
docs/xri-g7-fixture-only-candidate-normalization-contract.md
docs/xri-g70-post-g69-lane-selection-gate-contract.md
docs/xri-g71-post-g70-review-only-next-step-planning-gate-contract.md
docs/xri-g72-review-only-evidence-requirements-gate-contract.md
docs/xri-g73-fixture-only-validation-authorization-gate-contract.md
docs/xri-g74-fixture-only-validation-scope-command-gate-contract.md
docs/xri-g75-fixture-inventory-gate-contract.md
docs/xri-g76-fixture-inventory-results-gate-contract.md
docs/xri-g77-read-only-repository-tree-inventory-gate-contract.md
docs/xri-g78-read-only-repository-tree-inventory-results-gate-contract.md
docs/xri-g79-local-read-only-tree-inventory-output-capture-gate-contract.md
docs/xri-g8-fixture-only-candidate-preview-review-report-contract.md
docs/xri-g9-fixture-only-review-sorting-grouping-contract.md
docs/xri-recovery-baseline-after-pr77-contract.md
feed-metadata.json
major-feed-metadata.json
nycif_all_radar_map_events.json
nycif_major_radar_map_events.json
scripts/apply_gps_staged_feed_integration_update.py
scripts/audit_feed_anomalies.py
scripts/audit_remainder_year_coverage.py
scripts/audit_row_disposition.py
scripts/backend_reliability_gate.py
scripts/build_gps_geocoding_filled_proposals.py
scripts/build_gps_geocoding_proposals.py
scripts/build_gps_manual_approval_queue.py
scripts/build_gps_manual_approval_staging.py
scripts/build_gps_manual_review_sheet.py
scripts/build_gps_repository.py
scripts/build_gps_review_groups.py
scripts/build_gps_reviewed_approval_artifact.py
scripts/build_live_delta_report.py
scripts/build_location_cache.py
scripts/build_staged_production_feed.py
scripts/build_test_enriched_feed.py
scripts/dry_run_gps_phase2e_promotion.py
scripts/generate_gps_staged_feed_integration_adjudication_summary.py
scripts/generate_gps_staged_feed_integration_match_diagnostic.py
scripts/publish_c5p_approved_major_event_row.mjs
scripts/send_live_delta_email.py
scripts/sync_nyc_open_data.py
scripts/validate_gps_manual_approvals.py
scripts/validate_gps_phase2e_promotion_readiness.py
status/nycif-project-status.json
tests/registry/test_xri_g40_fixture_only_source_ingestion_scaffold.py
tests/registry/test_xri_g41_fixture_only_parser_normalizer.py
tests/registry/test_xri_g42_fixture_only_validation_execution.py
tests/registry/test_xri_g43_fixture_only_manual_review_handoff.py
tests/registry/test_xri_g44_fixture_only_audit_reporting.py
tools/registry/registry_candidate_extractor_prototype.py
tools/registry/xri_g10_fixture_grouped_review_export.py
tools/registry/xri_g11_fixture_grouped_export_validator.py
tools/registry/xri_g40_fixture_only_source_ingestion_scaffold.py
tools/registry/xri_g41_fixture_only_parser_normalizer.py
tools/registry/xri_g42_fixture_only_validation_execution.py
tools/registry/xri_g43_fixture_only_manual_review_handoff.py
tools/registry/xri_g44_fixture_only_audit_reporting.py
tools/registry/xri_g6_fixture_mapping_validator.py
tools/registry/xri_g7_fixture_candidate_normalizer.py
tools/registry/xri_g8_fixture_candidate_preview_report.py
tools/registry/xri_g9_fixture_review_sorting_grouping.py
```

## Decision

This capture records file/path inventory only. It does not authorize validation execution. A later gate must review these exact paths and authorize any exact fixture-only command before execution.
