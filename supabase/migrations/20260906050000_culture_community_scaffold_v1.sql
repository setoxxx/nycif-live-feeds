-- Culture community scaffold v1 (DRAFT — review before apply).
-- Does not enable publication. Does not seed storefronts.
-- Idempotent: safe if culture_place_beta_v1 / culture_reader_settings
-- already exist in project oggwpvdirkrnzoolparx.
--
-- Do not apply to production until a human confirms the live table
-- shapes match these IF NOT EXISTS / ADD COLUMN statements.

-- ---------------------------------------------------------------------------
-- Reader gates (singleton). business_publication_enabled stays false.
-- ---------------------------------------------------------------------------
create table if not exists public.culture_reader_settings (
  id smallint primary key default 1,
  business_publication_enabled boolean not null default false,
  civic_publication_enabled boolean not null default false,
  calendar_publication_enabled boolean not null default false,
  nypd_layer_enabled boolean not null default false,
  fdny_layer_enabled boolean not null default false,
  shelter_layer_enabled boolean not null default false,
  pet_care_layer_enabled boolean not null default false,
  resource_layer_enabled boolean not null default false,
  updated_at timestamptz not null default now(),
  constraint culture_reader_settings_singleton check (id = 1)
);

alter table public.culture_reader_settings
  add column if not exists civic_publication_enabled boolean not null default false;
alter table public.culture_reader_settings
  add column if not exists calendar_publication_enabled boolean not null default false;
alter table public.culture_reader_settings
  add column if not exists nypd_layer_enabled boolean not null default false;
alter table public.culture_reader_settings
  add column if not exists fdny_layer_enabled boolean not null default false;
alter table public.culture_reader_settings
  add column if not exists shelter_layer_enabled boolean not null default false;
alter table public.culture_reader_settings
  add column if not exists pet_care_layer_enabled boolean not null default false;
alter table public.culture_reader_settings
  add column if not exists resource_layer_enabled boolean not null default false;
alter table public.culture_reader_settings
  add column if not exists updated_at timestamptz not null default now();

insert into public.culture_reader_settings (id)
values (1)
on conflict (id) do nothing;

-- Force every gate false. This draft must never enable publication.
update public.culture_reader_settings
set
  business_publication_enabled = false,
  civic_publication_enabled = false,
  calendar_publication_enabled = false,
  nypd_layer_enabled = false,
  fdny_layer_enabled = false,
  shelter_layer_enabled = false,
  pet_care_layer_enabled = false,
  resource_layer_enabled = false,
  updated_at = now()
where id = 1;

-- ---------------------------------------------------------------------------
-- Curated / beta Culture places (reader contract + place_kind).
-- ---------------------------------------------------------------------------
create table if not exists public.culture_place_beta_v1 (
  business_id text primary key,
  business_name text not null,
  address text,
  community_district text,
  borough text,
  lat double precision,
  lng double precision,
  cultural_tags text[] not null default '{}',
  dietary_tags text[] not null default '{}',
  review_status text not null default 'pending',
  confidence text,
  area_ids text[] not null default '{}',
  matched_tags text[] not null default '{}',
  reason_codes text[] not null default '{}',
  is_sample boolean not null default false,
  feed_version text,
  place_kind text not null default 'storefront',
  qualification_hint text,
  map_eligible boolean not null default false,
  promotion_allowed boolean not null default false,
  manual_review_status text not null default 'pending',
  manual_reviewer text,
  manual_reviewed_at_utc timestamptz,
  approval_decision_reason text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.culture_place_beta_v1
  add column if not exists is_sample boolean not null default false;
alter table public.culture_place_beta_v1
  add column if not exists review_status text not null default 'pending';
alter table public.culture_place_beta_v1
  add column if not exists place_kind text;
alter table public.culture_place_beta_v1
  add column if not exists qualification_hint text;
alter table public.culture_place_beta_v1
  add column if not exists map_eligible boolean not null default false;
alter table public.culture_place_beta_v1
  add column if not exists promotion_allowed boolean not null default false;
alter table public.culture_place_beta_v1
  add column if not exists borough text;
alter table public.culture_place_beta_v1
  add column if not exists manual_review_status text not null default 'pending';
alter table public.culture_place_beta_v1
  add column if not exists manual_reviewer text;
alter table public.culture_place_beta_v1
  add column if not exists manual_reviewed_at_utc timestamptz;
alter table public.culture_place_beta_v1
  add column if not exists approval_decision_reason text;

update public.culture_place_beta_v1
set place_kind = 'storefront'
where place_kind is null or btrim(place_kind) = '';

alter table public.culture_place_beta_v1
  alter column place_kind set default 'storefront';
alter table public.culture_place_beta_v1
  alter column place_kind set not null;

alter table public.culture_place_beta_v1 drop constraint if exists culture_place_beta_v1_kind_ck;
alter table public.culture_place_beta_v1 add constraint culture_place_beta_v1_kind_ck
  check (place_kind in (
    'storefront', 'worship', 'civic_nypd', 'civic_fdny',
    'shelter', 'pet_care', 'resource'
  ));

-- Coord box is enforced in validate_before_publish + edge functions.
-- Do not CHECK-constrain existing beta samples; their live shape is unknown.

-- Samples and pending rows cannot be map-eligible.
update public.culture_place_beta_v1
set map_eligible = false, promotion_allowed = false
where is_sample is true
   or coalesce(review_status, '') is distinct from 'ACCEPTED'
   or promotion_allowed is true
   or map_eligible is true;

-- ---------------------------------------------------------------------------
-- Official civic facilities (NYPD / FDNY / shelters). Not Culture businesses.
-- ---------------------------------------------------------------------------
create table if not exists public.culture_civic_facility_v1 (
  facility_id text primary key,
  place_kind text not null,
  source_dataset text not null,
  source_facility_id text not null,
  display_name text not null,
  address text,
  borough text,
  lat double precision,
  lng double precision,
  emoji text,
  geometry jsonb,
  addressable boolean not null default false,
  map_eligible boolean not null default false,
  review_status text not null default 'pending',
  confidence_reason text,
  manual_review_status text not null default 'pending',
  manual_reviewer text,
  manual_reviewed_at_utc timestamptz,
  approval_decision_reason text,
  promotion_allowed boolean not null default false,
  public_map_modified boolean not null default false,
  location_cache_modified boolean not null default false,
  staged_feed_modified boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint culture_civic_facility_v1_kind_ck check (place_kind in (
    'civic_nypd', 'civic_fdny', 'shelter'
  )),
  constraint culture_civic_facility_v1_coord_pair_ck check (
    (lat is null and lng is null)
    or (lat between 40.4774 and 40.9176 and lng between -74.2591 and -73.7004)
  ),
  constraint culture_civic_facility_v1_source_uid unique (source_dataset, source_facility_id)
);

create index if not exists culture_civic_facility_v1_kind_idx
  on public.culture_civic_facility_v1 (place_kind);

-- ---------------------------------------------------------------------------
-- 8-day Culture calendar (not event_occurrences).
-- ---------------------------------------------------------------------------
create table if not exists public.culture_calendar_occurrence_v1 (
  occurrence_id text primary key,
  calendar_kind text not null,
  title text not null,
  start_at timestamptz not null,
  end_at timestamptz,
  timezone text not null default 'America/New_York',
  borough text,
  display_location text,
  place_id text,
  facility_id text,
  lat double precision,
  lng double precision,
  map_ready boolean not null default false,
  zip_codes text[] not null default '{}',
  waitlist_gated boolean not null default false,
  pin_policy text not null default 'list_only',
  source_name text,
  source_dataset text,
  source_event_id text,
  review_status text not null default 'pending',
  manual_review_status text not null default 'pending',
  manual_reviewer text,
  manual_reviewed_at_utc timestamptz,
  approval_decision_reason text,
  promotion_allowed boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint culture_calendar_occurrence_v1_kind_ck check (calendar_kind in (
    'worship_service', 'cultural_festival', 'aspca_van',
    'community_clinic', 'other'
  )),
  constraint culture_calendar_occurrence_v1_pin_ck check (pin_policy in (
    'certified_pin', 'list_only', 'zip_area_only'
  )),
  constraint culture_calendar_occurrence_v1_map_ck check (
    (map_ready and lat is not null and lng is not null and pin_policy = 'certified_pin')
    or (not map_ready and (lat is null or pin_policy in ('list_only', 'zip_area_only')))
  )
);

create index if not exists culture_calendar_occurrence_v1_start_idx
  on public.culture_calendar_occurrence_v1 (start_at);

-- ---------------------------------------------------------------------------
-- Sanctuary resources (hotlines stay non-map).
-- ---------------------------------------------------------------------------
create table if not exists public.culture_resource_v1 (
  resource_id text primary key,
  resource_kind text not null,
  display_name text not null,
  address text,
  borough text,
  phone text,
  url text,
  languages text[] not null default '{}',
  is_hotline boolean not null default false,
  lat double precision,
  lng double precision,
  map_ready boolean not null default false,
  review_status text not null default 'pending',
  manual_review_status text not null default 'pending',
  manual_reviewer text,
  manual_reviewed_at_utc timestamptz,
  approval_decision_reason text,
  promotion_allowed boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint culture_resource_v1_kind_ck check (resource_kind in (
    'immigration_legal', 'health', 'food_pantry',
    'community_faith', 'know_your_rights', 'multilingual_city'
  )),
  constraint culture_resource_v1_hotline_ck check (
    (is_hotline and map_ready is false and lat is null and lng is null)
    or (not is_hotline)
  )
);

-- ---------------------------------------------------------------------------
-- RLS: fail closed. Clients read through edge functions only.
-- ---------------------------------------------------------------------------
alter table public.culture_reader_settings enable row level security;
alter table public.culture_place_beta_v1 enable row level security;
alter table public.culture_civic_facility_v1 enable row level security;
alter table public.culture_calendar_occurrence_v1 enable row level security;
alter table public.culture_resource_v1 enable row level security;

-- No anon/authenticated SELECT policies on purpose. Edge functions use
-- the service role server-side. Do not add public read policies here.

comment on table public.culture_reader_settings is
  'Culture publication gates. All flags default false. Do not flip in clients.';
comment on table public.culture_civic_facility_v1 is
  'Official NYPD/FDNY/shelter staging. Not Culture storefronts.';
comment on table public.culture_calendar_occurrence_v1 is
  '8-day Culture calendar. Separate from event_occurrences.';
comment on table public.culture_resource_v1 is
  'Sanctuary-city resources. Hotlines are never map_ready.';
