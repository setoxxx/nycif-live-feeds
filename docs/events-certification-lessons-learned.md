# NYCIF Events Certification Lessons Learned

## Finalizer temp-table retry safety

Date: 2026-08-19

A certification run found a PostgreSQL session reuse edge case in `nycif_finalize_event_dataset_sync(...)`.

## Symptom

A repeated invocation in the same session failed with:

`ERROR: 42P07 relation "_nycif_dataset_expire" already exists`

## Root cause

`CREATE TEMPORARY TABLE ... ON COMMIT DROP` removes the temporary table only at transaction commit. A reused session can still contain the temporary relation before commit.

## Resolution

The finalizer now explicitly clears the temporary relation before recreation:

```sql
drop table if exists pg_temp._nycif_dataset_expire;
create temporary table _nycif_dataset_expire on commit drop as ...;
```

## Permanent certification rule

Database certification must test:

- repeated function invocation;
- retry/session reuse behavior;
- full membership success;
- incomplete membership fail-closed behavior;
- zero newsroom mutation;
- sibling dataset preservation.

## Architecture remains unchanged

- GitHub Actions performs orchestration and bounded processing.
- Supabase/Postgres remains canonical authority.
- Membership is complete before dataset finalization.
- Expiration remains dataset-scoped.
- Browser/map receives only the bounded Today+7 reader projection.
