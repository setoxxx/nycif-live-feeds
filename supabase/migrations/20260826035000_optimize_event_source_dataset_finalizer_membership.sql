-- Keep dataset-scoped expiration fast enough for the hosted Postgres statement timeout.
-- The finalizer filters event_sources by source_name + source_dataset + source_active
-- and anti-joins staged occurrence IDs. Without this leading-key partial index the
-- planner scans large raw_record rows sequentially even for one dataset.

create index if not exists event_sources_active_dataset_membership_idx
on public.event_sources (source_name, source_dataset, occurrence_id, source_event_id)
where source_active;
