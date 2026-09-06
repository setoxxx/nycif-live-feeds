# Culture ingest scripts

Staging first, then optional gated Supabase upsert. **Publication stays off.**
Pullers write `data/culture/staging/` and `data/culture/reports/` locally.
`load_calendar_civic_staging.py` may upsert pending rows into
`culture_calendar_occurrence_v1` / `culture_civic_facility_v1`. It does not
flip reader gates, deploy edges, or invent events.

Daily 6:00 AM America/New_York (EDT) is wired in
`.github/workflows/culture-help-calendar-daily.yml` (`0 10 * * *` UTC). During
EST that cron is 5:00 AM local; ops keep 10:00 UTC year-round as the morning
ET job. Manual replay: Actions → **Culture help-calendar daily pull**.

## Manual pull

From the repo root (`python3`, not `python`):

```bash
# Workforce1 — real SODA (kf2b-aeh5). Use --fixture when offline.
python3 scripts/culture/pull_workforce1_events.py --live
# python3 scripts/culture/pull_workforce1_events.py --fixture tests/fixtures/culture/workforce1_events.fixture.json

# Stubs — live scrape is not wired. --live exits 2/3; use --fixture.
python3 scripts/culture/pull_dol_career_events.py --fixture tests/fixtures/culture/dol_career_events.fixture.json
python3 scripts/culture/pull_cuny_career_events.py   # registry only; 0 invented events
python3 scripts/culture/pull_nybc_blood_drives.py --fixture tests/fixtures/culture/nybc_blood_drives.fixture.json
python3 scripts/culture/pull_show_mobile_clinics.py --fixture tests/fixtures/culture/show_mobile_clinics.fixture.json
python3 scripts/culture/pull_aspca_mobile.py --fixture tests/fixtures/culture/aspca_mobile.fixture.json

# Fail-closed gate. Expected: qa_pass=true publication_allowed=false
python3 scripts/culture/validate_before_publish.py

# Map staging → live tables (dry-run). Add --write to upsert; gates stay false.
python3 scripts/culture/load_calendar_civic_staging.py --dataset all

# One-shot pull + load (live SODA where wired, else fixtures)
python3 scripts/culture/backfill_calendar_civic.py --dataset all
# SUPABASE_URL=https://oggwpvdirkrnzoolparx.supabase.co \
# SUPABASE_SERVICE_ROLE_KEY=… \
# python3 scripts/culture/backfill_calendar_civic.py --dataset all --write
```

Weekly civic pullers (NYPD / FDNY / shelters):
`.github/workflows/culture-civic-weekly.yml` (`0 10 * * 1` UTC).
Howard flip recipe (after review only):
`docs/CULTURE_CALENDAR_CIVIC_PUBLICATION.md`.
