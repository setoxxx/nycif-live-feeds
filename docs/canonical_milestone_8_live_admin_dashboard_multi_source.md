# Canonical Milestone 8 — Live Admin Dashboard + Multi-Source Coverage

Milestone: **Canonical Milestone 8**
Codename: **Live Admin Dashboard + Multi-Source Coverage**
Branch evidence: `main` commits through PRs #149, #150, #151, #152
Status: **complete (backend)**; **field-desk GitHub Pages merge pending**

## Objective

Give NYCIF operators a **read-only live view** of backend pipeline health (staged counts, delta changes, multi-source gaps, Parks BigApps metrics) without mutating protected feeds or the public map.

## Exit criteria

| Criterion | Status | Evidence |
|-----------|--------|----------|
| Multi-source calendar staging sync | ✅ | `scripts/sync_nyc_citywide_events_calendar.py`, PR #149 |
| Multi-source coverage audit | ✅ | `scripts/audit_multi_source_coverage.py`, `data/reports/multi_source_coverage_report.json` |
| Live pipeline dashboard artifact | ✅ | `status/nycif-live-pipeline-dashboard.json`, PR #149 |
| NYC Parks BigApps events staging | ✅ | `scripts/sync_nyc_parks_bigapps_events.py`, PR #151 |
| Parks facility reference (Phase 2C) | ✅ | `data/nyc_parks_facility_reference.json`, PR #151 |
| Phase 2C fill uses Parks reference | ✅ | PR #152 — 40/50 top proposals from `nyc_parks_bigapps` |
| Admin Live Pipeline UI deployed | 🟡 | **Interim:** live-feeds GitHub Pages; **Target:** field-desk `admin/index.html` |
| Public map unchanged | ✅ | All reports: `public_map_modified: false` |
| No unauthorized promotion | ✅ | `promotion_allowed: false` on all review artifacts |

## Live counts snapshot (2026-07-13)

| Metric | Value |
|--------|-------|
| Staged feed events | 23,111 |
| GPS-valid permits | 27,528 (~93.8%) |
| GPS review tail | 1,827 |
| Citywide calendar rows | 2,781 |
| Parks BigApps events | 1,654 |
| Calendar-only gap | 2,571 |
| Parks-only gap | 1,600 |
| Phase 2C filled (top-50 batch) | 47/50 |
| Manual approval queue | 47 pending |

## Source map (four staged layers)

| Operator source | Backend dataset | Repo status |
|-----------------|-----------------|-------------|
| NYC Open Data / CSV | `tvpp-9vvx` | Live ingested |
| CECM E-Apply | Same as `tvpp-9vvx` | Same family |
| nyc.gov/main/events | `api.nyc.gov/calendar/*` | Staging sync live |
| NYC Parks BigApps | `nycgovparks.org/bigapps` + events RSS | Staging sync live |

## Admin dashboard URLs

| URL | Role |
|-----|------|
| https://setoxxx.github.io/nycif-live-feeds/admin/index.html | **Interim live dashboard** (deployed from `nycif-live-feeds` Pages) |
| https://setoxxx.github.io/nycif-field-desk/admin/index.html | **Target** (requires field-desk PR merge to `main`) |

## Field-desk merge (required for target URL)

Local branch `cursor/admin-live-pipeline-panel-5215` has commits but **remote branch on GitHub is still at `main`** (push blocked for automation). Human push:

```bash
cd nycif-field-desk
git checkout cursor/admin-live-pipeline-panel-5215
git push -u origin cursor/admin-live-pipeline-panel-5215 --force-with-lease
gh pr create --base main --head cursor/admin-live-pipeline-panel-5215 \
  --title "Add Live Pipeline panel to admin dashboard" \
  --body "Read-only live counts from nycif-live-feeds. See Canonical Milestone 8."
gh pr merge --merge
```

Or copy from `nycif-live-feeds/docs/field-desk-admin-deploy/admin/`.

## Key artifacts

```text
status/nycif-live-pipeline-dashboard.json
status/nycif-coverage-roadmap.json
data/reports/multi_source_coverage_report.json
data/live_delta_report.json
data/nyc_parks_facility_reference.json
data/gps_manual_approval_queue.json
docs/field-desk-admin-deploy/admin/
```

## Next milestone (not started)

**Milestone 8-B — GPS review tail reduction at scale**

- Run `GPS_PROPOSAL_LIMIT=292` through Phase 2C/2D
- Manual approval of filled rows
- Phase 2E promotion **only** with explicit publish authorization

## Safety confirmation

- `location_cache.json` — not modified
- `nycif_staged_live_events.json` — not modified by Milestone 8 scripts
- Public map — not modified
- Admin UI — read-only, no publish controls
