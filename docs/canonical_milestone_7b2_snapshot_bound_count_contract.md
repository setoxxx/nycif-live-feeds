# Canonical Milestone 7-B.2: Snapshot-Bound Count Contract

Milestone: Canonical Milestone 7-B.2
Branch: `canonical-milestone-7b2-snapshot-bound-count-contract`
Verified baseline: `d451003c5d5af7ca5f70134a99f905cb764f9700` (M7-B.1 on `main`)
Validation baseline: `cf3481ad75bbdd67a30ffc1cf053a2e3cdeca723` (current `main` at implementation)

## Incident and validation background

M7-B.1 snapshot provenance hardening merged successfully. Fresh validation proved:

- current staged-feed SHA-256 binding works
- diagnostic → adjudication → apply provenance chain passes
- stale contracts fail before identity matching
- legacy contracts fail closed
- production artifacts remain unchanged
- all tests pass

However, the **fresh contract still failed** because runtime gates retained stale hard-coded count assumptions:

| Field | Historical constant | Current snapshot-derived |
|---|---|---|
| safe identities | 204 | 155 |
| conflicts | 0 | 0 |
| no-safe-match promoted keys | 20 | 20 |
| staged-feed window start | 2026-06-30 (expired identities) | 2026-07-07 |

The 49 missing identities belong to the expired 2026-06-30 through 2026-07-06 window.

### Why 204 became stale

The content snapshot is current and valid, but the count contract remained tied to an older adjudication snapshot produced when the staged feed still contained 204 in-window identities. M7-B.1 correctly blocked stale snapshot bytes; the remaining failure was count gates comparing live artifact contents against historical constants.

### Why hard-coding 155 would also be wrong

Replacing `204` with `155` in source constants would merely encode today's snapshot size. The next staged-feed advance would recreate the same class of failure. Counts must be **derived**, **bound to provenance**, and **internally reconciled** — not swapped as literals.

## Count-constant inventory

| Location | Value / pattern | Class | Disposition |
|---|---|---|---|
| `scripts/generate_gps_staged_feed_integration_adjudication_summary.py` | `EXPECTED_SAFE_UPDATE_READY_COUNT = 204` | C (runtime gate) | **Removed** — replaced by `safe_update_count_contract` |
| same | `EXPECTED_NO_SAFE_MATCH_PROMOTED_KEY_COUNT = 20` | C | **Removed** — contract-bound |
| `scripts/apply_gps_staged_feed_integration_update.py` | same constants + `_is_204` validated_conditions | C | **Removed** — contract validation after snapshot preflight |
| `scripts/generate_gps_staged_feed_integration_match_diagnostic.py` | `EXPECTED_STAGED_MATCHES = 430` | F (dry-run legacy target) | **Preserved** — informational dry-run baseline, not apply gate |
| `data/gps_staged_feed_integration_*` artifacts | 204 counts | A (historical evidence) | **Preserved** — not modified |
| `tests/registry/test_canonical_milestone_7b1_snapshot_contract_hardening.py` | 204 fixtures | B/D | **Preserved** as historical incident fixtures; helpers extended with count contract |
| `docs/canonical_milestone_7b1_snapshot_contract_hardening.md` | 204 incident facts | A/E | **Preserved** — historical context |
| `scripts/validate_gps_phase2e_promotion_readiness.py` | `EXPECTED_APPROVED_COUNT = 25` | C (Phase 2E only) | **Preserved** — unrelated GPS promotion gate |
| `scripts/dry_run_gps_phase2e_promotion.py` | `EXPECTED_APPROVED_COUNT = 25` | C (Phase 2E only) | **Preserved** |
| `data/location_cache.json` / map feeds | literal `204` in street addresses | unrelated | **Untouched** |
| `major-feed-metadata.json` | `"low": 204` crowd score | unrelated | **Untouched** |

Classification key: A=historical evidence, B=fixture-only, C=active runtime gate, D=test oracle, E=documentation, F=migration/legacy compatibility.

## Count-contract schema (`gps-safe-update-count-contract-v1`)

Embedded in adjudication summary as `safe_update_count_contract`:

```json
{
  "schema_version": "gps-safe-update-count-contract-v1",
  "staged_feed_sha256": "<lowercase hex>",
  "staged_feed_byte_size": 123,
  "diagnostic_artifact_sha256": "<lowercase hex>",
  "adjudication_artifact_sha256": "<self-hash excluding this field>",
  "counts": {
    "selected_identity_count": 155,
    "safe_update_ready_identity_count": 155,
    "safe_update_ready_row_count": 155,
    "no_safe_match_promoted_key_count": 20,
    "multi_key_conflict_count": 0,
    "adjudication_row_count": 175,
    "adjudication_category_total": 20
  },
  "derivation": {
    "producer_script": "scripts/generate_gps_staged_feed_integration_adjudication_summary.py",
    "generated_at_utc": "2026-07-13T20:00:00+00:00",
    "rules_version": "gps-safe-update-count-rules-v1",
    "provenance_schema_version": "gps-staged-feed-provenance-v1"
  }
}
```

Shared helper: `scripts/gps_count_contract.py`

## Derivation rules

1. All counts derive from in-memory diagnostic/adjudication structures at producer time.
2. `selected_identity_count` and `safe_update_ready_identity_count` equal the number of unique `stable_event_identity` values in `safe_update_ready_rows`.
3. `safe_update_ready_row_count` equals `len(safe_update_ready_rows)`.
4. `no_safe_match_promoted_key_count` equals diagnostic unmatched promoted key count.
5. `adjudication_row_count` = `safe_update_ready_identity_count + no_safe_match_promoted_key_count`.
6. `adjudication_category_total` = sum of `adjudication_count_by_type` values.
7. `staged_feed_sha256` / `byte_size` copy from bound `staged_feed_provenance`.
8. `diagnostic_artifact_sha256` equals on-disk diagnostic file hash at adjudication time.
9. `adjudication_artifact_sha256` equals canonical self-hash of the full adjudication payload with this field nulled.
10. `generated_at_utc` is informational only.

## Arithmetic invariants

Apply independently recomputes and fail-closed validates:

- unique safe identity count equals contract counts
- safe row count equals contract counts
- no duplicate `stable_event_identity` in safe list
- `multi_key_conflict_count` must be 0
- adjudication row arithmetic reconciles
- category totals reconcile
- contract staged-feed hash matches adjudication provenance
- contract diagnostic hash matches adjudication summary field
- contract adjudication self-hash matches recomputation

Count validation runs **only after** snapshot provenance preflight passes.

## Producer behavior

`scripts/generate_gps_staged_feed_integration_adjudication_summary.py`:

- builds `safe_update_count_contract` from actual rows
- rejects duplicate safe identities at contract build
- rejects non-zero conflicts
- never imports historical 204/20 as runtime truth
- sets `qa_pass` from provenance + internal count consistency + safety flags
- emits dynamic `recommended_next_action` with derived counts

## Apply behavior

`scripts/apply_gps_staged_feed_integration_update.py`:

1. adjudication `qa_pass` gate
2. snapshot provenance preflight (M7-B.1)
3. count-contract load, schema, binding, and internal validation (M7-B.2)
4. identity matching and update using **contract counts**, not constants

## Legacy behavior

Provenance-valid adjudication artifacts **without** `safe_update_count_contract` fail closed:

```
failure_type: legacy_contract_missing_count_contract
required_next_step: Regenerate diagnostic and adjudication artifacts using the current M7-B.2 producer.
```

No silent migration. No runtime inference from legacy summary count fields.

## Failure taxonomy

| failure_type | Meaning |
|---|---|
| `legacy_contract_missing_count_contract` | No versioned count contract present |
| `missing_count_contract` | Contract key absent or null |
| `unsupported_count_contract_schema` | Bad/missing schema, rules_version, or count types |
| `count_contract_provenance_mismatch` | Staged-feed, diagnostic, or adjudication hash mismatch |
| `count_contract_internal_inconsistency` | Summary fields do not reconcile with rows/categories |
| `count_contract_duplicate_identity` | Duplicate safe identities |
| `count_contract_conflict_detected` | Non-zero multi-key conflicts |
| `count_contract_actual_count_mismatch` | Recomputed counts differ from contract |

(M7-B.1 snapshot failures remain unchanged: `stale_staged_feed_contract`, `legacy_contract_missing_snapshot_hash`.)

## July 13 regression evidence

Tests in `tests/registry/test_canonical_milestone_7b2_snapshot_bound_count_contract.py` prove:

- old 204-bound snapshot contract → `stale_staged_feed_contract` at snapshot preflight
- legacy contract without count schema → `legacy_contract_missing_count_contract`
- fresh 155-bound contract → snapshot + count preflight pass; 155 accepted because derived/bound
- tampering contract count to 204 while rows remain 155 → `count_contract_actual_count_mismatch`
- no production writes in tests

This is **not** "replace 204 with 155."

## Protected boundaries

Not modified:

- `data/nycif_staged_live_events.json`
- `data/location_cache.json`
- `data/staged_live_manifest.json`
- `data/previous_staged_live_events_snapshot.json`
- public-map outputs, production feeds, reviewed approval artifacts, deployment files

Not performed: geocode, promote, publish, auto-approve, M7-C work.

## Residual risks

- Diagnostic dry-run target (`430`) remains informational; operators must regenerate diagnostic/adjudication after staged-feed advances.
- Count contract self-hash depends on canonical JSON serialization; whitespace-only on-disk changes alter adjudication self-hash by design.
- Phase 2E promotion scripts retain their own unrelated count gates (`25` approved rows).

## M7-C status

**NOT READY.** Duplicate-key enforcement, positional-array changes, APIs, website/mobile runtime remain unauthorized.

## Future synchronization implications

When APIs, website, or mobile surfaces expose GPS integration status, they must read **bound count-contract metadata** from adjudication/update reports — not hard-coded safe counts. Any external dashboard should display `safe_update_count_contract.counts` and provenance hashes together.

## Final verdict

Implementation complete on branch `canonical-milestone-7b2-snapshot-bound-count-contract`. Independent review and separate merge authorization required before production artifact regeneration.
