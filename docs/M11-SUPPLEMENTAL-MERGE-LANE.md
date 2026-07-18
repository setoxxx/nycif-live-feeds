# M11 — Supplemental → Discovery merge lane

NYC five-borough supplemental calendar/Parks coverage merges into `schema-v1-discovery` **only after explicit human authorization**. Long Island expansion is a later lane.

## Current state (prep only)

| Artifact | Role |
|----------|------|
| `data/supplemental_manual_approval_queue.json` | Human approval source of truth |
| `data/supplemental_approved_export_feed.json` | Approved export for field-desk preview (`production_feed: false`) |
| `data/reports/supplemental_overlap_key_coord_conflict_audit_report.json` | Zero coord conflicts required |
| `data/reports/supplemental_discovery_merge_readiness_report.json` | Merge prep QA gate |
| `data/staging/supplemental_discovery_merge_proposal/summary.json` | Staging summary (no discovery writes) |

**Not authorized yet:** `status/nycif-project-status.json` → `supplemental_public_map_merge_authorized: false`

## QA gates (must all pass)

1. `validate_supplemental_manual_approvals.py` — `pending_count == 0`
2. `publish_supplemental_approved_export_feed.py` — export report `qa_pass`
3. `audit_supplemental_overlap_key_coord_conflicts.py` — `conflict_pair_count == 0`
4. `dry_run_supplemental_phase2e_promotion.py` — blocked only by `promotion_allowed_not_true` (expected)
5. `prepare_supplemental_discovery_merge.py` — readiness `qa_pass`

Run locally after export publish:

```bash
python3 scripts/audit_supplemental_overlap_key_coord_conflicts.py
python3 scripts/prepare_supplemental_discovery_merge.py
```

Inspect `data/reports/supplemental_discovery_merge_readiness_report.json`:

- `qa_pass` must be `true`
- `merge_authorized` stays `false` until human publish language
- `projected_after_merge.approved_discovery_total` = baseline + `net_new_to_merge` (duplicates skipped by identity)

## Identity dedupe rule

Merge prep compares `(source_dataset, source_event_id, event_date)` between supplemental export and approved discovery pages. Rows already present in discovery are skipped; only **net-new** identities would be merged.

## What this lane does **not** do

- Does not edit `data/schema-v1-discovery/approved/**` (feeds=main)
- Does not set `promotion_allowed: true` or `production_feed: true`
- Does not modify `location_cache.json`, staged live feeds, or the public WordPress map
- Does not expand to Long Island

## Preview (safe)

Field-desk supplemental preview (not feeds=main):

- `docs/field-desk-map-deploy/supplemental-export-preview/`
- Sync: `./scripts/sync_supplemental_export_preview_to_field_desk.sh`

## Next step after human authorization

When explicitly instructed (e.g. “merge approved supplemental into discovery” / “promote supplemental to feeds=main”):

1. Implement or run discovery merge (`project_events_discovery_v02.py` or dedicated merge script) ingesting `supplemental_approved_export_feed.json`
2. Rebuild discovery pages + manifest
3. Run full schema-v1 / discovery QA in CI
4. Field-desk deploy with updated `feeds=main` snapshot SHAs
5. WordPress map unchanged unless new deploy is requested

Until then, **feeds=main** remains the signed-off RC discovery feed (~30,719 approved events).
