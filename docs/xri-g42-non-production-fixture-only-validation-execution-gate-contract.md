# XRI-G42 Non-Production Fixture-Only Validation Execution Gate Contract

Phase: XRI-G42

Source pull request: #51

Source merge commit SHA: c521b4cc2aa4db2fcab4bfe41b107bba156046f5

## Purpose

XRI-G42 is a non-production fixture-only validation execution gate after XRI-G41.

This gate adds a fixture-only validation execution layer for explicitly supplied test fixtures only.

## Allowed files

- docs/xri-g42-non-production-fixture-only-validation-execution-gate-contract.md
- data/reports/xri_g42_non_production_fixture_only_validation_execution_gate_report.json
- tools/registry/xri_g42_fixture_only_validation_execution.py
- tests/registry/test_xri_g42_fixture_only_validation_execution.py

## Boundary

This gate is validation-execution only, non-production only, fixture-only, deterministic, and fail-closed.

It does not create production behavior or public runtime behavior. It does not create approval, promotion, publishing, scheduled workflow, geocoding, registry import/write, WordPress, or location cache behavior. XRI-G43 is not started.

## Validation behavior

The fixture-only validation execution must:

- accept only explicit fixture payloads supplied by tests or callers
- optionally use the XRI-G41 parser-normalizer for fixture payloads
- validate required stable identity fields
- validate parser-normalizer output shape
- validate review_rank remains display-only if present
- perform no network calls
- perform no production writes
- return deterministic fixture-only validation output

## Stable identity

Stable identity remains based only on:

- group_key
- display_location
- candidate_identity

Stable identity must not use review_rank, row position, array index, coordinates, geometry, public runtime targets, or production targets.

## Review gate

Open a pull request only. Do not merge. Do not start XRI-G43.
