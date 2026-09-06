-- Tonight is late afternoon through late night in America/New_York.
-- Product authority: field-desk isTonightEvent (hour >= 17) and iOS
-- NYCCalendar.startsTonightOrLater (hour >= 17). Do not use overlap for
-- p_mode=tonight — multi-day street permits would flood the evening list.
-- Public clients keep reading nycif-native-map-feed with a publishable key.

create or replace function public.nycif_native_map_feed_rows(
  p_mode text default 'now'::text,
  p_date text default null::text
)
returns table(
  occurrence_id text,
  title text,
  start_at timestamp with time zone,
  end_at timestamp with time zone,
  timezone text,
  borough text,
  location_id text,
  display_location text,
  lat double precision,
  lng double precision,
  public_category text,
  public_subtype text,
  certified_pin boolean,
  map_eligibility_state text,
  location_authority text,
  display_disposition text,
  is_major boolean,
  photo_pick boolean,
  significance text,
  source_dataset text,
  source_event_id text,
  public_url text
)
language sql
stable
set search_path to ''
set statement_timeout to '12s'
as $function$
  with bounds as (
    select
      ((now() at time zone 'America/New_York')::date::timestamp at time zone 'America/New_York') as today_start,
      (((now() at time zone 'America/New_York')::date + 1)::timestamp at time zone 'America/New_York') as tomorrow_start,
      (((now() at time zone 'America/New_York')::date + 8)::timestamp at time zone 'America/New_York') as seven_end,
      (((now() at time zone 'America/New_York')::date::timestamp + interval '17 hours') at time zone 'America/New_York') as tonight_start,
      case when coalesce(p_date,'') ~ '^\d{4}-\d{2}-\d{2}$'
        then ((p_date::date)::timestamp at time zone 'America/New_York') else null end as day_start
  ),
  mode_bound as (
    select
      lower(coalesce(p_mode,'now')) as mode,
      case
        when lower(coalesce(p_mode,'now')) in ('seven','7d') then b.tomorrow_start
        when lower(coalesce(p_mode,'now')) = 'day' and b.day_start is not null then b.day_start
        when lower(coalesce(p_mode,'now')) = 'tonight' then b.tonight_start
        else b.today_start
      end as window_start,
      case
        when lower(coalesce(p_mode,'now')) in ('seven','7d') then b.seven_end
        when lower(coalesce(p_mode,'now')) = 'day' and b.day_start is not null then b.day_start + interval '1 day'
        else b.tomorrow_start
      end as window_end
    from bounds b
  )
  select eo.occurrence_id, eo.title, eo.start_at, eo.end_at, eo.timezone, eo.borough, eo.location_id,
    eo.display_location, eo.lat, eo.lng, eo.public_category, eo.public_subtype,
    coalesce((eo.metadata->'reader'->>'certified_pin')::boolean, eo.map_ready),
    coalesce(eo.metadata->'reader'->>'map_eligibility_state', case when eo.map_ready and eo.lat is not null then 'MAP_READY' else 'LIST_ONLY' end),
    coalesce(eo.metadata->'reader'->>'location_authority', 'supabase_event_occurrences'),
    coalesce(eo.metadata->'reader'->>'display_disposition', case when eo.map_ready then 'MAP' else 'LIST_ONLY' end),
    coalesce((eo.metadata->'reader'->>'is_major')::boolean, eo.editorial_priority = any (array['high','urgent'])),
    coalesce((eo.metadata->'reader'->>'photo_pick')::boolean, false),
    coalesce(eo.metadata->'reader'->>'significance', eo.editorial_priority),
    eo.metadata->'reader'->>'source_dataset',
    eo.metadata->'reader'->>'source_event_id',
    src.source_url
  from public.event_occurrences eo
  cross join mode_bound m
  left join lateral (
    select es.source_url from public.event_sources es
    where es.occurrence_id=eo.occurrence_id and es.source_active=true and es.source_url is not null
    order by es.source_last_seen desc nulls last, es.updated_at desc, es.event_source_id desc limit 1
  ) src on true
  where eo.source_active=true and eo.status='active'
    and coalesce(eo.event_display_status,'') <> all (array['CANCELLED','COMPLETED'])
    and coalesce((eo.metadata->'reader')->>'event_role','public_event') <> 'special_calendar_event'
    and eo.title !~* '^\s*(canceled|cancelled)\s*:'
    and public.nycif_native_map_row_visible(eo.display_location, eo.borough, eo.metadata->'reader'->>'source_dataset')
    and (eo.lat is null or public.nycif_coords_match_borough(eo.lat, eo.lng, eo.borough))
    and (
      (
        m.mode = 'tonight'
        and eo.start_at >= m.window_start
        and eo.start_at < m.window_end
      )
      or (
        m.mode <> 'tonight'
        and coalesce(eo.end_at, eo.start_at + interval '3 hours') >= m.window_start
        and eo.start_at < m.window_end
      )
    )
  order by eo.start_at, eo.occurrence_id
$function$;

create or replace function public.nycif_native_map_feed_stats()
returns jsonb
language sql
stable
set search_path to ''
set statement_timeout to '8s'
as $function$
  with bounds as (
    select
      ((now() at time zone 'America/New_York')::date::timestamp at time zone 'America/New_York') as today_start,
      (((now() at time zone 'America/New_York')::date + 1)::timestamp at time zone 'America/New_York') as tomorrow_start,
      (((now() at time zone 'America/New_York')::date + 8)::timestamp at time zone 'America/New_York') as seven_end,
      (((now() at time zone 'America/New_York')::date::timestamp + interval '17 hours') at time zone 'America/New_York') as tonight_start
  ),
  base as (
    select eo.start_at, coalesce(eo.end_at, eo.start_at + interval '3 hours') as end_at,
      coalesce((eo.metadata->'reader'->>'certified_pin')::boolean, eo.map_ready) as certified_pin,
      coalesce(eo.metadata->'reader'->>'map_eligibility_state', case when eo.map_ready and eo.lat is not null then 'MAP_READY' else 'LIST_ONLY' end) as map_eligibility_state,
      eo.lat, eo.lng
    from public.event_occurrences eo
    cross join bounds b
    where eo.source_active=true and eo.status='active'
      and coalesce(eo.event_display_status,'') <> all (array['CANCELLED','COMPLETED'])
      and coalesce((eo.metadata->'reader')->>'event_role','public_event') <> 'special_calendar_event'
      and eo.title !~* '^\s*(canceled|cancelled)\s*:'
      and public.nycif_native_map_row_visible(eo.display_location, eo.borough, eo.metadata->'reader'->>'source_dataset')
      and (eo.lat is null or public.nycif_coords_match_borough(eo.lat, eo.lng, eo.borough))
      and coalesce(eo.end_at, eo.start_at + interval '3 hours') >= b.today_start
      and eo.start_at < b.seven_end
  ),
  mapped as (
    select start_at, end_at,
      (certified_pin=true and map_eligibility_state='MAP_READY' and lat is not null and lng is not null
       and lat>=40.45 and lat<=40.95 and lng>=-74.30 and lng<=-73.65) as is_mapped
    from base
  )
  select jsonb_build_object(
    'now', jsonb_build_object(
      'total', count(*) filter (where start_at < (select tomorrow_start from bounds) and end_at >= (select today_start from bounds)),
      'mapped', count(*) filter (where start_at < (select tomorrow_start from bounds) and end_at >= (select today_start from bounds) and is_mapped)
    ),
    'tonight', jsonb_build_object(
      'total', count(*) filter (where start_at >= (select tonight_start from bounds) and start_at < (select tomorrow_start from bounds)),
      'mapped', count(*) filter (where start_at >= (select tonight_start from bounds) and start_at < (select tomorrow_start from bounds) and is_mapped)
    ),
    'seven', jsonb_build_object(
      'total', count(*) filter (where start_at < (select seven_end from bounds) and end_at >= (select tomorrow_start from bounds)),
      'mapped', count(*) filter (where start_at < (select seven_end from bounds) and end_at >= (select tomorrow_start from bounds) and is_mapped)
    )
  ) from mapped
$function$;

comment on function public.nycif_native_map_feed_rows(text, text) is
  'Native map feed rows. mode=tonight is start_at >= today 17:00 America/New_York through tomorrow midnight. Not an overlap window.';

comment on function public.nycif_native_map_feed_stats() is
  'Native map feed counts. tonight uses the same 17:00 America/New_York start-time bound as nycif_native_map_feed_rows.';
