# Canonical Milestone 7-B.1: Snapshot Contract Hardening

Milestone: Canonical Milestone 7-B.1
Branch: `canonical-milestone-7b1-snapshot-contract-hardening`
Verified baseline: `42d1d36fccee32d08f6a351755c9e434272c164e` (M7-B merge on `main`)

## Incident summary

| Field | Value |
|---|---|
| Workflow | `update-staged-feed-gps` |
| Run ID | 29255753666 |
| Job ID | 86835503805 |
| Date | 2026-07-13 |

### Verified incident facts

- `safe_update_contract_count`: 204
- `safe_update_ready_identity_count`: 204
- `updated_staged_event_count`: 155
- `unmatched_safe_identity_count`: 49
- `skipped_count`: 49
- `conflict_count`: 0
- `update_performed`: false
- `staged_feed_modified`: false
- `location_cache_modified`: false
- `public_map_modified`: false
- `qa_pass`: false
- All 49 unmatched identities were dated **2026-06-30 through 2026-07-06**
- The staged feed consumed by the failed run began on **2026-07-07**
- The workflow synchronized latest `main` before applying
- The contract was **not** bound to the exact staged-feed content hash
- No identity regression was found in M7-A or M7-B

### Root cause

**Stale contract / legitimate source advance.** The adjudication contract was created against an older rolling staged-feed snapshot. By execution time, the staged feed had advanced and 49 historical identities had aged out. The existing safety gate correctly blocked all writes, but the failure surfaced only after identity matching as a count mismatch (`155/204`).

## Provenance inventory

| Stage | Script | Primary inputs | Primary outputs | Provenance before M7-B.1 | Provenance after M7-B.1 |
|---|---|---|---|---|---|
| Staged feed generation | `scripts/build_staged_production_feed.py` | NYC Open Data sync artifacts | `data/nycif_staged_live_events.json` | none | unchanged (upstream producer) |
| Manifest | live-sync workflows | staged feed | `data/staged_live_manifest.json` | none | unchanged |
| Diagnostic | `scripts/generate_gps_staged_feed_integration_match_diagnostic.py` | staged feed, location cache, promotion/dry-run reports | `data/gps_staged_feed_integration_match_diagnostic.json` | path string only | `staged_feed_provenance` bound to exact staged-feed bytes |
| Adjudication | `scripts/generate_gps_staged_feed_integration_adjudication_summary.py` | diagnostic artifact | `data/gps_staged_feed_integration_adjudication_summary.json` | none | copies diagnostic `staged_feed` provenance; records `diagnostic_artifact_sha256` |
| Apply | `scripts/apply_gps_staged_feed_integration_update.py` | adjudication summary, staged feed | update report; staged feed write only on full pass | count-based only | snapshot preflight before identity matching |
| Workflow | `.github/workflows/gps-staged-feed-integration-update.yml` | repo checkout | commit on success | sync latest main | unchanged (fail-closed report already blocks commit) |

## Hash contract

- Algorithm: **SHA-256** over **exact on-disk file bytes**
- Digest input excludes file path and all timestamps
- UTF-8 JSON text is expected, but validation is byte-for-byte:
  - newline sensitivity: yes
  - whitespace sensitivity: yes
  - key-order sensitivity: yes
  - Unicode code-unit sensitivity: yes
- Empty file: valid; digest is SHA-256 of zero bytes
- Row counts are **never** used as content identity

Shared helper: `scripts/gps_snapshot_provenance.py`

## Provenance schema (`gps-staged-feed-provenance-v1`)

```json
{
  "schema_version": "gps-staged-feed-provenance-v1",
  "staged_feed": {
    "path": "data/nycif_staged_live_events.json",
    "sha256": "<lowercase hex>",
    "byte_size": 123,
    "git_blob_sha": null,
    "commit_sha": null
  },
  "producer": {
    "script": "scripts/generate_gps_staged_feed_integration_match_diagnostic.py",
    "generated_at_utc": "2026-07-13T12:00:00+00:00",
    "upstream_artifact_sha256": null
  }
}
```

Rules:

- `schema_version`, `staged_feed.path`, `staged_feed.sha256`, and `staged_feed.byte_size` are mandatory for apply preflight
- `generated_at_utc` is informational only
- `staged_feed` section is copied forward without mutation across diagnostic → adjudication → apply
- adjudication records diagnostic artifact SHA-256 in `producer.upstream_artifact_sha256` and top-level `diagnostic_artifact_sha256`

## Producer flow

1. **Diagnostic** hashes the staged feed it actually read and writes `staged_feed_provenance`.
2. **Adjudication** deep-copies diagnostic `staged_feed_provenance`, updates only `producer`, and fails `qa_pass` when diagnostic provenance is missing.
3. **Apply** validates adjudication `staged_feed_provenance` against the current staged feed **before** identity matching or count validation.

## Consumer validation (apply preflight)

Checks, in order:

1. `staged_feed_provenance` present and schema supported
2. expected path matches current staged-feed path
3. current byte size equals bound size
4. current SHA-256 equals bound SHA-256

On failure:

- no identity matching attempted
- no staged-feed mutation
- `qa_pass: false`, `update_performed: false`
- `failure_type` is explicit (`stale_staged_feed_contract` or `legacy_contract_missing_snapshot_hash`)
- `required_next_step` instructs humans to regenerate diagnostic and adjudication against the current staged feed

## Stale behavior

When the staged feed has advanced but the contract still carries the old snapshot hash:

- preflight fails with `failure_type: stale_staged_feed_contract`
- report includes expected vs actual SHA-256 and byte size
- the July 13 incident shape (204-contract / 155-present) is blocked **before** count validation

## Legacy behavior

Contracts without `staged_feed_provenance` (or without mandatory hash fields) fail closed with:

- `failure_type: legacy_contract_missing_snapshot_hash`
- `required_next_step`: regenerate diagnostic and adjudication against the current staged feed

No auto-regeneration. No auto-approval.

## Incident regression evidence

Offline fixture in `tests/registry/test_canonical_milestone_7b1_snapshot_contract_hardening.py`:

- old snapshot: 204 identities dated 2026-06-30..2026-07-06
- new snapshot: begins 2026-07-07; only 155 old identities remain
- apply preflight detects hash mismatch; zero mutations

## Normal-path behavior

When the current staged feed bytes match the bound contract:

- preflight passes (`snapshot_contract_preflight_passed: true`)
- existing M7-B identity matching and count gates run unchanged
- full success still requires all 204 identities matched with zero conflicts

## Fresh-contract migration instructions

1. Ensure `data/nycif_staged_live_events.json` is the intended target snapshot.
2. Run diagnostic workflow/script to regenerate `data/gps_staged_feed_integration_match_diagnostic.json`.
3. Run adjudication workflow/script to regenerate `data/gps_staged_feed_integration_adjudication_summary.json`.
4. Verify adjudication `qa_pass: true` and `staged_feed_provenance` present.
5. Only then run the staged-feed GPS update workflow.

## Rollback behavior

This milestone is source/tests/docs only. No production data changed. Roll back by reverting the PR; legacy contracts remain blocked until regenerated.

## Residual risks

- Upstream producers outside the diagnostic/adjudication/apply chain still do not emit provenance (by design; out of scope).
- Git blob/commit SHA fields are reserved but currently null.
- Human operators must regenerate artifacts after staged-feed rolls; the apply stage will not infer freshness from counts.

## Protected boundaries

Unchanged and not modified by this milestone:

- `data/nycif_staged_live_events.json`
- `data/location_cache.json`
- `data/staged_live_manifest.json`
- `data/previous_staged_live_events_snapshot.json`
- public-map outputs
- promotion / Phase 2E execution

No old identities are force-applied. M7-C remains unauthorized.

## Future synchronization implications

API, website, and mobile consumers must continue to treat only promoted public feeds as authoritative. Snapshot provenance is a backend apply gate only; frontend repos must not load diagnostic/adjudication artifacts as public event data.

## Final verdict

Implementation complete on branch `canonical-milestone-7b1-snapshot-contract-hardening`. Independent review and separate merge authorization required. **Do not merge from this milestone prompt.**
