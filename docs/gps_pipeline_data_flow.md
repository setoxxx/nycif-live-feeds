# NYCIF GPS Pipeline: Data Flow (Adjudication / Diagnostic / Update / Promotion)

Status: audit document (Canonical Milestone 6, Stage 6D). Describes committed code behavior only; no implementation changes.

Scope: the four staged-feed-facing stages named in the Milestone 6 authorization —

- **diagnostic**: `scripts/generate_gps_staged_feed_integration_match_diagnostic.py`
- **adjudication**: `scripts/generate_gps_staged_feed_integration_adjudication_summary.py`
- **update**: `scripts/apply_gps_staged_feed_integration_update.py`
- **promotion**: `scripts/dry_run_gps_phase2e_promotion.py` and `scripts/validate_gps_phase2e_promotion_readiness.py`

Canonical Milestone 7-B.1 addition (snapshot contract hardening): diagnostic now writes `staged_feed_provenance`; adjudication copies it forward and records `diagnostic_artifact_sha256`; apply validates bound staged-feed SHA-256 and byte size **before** identity matching. See `docs/canonical_milestone_7b1_snapshot_contract_hardening.md`.

Canonical Milestone 7-B.2 addition (count contract): adjudication emits `safe_update_count_contract` bound to staged-feed and diagnostic provenance; apply validates count schema, bindings, and independently recomputed counts **after** snapshot preflight and **before** identity matching. See `docs/canonical_milestone_7b2_snapshot_bound_count_contract.md`.

## Verified fact: every stage consumes the same identity vocabulary

All four stages operate on the **same two identity names**: `stable_event_identity` (staged-event side, a 5-component pipe-joined natural key) and `stable_identity_key` / `promoted_cache_key` (registry side, a `group:<group_key>` or `display:<normalized text>` string). No stage introduces a third, incompatible identity name within this scope. The join between the two vocabularies is a fuzzy match (RapidFuzz thresholds + CEMSID overlap + borough compatibility), not string equality — this is inherent to the design (staged events don't carry a promoted cache key until after matching) and is documented, not treated as a defect.

## Stage: diagnostic (`generate_gps_staged_feed_integration_match_diagnostic.py`)

**Inputs (files read):**
- `data/nycif_staged_live_events.json` — staged events; fields read per row: `source_event_id`/`event_id`/`id`, `display_location`/`location`/`event_location`, `source_cemsid`/`cemsid`, `date`, `start_date_time`, plus site/facility text fields used for fuzzy matching.
- `data/location_cache.json` — registry cache; fields read: `stable_identity_key`/`group_key` (whichever is present), coordinates, promoted metadata.
- `data/gps_reviewed_approval_artifact.json` — promoted/reviewed rows (source of `promoted_cache_key` candidates).

**Computed identity:** `stable_event_identity(row)` per staged event (function defined here; copy-pasted, not imported, into `apply_gps_staged_feed_integration_update.py`).

**Matching logic:** `row_match()` — RapidFuzz site-name token-sort-ratio ≥ 96.0 or facility-name ratio ≥ 92.0, plus CEMSID-set overlap and borough compatibility. Produces `match_modes` (`source_cemsid` or a rapidfuzz mode).

**Outputs (fields written):**
- `data/gps_staged_feed_integration_match_diagnostic.json` — `selected_rows` (each carrying `stable_event_identity`, matched `promoted_cache_key`, `match_modes`), `multi_key_conflicts` (ambiguous multi-match identities, excluded from `selected_rows`), `conflict_identities`.

**Duplicate/conflict handling:** `seen_identities` drops repeat matches within one promoted key's candidates; `multi_key_conflicts` flags one `stable_event_identity` matching multiple `promoted_cache_key`s with differing coordinates and excludes those identities from selection.

## Stage: adjudication (`generate_gps_staged_feed_integration_adjudication_summary.py`)

**Inputs:** `data/gps_staged_feed_integration_match_diagnostic.json` (reads `selected_rows` produced by the diagnostic stage — **`stable_event_identity` and `promoted_cache_key` field names are consumed unchanged**, no renaming between diagnostic → adjudication).

**Computed check:** `selected_stable_event_identity_count == selected_candidate_count` (uniqueness assertion — `validated_conditions.selected_identities_are_unique`).

**Outputs:** `data/gps_staged_feed_integration_adjudication_summary.json` — `safe_update_ready_rows` (rows cleared for the update stage, each still carrying `stable_event_identity` and its matched `promoted_cache_key`), `qa_pass`, counts (`safe_update_contract_count`, `safe_update_ready_identity_count`, `excluded_no_safe_match_promoted_keys_count`, `conflicts`), and `safe_update_count_contract` (M7-B.2 snapshot-bound count metadata).

**Field-name continuity:** `stable_event_identity` flows diagnostic → adjudication unchanged; this is the exact field the **update** stage below re-keys against.

## Stage: update (`apply_gps_staged_feed_integration_update.py`)

**Inputs:**
- `data/gps_staged_feed_integration_adjudication_summary.json` — reads `safe_update_ready_rows`, builds `safe_by_identity = {stable_event_identity: row}` via `build_safe_identity_map()`.
- `data/nycif_staged_live_events.json` — the actual staged events to be updated; for each, `stable_event_identity(event_row)` is **re-derived independently** (not read from a persisted field — the staged event JSON does not carry a `stable_event_identity` field before this stage runs) using the identical function definition copy-pasted from the diagnostic stage.

**Snapshot preflight (M7-B.1):** before identity matching, apply compares `staged_feed_provenance.staged_feed.sha256` and `byte_size` from the adjudication summary against the exact current staged-feed bytes. Stale or legacy contracts fail closed with `failure_type` set and zero mutations.

**Count-contract preflight (M7-B.2):** after snapshot preflight, apply validates `safe_update_count_contract` schema, provenance bindings, and independently recomputed counts. Legacy artifacts without a count contract fail with `legacy_contract_missing_count_contract`. All expected apply counts come from the contract, not source constants.

**Duplicate/conflict handling (fail-closed, in order):**
1. `build_safe_identity_map()` — if two different-content rows in the adjudication summary share one `stable_event_identity`, marks `duplicate_safe_stable_event_identity_in_adjudication_summary` and the map is rejected as non-unique before any update is attempted.
2. While iterating staged events — if the same re-derived `identity` is seen twice, it is logged to `duplicate_identity_hits` (reason `staged_feed_contains_duplicate_safe_stable_event_identity`) and the second occurrence is **skipped**, not double-applied; this counts toward `conflict_count`, which must be exactly 0 for `qa_pass`.

**Outputs (fields written onto the staged event row itself, only on a matched + safe identity):**
```
event_row["stable_identity_key"] = promoted_cache_key
event_row["group_key"] = promoted_cache_key.removeprefix("group:")
event_row["matched_promoted_cache_keys"] = [...]
event_row["gps_integration_phase"] = ...
```
This is the **only point in the entire scripts/ pipeline where the registry-side identity (`promoted_cache_key` → `stable_identity_key`/`group_key`) is written into a staged production file** (`data/nycif_staged_live_events.json`), and it only happens when `qa_pass` is true for the whole run (all counts as expected: `updated_staged_event_count == safe_update_ready_identity_count`, `unmatched_safe_identity_count == 0`, `skipped_count == 0`, `conflict_count == 0`).

**Report output:** `data/gps_staged_feed_integration_update_report.json` — carries forward the same counts plus `duplicate_identity_hits`.

## Stage: promotion (`dry_run_gps_phase2e_promotion.py`, `validate_gps_phase2e_promotion_readiness.py`)

**Inputs:**
- `data/gps_reviewed_approval_artifact.json` — `approved_rows`, each carrying `stable_identity_key` (this is the field name from the **Phase 2D manual-approval chain**, i.e. `build_gps_manual_approval_staging.py`'s output — a **separate lineage** from the diagnostic/adjudication/update chain above, which operates on `stable_event_identity`/staged-feed data. Both lineages converge only in that the update stage writes `stable_identity_key` onto staged events using values sourced from `gps_reviewed_approval_artifact.json` via the diagnostic stage's promoted-row lookup).
- `data/location_cache.json` — read via `cache_entries_by_key()`, which normalizes the lookup key as `value.get("stable_identity_key") or value.get("group_key") or <raw dict key>` — a compatibility fallback chain, since `build_gps_repository.py` (the cache's original writer) never writes a field literally named `stable_identity_key`.

**Computed checks:**
- `duplicate_stable_keys` (via `Counter` on `approved_rows`) — must be empty.
- Coordinate-conflict check: if `stable_identity_key` already exists in the cache with a different lat/lng than the newly reviewed value, flagged as `existing_cache_coordinate_differs_from_reviewed_approval` and **excluded from `proposed_updates`** (never silently overwritten).
- `validate_gps_phase2e_promotion_readiness.py`: `duplicate_approved_keys` and `overlap_with_excluded` (approved ∩ excluded keys) — both must be empty for `readiness_pass`.

**Outputs:** dry-run proposed-update reports only; per repository convention and this milestone's restrictions, **no promotion write occurs** and none was performed as part of this audit.

## Field-name continuity summary (diagnostic → adjudication → update)

| Field | diagnostic | adjudication | update |
|---|---|---|---|
| `stable_event_identity` | computed, attached to `selected_rows` | read from `selected_rows`, re-emitted on `safe_update_ready_rows` | re-derived independently from the staged event row; looked up against `safe_by_identity` |
| `promoted_cache_key` | computed from fuzzy match against `gps_reviewed_approval_artifact.json` | carried through on `safe_update_ready_rows` | written onto the staged event as `stable_identity_key` |
| `stable_identity_key` (registry lineage, from Phase 2D) | consumed as the source of `promoted_cache_key` candidates | not directly referenced | written onto staged events (post-match); also the field `dry_run_gps_phase2e_promotion.py` and `validate_gps_phase2e_promotion_readiness.py` operate on |

No stage in this four-stage scope silently drops or renames an identity field without a corresponding, greppable field-name change documented above; the one true renaming/conversion point is `promoted_cache_key` → `stable_identity_key`/`group_key`, which happens explicitly in the update stage's write-back logic, not implicitly.
