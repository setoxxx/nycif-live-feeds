# Canonical Milestone 6: GPS Pipeline Reliability & Identity Integrity

Milestone: Canonical Milestone 6
Baseline SHA: `b59fb070de238ea97c699a29b6ef3ec61155593f` (Canonical Milestone 5 closure merge)

## Scope and method

This milestone is an audit-plus-test milestone: it documents the GPS pipeline's identity model and data flow as they exist in committed code (Stages 6A/6B/6D/6E), and adds deterministic offline tests proving identity-drift resistance and gating behavior against the fixture-only reference contracts, `tools/registry/xri_g40`–`xri_g44` (Stages 6C/6F). **No `scripts/**` or `tools/**` implementation file was modified.** The `scripts/` pipeline itself is not independently unit-testable in this repository's current structure (it consists of standalone file-reading/file-writing CLI programs, not importable functions over in-memory data), so genuine, executable test coverage in this milestone is scoped to the fixture-only reference contracts — the same scope every prior test file in this repository already uses. Static-audit findings about `scripts/**` are documented as findings, not fabricated as tested guarantees.

## Architecture

Three separate identity systems coexist in this repository (see `docs/gps_identity_model.md` for full detail):

1. `scripts/` live pipeline — composite string keys evolving from raw cache keys → `group_key` → `stable_identity_key` → `stable_event_identity`, each stage largely passing the prior stage's identity field forward under the same name.
2. `tools/registry/xri_g6`–`xri_g11` (early prototypes) — SHA-256-hashed `candidate_identity_key`.
3. `tools/registry/xri_g40`–`xri_g44` (current fixture-only reference contracts) — a caller-supplied 3-tuple `(group_key, display_location, candidate_identity)`, unhashed.

These are independent and not interoperable; each reimplements its own text-normalization helper (five to six independent copies across the tree, differing in case-sensitivity and punctuation handling).

## Identity lifecycle

`group_key` and `display_location` are supplied or derived early (source ingestion / review grouping) and persist, largely unchanged in name, through review, staging, adjudication, and (in the fixture contracts) audit reporting. `candidate_identity` / `stable_event_identity` / `stable_identity_key` are the terminal, most-specific identity strings actually used for approval/match/promotion decisions. `review_rank` is generated exactly once (as a sort position) and is explicitly, redundantly enforced as **display-only** at multiple layers: tagged at generation, checked at validation (`xri_g42`), checked again at handoff (`xri_g43`), and unit-tested (`tests/registry/test_xri_g41_fixture_only_parser_normalizer.py`). This milestone's own tests (`tests/registry/test_gps_identity_drift_detection.py`) add further coverage: reordering, duplicate-location, renamed-text, missing-row, stale-rank, and ranking-change scenarios all confirmed not to alter computed identity.

## Pipeline flow

See `docs/gps_pipeline_data_flow.md` for the full field-by-field trace of the diagnostic → adjudication → update → promotion chain. Summary: `stable_event_identity` is computed at the diagnostic stage, carried unchanged through adjudication, re-derived independently (not read from a persisted field) at the update stage for verification, and only converted to the registry-side `stable_identity_key`/`group_key` name at the moment a staged event is actually updated — the one point in the pipeline where registry identity is written into production staged data, gated behind `qa_pass`.

## Failure matrix (verified against committed code; Stage 6E)

| Failure condition | Verified enforcement point | Behavior |
|---|---|---|
| Identity mismatch (staged event's derived identity has no safe adjudicated counterpart) | `apply_gps_staged_feed_integration_update.py` | Counted in `unmatched_safe_identity_count`; must be 0 for `qa_pass`, else no staged-feed write occurs |
| Missing adjudication (adjudication summary absent required rows/fields) | `generate_gps_staged_feed_integration_adjudication_summary.py`, `validate_gps_manual_approvals.py` | Flagged in respective validation reports; `qa_pass`/readiness gated |
| Duplicate identity (adjudication summary) | `apply_gps_staged_feed_integration_update.py::build_safe_identity_map()` | Fails closed before any update is attempted |
| Duplicate identity (staged feed at apply time) | `apply_gps_staged_feed_integration_update.py` | Logged to `duplicate_identity_hits`, second occurrence skipped, counted toward `conflict_count` (must be 0) |
| Duplicate identity (reviewed approval artifact) | `build_gps_reviewed_approval_artifact.py`, `dry_run_gps_phase2e_promotion.py`, `validate_gps_phase2e_promotion_readiness.py` | `qa_pass`/`readiness_pass = False` |
| Orphan candidate (one staged identity fuzzy-matches multiple promoted keys with differing coordinates) | `generate_gps_staged_feed_integration_match_diagnostic.py::multi_key_conflicts` | Excluded from `selected_rows` |
| Missing staging row / required field | `build_gps_reviewed_approval_artifact.py::missing_required_rows`, `validate_gps_phase2e_promotion_readiness.py::missing_required_fields`, `dry_run_gps_phase2e_promotion.py::missing_required_metadata` | Row flagged, counted, excluded from the passing set |
| Unexpected promotion target (existing cache entry under the same key differs in coordinates from the proposed value) | `dry_run_gps_phase2e_promotion.py` — `existing_cache_coordinate_differs_from_reviewed_approval` | Recorded as a conflict, excluded from `proposed_updates`; **never silently overwritten**. Note: this is the closest existing mechanism to a general "unexpected promotion target" guard; there is no separate, more general check that a promotion target key itself must already be an allowlisted/expected key beyond the coordinate-conflict check — documented here as a scoping note, not a failure |
| Duplicate cache key at initial registry build | `build_gps_repository.py` | **Gap found:** first-writer-wins, silent skip, no log, no error — the only stage in the whole pipeline with no duplicate/conflict signal. Documented as a deferred risk (see below); not modified in this milestone since it is not an active violation of any currently-documented rule, only an absence of one |
| `review_rank` used as identity | `xri_g42`/`xri_g43` (active runtime exceptions), unit-tested | Raises `FixtureOnly*Error` |
| Forbidden final-state field present at handoff or audit-report layer | `xri_g43::_reject_forbidden_states`, `xri_g44::_reject_blocked_report_states` (independent, redundant checks — this milestone's `test_gps_pipeline_transition_coverage.py` proves both layers independently) | Raises `FixtureOnly*Error` |

## Approved invariants

1. Identity is never derived from `review_rank`, row position, or array index.
2. A stable identity's approval/handoff readiness never depends on `review_rank`'s value.
3. Duplicate stable identities are detected and fail closed at every stage from manual-approval staging onward (the one exception — `build_gps_repository.py`'s initial cache build — is a documented gap, not a violated invariant, since no write to a stable identity/approval decision happens at that stage).
4. Coordinate conflicts for an existing identity are recorded and excluded, never silently overwritten.
5. Final-state fields (`approved`, `promoted`, `published`, `geocoded`, etc.) cannot be smuggled through the fixture-only contracts at either the handoff or the audit-report layer.

## Repository boundaries respected by this milestone

No live-source ingestion, no workflow dispatch, no email, no WordPress/publishing/public-map/production action, no GPS promotion, no registry write, no geocoding occurred. No `data/**` file was modified. No `scripts/**` or `tools/**` implementation file was modified — this milestone is audit-plus-test only.

## Future extension guidance (Milestone 7 candidate scope — not authorized by this document)

- Consolidate the five-to-six independent `norm`/`normalize`/`slug`/`_clean_text` implementations in `scripts/**` into one shared function, without touching the intentionally separate xri_g6-11 and xri_g40-44 identity vocabularies.
- Add an explicit duplicate/conflict signal to `build_gps_repository.py`'s cache-key writer (currently silent first-writer-wins).
- Consider whether the unused `recommended_approve_rows`/`do_not_approve_rows` position-number arrays in `data/gps_manual_approval_review_findings.json` should be removed from the artifact (since nothing reads them) or wired in with an explicit stable-identity cross-check (since introducing them naively would reintroduce a review_rank-as-identity risk).
- Broader `scripts/**` test coverage remains deferred, as recorded in the Canonical Milestone 5 closure document; this milestone does not change that.

## Final verdict

**PASS**
