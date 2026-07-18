# M11 — Supplemental → Discovery merge lane

NYC five-borough supplemental calendar/Parks coverage merges into `schema-v1-discovery` **only after explicit human authorization**. Long Island expansion is a later lane.

**Authorized:** `supplemental_public_map_merge_authorized: true` in `status/nycif-project-status.json`

## Current state (merged 2026-07-18)

| Metric | Value |
|--------|-------|
| Approved discovery total (`feeds=main`) | **32,529** |
| Net-new supplemental merged | **1,810** |
| Duplicates skipped | 1,682 |
| Overlap coord conflicts | 0 |
| Pending human review | 0 |

Merge report: `data/reports/supplemental_discovery_merge_report.json`

## Prep artifacts (pre-merge / ongoing QA)

| Artifact | Role |
|----------|------|
| `data/supplemental_manual_approval_queue.json` | Human approval source of truth |
| `data/supplemental_approved_export_feed.json` | Approved export for field-desk preview |
| `data/reports/supplemental_overlap_key_coord_conflict_audit_report.json` | Zero coord conflicts required |
| `data/reports/supplemental_discovery_merge_readiness_report.json` | Merge prep QA gate (`net_new_to_merge` should be 0 after merge) |

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

- Does not set GPS `promotion_allowed: true` or edit `location_cache.json`
- Does not modify staged live feeds directly
- Does not expand to Long Island

## Preview (safe)

Field-desk supplemental preview (not feeds=main):

- `docs/field-desk-map-deploy/supplemental-export-preview/`
- Sync: `./scripts/sync_supplemental_export_preview_to_field_desk.sh`

## Field-desk deploy (after merge lands on main)

Discovery `feeds=main` total is now **32,529** approved events. Deploy field-desk so the map loads the updated manifest SHAs (workflow: **Deploy to Field Desk Pages**). WordPress `/map/` iframe URL unchanged unless a new `v=` cache-bust is requested.

## Later lanes

- Long Island expansion (out of scope for M11)
- Paid events
- GPS Phase 2E hardening (`location_cache` promotion still unauthorized)
