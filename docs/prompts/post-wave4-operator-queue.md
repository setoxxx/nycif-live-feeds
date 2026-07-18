# Post–Wave 4 operator queue

Run these in order. **Step 1 is complete** (PR #312 merged to `main` on 2026-07-18).

| Step | Repo | Status |
|------|------|--------|
| 1 | `nycif-live-feeds` — merge PR #312 | **DONE** |
| 2 | `nycif-field-desk` — map pin verification | **NEXT** |
| 3 | `nycif-live-feeds` — optional raw SAPO sync | Queued |
| 4 | `nycif-live-feeds` — Wave 5 gap-fill | Queued (after 2–3) |

**Merged baseline (main):** seed 223 · map_ready 220 · list_only 0 · discovery 218 · religious_feast 50 · all `qa_pass` true.

**Checklist artifact:** `data/reports/projected_feast_field_desk_verification_checklist.json`

---

## Step 1 — DONE

PR #312 merged. Required CI passed (`discovery-v02-qa`, `schema-v1-qa`). SonarCloud failed (non-blocking). Protected feeds unchanged; `promotion_allowed` all false.

---

## Step 2 — Field-desk map verification (NEXT)

```
You are working in setoxxx/nycif-field-desk.
Read AGENTS.md first.

Backend PR #312 is MERGED to main on setoxxx/nycif-live-feeds.
Backend checklist: nycif-live-feeds/data/reports/projected_feast_field_desk_verification_checklist.json
Feed path: data/events_discovery_v02_approved.json (from merged main)

GOAL: Verify projected feast pins render correctly on the field desk / preview map.

VERIFY:
□ Discovery approved feed loads >= 218 projected_feast_reference rows
□ St. Bernard Jul 23–26 — 🎡 multi-day larger pin, major
□ San Gennaro Sep 10–20 — 🎡 major pin in Little Italy
□ Giglio / OLMC Williamsburg — map_ready (raw 906428 or projected Giglio)
□ Puerto Rican Day Parade — map_ready major
□ Emoji taxonomy: 🎡 religious_feast, 🎉 street_fair, 🍽️ food_festival, 🎊 parade/cultural, 🎄 holiday_market
□ Projected rows styled differently from raw SAPO where applicable
□ No GPS review / manual approval / proposal artifacts loaded as live public data
□ list_only = 0
□ At least 50 religious_feast projected pins visible

Do NOT treat gps_review_* or manual_approval_* backend artifacts as public feed data.
Report pass/fail per checklist item with pin IDs or screenshots.
```

---

## Step 3 — Optional raw SAPO sync (after Step 2)

```
You are working in setoxxx/nycif-live-feeds (read AGENTS.md).
Branch from main.

Human authorizes network sync for this run.

TASK:
1. python3 scripts/sync_nyc_open_data.py
2. python3 scripts/build_nyc_feast_festival_reference_report.py
3. python3 scripts/build_projected_feast_map_readiness_report.py --reference-today 2026-07-18
4. NYCIF_ALLOW_LIVE_GEOSEARCH=1 python3 scripts/intake_projected_feast_events.py --allow-live-geosearch
5. python3 scripts/project_events_discovery_v02.py

RECONCILE:
- Raw confirmed rows (906428 Mount Carmel Williamsburg, 952432 Church at the Park, 952465 Our Lady of Snows) must win over projected duplicates
- intake skips confirmed_permit_id keys — expected
- Keep list_only_count = 0; all qa_pass = true

SAFETY:
- Do NOT edit location_cache.json, nycif_staged_live_events.json, public feeds
- Do NOT set promotion_allowed=true or run Phase 2E promotion
- Do NOT publish to public map without explicit human approval

Commit sync artifacts + updated reports. Open PR if match counts changed materially.
```

---

## Step 4 — Wave 5 gap-fill (after Steps 2–3)

```
You are working in setoxxx/nycif-live-feeds (read AGENTS.md).
Branch from main. Baseline on main: seed 223, discovery 218, list_only 0.

GOAL: Wave 5 neighborhood parish gaps (+12–15 rows).

PRIORITY GAPS (from projected_feast_pr_merge_readiness_report.json wave5_gaps):
- Woodhaven / Ozone Park dedicated parish carnivals (beyond OLOA)
- Gravesend / Bensonhurst parish feasts beyond existing rows
- Dyker Heights summer church events (beyond Christmas lights)
- Parkchester dedicated parish feast rows
- Pleasant Plains parish carnivals beyond Travis July 4 parade

PIPELINE (same as Wave 4):
1. Create data/staging/nyc_feast_festival_reference_seed_gap_patch_wave5.json
2. python3 scripts/bulk_import_feast_festival_seed.py --patch .../gap_patch_wave5.json
3. python3 scripts/build_nyc_feast_festival_reference_report.py
4. python3 scripts/build_projected_feast_map_readiness_report.py --reference-today YYYY-MM-DD
5. NYCIF_ALLOW_LIVE_GEOSEARCH=1 python3 scripts/intake_projected_feast_events.py --allow-live-geosearch
6. python3 scripts/project_events_discovery_v02.py

RULES: append-only by key; match name+street+dates not permit ID; reference_lat/lng for parks; bulk_import_batch = operator_gap_fill_wave5_2026_07

TARGET: seed >= 235, discovery >= 225, list_only = 0, religious_feast >= 55 projected pins.

SAFETY: protected feeds unchanged; promotion_allowed all false; no Phase 2E without explicit approval.
```
