-- Live-safe Culture calendar + civic reader tables for project
-- oggwpvdirkrnzoolparx (nycif-location-authority).
--
-- Why this file exists instead of applying the draft scaffolds as-is:
--   * Live culture_reader_settings.id is text 'v1', not smallint 1.
--     20260906050000 inserts id=1 and would create a second settings row.
--   * Live culture_place_beta_v1 already serves nycif-culture-places.
--     This migration does not alter that table or flip
--     business_publication_enabled.
--   * civic / calendar / resource tables were never applied.
--
-- Gates default OFF. No storefronts. No WordPress. No event_occurrences writes.

-- ---------------------------------------------------------------------------
-- Reader gates on the existing singleton (id = 'v1').
-- ---------------------------------------------------------------------------
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
  add column if not exists help_calendar_publication_enabled boolean not null default false;
alter table public.culture_reader_settings
  add column if not exists blood_layer_enabled boolean not null default false;
alter table public.culture_reader_settings
  add column if not exists mobile_clinic_layer_enabled boolean not null default false;
alter table public.culture_reader_settings
  add column if not exists jobs_layer_enabled boolean not null default false;
alter table public.culture_reader_settings
  add column if not exists college_layer_enabled boolean not null default false;

-- New gates only. Do not assign business_publication_enabled.
update public.culture_reader_settings
set
  civic_publication_enabled = false,
  calendar_publication_enabled = false,
  nypd_layer_enabled = false,
  fdny_layer_enabled = false,
  shelter_layer_enabled = false,
  pet_care_layer_enabled = false,
  resource_layer_enabled = false,
  help_calendar_publication_enabled = false,
  blood_layer_enabled = false,
  mobile_clinic_layer_enabled = false,
  jobs_layer_enabled = false,
  college_layer_enabled = false,
  updated_at = now()
where id = 'v1';

-- ---------------------------------------------------------------------------
-- Official civic facilities (NYPD / FDNY / shelters). Not Culture storefronts.
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
  is_sample boolean not null default false,
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
    'civic_nypd', 'civic_fdny', 'shelter', 'pet_care'
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
-- 8-day Culture / help calendar (not event_occurrences).
-- ---------------------------------------------------------------------------
create table if not exists public.culture_calendar_occurrence_v1 (
  occurrence_id text primary key,
  calendar_kind text not null,
  occurrence_kind text,
  title text not null,
  start_at timestamptz not null,
  end_at timestamptz,
  timezone text not null default 'America/New_York',
  time_precision text,
  borough text,
  display_location text,
  address text,
  place_id text,
  facility_id text,
  lat double precision,
  lng double precision,
  map_ready boolean not null default false,
  zip_codes text[] not null default '{}',
  waitlist_gated boolean not null default false,
  pin_policy text not null default 'list_only',
  chip_id text,
  chip_label text,
  emoji text,
  source_name text,
  source_dataset text,
  source_event_id text,
  source_family text,
  public_url text,
  is_sample boolean not null default false,
  review_status text not null default 'pending',
  manual_review_status text not null default 'pending',
  manual_reviewer text,
  manual_reviewed_at_utc timestamptz,
  approval_decision_reason text,
  promotion_allowed boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint culture_calendar_occurrence_v1_kind_ck check (calendar_kind in (
    'worship_service',
    'cultural_festival',
    'aspca_van',
    'community_clinic',
    'blood_drive',
    'mobile_clinic',
    'job_fair',
    'workshop',
    'pet_mobile',
    'resource_van',
    'other'
  )),
  constraint culture_calendar_occurrence_v1_occurrence_kind_ck check (
    occurrence_kind is null or occurrence_kind in (
      'blood_drive',
      'mobile_clinic',
      'job_fair',
      'workshop',
      'pet_mobile',
      'resource_van',
      'worship_service',
      'cultural_festival',
      'aspca_van',
      'community_clinic',
      'other'
    )
  ),
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
-- Sanctuary resources (hotlines stay non-map). Created for later C5 sheet.
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
alter table public.culture_civic_facility_v1 enable row level security;
alter table public.culture_calendar_occurrence_v1 enable row level security;
alter table public.culture_resource_v1 enable row level security;

comment on table public.culture_civic_facility_v1 is
  'Official NYPD/FDNY/shelter staging. Not Culture storefronts. Reader: nycif-culture-civic.';
comment on table public.culture_calendar_occurrence_v1 is
  '8-day Culture / help calendar. Separate from event_occurrences. Reader: nycif-culture-calendar.';
comment on table public.culture_resource_v1 is
  'Sanctuary-city resources. Hotlines are never map_ready.';
comment on column public.culture_reader_settings.calendar_publication_enabled is
  'Master switch for nycif-culture-calendar. Must stay false until Phase C6.';
comment on column public.culture_reader_settings.civic_publication_enabled is
  'Master switch for nycif-culture-civic. Must stay false until Phase C6.';
comment on column public.culture_reader_settings.help_calendar_publication_enabled is
  'Master switch for rolling public-help calendar chips. Must stay false until Phase C6.';
