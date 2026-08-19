create or replace function public.nycif_apply_staging_event_batch(
  p_events jsonb,
  p_source_name text,
  p_allow_expire boolean default false,
  p_simulate_failure boolean default false,
  p_expected_project_ref text default null
)
returns jsonb
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_run_id bigint;
  v_inserted integer := 0;
  v_updated integer := 0;
  v_unchanged integer := 0;
  v_expired integer := 0;
  v_classification_changes integer := 0;
  v_quality_changes integer := 0;
  v_newsroom_before bigint;
  v_newsroom_after bigint;
  v_database_ref text;
begin
  if p_expected_project_ref is null or p_expected_project_ref <> 'oggwpvdirkrnzoolparx' then
    raise exception 'RUNG8_TARGET_DENIED';
  end if;
  select split_part(nullif(current_setting('request.headers', true),'')::jsonb ->> 'host', '.', 1)
    into v_database_ref;
  if v_database_ref is not null and v_database_ref <> '' and v_database_ref <> p_expected_project_ref then
    raise exception 'RUNG8_PROJECT_REF_MISMATCH';
  end if;
  if p_source_name is null or btrim(p_source_name) = '' then
    raise exception 'RUNG8_SOURCE_NAME_REQUIRED';
  end if;
  if p_events is null or jsonb_typeof(p_events) <> 'array' then
    raise exception 'RUNG8_EVENTS_MUST_BE_ARRAY';
  end if;
  if jsonb_array_length(p_events) = 0 and not p_allow_expire then
    raise exception 'RUNG8_EMPTY_BATCH_DENIED';
  end if;
  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended('nycif-rung8:' || p_source_name, 0)
  );

  create temporary table _nycif_rung8_input on commit drop as
  select
    e->>'occurrence_id' occurrence_id,
    e->>'title' title,
    nullif(e->>'start_at','')::timestamptz start_at,
    nullif(e->>'end_at','')::timestamptz end_at,
    coalesce(nullif(e->>'timezone',''),'America/New_York') timezone,
    e->>'borough' borough,
    e->>'display_location' display_location,
    nullif(e->>'lat','')::double precision lat,
    nullif(e->>'lng','')::double precision lng,
    e->>'public_category' public_category,
    e->>'public_subtype' public_subtype,
    coalesce(nullif(e->>'status',''),'active') status,
    coalesce((e->>'source_active')::boolean,true) source_active,
    coalesce((e->>'map_ready')::boolean,false) map_ready,
    coalesce(nullif(e->>'editorial_priority',''),'normal') editorial_priority,
    coalesce(e->'metadata','{}'::jsonb) metadata,
    e->'source' source,
    e->'classification' classification,
    e->'quality' quality,
    false is_insert,
    false is_update,
    false classification_changed,
    false quality_changed
  from jsonb_array_elements(p_events) e;

  if exists (
    select 1 from _nycif_rung8_input
    where occurrence_id is null or occurrence_id !~ '^[0-9a-f]{64}$'
      or title is null or btrim(title) = ''
      or source->>'source_name' is distinct from p_source_name
      or nullif(source->>'source_dataset','') is null
      or nullif(source->>'source_event_id','') is null
  ) then
    raise exception 'RUNG8_INVALID_INPUT_OR_IDENTITY';
  end if;
  if exists (select 1 from _nycif_rung8_input group by occurrence_id having count(*) > 1) then
    raise exception 'RUNG8_DUPLICATE_OCCURRENCE_ID';
  end if;

  select count(*) into v_newsroom_before from public.newsroom_queue;

  insert into public.pipeline_runs(source_name, source_row_count, notes)
  values (p_source_name, jsonb_array_length(p_events), 'Rung 8 atomic staging writer')
  returning run_id into v_run_id;

  update _nycif_rung8_input i set
    is_insert = (o.occurrence_id is null),
    is_update = (o.occurrence_id is not null and (
      row(o.title,o.start_at,o.end_at,o.timezone,o.borough,o.display_location,o.lat,o.lng,
          o.public_category,o.public_subtype,o.status,o.source_active,o.map_ready,o.editorial_priority,o.metadata)
      is distinct from
      row(i.title,i.start_at,i.end_at,i.timezone,i.borough,i.display_location,i.lat,i.lng,
          i.public_category,i.public_subtype,i.status,i.source_active,i.map_ready,i.editorial_priority,i.metadata)
      or not exists (
        select 1 from public.event_sources s where s.occurrence_id=i.occurrence_id
          and s.source_name=p_source_name
          and s.source_dataset=i.source->>'source_dataset'
          and s.source_event_id=i.source->>'source_event_id'
          and row(s.source_cemsid,s.source_event_type,s.source_agency,s.source_url,s.source_first_seen,
                  s.source_last_seen,s.source_active,s.raw_record)
              is not distinct from
              row(i.source->>'source_cemsid',i.source->>'source_event_type',i.source->>'source_agency',
                  i.source->>'source_url',nullif(i.source->>'source_first_seen','')::timestamptz,
                  nullif(i.source->>'source_last_seen','')::timestamptz,
                  coalesce((i.source->>'source_active')::boolean,true),i.source->'raw_record')
      )
    )),
    classification_changed = (o.occurrence_id is null or not exists (
      select 1 from public.event_classifications c where c.occurrence_id=i.occurrence_id and c.is_current
        and row(c.public_category,c.public_subtype,c.classification_reason,c.classifier_version,c.confidence,
                c.source_event_type,c.source_agency)
            is not distinct from
            row(i.classification->>'public_category',i.classification->>'public_subtype',
                i.classification->>'classification_reason',i.classification->>'classifier_version',
                nullif(i.classification->>'confidence','')::numeric,i.classification->>'source_event_type',
                i.classification->>'source_agency')
    )),
    quality_changed = (o.occurrence_id is null or not exists (
      select 1 from public.event_quality q where q.occurrence_id=i.occurrence_id
        and row(q.quality_status,q.quality_flags,q.public_display_status,q.details)
            is not distinct from
            row(coalesce(i.quality->>'quality_status','VALID'),coalesce(i.quality->'quality_flags','[]'::jsonb),
                coalesce(i.quality->>'public_display_status','FULL_TIME'),coalesce(i.quality->'details','{}'::jsonb))
    ))
  from public.event_occurrences o
  where o.occurrence_id = i.occurrence_id;
  update _nycif_rung8_input set
    is_insert=true,
    classification_changed=true,
    quality_changed=true
  where not is_insert and not is_update
    and not exists (select 1 from public.event_occurrences o where o.occurrence_id=_nycif_rung8_input.occurrence_id);
  update _nycif_rung8_input set is_update=true
    where not is_insert and (classification_changed or quality_changed);

  select count(*) filter(where is_insert), count(*) filter(where is_update),
         count(*) filter(where not is_insert and not is_update),
         count(*) filter(where classification_changed), count(*) filter(where quality_changed)
  into v_inserted,v_updated,v_unchanged,v_classification_changes,v_quality_changes
  from _nycif_rung8_input;

  insert into public.event_occurrences(
    occurrence_id,title,start_at,end_at,timezone,borough,display_location,lat,lng,
    public_category,public_subtype,status,source_active,map_ready,editorial_priority,
    last_pipeline_run_id,metadata,first_seen,last_seen
  )
  select occurrence_id,title,start_at,end_at,timezone,borough,display_location,lat,lng,
         public_category,public_subtype,status,source_active,map_ready,editorial_priority,
         v_run_id,metadata,now(),now()
  from _nycif_rung8_input where is_insert
  on conflict (occurrence_id) do nothing;

  update public.event_occurrences o set
    title=i.title,start_at=i.start_at,end_at=i.end_at,timezone=i.timezone,borough=i.borough,
    display_location=i.display_location,lat=i.lat,lng=i.lng,public_category=i.public_category,
    public_subtype=i.public_subtype,status=i.status,source_active=i.source_active,map_ready=i.map_ready,
    editorial_priority=i.editorial_priority,last_pipeline_run_id=v_run_id,metadata=i.metadata,
    last_seen=now(),updated_at=now()
  from _nycif_rung8_input i where i.is_update and o.occurrence_id=i.occurrence_id;

  insert into public.event_sources(
    occurrence_id,source_name,source_dataset,source_event_id,source_cemsid,source_event_type,
    source_agency,source_url,source_first_seen,source_last_seen,source_active,raw_record
  )
  select occurrence_id,p_source_name,source->>'source_dataset',source->>'source_event_id',
         source->>'source_cemsid',source->>'source_event_type',source->>'source_agency',source->>'source_url',
         nullif(source->>'source_first_seen','')::timestamptz,nullif(source->>'source_last_seen','')::timestamptz,
         coalesce((source->>'source_active')::boolean,true),source->'raw_record'
  from _nycif_rung8_input
  on conflict (source_name,source_dataset,source_event_id,occurrence_id) do update set
    source_cemsid=excluded.source_cemsid,source_event_type=excluded.source_event_type,
    source_agency=excluded.source_agency,source_url=excluded.source_url,
    source_first_seen=excluded.source_first_seen,source_last_seen=excluded.source_last_seen,
    source_active=excluded.source_active,raw_record=excluded.raw_record,updated_at=now()
  where row(event_sources.source_cemsid,event_sources.source_event_type,event_sources.source_agency,
            event_sources.source_url,event_sources.source_first_seen,event_sources.source_last_seen,
            event_sources.source_active,event_sources.raw_record)
        is distinct from
        row(excluded.source_cemsid,excluded.source_event_type,excluded.source_agency,
            excluded.source_url,excluded.source_first_seen,excluded.source_last_seen,
            excluded.source_active,excluded.raw_record);

  update public.event_classifications c set is_current=false
  from _nycif_rung8_input i
  where i.classification_changed and c.occurrence_id=i.occurrence_id and c.is_current;
  insert into public.event_classifications(
    occurrence_id,public_category,public_subtype,classification_reason,classifier_version,
    confidence,source_event_type,source_agency,is_current
  )
  select occurrence_id,classification->>'public_category',classification->>'public_subtype',
         classification->>'classification_reason',classification->>'classifier_version',
         nullif(classification->>'confidence','')::numeric,classification->>'source_event_type',
         classification->>'source_agency',true
  from _nycif_rung8_input where classification_changed;

  insert into public.event_quality_history(
    occurrence_id,previous_status,new_status,previous_flags,new_flags,
    previous_display_status,new_display_status,change_reason,pipeline_run_id,details
  )
  select i.occurrence_id,q.quality_status,coalesce(i.quality->>'quality_status','VALID'),
         coalesce(q.quality_flags,'[]'::jsonb),coalesce(i.quality->'quality_flags','[]'::jsonb),
         q.public_display_status,coalesce(i.quality->>'public_display_status','FULL_TIME'),
         case when i.is_insert then 'RUNG8_INSERT' else 'RUNG8_QUALITY_CHANGE' end,
         v_run_id,coalesce(i.quality->'details','{}'::jsonb)
  from _nycif_rung8_input i left join public.event_quality q using(occurrence_id)
  where i.quality_changed;
  insert into public.event_quality(
    occurrence_id,quality_status,quality_flags,public_display_status,pipeline_run_id,details
  )
  select occurrence_id,coalesce(quality->>'quality_status','VALID'),
         coalesce(quality->'quality_flags','[]'::jsonb),
         coalesce(quality->>'public_display_status','FULL_TIME'),v_run_id,
         coalesce(quality->'details','{}'::jsonb)
  from _nycif_rung8_input
  on conflict (occurrence_id) do update set
    quality_status=excluded.quality_status,quality_flags=excluded.quality_flags,
    public_display_status=excluded.public_display_status,pipeline_run_id=excluded.pipeline_run_id,
    details=excluded.details,detected_at=now(),updated_at=now()
  where row(event_quality.quality_status,event_quality.quality_flags,event_quality.public_display_status,event_quality.details)
    is distinct from row(excluded.quality_status,excluded.quality_flags,excluded.public_display_status,excluded.details);

  insert into public.event_change_log(occurrence_id,pipeline_run_id,change_type,changed_fields,after_state,reason)
  select occurrence_id,v_run_id,case when is_insert then 'INSERT' else 'UPDATE' end,
         case when is_insert then '["all"]'::jsonb else '["canonical_state"]'::jsonb end,
         jsonb_build_object('status',status,'source_active',source_active),'RUNG8_ATOMIC_WRITE'
  from _nycif_rung8_input where is_insert or is_update;

  if p_allow_expire then
    create temporary table _nycif_rung8_expire on commit drop as
    select distinct s.occurrence_id
    from public.event_sources s
    where s.source_name=p_source_name and s.source_active
      and not exists (select 1 from _nycif_rung8_input i where i.occurrence_id=s.occurrence_id);
    update public.event_sources s set source_active=false,source_last_seen=now(),updated_at=now()
      from _nycif_rung8_expire x where s.occurrence_id=x.occurrence_id and s.source_name=p_source_name;
    update public.event_occurrences o set status='expired',source_active=false,last_pipeline_run_id=v_run_id,
      last_seen=now(),updated_at=now()
      from _nycif_rung8_expire x where o.occurrence_id=x.occurrence_id
      and not exists (select 1 from public.event_sources s where s.occurrence_id=o.occurrence_id and s.source_active);
    get diagnostics v_expired = row_count;
    insert into public.event_change_log(occurrence_id,pipeline_run_id,change_type,changed_fields,reason)
      select x.occurrence_id,v_run_id,'EXPIRE','["status","source_active"]'::jsonb,'RUNG8_SOURCE_ABSENT'
      from _nycif_rung8_expire x join public.event_occurrences o using(occurrence_id)
      where o.last_pipeline_run_id=v_run_id and o.status='expired';
  end if;

  select count(*) into v_newsroom_after from public.newsroom_queue;
  if v_newsroom_after <> v_newsroom_before then
    raise exception 'RUNG8_NEWSROOM_MUTATION_DENIED';
  end if;
  if p_simulate_failure then
    raise exception 'RUNG8_SIMULATED_FAILURE';
  end if;

  update public.pipeline_runs set completed_at=now(),status='completed',qa_pass=true,
    added_count=v_inserted,modified_count=v_updated,removed_count=v_expired,
    unchanged_count=v_unchanged,failures='[]'::jsonb
  where run_id=v_run_id;

  return jsonb_build_object(
    'transaction','committed','pipeline_run_id',v_run_id,
    'actions',jsonb_build_object('INSERT',v_inserted,'UPDATE',v_updated,
      'UNCHANGED',v_unchanged,'EXPIRE',v_expired),
    'classification_changes',v_classification_changes,
    'quality_changes',v_quality_changes,
    'newsroom_queue_delta',v_newsroom_after-v_newsroom_before
  );
end;
$$;

revoke all on function public.nycif_apply_staging_event_batch(jsonb,text,boolean,boolean,text) from public;
revoke all on function public.nycif_apply_staging_event_batch(jsonb,text,boolean,boolean,text) from anon;
revoke all on function public.nycif_apply_staging_event_batch(jsonb,text,boolean,boolean,text) from authenticated;
grant execute on function public.nycif_apply_staging_event_batch(jsonb,text,boolean,boolean,text) to service_role;
