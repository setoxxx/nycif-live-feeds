# XRI-G44 Audit Reporting Gate Contract

Phase: XRI-G44

Source pull request: #53

Source merge commit SHA: dfb4048977edc20d2806f769aa609fae75a06463

## Purpose

XRI-G44 adds a non-production fixture-only audit-reporting layer after XRI-G43.

## Allowed files

- docs/xri-g44-non-production-fixture-only-audit-reporting-gate-contract.md
- data/reports/xri_g44_non_production_fixture_only_audit_reporting_gate_report.json
- tools/registry/xri_g44_fixture_only_audit_reporting.py
- tests/registry/test_xri_g44_fixture_only_audit_reporting.py

## Boundary

This gate is audit-reporting only, non-production only, fixture-only, deterministic, and fail-closed.

It does not create production, public runtime, approval, promotion, publishing, scheduled workflow, geocoding, registry import/write, WordPress, or location cache behavior.

XRI-G45 is not started.

## Stable identity

Stable identity remains based only on:

- group_key
- display_location
- candidate_identity

Stable identity must not use review_rank, row position, array index, coordinates, geometry, public runtime targets, or production targets.

## Review gate

Open a pull request only. Do not merge. Do not start XRI-G45.
