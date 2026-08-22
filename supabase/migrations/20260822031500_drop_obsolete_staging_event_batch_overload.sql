-- Remove the stale overloaded writer that makes PostgREST resolution ambiguous.
-- The production writer/orchestrator call the canonical five-argument contract.

do $$
begin
  if to_regprocedure('public.nycif_apply_staging_event_batch(jsonb,text,boolean,boolean,text)') is null then
    raise exception 'NYCIF_CANONICAL_STAGING_EVENT_BATCH_MISSING';
  end if;

  if to_regprocedure('public.nycif_apply_staging_event_batch(jsonb,text,boolean,boolean,text,jsonb,boolean)') is not null then
    drop function public.nycif_apply_staging_event_batch(jsonb,text,boolean,boolean,text,jsonb,boolean);
  end if;
end
$$;
