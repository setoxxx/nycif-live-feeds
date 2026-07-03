# XRI-G8 Fixture-Only Candidate Preview Review Report Contract

Phase: XRI-G8
Mode: fixture-only review report formatting
Production allowed: false

This phase defines sample-only review report formatting for blocked XRI preview records.

Allowed files:

- `docs/xri-g8-fixture-only-candidate-preview-review-report-contract.md`
- `tools/registry/xri_g8_fixture_candidate_preview_report.py`
- `data/reports/xri_g8_fixture_candidate_preview_review_report.json`

The report must use review-safe fields only and keep every row blocked for review. It must not use live source data, geocoding, production writes, public map runtime changes, WordPress changes, workflow changes, or `data/location_cache.json`.

Next recommended phase gate: XRI-G9 fixture-only review sorting/grouping rules.
