# NYCIF Events — Supabase Completion Checklist

Issue: #440
Branch: `fix/events-dataset-expiration-20260819`
Authority project: `oggwpvdirkrnzoolparx`

This file is the branch-local execution checklist for the final Events completion pass. It is not a public data source.

## Gates

- [x] Dataset-scoped expiration design added.
- [x] Chunk-safe dataset membership staging/finalization added.
- [x] Bounded Supabase authority sync orchestrator added.
- [x] Supabase reader-safe Today+7 RPC added.
- [x] Reader-window regression coverage added.
- [x] Dedicated Events Supabase authority CI workflow added.
- [ ] Pull-request CI passes.
- [ ] Membership/finalizer migration applied and verified on `oggwpvdirkrnzoolparx`.
- [ ] Reader RPC permissions/metadata/semantic checks pass.
- [ ] Full current TVPP corpus bootstrapped in bounded chunks with expiration disabled per chunk.
- [ ] Final TVPP dataset membership reconciliation succeeds.
- [ ] Calendar/Feast sibling source rows remain unchanged.
- [ ] Immediate identical rerun proves semantic INSERT=0, UPDATE=0, EXPIRE=0.
- [ ] Existing daily production transaction invokes the Supabase authority sync and blocks READY on DB failure.
- [ ] Public map/app reads event data only from the Supabase Today+7 reader path.
- [ ] Event-derived temporal filtering no longer depends on GitHub-hosted event JSON/GeoJSON sidecars.
- [ ] Browser/network acceptance confirms event-data origin is `oggwpvdirkrnzoolparx.supabase.co` only.

## Safety rules

- Never expire a corpus per chunk.
- Never expire by `source_name` alone.
- Never expose a service-role key to browser code or repository content.
- Never hard-delete removed source events.
- Preserve OccurrenceIdentityV2 as the only occurrence identity authority.
- Preserve Projector V3 as the exact-location authority.
- Keep the full corpus in the database/processing lane; browser receives Today+7 only.
- Do not mark COMPLETE until bootstrap, idempotence, automation, and runtime acceptance evidence exists.
