-- Match the existing production MapLibre reader contract:
--   * all Projector V3-certified exact markers remain visible corpus-wide;
--   * non-marker/list-only events are limited to Today + 7 days.
-- This preserves the >=1000 exact-marker cutover gate without widening list payloads.

create or replace function public.nycif_events_reader_v1()
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
set statement_timeout = '10s'
as $$
declare
  v_window_start date := (now() at time zone 'America/New_York')::date;
  v_window_end date := ((now() at time zone 'America/New_York')::date + 7);
  v_window_start_ts timestamptz;
  v_window_end_exclusive_ts timestamptz;
  v_feature_count integer := 0;
  v_exact_marker_count integer := 0;
  v_reader_metadata_count integer := 0;
  v_features jsonb := '[]'::jsonb;
  v_payload jsonb;
  v_feature_bytes integer := 0;
  v_warning_event_count constant integer := 15000;
  v_hard_event_count constant integer := 20000;
  v_warning_bytes constant integer := 12582912;
  v_hard_bytes constant integer := 16777216;
begin
  v_window_start_ts := v_window_start::timestamp at time zone 'America/New_York';
  v_window_end_exclusive_ts := (v_window_end + 1)::timestamp at time zone 'America/New_York';

  with reader_rows as (
    select
      o.occurrence_id,
      o.title,
      o.start_at,
      o.end_at,
      o.timezone,
      o.borough,
      o.display_location,
      o.lat,
      o.lng,
      o.public_category,
      o.public_subtype,
      o.map_ready,
      o.metadata,
      coalesce(q.quality_status, 'VALID') as quality_status,
      coalesce(q.public_display_status, 'FULL_TIME') as public_display_status,
      o.metadata->'reader' as reader,
      src.source_dataset,
      src.source_event_id,
      (
        o.start_at is not null
        and o.start_at < v_window_end_exclusive_ts
        and greatest(coalesce(o.end_at, o.start_at), o.start_at) >= v_window_start_ts
      ) as in_reader_window
    from public.event_occurrences o
    left join public.event_quality q
      on q.occurrence_id = o.occurrence_id
    left join lateral (
      select s.source_dataset, s.source_event_id
      from public.event_sources s
      where s.occurrence_id = o.occurrence_id
        and s.source_active
      order by s.event_source_id
      limit 1
    ) src on true
    where o.source_active
      and o.status = 'active'
      and coalesce(q.quality_status, 'VALID') <> 'INVALID'
      and coalesce(o.metadata->'reader'->>'event_role', 'public_event') = 'public_event'
      and coalesce(o.metadata->'reader'->>'parent_event_id', '') = ''
      and coalesce(
        o.metadata->'reader'->>'display_disposition',
        case when o.map_ready then 'standalone_public_event' else 'list_only' end
      ) in ('standalone_public_event', 'list_only')
      and (
        o.map_ready
        or (
          o.start_at is not null
          and o.start_at < v_window_end_exclusive_ts
          and greatest(coalesce(o.end_at, o.start_at), o.start_at) >= v_window_start_ts
        )
      )
  ), prepared as (
    select
      r.*,
      coalesce(
        nullif(r.reader->>'map_eligibility_state', ''),
        case when r.map_ready then 'MAP_READY' else 'LIST_ONLY' end
      ) as map_eligibility_state,
      case
        when lower(coalesce(r.reader->>'certified_pin', '')) in ('true', 'false')
          then (r.reader->>'certified_pin')::boolean
        else r.map_ready
      end as certified_pin,
      coalesce(
        nullif(r.reader->>'display_disposition', ''),
        case when r.map_ready then 'standalone_public_event' else 'list_only' end
      ) as display_disposition,
      coalesce(nullif(r.reader->>'event_role', ''), 'public_event') as event_role,
      coalesce(nullif(r.reader->>'source_dataset', ''), r.source_dataset) as reader_source_dataset,
      coalesce(nullif(r.reader->>'source_event_id', ''), r.source_event_id) as reader_source_event_id,
      case
        when r.map_ready
          and r.lat is not null
          and r.lng is not null
          and r.lat between 40.35 and 41.05
          and r.lng between -74.35 and -73.65
          and coalesce(r.public_display_status, 'FULL_TIME') <> 'LIST_ONLY'
          and coalesce(
            nullif(r.reader->>'map_eligibility_state', ''),
            case when r.map_ready then 'MAP_READY' else 'LIST_ONLY' end
          ) = 'MAP_READY'
          and case
            when lower(coalesce(r.reader->>'certified_pin', '')) in ('true', 'false')
              then (r.reader->>'certified_pin')::boolean
            else r.map_ready
          end
          and coalesce(nullif(r.reader->>'location_authority', ''), '') = 'projector_v3_semantic_map_decision'
        then true
        else false
      end as exact_pin
    from reader_rows r
  ), visible as (
    select *
    from prepared
    where exact_pin or in_reader_window
  )
  select
    count(*),
    count(*) filter (where exact_pin),
    count(*) filter (where jsonb_typeof(reader) = 'object'),
    coalesce(
      jsonb_agg(
        jsonb_build_object(
          'type', 'Feature',
          'geometry', case
            when exact_pin then jsonb_build_object(
              'type', 'Point',
              'coordinates', jsonb_build_array(lng, lat)
            )
            else null
          end,
          'properties', jsonb_strip_nulls(jsonb_build_object(
            'id', occurrence_id,
            'occurrence_id', occurrence_id,
            'title', title,
            'category', public_category,
            'public_subtype', public_subtype,
            'borough', borough,
            'neighborhood', reader->>'neighborhood',
            'location', display_location,
            'event_date', to_char(start_at at time zone 'America/New_York', 'YYYY-MM-DD'),
            'start_date_time', to_char(start_at at time zone 'America/New_York', 'YYYY-MM-DD"T"HH24:MI:SS'),
            'end_date_time', case
              when end_at is null then null
              else to_char(end_at at time zone 'America/New_York', 'YYYY-MM-DD"T"HH24:MI:SS')
            end,
            'timezone', timezone,
            'significance', reader->>'significance',
            'public_url', reader->>'public_url',
            'source_dataset', reader_source_dataset,
            'source_event_id', reader_source_event_id,
            'map_eligibility_state', map_eligibility_state,
            'certified_pin', exact_pin,
            'location_authority', reader->>'location_authority',
            'event_role', event_role,
            'display_disposition', display_disposition,
            'is_major', case
              when lower(coalesce(reader->>'is_major', '')) in ('true', 'false')
                then (reader->>'is_major')::boolean
              else null
            end,
            'photo_pick', case
              when lower(coalesce(reader->>'photo_pick', '')) in ('true', 'false')
                then (reader->>'photo_pick')::boolean
              else null
            end
          ))
        )
        order by start_at, title, occurrence_id
      ),
      '[]'::jsonb
    )
  into v_feature_count, v_exact_marker_count, v_reader_metadata_count, v_features
  from visible;

  if v_feature_count > v_hard_event_count then
    raise exception 'NYCIF_READER_EVENT_BUDGET_EXCEEDED count=% hard_limit=%',
      v_feature_count, v_hard_event_count;
  end if;

  v_feature_bytes := octet_length(v_features::text);
  if v_feature_bytes > v_hard_bytes then
    raise exception 'NYCIF_READER_BYTE_BUDGET_EXCEEDED bytes=% hard_limit=%',
      v_feature_bytes, v_hard_bytes;
  end if;

  v_payload := jsonb_build_object(
    'type', 'FeatureCollection',
    'metadata', jsonb_build_object(
      'schema_version', 'nycif-supabase-reader-v1',
      'authority', 'supabase_event_authority',
      'generated_at_utc', to_char(now() at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'),
      'reader_window_days', 7,
      'reader_window_start', v_window_start,
      'reader_window_end', v_window_end,
      'marker_scope', 'all_certified_markers',
      'list_scope', 'today_plus_7',
      'reader_safe_event_count', v_feature_count,
      'exact_marker_count', v_exact_marker_count,
      'reader_metadata_complete_count', v_reader_metadata_count,
      'reader_metadata_fallback_count', v_feature_count - v_reader_metadata_count,
      'feature_payload_bytes', v_feature_bytes,
      'resource_warning', (
        v_feature_count > v_warning_event_count
        or v_feature_bytes > v_warning_bytes
      ),
      'warning_event_count', v_warning_event_count,
      'hard_event_count', v_hard_event_count,
      'warning_feature_bytes', v_warning_bytes,
      'hard_feature_bytes', v_hard_bytes,
      'event_data_origin', 'supabase_only'
    ),
    'features', v_features
  );

  return v_payload;
end;
$$;

revoke all on function public.nycif_events_reader_v1() from public;
revoke all on function public.nycif_events_reader_v1() from anon;
revoke all on function public.nycif_events_reader_v1() from authenticated;
grant execute on function public.nycif_events_reader_v1() to anon;
grant execute on function public.nycif_events_reader_v1() to authenticated;
grant execute on function public.nycif_events_reader_v1() to service_role;
