-- Phone feed window: read-only rows for nycif-native-map-feed.
-- Do not write occurrences, do not expire, and do not promote coordinates.

create or replace function public.nycif_native_map_feed_rows(p_mode text default 'now')
returns table (
  occurrence_id text,
  title text,
  start_at timestamptz,
  end_at timestamptz,
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
security invoker
set search_path = ''
set statement_timeout = '12s'
as $$
  with bounds as (
    select
      ((now() at time zone 'America/New_York')::date::timestamp at time zone 'America/New_York') as today_start,
      (((now() at time zone 'America/New_York')::date + 1)::timestamp at time zone 'America/New_York') as tomorrow_start,
      (((now() at time zone 'America/New_York')::date + 7)::timestamp at time zone 'America/New_York') as seven_end
  ),
  mode_bound as (
    select case
      when lower(coalesce(p_mode, 'now')) in ('seven', '7d') then seven_end
      else tomorrow_start
    end as start_before
    from bounds
  )
  select
    eo.occurrence_id,
    eo.title,
    eo.start_at,
    eo.end_at,
    eo.timezone,
    eo.borough,
    eo.location_id,
    eo.display_location,
    eo.lat,
    eo.lng,
    eo.public_category,
    eo.public_subtype,
    coalesce((eo.metadata -> 'reader' ->> 'certified_pin')::boolean, eo.map_ready) as certified_pin,
    coalesce(
      eo.metadata -> 'reader' ->> 'map_eligibility_state',
      case
        when eo.map_ready and eo.lat is not null and eo.lng is not null then 'MAP_READY'
        else 'LIST_ONLY'
      end
    ) as map_eligibility_state,
    coalesce(
      eo.metadata -> 'reader' ->> 'location_authority',
      eo.metadata ->> 'location_authority',
      'supabase_event_occurrences'
    ) as location_authority,
    coalesce(
      eo.metadata -> 'reader' ->> 'display_disposition',
      case when eo.map_ready then 'MAP' else 'LIST_ONLY' end
    ) as display_disposition,
    coalesce(
      (eo.metadata -> 'reader' ->> 'is_major')::boolean,
      eo.editorial_priority = any (array['high', 'urgent'])
    ) as is_major,
    coalesce((eo.metadata -> 'reader' ->> 'photo_pick')::boolean, false) as photo_pick,
    coalesce(eo.metadata -> 'reader' ->> 'significance', eo.editorial_priority) as significance,
    eo.metadata -> 'reader' ->> 'source_dataset' as source_dataset,
    eo.metadata -> 'reader' ->> 'source_event_id' as source_event_id,
    src.source_url as public_url
  from public.event_occurrences eo
  cross join bounds b
  cross join mode_bound m
  left join lateral (
    select es.source_url
    from public.event_sources es
    where es.occurrence_id = eo.occurrence_id
      and es.source_active = true
      and es.source_url is not null
    order by es.source_last_seen desc nulls last, es.updated_at desc, es.event_source_id desc
    limit 1
  ) src on true
  where eo.source_active = true
    and eo.status = 'active'
    and coalesce(eo.event_display_status, '') <> all (array['CANCELLED', 'COMPLETED'])
    and coalesce((eo.metadata -> 'reader') ->> 'event_role', 'public_event') <> 'special_calendar_event'
    and eo.title !~* '^\s*(canceled|cancelled)\s*:'
    and coalesce(eo.end_at, eo.start_at + interval '3 hours') >= b.today_start
    and eo.start_at < m.start_before
  order by eo.start_at asc, eo.occurrence_id asc
$$;

create or replace function public.nycif_native_map_feed_stats()
returns jsonb
language sql
stable
security invoker
set search_path = ''
set statement_timeout = '8s'
as $$
  with bounds as (
    select
      ((now() at time zone 'America/New_York')::date::timestamp at time zone 'America/New_York') as today_start,
      (((now() at time zone 'America/New_York')::date + 1)::timestamp at time zone 'America/New_York') as tomorrow_start,
      (((now() at time zone 'America/New_York')::date + 7)::timestamp at time zone 'America/New_York') as seven_end
  ),
  base as (
    select
      eo.start_at,
      coalesce(
        (eo.metadata -> 'reader' ->> 'certified_pin')::boolean,
        eo.map_ready
      ) as certified_pin,
      coalesce(
        eo.metadata -> 'reader' ->> 'map_eligibility_state',
        case
          when eo.map_ready and eo.lat is not null and eo.lng is not null then 'MAP_READY'
          else 'LIST_ONLY'
        end
      ) as map_eligibility_state,
      eo.lat,
      eo.lng
    from public.event_occurrences eo
    cross join bounds b
    where eo.source_active = true
      and eo.status = 'active'
      and coalesce(eo.event_display_status, '') <> all (array['CANCELLED', 'COMPLETED'])
      and coalesce((eo.metadata -> 'reader') ->> 'event_role', 'public_event') <> 'special_calendar_event'
      and eo.title !~* '^\s*(canceled|cancelled)\s*:'
      and coalesce(eo.end_at, eo.start_at + interval '3 hours') >= b.today_start
      and eo.start_at < b.seven_end
  ),
  mapped as (
    select
      start_at,
      (
        certified_pin = true
        and map_eligibility_state = 'MAP_READY'
        and lat is not null and lng is not null
        and lat >= 40.45 and lat <= 40.95
        and lng >= -74.30 and lng <= -73.65
      ) as is_mapped
    from base
  )
  select jsonb_build_object(
    'now', jsonb_build_object(
      'total', count(*) filter (where start_at < (select tomorrow_start from bounds)),
      'mapped', count(*) filter (where start_at < (select tomorrow_start from bounds) and is_mapped)
    ),
    'seven', jsonb_build_object(
      'total', count(*),
      'mapped', count(*) filter (where is_mapped)
    )
  )
  from mapped
$$;

revoke all on function public.nycif_native_map_feed_rows(text) from public;
revoke all on function public.nycif_native_map_feed_rows(text) from anon;
revoke all on function public.nycif_native_map_feed_rows(text) from authenticated;
grant execute on function public.nycif_native_map_feed_rows(text) to service_role;

revoke all on function public.nycif_native_map_feed_stats() from public;
revoke all on function public.nycif_native_map_feed_stats() from anon;
revoke all on function public.nycif_native_map_feed_stats() from authenticated;
grant execute on function public.nycif_native_map_feed_stats() to service_role;

comment on function public.nycif_native_map_feed_rows(text) is
  'Read-only native map feed window. p_mode now/tonight = today overlap; seven = next 7 days. Never expires or promotes.';

comment on function public.nycif_native_map_feed_stats() is
  'Read-only native map feed counts for today overlap and the 7-day window.';
