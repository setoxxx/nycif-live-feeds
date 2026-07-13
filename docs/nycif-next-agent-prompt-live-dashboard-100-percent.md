# NYCIF Next Agent Prompt — Live Admin Dashboard + 100% Coverage

Copy everything below the line into a new Cursor Cloud Agent (or field-desk agent) session.

---

## Mission

Wire the **NYCIF admin dashboard** to show **live backend pipeline data** (what is current, what was newly added, multi-source gaps) and continue the safe path to **100% city event coverage** without unauthorized public-map publish.

## Repositories

| Repo | Role |
|------|------|
| `setoxxx/nycif-live-feeds` | Backend feeds, GPS pipeline, QA artifacts, status JSON |
| `setoxxx/nycif-field-desk` | Admin dashboard (`admin/index.html`), field desk map, feed-status panels |

Read **both** `AGENTS.md` files before editing.

## Current state (2026-07-13)

### Backend (`nycif-live-feeds`)

- **PR #149** (draft): multi-source calendar staging sync + coverage audit
- **PR #148** (draft): M7-B.2 adjudication self-hash remediation
- Permit pipeline (`tvpp-9vvx`): ~100% row accountability, ~94% auto GPS match, ~1,827 GPS review tail
- Staged feed: **~23,111** GPS-valid events in `data/nycif_staged_live_events.json`
- Citywide calendar (`api.nyc.gov/calendar/*`): staging sync added; **~2,593 calendar-only** events not yet in permit pipeline
- New dashboard artifact generator: `scripts/generate_live_pipeline_dashboard_status.py` → `status/nycif-live-pipeline-dashboard.json`

### Frontend (`nycif-field-desk`)

- Admin dashboard: `https://setoxxx.github.io/nycif-field-desk/admin/index.html`
- Master projects: `admin/master-projects.html` (already reads `nycif-live-feeds/status/nycif-project-status.json`)
- **Problem:** `admin/data/*.json` snapshots are stale (July 2, sample limit 3 rows). Dashboard does NOT yet show live multi-source counts or newly-added live data at full scale.

## Hard rules (do not violate)

- Do **not** publish/promote to public map unless user explicitly says "publish" or "promote approved rows"
- Do **not** modify protected files: `location_cache.json`, `nycif_staged_live_events.json`, `staged_live_manifest.json`, public feed JSON, WordPress embed
- Do **not** load GPS review/proposal artifacts as public live events
- Admin dashboard changes must remain **read-only** (no write/publish/deploy controls)
- Prefer admin-only paths over changing `nycinfocus.com/map/` production runtime

## Task A — Backend: refresh live dashboard artifact

In `nycif-live-feeds`:

1. Merge **PR #149** if approved
2. Run:
   ```bash
   python3 scripts/sync_nyc_open_data.py
   python3 scripts/sync_nyc_citywide_events_calendar.py
   python3 scripts/audit_multi_source_coverage.py
   python3 scripts/generate_live_pipeline_dashboard_status.py
   ```
3. Commit refreshed artifacts:
   - `status/nycif-live-pipeline-dashboard.json`
   - `status/nycif-coverage-roadmap.json`
   - `data/reports/multi_source_coverage_report.json`
   - `data/nyc_citywide_events_calendar_sync_report.json`
4. Optionally wire `generate_live_pipeline_dashboard_status.py` into `.github/workflows/live-sync-qa.yml` after QA steps (report-only)

## Task B — Frontend: admin dashboard live data panels

In `nycif-field-desk`:

1. Read `admin/index.html` and `admin/master-projects.html`
2. Add a **Live Pipeline** panel that fetches (cache-busted, read-only):
   - `https://raw.githubusercontent.com/setoxxx/nycif-live-feeds/main/status/nycif-live-pipeline-dashboard.json`
   - `https://raw.githubusercontent.com/setoxxx/nycif-live-feeds/main/data/live_delta_report.json`
   - `https://raw.githubusercontent.com/setoxxx/nycif-live-feeds/main/data/reports/multi_source_coverage_report.json`

3. Display clearly:

   **Current (what the map can show today)**
   - Staged feed events count
   - Staged with valid GPS
   - Last staged manifest timestamp

   **Newly added (since last snapshot)**
   - Added / removed / changed counts from `live_delta_report.json`
   - Top 5 newly added event cards (title, date, borough, location, source_event_id)

   **Multi-source coverage**
   - Permit rows (tvpp-9vvx)
   - Citywide calendar rows (api.nyc.gov)
   - Overlap / permit-only / calendar-only counts
   - Progress bars from `nycif-live-pipeline-dashboard.json`

   **GPS review tail**
   - gps_review_queue count
   - Link to backend report artifacts (not inline private data)

4. Update **Source Freshness** section:
   - Either regenerate `admin/data/source-freshness.json` via existing snapshot builder with full counts, OR
   - Replace static TVPP rowCount with live values from `nycif-live-pipeline-dashboard.json`

5. Add links panel:
   - Staged feed raw URL (for field desk QA)
   - Coverage report on GitHub
   - Admin newly-added panel already uses delta report — ensure counts match new live panel

6. Keep **read-only guardrails** visible. No mutation buttons.

## Task C — Field desk map preview (admin-only)

1. Ensure field desk can preview staged feed:
   `https://raw.githubusercontent.com/setoxxx/nycif-live-feeds/main/data/nycif_staged_live_events.json`
2. Do **not** change production public map feed URL unless explicitly authorized
3. `feed-status-panel-v01.js` and `admin-newly-added-v01.js` already read `live_delta_report.json` — verify they work after backend refresh

## Task D — Path to 100%

1. Complete M7-B.2 (PR #148) review/merge
2. Dispatch `live-sync-qa.yml` with `allow_live_fetch=yes`
3. GPS review tail: work `data/gps_review_location_groups.json` (~292 geocoding groups)
4. Calendar-only rows: manual review queue only — no auto-promote
5. Public publish: blocked until explicit user authorization

## Acceptance criteria

- [ ] Admin dashboard shows **live counts** (not July 2 sample-of-3)
- [ ] Admin dashboard shows **current staged** vs **newly added** side by side
- [ ] Admin dashboard shows **multi-source gap** (calendar-only ~2,593)
- [ ] All panels read static JSON via fetch; no GitHub API tokens in browser
- [ ] Production public map URL unchanged unless explicitly requested
- [ ] Final response lists files changed, safety confirmation, and what remains gated

## Key artifact URLs for testing

```text
https://raw.githubusercontent.com/setoxxx/nycif-live-feeds/main/status/nycif-live-pipeline-dashboard.json
https://raw.githubusercontent.com/setoxxx/nycif-live-feeds/main/status/nycif-coverage-roadmap.json
https://raw.githubusercontent.com/setoxxx/nycif-live-feeds/main/data/live_delta_report.json
https://raw.githubusercontent.com/setoxxx/nycif-live-feeds/main/data/row_disposition_report.json
https://raw.githubusercontent.com/setoxxx/nycif-live-feeds/main/data/staged_live_manifest.json
https://setoxxx.github.io/nycif-field-desk/admin/index.html
```

## Source reference (user's 3 inputs)

| User source | Backend dataset |
|-------------|-----------------|
| CSV / Open Data JSON | `tvpp-9vvx` |
| CECM E-Apply page | Same family as `tvpp-9vvx` |
| nyc.gov/main/events | `api.nyc.gov/calendar/*` (staging sync in PR #149) |
