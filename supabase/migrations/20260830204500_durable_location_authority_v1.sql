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
