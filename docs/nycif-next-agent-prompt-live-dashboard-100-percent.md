# NYCIF Next Agent Prompt — Live Admin Dashboard + 100% Coverage

Copy everything below the line into a new Cursor Cloud Agent session.

---

## Mission

Complete **field-desk admin Live Pipeline panel** deployment and continue **GPS review tail reduction** using staged Parks BigApps facility reference — no public-map publish.

## Repositories

| Repo | Role |
|------|------|
| `setoxxx/nycif-live-feeds` | Backend feeds, GPS pipeline, QA artifacts, status JSON |
| `setoxxx/nycif-field-desk` | Admin dashboard (`admin/index.html`), field desk map |

Read **both** `AGENTS.md` files before editing.

## Current state (2026-07-13, approved completion pass)

### Backend (`nycif-live-feeds`) — DONE on branch pending merge

- PR #149, #150 merged to `main`
- NYC Parks BigApps staging added (branch `cursor/parks-bigapps-coverage-5215`):
  - `scripts/sync_nyc_parks_bigapps_events.py` → `data/nyc_parks_bigapps_events_snapshot.json` (1,654 rows)
  - `scripts/build_nyc_parks_facility_reference.py` → `data/nyc_parks_facility_reference.json` (2,290 with coordinates)
  - Extended `audit_multi_source_coverage.py` with Parks overlap analysis
  - `live_delta_report.json` refreshed (1 newly added, baseline updated)
- Live counts: **23,111 staged**, **1,827 GPS review**, **2,571 calendar-only**, **1,600 Parks-only**

### Frontend (`nycif-field-desk`) — BLOCKED (403 for cursor[bot])

- Implementation complete on branch `cursor/admin-live-pipeline-panel-5215` (local + commit ready)
- Deploy copies in `nycif-live-feeds/docs/field-desk-admin-deploy/admin/`
- **Human must push:**

```bash
cd nycif-field-desk
git fetch origin
git checkout cursor/admin-live-pipeline-panel-5215
git push -u origin cursor/admin-live-pipeline-panel-5215
# Open PR → merge → verify GitHub Pages admin
```

Or copy files from `docs/field-desk-admin-deploy/admin/` into field-desk `admin/`.

## Hard rules

- No publish/promote without explicit authorization
- No protected file edits (`location_cache.json`, staged production feeds) unless explicitly instructed
- Admin dashboard read-only only

## Task 1 — Merge field-desk PR (PRIORITY)

Verify https://setoxxx.github.io/nycif-field-desk/admin/index.html shows:
- ~23,111 live staged events
- Parks BigApps + facility reference counts
- System Overview updates after live pipeline loads

## Task 2 — Phase 2C GPS fill with Parks reference

```bash
python3 scripts/build_gps_geocoding_filled_proposals.py
python3 scripts/build_gps_geocoding_filled_proposals.py  # proposals must exist first
python3 scripts/build_gps_geocoding_filled_proposals.py
```

Run full GPS proposal pipeline if proposals artifact exists, then verify fill report uses `nyc_parks_facility_reference.json`.

## Task 3 — Optional

- Merge PR #148 (M7-B.2) when authorized
- Dispatch `live-sync-qa.yml` with `allow_live_fetch=yes`

## Key URLs

```text
https://raw.githubusercontent.com/setoxxx/nycif-live-feeds/main/status/nycif-live-pipeline-dashboard.json
https://raw.githubusercontent.com/setoxxx/nycif-live-feeds/main/data/nyc_parks_facility_reference.json
https://setoxxx.github.io/nycif-field-desk/admin/index.html
https://www.nycgovparks.org/bigapps
```
