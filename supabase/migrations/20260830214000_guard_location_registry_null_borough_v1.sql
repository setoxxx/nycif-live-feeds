-- Hotfix the durable location-registry RPC so one geography row that cannot
-- satisfy locations.borough NOT NULL cannot abort the full validated batch.
-- The original implementation remains as a private core function; this wrapper
-- filters only missing/blank borough rows, reports the skip count, and preserves
-- every existing exact-vs-approximate safety rule in the core.

alter function public.sync_location_registry_v1(jsonb)
  rename to sync_location_registry_v1_core_v1;

revoke all on function public.sync_location_registry_v1_core_v1(jsonb) from public;
revoke all on function public.sync_location_registry_v1_core_v1(jsonb) from anon;
revoke all on function public.sync_location_registry_v1_core_v1(jsonb) from authenticated;
revoke all on function public.sync_location_registry_v1_core_v1(jsonb) from service_role;

create or replace function public.sync_location_registry_v1(payload jsonb)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  filtered_locations jsonb;
  filtered_payload jsonb;
  result jsonb;
  skipped_missing_borough integer := 0;
begin
  if jsonb_typeof(payload) <> 'object'
     or jsonb_typeof(payload->'locations') <> 'array'
     or jsonb_typeof(payload->'aliases') <> 'array' then
    raise exception 'invalid location registry payload';
  end if;

  select
    coalesce(jsonb_agg(item), '[]'::jsonb),
    count(*) filter (
      where nullif(btrim(coalesce(item->>'borough', '')), '') is null
    )::integer
  into filtered_locations, skipped_missing_borough
  from jsonb_array_elements(payload->'locations') as item
  where nullif(btrim(coalesce(item->>'borough', '')), '') is not null;

  -- COUNT with the filtered WHERE cannot see rejected rows, so compute the
  -- rejected count independently from the original array.
  select count(*)::integer
  into skipped_missing_borough
  from jsonb_array_elements(payload->'locations') as item
  where nullif(btrim(coalesce(item->>'borough', '')), '') is null;

  filtered_payload := jsonb_set(payload, '{locations}', filtered_locations, false);
  result := public.sync_location_registry_v1_core_v1(filtered_payload);

  return result || jsonb_build_object(
    'skipped_missing_borough', skipped_missing_borough,
    'input_location_count', jsonb_array_length(payload->'locations'),
    'accepted_location_count', jsonb_array_length(filtered_locations)
  );
end;
$$;

revoke all on function public.sync_location_registry_v1(jsonb) from public;
revoke all on function public.sync_location_registry_v1(jsonb) from anon;
revoke all on function public.sync_location_registry_v1(jsonb) from authenticated;
grant execute on function public.sync_location_registry_v1(jsonb) to service_role;

comment on function public.sync_location_registry_v1(jsonb) is
  'Service-role durable location registry sync. Missing/blank borough geography is skipped and counted; exact location authority can never be downgraded by approximate input.';
