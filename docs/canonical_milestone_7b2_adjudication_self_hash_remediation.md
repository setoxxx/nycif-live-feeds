# Canonical Milestone 7-B.2: Adjudication Self-Hash Remediation

Milestone: Canonical Milestone 7-B.2 remediation (self-hash lifecycle)
Branch: `canonical-milestone-7b2-adjudication-self-hash-remediation`
Baseline: `8b75524c9ae552435b98532e1c4adf0728aba39c` (M7-B.2 merge on `main`)
Incident observed on: `d1b465904e31fd7ff29e77dbe7ba80798db21f72`

## Validation incident

Fresh M7-B.2 contract regeneration and dry-run validation passed snapshot provenance and count-contract arithmetic, but **dry-run apply failed**:

| Check | Result |
|---|---|
| Snapshot provenance | PASS |
| Fresh diagnostic | PASS |
| Count contract derivation | PASS (155 / 20 / 0) |
| Dry-run apply | **FAIL** |
| `failure_type` | `count_contract_provenance_mismatch` (now `adjudication_artifact_hash_mismatch`) |
| Reason | Embedded `adjudication_artifact_sha256` did not match saved adjudication summary bytes |

## Root cause

Two defects in the M7-B.2 producer lifecycle:

1. **Mutation after hash finalization** — `finalize_count_contract_adjudication_hash()` ran before `qa_pass`, `recommended_next_action`, and `validated_conditions` were added to the summary. The saved artifact included fields not covered by the embedded hash.

2. **Serialization drift** — early hash computation used compact JSON while `save_json` writes `indent=2`, `sort_keys=True`, `ensure_ascii=False`, trailing newline. Float values also required JSON round-trip normalization before hashing so producer and reload paths match.

## Why raw self-embedded file SHA-256 is impossible

A JSON file cannot contain the SHA-256 of its own final on-disk bytes unless the hash field is excluded or stored externally. Embedding the digest inside the payload changes the bytes being hashed. M7-B.2 therefore uses a **canonical object hash** with the self-hash field normalized to `null`.

## Canonical self-hash contract (`gps-adjudication-self-hash-v1`)

Shared helpers live in `scripts/gps_count_contract.py`.

### Algorithm

1. Deep-copy the complete adjudication summary object.
2. Set `safe_update_count_contract.adjudication_artifact_sha256` to `null`.
3. Serialize with repository JSON rules:
   - UTF-8
   - `indent=2`
   - `ensure_ascii=False`
   - `sort_keys=True`
   - final newline (`\n`)
4. SHA-256 the serialized bytes (lowercase hex digest).
5. Store digest in `safe_update_count_contract.adjudication_artifact_sha256`.
6. Record schema in `safe_update_count_contract.derivation.adjudication_artifact_hash_schema`.
7. Save the complete object without mutating hash-covered fields afterward.
8. Validator repeats steps 1–4 on the loaded object and compares digests.

### Included / excluded

| Item | Policy |
|---|---|
| All summary fields present at finalization | **Included** |
| `adjudication_artifact_sha256` | **Normalized to null** before hashing |
| File path | **Not included** (object hash only) |
| Timestamps (`generated_at_utc`, etc.) | **Included** (informational, frozen before finalization) |
| Post-finalization mutation | **Forbidden** |

### Diagnostic hash distinction

`diagnostic_artifact_sha256` remains **exact-byte SHA-256** of the diagnostic file on disk. That hash is stored in the downstream adjudication artifact, not inside the diagnostic itself, so raw file hashing remains valid. Only the adjudication summary uses self-hash semantics.

## Hash lifecycle inventory

| Symbol / field | Path | Role | Hash type |
|---|---|---|---|
| `sha256_file` | `scripts/gps_snapshot_provenance.py` | Byte-exact file hash | Raw bytes |
| `diagnostic_artifact_sha256` | adjudication summary + count contract | Diagnostic provenance | Raw file bytes |
| `adjudication_artifact_sha256` | count contract | Self-integrity | Canonical object hash (field nulled) |
| `canonical_json_bytes` | `scripts/gps_count_contract.py` | Shared serializer | N/A |
| `canonicalize_adjudication_summary` | same | JSON round-trip normalization | N/A |
| `adjudication_artifact_hash_payload` | same | Null self-hash field | N/A |
| `compute_adjudication_artifact_sha256` | same | Producer + validator digest | Object |
| `finalize_count_contract_adjudication_hash` | same | Producer finalization (mutates) | Object |
| `validate_adjudication_artifact_sha256` | same | Apply/count validator | Object |
| `validate_count_contract_bindings` | same | Calls self-hash validator | Consumer |
| `save_json` / `load_json` | producer + apply scripts | Persist/reload | Must match canonical serializer |

## Producer lifecycle (repaired)

`scripts/generate_gps_staged_feed_integration_adjudication_summary.py`:

1. Load diagnostic.
2. Build complete summary including `qa_pass`, `recommended_next_action`, `validated_conditions`, and count contract.
3. `canonicalize_adjudication_summary(summary)` — JSON round-trip.
4. `finalize_count_contract_adjudication_hash(summary)` — single finalization.
5. `validate_count_contract_for_apply(summary)` — in-memory gate.
6. `save_json` — no further hash-covered mutations.
7. Reload saved file and re-validate; nonzero exit on failure.

## Validator lifecycle (repaired)

`scripts/apply_gps_staged_feed_integration_update.py`:

1. Snapshot provenance preflight (M7-B.1).
2. Count-contract schema + bindings + internal counts (M7-B.2).
3. Canonical adjudication self-hash via shared helper (not raw file SHA-256).
4. Identity matching only after all prefights pass.
5. Success report exposes `adjudication_artifact_hash_preflight_passed` and `snapshot_contract_preflight_passed`.

## Failure taxonomy

| `failure_type` | Meaning |
|---|---|
| `missing_adjudication_artifact_hash` | Schema or digest field absent |
| `unsupported_adjudication_artifact_hash_schema` | Unknown schema version |
| `malformed_adjudication_artifact_hash` | Non-lowercase or non-64-hex digest |
| `adjudication_artifact_hash_mismatch` | Recomputed canonical digest differs |
| `adjudication_artifact_finalization_failed` | Producer final in-memory validation failed |

Legacy outer category `count_contract_provenance_mismatch` is preserved for staged-feed and diagnostic binding failures only.

## Regression tests

`tests/registry/test_canonical_milestone_7b2_adjudication_self_hash_remediation.py` covers:

- old vs new finalization order
- canonical hash determinism and non-mutation
- covered-field tampering
- excluded-field normalization
- serialization stability
- hash schema rejection
- producer save/reload/validate
- apply preflight and tamper fail-closed
- diagnostic exact-byte hash non-regression

## Fresh-chain validation evidence

Isolated evidence directory:

`/tmp/nycif-m7b2-self-hash-remediation-validation/`

Report: `fresh_chain_validation_report.json`

Verified on current snapshot:

- 155 safe identities
- 20 no-safe-match promoted keys
- 0 conflicts
- self-hash validates after save/reload
- apply prefights pass
- self-hash tamper fails before identity matching with zero repo mutations

## Protected boundaries

Not modified by this remediation:

- `data/nycif_staged_live_events.json`
- `data/location_cache.json`
- staged manifests
- tracked production diagnostic/adjudication/apply artifacts
- public-map outputs

No geocoding, promotion, publication, or M7-C work.

## Residual risks

- Artifacts produced before this remediation lack `gps-adjudication-self-hash-v1` and require regeneration.
- Producer must never mutate hash-covered fields after finalization (including `validated_conditions`).
- Any future serializer change must update `canonical_json_bytes` and both producer and validator together.

## Final verdict

**PASS** — canonical self-hash contract implemented, producer/validator aligned, fresh-chain validation passes, full test suite passes. Independent review and separate merge authorization required before landing on `main`.

M7-C readiness: **NOT READY** until this remediation is reviewed, merged, and fresh validation passes on `main`.
