# XRI-G40 Non-Production Fixture-Only Implementation Scaffold Gate Contract

Phase: XRI-G40

Source pull request: #49

Source merge commit SHA: e2a82f8a80136a650de227ae6057b280c7d4e9ea

## Purpose

XRI-G40 is a non-production fixture-only implementation scaffold gate after XRI-G39.

This gate creates a scaffold for future non-production, fixture-only source-ingestion implementation work.

## Allowed files

- docs/xri-g40-non-production-fixture-only-implementation-scaffold-gate-contract.md
- data/reports/xri_g40_non_production_fixture_only_implementation_scaffold_gate_report.json
- tools/registry/xri_g40_fixture_only_source_ingestion_scaffold.py
- tests/registry/test_xri_g40_fixture_only_source_ingestion_scaffold.py

## Boundary

This gate is scaffold only, non-production only, and fixture-only.

It does not implement live source ingestion, runtime production ingestion, live source fetch, SODA/live fetch, NYC Open Data calls, API calls, website scraping, live staging, geocoding, live candidate creation, registry writes, registry imports, production export, public map runtime, public map output, WordPress output, scheduled workflow changes, location_cache access, approval, promotion, publishing, production deployment, or XRI-G41.

## Scaffold behavior

The fixture-only scaffold must:

- accept only explicit fixture payloads supplied by tests or callers
- reject live URLs and live/API/SODA/NYC Open Data targets
- reject geocoding requests
- reject registry write/import requests
- reject approval, promotion, and publishing requests
- reject public map runtime/output requests
- reject location_cache access
- perform no network calls
- perform no production writes
- return deterministic fixture-only normalized output

## Stable identity

Stable identity remains based only on:

- group_key
- display_location
- candidate_identity

Stable identity must not use review_rank, row position, array index, source order, reviewer order, status fields, coordinates, geometry, public runtime targets, or production targets.

## Review gate

Open a pull request only. Do not merge. Do not start XRI-G41.
