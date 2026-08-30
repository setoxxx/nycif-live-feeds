alter table public.locations
  add column if not exists latitude double precision,
  add column if not exists longitude double precision,
  add column if not exists precision text,
  add column if not exists location_authority text,
  add column if not exists confidence numeric,
  add column if not exists updated_at timestamptz not null default now(),
  add column if not exists metadata jsonb not null default '{}'::jsonb;

alter table public.location_aliases
  add column if not exists source_dataset text,
  add column if not exists metadata jsonb not null default '{}'::jsonb;

create index if not exists locations_source_cemsid_idx
  on public.locations(source_cemsid) where source_cemsid is not null;
create index if not exists locations_canonical_name_idx
  on public.locations(canonical_name);
create index if not exists locations_lat_lng_idx
  on public.locations(latitude, longitude)
  where latitude is not null and longitude is not null;
create index if not exists location_aliases_normalized_dataset_idx
  on public.location_aliases(normalized_alias, source_dataset);

alter table public.locations drop constraint if exists locations_coordinate_pair_ck;
alter table public.locations add constraint locations_coordinate_pair_ck
  check (
    (latitude is null and longitude is null)
    or (latitude between -90 and 90 and longitude between -180 and 180)
  );

alter table public.locations drop constraint if exists locations_precision_ck;
alter table public.locations add constraint locations_precision_ck
  check (precision is null or precision in ('exact','approximate','route','none'));

comment on column public.locations.precision is
  'Location precision class only; approximate rows must never imply certified exact event pins.';
comment on column public.locations.location_authority is
  'Authority that justified this location geometry or identity.';
comment on column public.location_aliases.source_dataset is
  'Source dataset that supplied or observed this alias, when known.';

create or replace function public.sync_location_registry_v1(payload jsonb)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  location_rows integer := 0;
  alias_rows integer := 0;
begin
  if jsonb_typeof(payload) <> 'object'
     or jsonb_typeof(payload->'locations') <> 'array'
     or jsonb_typeof(payload->'aliases') <> 'array' then
    raise exception 'invalid location registry payload';
  end if;

  insert into public.locations (
    location_id, borough, canonical_name, canonical_full_name,
    facility_name, location_type, facility_type, source_cemsid,
    street_address, street_segment, cross_streets, review_required,
    latitude, longitude, precision, location_authority, confidence,
    last_seen, updated_at, metadata
  )
  select
    x.location_id, x.borough, x.canonical_name, x.canonical_full_name,
    x.facility_name, x.location_type, x.facility_type, x.source_cemsid,
    x.street_address, x.street_segment, x.cross_streets,
    coalesce(x.review_required, false),
    x.latitude, x.longitude, x.precision, x.location_authority, x.confidence,
    coalesce(x.last_seen, now()), now(), coalesce(x.metadata, '{}'::jsonb)
  from jsonb_to_recordset(payload->'locations') as x(
    location_id text,
    borough text,
    canonical_name text,
    canonical_full_name text,
    facility_name text,
    location_type text,
    facility_type text,
    source_cemsid text,
    street_address text,
    street_segment text,
    cross_streets text,
    review_required boolean,
    latitude double precision,
    longitude double precision,
    precision text,
    location_authority text,
    confidence numeric,
    last_seen timestamptz,
    metadata jsonb
  )
  where x.location_id is not null
    and x.canonical_name is not null
    and x.precision in ('exact', 'approximate')
    and x.latitude between -90 and 90
    and x.longitude between -180 and 180
  on conflict (location_id) do update
  set
    borough = coalesce(excluded.borough, locations.borough),
    canonical_name = coalesce(excluded.canonical_name, locations.canonical_name),
    canonical_full_name = coalesce(excluded.canonical_full_name, locations.canonical_full_name),
    facility_name = coalesce(excluded.facility_name, locations.facility_name),
    location_type = coalesce(excluded.location_type, locations.location_type),
    facility_type = coalesce(excluded.facility_type, locations.facility_type),
    source_cemsid = coalesce(excluded.source_cemsid, locations.source_cemsid),
    street_address = coalesce(excluded.street_address, locations.street_address),
    street_segment = coalesce(excluded.street_segment, locations.street_segment),
    cross_streets = coalesce(excluded.cross_streets, locations.cross_streets),
    review_required = case
      when locations.precision = 'exact' then false
      else excluded.review_required
    end,
    latitude = case
      when locations.precision = 'exact' and excluded.precision = 'approximate' then locations.latitude
      else excluded.latitude
    end,
    longitude = case
      when locations.precision = 'exact' and excluded.precision = 'approximate' then locations.longitude
      else excluded.longitude
    end,
    precision = case
      when locations.precision = 'exact' then 'exact'
      else excluded.precision
    end,
    location_authority = case
      when locations.precision = 'exact' and excluded.precision = 'approximate' then locations.location_authority
      else excluded.location_authority
    end,
    confidence = case
      when locations.precision = 'exact' and excluded.precision = 'approximate' then locations.confidence
      else coalesce(excluded.confidence, locations.confidence)
    end,
    last_seen = greatest(coalesce(locations.last_seen, excluded.last_seen), excluded.last_seen),
    updated_at = now(),
    metadata = locations.metadata || excluded.metadata;
  get diagnostics location_rows = row_count;

  insert into public.location_aliases (
    location_id, raw_alias, normalized_alias, occurrence_count,
    first_seen, last_seen, source_dataset, metadata
  )
  select
    x.location_id, x.raw_alias, x.normalized_alias,
    greatest(coalesce(x.occurrence_count, 1), 1),
    coalesce(x.first_seen, now()), coalesce(x.last_seen, now()),
    x.source_dataset, coalesce(x.metadata, '{}'::jsonb)
  from jsonb_to_recordset(payload->'aliases') as x(
    location_id text,
    raw_alias text,
    normalized_alias text,
    occurrence_count integer,
    first_seen timestamptz,
    last_seen timestamptz,
    source_dataset text,
    metadata jsonb
  )
  where x.location_id is not null
    and nullif(x.normalized_alias, '') is not null
    and exists (select 1 from public.locations l where l.location_id = x.location_id)
  on conflict (location_id, normalized_alias) do update
  set
    raw_alias = excluded.raw_alias,
    occurrence_count = greatest(location_aliases.occurrence_count, excluded.occurrence_count),
    first_seen = least(location_aliases.first_seen, excluded.first_seen),
    last_seen = greatest(location_aliases.last_seen, excluded.last_seen),
    source_dataset = coalesce(excluded.source_dataset, location_aliases.source_dataset),
    metadata = location_aliases.metadata || excluded.metadata;
  get diagnostics alias_rows = row_count;

  return jsonb_build_object(
    'qa_pass', true,
    'location_rows_touched', location_rows,
    'alias_rows_touched', alias_rows,
    'exact_downgrade_allowed', false
  );
end;
$$;

revoke all on function public.sync_location_registry_v1(jsonb) from public;
revoke all on function public.sync_location_registry_v1(jsonb) from anon;
revoke all on function public.sync_location_registry_v1(jsonb) from authenticated;
grant execute on function public.sync_location_registry_v1(jsonb) to service_role;
