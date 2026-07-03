# XRI-G9 Fixture-Only Review Sorting/Grouping Contract

Phase: XRI-G9
Mode: fixture-only review sorting/grouping rules
Production allowed: false

XRI-G9 defines deterministic sorting and grouping rules for sample XRI review rows from XRI-G8.

Allowed files:

- `docs/xri-g9-fixture-only-review-sorting-grouping-contract.md`
- `tools/registry/xri_g9_fixture_review_sorting_grouping.py`
- `data/reports/xri_g9_fixture_review_sorting_grouping_report.json`

Rules:

- Use fixture/sample rows only.
- Do not use live source data, geocoding, coordinates, row order, review rank, display order, production state, or `data/location_cache.json`.
- Use only fixture-safe review fields for sorting/grouping.
- Keep every output row blocked for review.
- Keep `cpcm-i88g` and `xtsw-fqvh` as review-only supporting references.
- Do not modify production feeds, public map runtime, WordPress, workflows, or cache files.

Safe groups:

- `public_event_candidate_previews`
- `supporting_reference_only_rows`
- `missing_or_context_location_rows`
- `ambiguity_review_rows`
- `source_dataset_groups`

Next recommended phase gate: XRI-G10 fixture-only grouped review export contract.
