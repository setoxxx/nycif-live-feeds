-- OPTIONAL. Do not apply until a human explicitly asks to apply this
-- migration on oggwpvdirkrnzoolparx.
--
-- Purpose: one-row cache token so iOS can cheaply ask "did today's
-- official catch-up finish?" without downloading the map feed again.
-- Civic events stay a daily batch. This table is NOT added to
-- supabase_realtime. Frequency / radio Realtime channels stay isolated.
--
-- Not wired to scripts/sync_supabase_official_source_catchup.py yet.
-- Wiring that writer is a separate, explicit change. This file does not
-- touch location_cache.json or any staged live feed artifact.

create table if not exists public.native_map_feed_epoch (
  id smallint primary key default 1 check (id = 1),
  published_at timestamptz not null default now(),
  timezone text not null default 'America/New_York',
  nyc_date date not null default ((now() at time zone 'America/New_York')::date),
  occurrence_count integer,
  map_ready_count integer,
  source_run_id bigint references public.pipeline_runs(run_id),
  notes text
);

comment on table public.native_map_feed_epoch is
  'Single-row epoch for native map cache invalidation. Polling only. Not a Realtime source.';

insert into public.native_map_feed_epoch (id, notes)
values (1, 'seed row; unpublished until catch-up writes it')
on conflict (id) do nothing;

alter table public.native_map_feed_epoch enable row level security;

revoke all on table public.native_map_feed_epoch from public;
revoke all on table public.native_map_feed_epoch from anon;
revoke all on table public.native_map_feed_epoch from authenticated;

grant select on table public.native_map_feed_epoch to anon;
grant select on table public.native_map_feed_epoch to authenticated;
grant select, insert, update on table public.native_map_feed_epoch to service_role;

drop policy if exists native_map_feed_epoch_select_anon on public.native_map_feed_epoch;
create policy native_map_feed_epoch_select_anon
  on public.native_map_feed_epoch
  for select
  to anon, authenticated
  using (true);

-- Deliberately omitted:
--   alter publication supabase_realtime add table public.native_map_feed_epoch;
-- Realtime stays reserved for frequency / radio.
