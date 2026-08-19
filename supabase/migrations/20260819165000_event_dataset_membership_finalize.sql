create table if not exists public.event_dataset_sync_membership (
  sync_token text not null,
  source_name text not null,
  source_dataset text not null,
  occurrence_id text not null references public.event_occurrences(occurrence_id) on delete cascade,
  expected_count integer not null check (expected_count > 0),
  staged_at timestamptz not null default now(),
  primary key (sync_token, occurrence_id)
);

alter table public.event_dataset_sync_membership enable row level security;
revoke all on table public.event_dataset_sync_membership from public;
revoke all on table public.event_dataset_sync_membership from anon;
revoke all on table public.event_dataset_sync_membership from authenticated;
grant select, insert, update, delete on table public.event_dataset_sync_membership to service_role;

create index if not exists event_dataset_sync_membership_scope_idx
  on public.event_dataset_sync_membership(sync_token, source_name, source_dataset);

create or replace function public.nycif_stage_event_dataset_membership(
  p_sync_token text,
  p_source_name text,
  p_source_dataset text,
  p_occurrence_ids text[],
  p_expected_count integer,
  p_expected_project_ref text
)
returns jsonb
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_database_ref text;
  v_staged_count integer;
begin
  if p_expected_project_ref is null or p_expected_project_ref <> 'oggwpvdirkrnzoolparx' then
    raise exception 'NYCIF_SYNC_TARGET_DENIED';
  end if;
  select split_part(nullif(current_setting('request.headers', true),'')::jsonb ->> 'host', '.', 1)
    into v_database_ref;
  if v_database_ref is not null and v_database_ref <> '' and v_database_ref <> p_expected_project_ref then
    raise exception 'NYCIF_SYNC_PROJECT_REF_MISMATCH';
  end if;
  if p_sync_token is null or p_sync_token !~* '^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$' then
    raise exception 'NYCIF_SYNC_TOKEN_INVALID';
  end if;
  if p_source_name is null or btrim(p_source_name) = '' or p_source_dataset is null or btrim(p_source_dataset) = '' then
    raise exception 'NYCIF_SYNC_SCOPE_REQUIRED';
  end if;
  if p_expected_count is null or p_expected_count <= 0 then
    raise exception 'NYCIF_SYNC_EXPECTED_COUNT_INVALID';
  end if;
  if p_occurrence_ids is null or cardinality(p_occurrence_ids) = 0 then
    raise exception 'NYCIF_SYNC_EMPTY_MEMBERSHIP_CHUNK';
  end if;
  if exists (
    select 1
    from unnest(p_occurrence_ids) as u(occurrence_id)
    where occurrence_id !~ '^[0-9a-f]{64}$'
  ) then
    raise exception 'NYCIF_SYNC_OCCURRENCE_ID_INVALID';
  end if;

  delete from public.event_dataset_sync_membership
  where staged_at < now() - interval '2 days';

  if exists (
    select 1
    from public.event_dataset_sync_membership m
    where m.sync_token = p_sync_token
      and (
        m.source_name <> p_source_name
        or m.source_dataset <> p_source_dataset
        or m.expected_count <> p_expected_count
      )
  ) then
    raise exception 'NYCIF_SYNC_TOKEN_SCOPE_MISMATCH';
  end if;

  if exists (
    select 1
    from unnest(p_occurrence_ids) as u(occurrence_id)
    where not exists (
      select 1
      from public.event_sources s
      where s.occurrence_id = u.occurrence_id
        and s.source_name = p_source_name
        and s.source_dataset = p_source_dataset
        and s.source_active
    )
  ) then
    raise exception 'NYCIF_SYNC_MEMBERSHIP_NOT_WRITTEN';
  end if;

  insert into public.event_dataset_sync_membership(
    sync_token, source_name, source_dataset, occurrence_id, expected_count
  )
  select p_sync_token, p_source_name, p_source_dataset, u.occurrence_id, p_expected_count
  from unnest(p_occurrence_ids) as u(occurrence_id)
  on conflict (sync_token, occurrence_id) do nothing;

  select count(*) into v_staged_count
  from public.event_dataset_sync_membership
  where sync_token = p_sync_token
    and source_name = p_source_name
    and source_dataset = p_source_dataset;

  if v_staged_count > p_expected_count then
    raise exception 'NYCIF_SYNC_STAGED_COUNT_OVERFLOW';
  end if;

  return jsonb_build_object(
    'transaction', 'committed',
    'sync_token', p_sync_token,
    'source_name', p_source_name,
    'source_dataset', p_source_dataset,
    'staged_count', v_staged_count,
    'expected_count', p_expected_count
  );
end;
$$;

create or replace function public.nycif_finalize_event_dataset_sync(
  p_sync_token text,
  p_source_name text,
  p_source_dataset text,
  p_expected_count integer,
  p_expected_project_ref text
)
returns jsonb
language plpgsql
security invoker
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

  select count(*) into v_newsroom_before from public.newsroom_queue;

  insert into public.pipeline_runs(source_name, source_row_count, notes)
  values (
    p_source_name,
    p_expected_count,
    'Dataset-scoped membership finalization: ' || p_source_dataset
  )
  returning run_id into v_run_id;

  create temporary table _nycif_dataset_expire on commit drop as
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
    );

  update public.event_sources s
  set source_active = false,
      source_last_seen = now(),
      updated_at = now()
  from _nycif_dataset_expire x
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
  from _nycif_dataset_expire x;

  update public.event_occurrences o
  set status = 'expired',
      source_active = false,
      last_pipeline_run_id = v_run_id,
      last_seen = now(),
      updated_at = now()
  from (select distinct occurrence_id from _nycif_dataset_expire) x
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
  from _nycif_dataset_expire x
  join public.event_occurrences o on o.occurrence_id = x.occurrence_id
  where o.last_pipeline_run_id = v_run_id
    and o.status = 'expired';

  select count(*) into v_newsroom_after from public.newsroom_queue;
  if v_newsroom_after <> v_newsroom_before then
    raise exception 'NYCIF_SYNC_NEWSROOM_MUTATION_DENIED';
  end if;

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

  delete from public.event_dataset_sync_membership
  where sync_token = p_sync_token
    and source_name = p_source_name
    and source_dataset = p_source_dataset;

  return jsonb_build_object(
    'transaction', 'committed',
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

revoke all on function public.nycif_stage_event_dataset_membership(text,text,text,text[],integer,text) from public;
revoke all on function public.nycif_stage_event_dataset_membership(text,text,text,text[],integer,text) from anon;
revoke all on function public.nycif_stage_event_dataset_membership(text,text,text,text[],integer,text) from authenticated;
grant execute on function public.nycif_stage_event_dataset_membership(text,text,text,text[],integer,text) to service_role;

revoke all on function public.nycif_finalize_event_dataset_sync(text,text,text,integer,text) from public;
revoke all on function public.nycif_finalize_event_dataset_sync(text,text,text,integer,text) from anon;
revoke all on function public.nycif_finalize_event_dataset_sync(text,text,text,integer,text) from authenticated;
grant execute on function public.nycif_finalize_event_dataset_sync(text,text,text,integer,text) to service_role;
