-- Catch-up now writes TVPP pins. An 80-row Rung 8 batch can exceed the
-- default API statement timeout (57014). Keep the atomic writer, give it
-- two minutes per call.

ALTER FUNCTION public.nycif_apply_staging_event_batch(jsonb, text, boolean, boolean, text)
  SET statement_timeout = '120s';
