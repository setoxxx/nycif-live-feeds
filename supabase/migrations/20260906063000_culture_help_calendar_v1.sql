-- Culture rolling public-help calendar (DRAFT).
-- Extends culture_calendar_occurrence_v1 kinds. Does not enable publication.
-- Does not seed events.

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

update public.culture_reader_settings
set
  help_calendar_publication_enabled = false,
  blood_layer_enabled = false,
  mobile_clinic_layer_enabled = false,
  jobs_layer_enabled = false,
  college_layer_enabled = false,
  calendar_publication_enabled = false,
  updated_at = now()
where id = 1;

alter table public.culture_calendar_occurrence_v1
  add column if not exists occurrence_kind text;
alter table public.culture_calendar_occurrence_v1
  add column if not exists chip_id text;
alter table public.culture_calendar_occurrence_v1
  add column if not exists emoji text;
alter table public.culture_calendar_occurrence_v1
  add column if not exists source_family text;
alter table public.culture_calendar_occurrence_v1
  add column if not exists time_precision text;

update public.culture_calendar_occurrence_v1
set occurrence_kind = calendar_kind
where occurrence_kind is null or btrim(occurrence_kind) = '';

alter table public.culture_calendar_occurrence_v1
  drop constraint if exists culture_calendar_occurrence_v1_kind_ck;

alter table public.culture_calendar_occurrence_v1
  add constraint culture_calendar_occurrence_v1_kind_ck check (calendar_kind in (
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
  ));

alter table public.culture_calendar_occurrence_v1
  drop constraint if exists culture_calendar_occurrence_v1_occurrence_kind_ck;

alter table public.culture_calendar_occurrence_v1
  add constraint culture_calendar_occurrence_v1_occurrence_kind_ck check (
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
  );

comment on column public.culture_calendar_occurrence_v1.occurrence_kind is
  'Help-calendar kind: blood_drive | mobile_clinic | job_fair | workshop | pet_mobile | resource_van (plus earlier Culture kinds).';
comment on column public.culture_reader_settings.help_calendar_publication_enabled is
  'Master switch for rolling public-help calendar chips. Must stay false until Phase C6.';
