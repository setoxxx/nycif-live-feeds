-- Large bootstrap deltas can exceed the hosted PostgREST statement timeout when
-- expired in one transaction. Process stale dataset membership in bounded,
-- resumable batches while preserving the same dataset-scoped expiration rules.

create or replace function public.nycif_finalize_event_dataset_sync_batch_v1(
  p_sync_token text,
  p_source_name text,
  p_source_dataset text,
  p_expected_count integer,
  p_expected_project_ref text,
  p_batch_size integer default 1000
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_database_ref text;
  v_staged_count integer;
  v_source_rows_inactivated integer := 0;
  v_expired integer := 0;
  v_run_id bigint;
  v_newsroom_before bigint;
  v_newsroom_after bigint;
  v_more boolean := false;
begin
  if p_expected_project_ref is null or p_expected_project_ref <> 'oggwpvdirkrnzoolparx' then
    raise exception 'NYCIF_SYNC_TARGET_DENIED';
  end if;
  select split_part(nullif(current_setting('request.headers', true),'')::jsonb ->> 'host', '.', 1)
    into v_database_ref;
  if v_database_ref is not null and v_database_ref <> '' and v_database_ref <> p_expected_project_ref then
    raise exception 'NYCIF_SYNC_PROJECT_REF_MISMATCH';
  end if;
  if p_expected_count is null or p_expected_count <= 0 then
    raise exception 'NYCIF_SYNC_EXPECTED_COUNT_INVALID';
  end if;
  if p_batch_size is null or p_batch_size < 100 or p_batch_size > 2000 then
    raise exception 'NYCIF_SYNC_BATCH_SIZE_INVALID';
  end if;

  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended('nycif-rung8:' || p_source_name, 0)
  );

  select count(*) into v_staged_count
  from public.event_dataset_sync_membership
  where sync_token = p_sync_token
    and source_name = p_source_name
    and source_dataset = p_source_dataset
    and expected_count = p_expected_count;

  if v_staged_count <> p_expected_count then
    raise exception 'NYCIF_SYNC_INCOMPLETE_MEMBERSHIP staged=% expected=%', v_staged_count, p_expected_count;
  end if;

  if exists (
    select 1
    from public.event_dataset_sync_membership m
    where m.sync_token = p_sync_token
      and m.source_name = p_source_name
      and m.source_dataset = p_source_dataset
      and not exists (
        select 1
        from public.event_sources s
        where s.occurrence_id = m.occurrence_id
          and s.source_name = p_source_name
          and s.source_dataset = p_source_dataset
          and s.source_active
      )
  ) then
    raise exception 'NYCIF_SYNC_STAGED_SOURCE_NOT_ACTIVE';
  end if;

  drop table if exists pg_temp._nycif_dataset_expire_batch;
  create temporary table _nycif_dataset_expire_batch on commit drop as
  select distinct s.occurrence_id, s.source_dataset, s.source_event_id
  from public.event_sources s
  where s.source_name = p_source_name
    and s.source_dataset = p_source_dataset
    and s.source_active
    and not exists (
      select 1
      from public.event_dataset_sync_membership m
      where m.sync_token = p_sync_token
        and m.source_name = p_source_name
        and m.source_dataset = p_source_dataset
        and m.occurrence_id = s.occurrence_id
    )
  order by s.occurrence_id, s.source_event_id
  limit p_batch_size;

  if not exists (select 1 from _nycif_dataset_expire_batch) then
    delete from public.event_dataset_sync_membership
    where sync_token = p_sync_token
      and source_name = p_source_name
      and source_dataset = p_source_dataset;
    return jsonb_build_object(
      'transaction', 'committed',
      'finalization_complete', true,
      'pipeline_run_id', null,
      'staged_count', v_staged_count,
      'expected_count', p_expected_count,
      'source_rows_inactivated', 0,
      'actions', jsonb_build_object('INSERT',0,'UPDATE',0,'UNCHANGED',p_expected_count,'EXPIRE',0),
      'newsroom_queue_delta', 0
    );
  end if;

  select count(*) into v_newsroom_before from public.newsroom_queue;

  insert into public.pipeline_runs(source_name, source_row_count, notes)
  values (
    p_source_name,
    p_expected_count,
    'Dataset-scoped bounded membership finalization: ' || p_source_dataset
  )
  returning run_id into v_run_id;

  update public.event_sources s
  set source_active = false,
      source_last_seen = now(),
      updated_at = now()
  from _nycif_dataset_expire_batch x
  where s.occurrence_id = x.occurrence_id
    and s.source_name = p_source_name
    and s.source_dataset = p_source_dataset
    and s.source_event_id is not distinct from x.source_event_id
    and s.source_active;
  get diagnostics v_source_rows_inactivated = row_count;

  insert into public.event_change_log(
    occurrence_id, pipeline_run_id, change_type, changed_fields, reason
  )
  select distinct
    x.occurrence_id,
    v_run_id,
    'SOURCE_EXPIRE',
    '["source_active"]'::jsonb,
    'NYCIF_DATASET_MEMBERSHIP_ABSENT:' || p_source_dataset
  from _nycif_dataset_expire_batch x;

  update public.event_occurrences o
  set status = 'expired',
      source_active = false,
      last_pipeline_run_id = v_run_id,
      last_seen = now(),
      updated_at = now()
  from (select distinct occurrence_id from _nycif_dataset_expire_batch) x
  where o.occurrence_id = x.occurrence_id
    and not exists (
      select 1
      from public.event_sources s
      where s.occurrence_id = o.occurrence_id
        and s.source_active
    );
  get diagnostics v_expired = row_count;

  insert into public.event_change_log(
    occurrence_id, pipeline_run_id, change_type, changed_fields, reason
  )
  select distinct
    x.occurrence_id,
    v_run_id,
    'EXPIRE',
    '["status","source_active"]'::jsonb,
    'NYCIF_ALL_SOURCES_INACTIVE'
  from _nycif_dataset_expire_batch x
  join public.event_occurrences o on o.occurrence_id = x.occurrence_id
  where o.last_pipeline_run_id = v_run_id
    and o.status = 'expired';

  select count(*) into v_newsroom_after from public.newsroom_queue;
  if v_newsroom_after <> v_newsroom_before then
    raise exception 'NYCIF_SYNC_NEWSROOM_MUTATION_DENIED';
  end if;

  select exists (
    select 1
    from public.event_sources s
    where s.source_name = p_source_name
      and s.source_dataset = p_source_dataset
      and s.source_active
      and not exists (
        select 1
        from public.event_dataset_sync_membership m
        where m.sync_token = p_sync_token
          and m.source_name = p_source_name
          and m.source_dataset = p_source_dataset
          and m.occurrence_id = s.occurrence_id
      )
  ) into v_more;

  update public.pipeline_runs
  set completed_at = now(),
      status = 'completed',
      qa_pass = true,
      added_count = 0,
      modified_count = 0,
      removed_count = v_expired,
      unchanged_count = p_expected_count,
      failures = '[]'::jsonb
  where run_id = v_run_id;

  if not v_more then
    delete from public.event_dataset_sync_membership
    where sync_token = p_sync_token
      and source_name = p_source_name
      and source_dataset = p_source_dataset;
  end if;

  return jsonb_build_object(
    'transaction', 'committed',
    'finalization_complete', not v_more,
    'pipeline_run_id', v_run_id,
    'staged_count', v_staged_count,
    'expected_count', p_expected_count,
    'source_rows_inactivated', v_source_rows_inactivated,
    'actions', jsonb_build_object(
      'INSERT', 0,
      'UPDATE', 0,
      'UNCHANGED', p_expected_count,
      'EXPIRE', v_expired
    ),
    'newsroom_queue_delta', v_newsroom_after - v_newsroom_before
  );
end;
$$;

revoke all on function public.nycif_finalize_event_dataset_sync_batch_v1(text,text,text,integer,text,integer) from public;
revoke all on function public.nycif_finalize_event_dataset_sync_batch_v1(text,text,text,integer,text,integer) from anon;
revoke all on function public.nycif_finalize_event_dataset_sync_batch_v1(text,text,text,integer,text,integer) from authenticated;
grant execute on function public.nycif_finalize_event_dataset_sync_batch_v1(text,text,text,integer,text,integer) to service_role;
