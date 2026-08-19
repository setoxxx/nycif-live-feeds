# STAGING WRITE MODE PASS

Rung 8 — Controlled Staging Write Mode — is closed on the evidence below.
Rung 9 remains locked and was not started.

## Source checkpoint

- Repository: `setoxxx/nycif-live-feeds`
- Re-fetched `main`: `a8ed5a3b67e5f9b21bf2792c91e555c7161fef29`
- Commit message: `Add Supabase read-only adapter interface to writer`
- Re-fetched writer blob: `e82279c7cb271622892a80adf90acf01bffecdf8`
- The fetched writer was dry-run/read-only before this Rung 8 change.

## Authorized staging target and schema

- Project name: `nycif-location-authority`
- Project/ref: `oggwpvdirkrnzoolparx`
- URL: `https://oggwpvdirkrnzoolparx.supabase.co`
- PostgreSQL: 17
- Applied migration: `20260819015838_rung8_atomic_event_write`

The live FK/constraint inventory was inspected before implementation. The
write sequence follows the observed graph: `pipeline_runs` first,
`event_occurrences` before `event_sources`, `event_classifications`,
`event_quality`, `event_quality_history`, and `event_change_log`. Existing
uniqueness includes the occurrence primary key, one current classification per
occurrence, one current quality row per occurrence, and the source relationship
key `(source_name, source_dataset, source_event_id, occurrence_id)`.

## Safety and transaction design

- `SUPABASE_WRITE_ENABLED` defaults to false.
- Writes also require `SUPABASE_TARGET_ENV=staging`, the exact compiled-in
  staging ref/URL pair, and an environment-only service-role credential.
- Unknown, missing, mismatched, non-HTTPS, or explicitly denied production
  refs/URLs fail before network access.
- Supplied occurrence IDs are consumed unchanged and must match the 64-hex
  OccurrenceIdentityV2 output contract. Canonical rows without that field call
  the existing `enigma.shadow2.occurrence_identity` authority; no second
  identity implementation was created.
- Dry-run remains the default and its existing comparison path remains usable.
- A single service-role-only, `SECURITY INVOKER` Postgres RPC owns every batch.
  It takes a transaction-scoped advisory lock and raises on any failure, so
  separate REST/upsert calls are not used as a transaction substitute.
- RPC execution is revoked from `PUBLIC`, `anon`, and `authenticated`; only
  `service_role` has execute permission.
- Newsroom queue count is checked inside the transaction and any delta aborts
  the transaction.

## Executed database evidence

Authoritative 1,526-row idempotence run (`pipeline_runs.run_id=24`):

| Action | Count |
| --- | ---: |
| INSERT | 0 |
| UPDATE | 0 |
| EXPIRE | 0 |
| UNCHANGED | 1,526 |

The run completed with `qa_pass=true`, `source_row_count=1526`, and
`newsroom_queue_delta=0`. A preceding convergence pass updated 21 pre-existing
rows without inserting or expiring any occurrence; the immediately repeated
identical full-corpus pass above is the closure idempotence evidence.

Clearly synthetic fixtures then proved:

| Proof | Result |
| --- | --- |
| INSERT | 2 inserted; 2 classification and 2 quality initializations |
| UPDATE | 1 updated, 1 unchanged; classification change 1; quality change 1 |
| EXPIRE | 1 expired, 1 unchanged |
| ROLLBACK | forced `RUNG8_SIMULATED_FAILURE`; zero rows remained in occurrences, sources, classifications, current quality, quality history, lifecycle history, and pipeline runs |

Before fixture cleanup, integrity evidence showed 2 sources, 2 current
classifications, 2 current quality rows, 3 quality-history rows, 4 lifecycle
rows, the intended updated row, and the intended expired row. The two synthetic
business occurrences were then deleted; FK actions removed their dependent
business rows. Final `synthetic_business_rows=0`.

## Final staging integrity

| Check | Result |
| --- | ---: |
| event occurrences | 1,526 |
| source relationships | 1,526 |
| current classifications | 1,526 |
| current quality rows | 1,526 |
| quality history rows | 1,532 |
| lifecycle history rows | 51 |
| newsroom queue | 0 |
| duplicate occurrence IDs | 0 |
| duplicate source relationships | 0 |
| duplicate current classifications | 0 |
| duplicate current quality rows | 0 |
| orphan sources/classifications/quality/quality history | 0 |

Supabase security advisors returned zero findings after the migration.
Performance advisors reported only pre-existing unused-index informational
items and a pre-existing duplicate current-classification index warning; no
index was removed in Rung 8.

## Repository verification

- Writer and OccurrenceIdentityV2 tests: `22 passed`
- Standalone writer tests: `13 passed`
- Independent integration review restored the legacy dry-run `id`-first key
  precedence and added a regression test for rows that also carry a V2 ID.
- Python compilation: passed
- SQL function compilation in a rolled-back transaction: passed
- Existing dry-run against the canonical artifact: `run_type=dry_run`,
  `database_write_performed=false`
- Current canonical artifact normalization: 36,322 input, 36,322 normalized,
  36,322 unique OccurrenceIdentityV2 IDs, 0 errors, 0 duplicates

## Open issue / PR classification

- Issue #433 — **NON-BLOCKER**: repository-wide Sonar/security/runtime debt;
  independent of the controlled staging writer acceptance tests.
- Issue #437 — **NON-BLOCKER**: production refresh CAS/rollback integration
  tests; independent of the staging database transaction.
- Issue #386 — **LATER-RUNG**: public-map freshness/promotion incident; public
  delivery was explicitly out of Rung 8 scope.
- Issue #388 — **LATER-RUNG**: full-corpus production certification and National
  Map template work.
- PR #434 — **NON-BLOCKER**: daily refresh runtime/path hardening. It was not
  merged or modified for backlog cleanup.
- Open Supabase-specific issues/PRs found by repository search: none.

No production feed, public map, mobile app, production scheduler, production
database, or unrelated pull request was changed.
