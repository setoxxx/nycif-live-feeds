# Culture ingest scripts

Staging only. **Publication stays off.** These scripts write
`data/culture/staging/` and `data/culture/reports/` locally. They do not write
production Supabase, flip reader gates, deploy edges, or invent events.

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
```

Weekly civic pullers (NYPD / FDNY / shelters) are not part of the daily job.
See `docs/CULTURE_COMMUNITY_ENGINEERING_PLAN.md` for Howard’s schedule table.
