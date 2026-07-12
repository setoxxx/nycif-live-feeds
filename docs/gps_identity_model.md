# NYCIF GPS Pipeline: Identity Model

Status: audit document (Canonical Milestone 6, Stage 6B). Describes the identity model **as it currently exists in the committed code**, including inconsistencies. This document does not itself change any implementation.

## Summary finding

The repository currently contains **three separate, unconnected identity systems**, each with its own independently reimplemented normalization logic. They are not interchangeable, and no adapter/migration path connects them:

1. **`scripts/` live pipeline** — an evolving family of composite string keys: raw cache keys (`build_gps_repository.py`), `group_key` (`build_gps_review_groups.py` onward), `stable_identity_key` (`build_gps_manual_approval_staging.py` onward), and `stable_event_identity` (adjudication/staged-feed stage).
2. **`tools/registry/xri_g6`–`xri_g11`** (early prototypes) — a SHA-256-hashed `candidate_identity_key`.
3. **`tools/registry/xri_g40`–`xri_g44`** (current fixture-only reference contracts) — a caller-supplied 3-tuple `(group_key, display_location, candidate_identity)`, no hashing.

Each of the three systems reimplements its own normalization helper (`norm()` in two scripts, `normalize()` in two more, `norm_text()` in a third, `_clean_text()` in the fixture contracts, `slug()` in xri_g7) — five to six independent implementations, not a shared library function. They differ in case-sensitivity and punctuation-handling (see "Normalization comparison" below). This is documented here as a finding, not silently resolved.

## 1. Complete identity flow (scripts/ live pipeline)

```
build_gps_repository.py
  -> candidate_keys(): {event_id, cemsid, location, text_date_location} composite keys
  -> written as raw dict keys into data/location_cache.json (first-writer-wins; no key_type field named "identity")

build_gps_review_groups.py
  -> group_key(row) = f"{norm(borough)}|{norm(location)}"   (borough+location only, source_event_id-agnostic)
  -> gps_review_location_groups.json { "group_key": ... }

build_gps_geocoding_proposals.py
  -> group_key passthrough, unchanged field name
  -> gps_review_geocoding_proposals.json

build_gps_geocoding_filled_proposals.py
  -> group_key passthrough
  -> additionally builds transient proposal_keys()/reference_keys() sets for fuzzy joining
     against manual/Parks reference data (not persisted as identity)

build_gps_manual_approval_queue.py
  -> group_key passthrough
  -> gps_manual_approval_queue.json

build_gps_manual_review_sheet.py
  -> group_key passthrough (true identity)
  -> ALSO introduces review_rank = enumerate(sorted_by_priority_score) + 1
     (a display-order position number, NOT identity — see Section 3)
  -> gps_manual_approval_review_sheet.{json,csv}   (review_rank is the first CSV column)

build_gps_manual_approval_staging.py
  -> stable_key(row) = f"group:{group_key}" if group_key else f"display:{norm_text(display_location)}"
  -> persisted field name from here forward: stable_identity_key
  -> matches manual review findings (gps_manual_approval_review_findings.json) by
     norm_text(display_location) only — review_rank from findings is carried through
     as informational (review_rank_original_from_findings) but never used as a join key
  -> gps_manual_approval_staging_candidates.json

build_gps_reviewed_approval_artifact.py
  -> stable_identity_key passthrough (unchanged field name)
  -> checks approved_identity_keys ∩ excluded_identity_keys == {} (duplicate/conflict detector)
  -> gps_reviewed_approval_artifact.json

validate_gps_manual_approvals.py
  -> validates the safety-field contract (status/promotion_allowed/coordinates/source/
     confidence/reviewer/timestamp/reason) using group_key/display_location for error
     messages only; does not itself perform identity-uniqueness validation

generate_gps_staged_feed_integration_match_diagnostic.py /
generate_gps_staged_feed_integration_adjudication_summary.py
  -> stable_event_identity(row) = "|".join([
         source_event_id or event_id or id,
         normalize(display_location),
         ",".join(sorted(source_cemsid set)),
         date,
         start_date_time,
     ])
     (a 5-component pipe-joined natural key over the STAGED EVENT side)
  -> registry-side identity here is promoted_cache_key, taken from
     stable_identity_key on promoted/reviewed rows
  -> the two are joined not by string equality but by a FUZZY MATCH
     (row_match(): RapidFuzz site/facility token-sort-ratio thresholds
     96.0 / 92.0, plus CEMSID-set overlap and borough compatibility)
  -> multi_key_conflicts: a stable_event_identity matching multiple different
     promoted_cache_keys with differing coordinates is detected and excluded
     from selected_rows
  -> seen_identities set drops repeat matches within one promoted key's candidates
  -> adjudication summary asserts selected_stable_event_identity_count ==
     selected_candidate_count (uniqueness check)

apply_gps_staged_feed_integration_update.py
  -> re-derives stable_event_identity(event_row) per staged-feed row, looks it
     up against the adjudication summary's safe_update_ready_rows
  -> build_safe_identity_map() fails closed if two different-content adjudication
     rows share the same stable_event_identity (duplicate_safe_stable_event_identity_in_adjudication_summary)
  -> at apply time, a repeated identity within the staged feed itself is logged
     to duplicate_identity_hits and SKIPPED (not double-applied); counts toward
     conflict_count (must be 0 for qa_pass)
  -> on match, WRITES the registry-side identity back onto the staged event:
     event_row["stable_identity_key"] = promoted_cache_key
     event_row["group_key"] = promoted_cache_key.removeprefix("group:")
  -> this is the only script that mutates data/nycif_staged_live_events.json,
     gated behind qa_pass

dry_run_gps_phase2e_promotion.py
  -> stable_identity_key from gps_reviewed_approval_artifact.json
  -> cache_entries_by_key() falls back through
     value.get("stable_identity_key") or value.get("group_key") or <raw dict key>
     — a compatibility shim, since build_gps_repository.py's cache never actually
     writes a field literally named "stable_identity_key"
  -> duplicate_stable_keys (Counter) and coordinate-conflict detection
     (existing_cache_coordinate_differs_from_reviewed_approval) both required
     empty for qa_pass; conflicting rows are excluded, never silently overwritten

validate_gps_phase2e_promotion_readiness.py
  -> stable_identity_key required non-empty; duplicate_approved_keys and
     overlap_with_excluded (approved ∩ excluded) both required empty
```

## 2. Identity ownership

| Identity concept | Owning/originating script | Consumed by |
|---|---|---|
| Raw cache composite keys (`event_id:`, `cemsid:`, `location:`, `text_date_location:`) | `build_gps_repository.py` | `dry_run_gps_phase2e_promotion.py` (fallback lookup only) |
| `group_key` | `build_gps_review_groups.py` | Every script through `build_gps_reviewed_approval_artifact.py`; re-derived into `stable_identity_key`/`group_key` on the staged feed by `apply_gps_staged_feed_integration_update.py` |
| `stable_identity_key` | `build_gps_manual_approval_staging.py` | `build_gps_reviewed_approval_artifact.py`, `dry_run_gps_phase2e_promotion.py`, `validate_gps_phase2e_promotion_readiness.py`; written back onto staged events by `apply_gps_staged_feed_integration_update.py` (as `promoted_cache_key`) |
| `stable_event_identity` | `generate_gps_staged_feed_integration_match_diagnostic.py` (function copy-pasted, not shared, into `apply_gps_staged_feed_integration_update.py`) | `generate_gps_staged_feed_integration_adjudication_summary.py`, `apply_gps_staged_feed_integration_update.py` |
| `candidate_identity_key` (SHA-256) | `tools/registry/xri_g7_fixture_candidate_normalizer.py` | `xri_g8`–`xri_g11` (unrelated to the scripts/ pipeline above) |
| `(group_key, display_location, candidate_identity)` tuple | `tools/registry/xri_g40_fixture_only_source_ingestion_scaffold.py` (caller-supplied, not derived) | `xri_g41`–`xri_g44` (unrelated to both other systems) |

## 3. `review_rank`: explicit limitations

`review_rank` is created exactly once, in `build_gps_manual_approval_review_sheet.py`, as a **1-based position in a priority-sorted list** (`enumerate(queue) + 1` after sorting by `priority_score` descending). It is **not derived from any stable field** and can change between regenerations if priority scores tie differently or rows are added/removed.

Every later stage treats it as display-only:

- `build_gps_manual_approval_staging.py` docstring states explicitly: *"It uses stable identity matching. Rank-only findings are not trusted because review_rank can shift when the review sheet regenerates."* Matching against manual-review findings is done by normalized `display_location` text, never by `review_rank`.
- `tools/registry/xri_g40_fixture_only_source_ingestion_scaffold.py` and `xri_g41_fixture_only_parser_normalizer.py` tag any incoming `review_rank` with `"review_rank_identity_use": "forbidden_display_only"`.
- `xri_g42_fixture_only_validation_execution.py` and `xri_g43_fixture_only_manual_review_handoff.py` **actively raise an error at runtime** if `review_rank` appears without that tag.
- `tests/registry/test_xri_g41_fixture_only_parser_normalizer.py::test_review_rank_is_not_identity` asserts that changing `review_rank` from 1 to 99 does not change `candidate_identity`.
- The formal prohibition is written in `docs/xri-g41-non-production-fixture-only-parser-normalizer-gate-contract.md`: *"Stable identity must not use review_rank, row position, array index, coordinates, geometry, public runtime targets, or production targets."*

**One latent, currently-inert soft spot:** `data/gps_manual_approval_review_findings.json` stores `recommended_approve_rows` / `do_not_approve_rows` as literal arrays of position numbers (the same values as `review_rank`). `build_gps_manual_approval_staging.py` never reads these two arrays — it only consumes `corrections_needed`, matched by normalized `display_location`. This means a position-based "approval list" exists in a committed data artifact but is deliberately bypassed by the code that consumes that artifact. It is harmless as long as nothing is ever changed to read those two arrays; it is flagged here as a risk to watch, not a currently-active bug.

## 4. Normalization comparison

| Function | File | Case-folds? | Strips punctuation? | Notes |
|---|---|---|---|---|
| `norm()` | `build_gps_repository.py` | yes | yes (`[^a-z0-9]+` → space) | |
| `norm()` | `build_gps_review_groups.py` | yes | yes (same regex, independently redefined) | |
| `norm()` | `build_gps_geocoding_filled_proposals.py` | yes | yes (same regex, independently redefined again) | |
| `norm_text()` | `build_gps_manual_approval_staging.py` | yes | yes, plus `&` → ` and ` | |
| `normalize()` | `generate_gps_staged_feed_integration_match_diagnostic.py` / `apply_gps_staged_feed_integration_update.py` | yes | yes, plus `&` → ` and ` (copy-pasted between the two files, not shared) | |
| `_clean_text()` | `tools/registry/xri_g41_fixture_only_parser_normalizer.py` | **no** | **no** — whitespace-collapse only | Materially weaker than every scripts/ normalization; a value differing only in case or punctuation is treated as a **different** identity component here but the **same** component under every scripts/ `norm`/`normalize` |
| `slug()` | `tools/registry/xri_g7_fixture_candidate_normalizer.py` | yes | yes (`[^a-z0-9]+` → `-`) | Used only for hashing input, not persisted as identity itself |

## 5. Failure cases (existing duplicate/conflict/mismatch detection, by stage)

| Stage | Detection | Behavior on detection |
|---|---|---|
| `build_gps_repository.py` | Duplicate cache key | Silent skip (first-writer-wins); **no error, no log** |
| `build_gps_reviewed_approval_artifact.py` | `approved_identity_keys ∩ excluded_identity_keys` non-empty | `qa_pass = False` |
| `apply_gps_staged_feed_integration_update.py` | Duplicate `stable_event_identity` within adjudication summary | Fails closed before any update is attempted |
| `apply_gps_staged_feed_integration_update.py` | Duplicate `stable_event_identity` encountered while applying | Logged to `duplicate_identity_hits`, second occurrence skipped, counted in `conflict_count` (must be 0) |
| `generate_gps_staged_feed_integration_match_diagnostic.py` | One `stable_event_identity` fuzzy-matches multiple `promoted_cache_key`s with differing coordinates | Excluded from `selected_rows`, recorded in `multi_key_conflicts` |
| `dry_run_gps_phase2e_promotion.py` | Duplicate `stable_identity_key` in approved rows | `qa_pass = False` |
| `dry_run_gps_phase2e_promotion.py` | Existing cache coordinate differs from newly reviewed coordinate for the same key | Recorded as conflict, excluded from `proposed_updates` (never silently overwritten) |
| `validate_gps_phase2e_promotion_readiness.py` | Duplicate approved keys, or approved∩excluded overlap | `readiness_pass = False` |

The one stage with **no** duplicate/error handling at all is `build_gps_repository.py`'s cache-key writer — a duplicate key is silently ignored rather than flagged. This is noted as a finding for the risk register (Section 6G / closure document), not changed by this audit.

## 6. Prohibited transient identifiers

The following must never be used as identity, per the explicit rules found in code/docs cited above:

- `review_rank` (position in a sorted list; changes between regenerations)
- Row position / array index generally
- Raw coordinates (`lat`/`lng`) or geometry — these describe *where* an identified event is, not *what* it is
- Any field marked `public_runtime_ready` / `production_ready` / `promoted` / `published` / `approved` / `geocoded` (these are pipeline **state** flags checked by `xri_g43`/`xri_g44`'s forbidden-state list, not identity components — conflating state with identity is a distinct hazard from the review_rank hazard, called out here for completeness)

## 7. Recommendation (not implemented by this audit)

This document intentionally makes no code changes. The three-identity-system split and the five-to-six independent normalization reimplementations are the primary structural risk this audit surfaces; a future milestone could consider consolidating scripts/'s `norm`/`normalize`/`norm_text` into one shared function (they are already near-identical) without touching the intentionally separate xri_g6-11 and xri_g40-44 fixture-only identity vocabularies, which serve different, narrower purposes.
