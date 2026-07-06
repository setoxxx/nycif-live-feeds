# XRI-G41 Non-Production Fixture-Only Parser-Normalizer Gate Contract

Phase: XRI-G41

Source pull request: #50

Source merge commit SHA: f8cb2f6d00b7dbb24827e096c5e03644ccdad93f

## Purpose

XRI-G41 is a non-production fixture-only parser-normalizer gate after XRI-G40.

This gate extends the XRI-G40 fixture-only scaffold into a parser-normalizer layer for explicitly supplied test fixtures only.

## Allowed files

- docs/xri-g41-non-production-fixture-only-parser-normalizer-gate-contract.md
- data/reports/xri_g41_non_production_fixture_only_parser_normalizer_gate_report.json
- tools/registry/xri_g41_fixture_only_parser_normalizer.py
- tests/registry/test_xri_g41_fixture_only_parser_normalizer.py

## Boundary

This gate is parser-normalizer only, non-production only, and fixture-only.

It does not create production behavior or public runtime behavior. It does not create approval, promotion, publishing, scheduled workflow, geocoding, registry import/write, WordPress, or location cache behavior. XRI-G42 is not started.

## Parser-normalizer behavior

The fixture-only parser-normalizer must:

- accept only explicit fixture payloads supplied by tests or callers
- reject blocked source/action fields
- normalize source, title, location, and date/time fields when supplied
- preserve raw fixture payload metadata for audit/debugging
- perform no network calls
- perform no production writes
- return deterministic fixture-only normalized output

## Stable identity

Stable identity remains based only on:

- group_key
- display_location
- candidate_identity

Stable identity must not use review_rank, row position, array index, coordinates, geometry, public runtime targets, or production targets.

## Review gate

Open a pull request only. Do not merge. Do not start XRI-G42.
