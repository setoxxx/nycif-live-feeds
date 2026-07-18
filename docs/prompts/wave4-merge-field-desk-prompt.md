# NYC feast map — Wave 4 + merge + field-desk verification prompt

Use after Wave 3 is complete. Current baseline is in `data/reports/projected_feast_map_readiness_report.json`.

---

## Copy-paste prompt (full power)

```
You are working in setoxxx/nycif-live-feeds (read AGENTS.md first).

═══════════════════════════════════════════════════════════════════════════════
CONTEXT — WHAT IS ALREADY DONE (do not redo from scratch)
═══════════════════════════════════════════════════════════════════════════════

PIPELINE BUILT:
- scripts/bulk_import_feast_festival_seed.py — append-only merge by key
- scripts/build_nyc_feast_festival_reference_report.py — raw SAPO match QA
- scripts/intake_projected_feast_events.py — geocode projected rows
- scripts/project_events_discovery_v02.py — discovery projector
- scripts/build_projected_feast_map_readiness_report.py — map QA summary

DATA IMPORTED (cumulative):
- Bulk Google Studio Parts 1–9: 143 rows
- Gap-fill wave 1: +20 neighborhood church feasts (St. Bernard Bergen Beach, St. Irene, etc.)
- Gap-fill wave 2: +14 thin-borough rows + 5 list-only geocode fixes
- Gap-fill wave 3: +22 ethnic/neighborhood festivals (IAAF, Mermaid Parade, Rockaway Carnival, etc.)

CURRENT BASELINE (verify in projected_feast_map_readiness_report.json):
- 199 seed rows | 198 map_ready intake | 0 list_only | 196 projected discovery pins
- Borough seed: Manhattan 81, Brooklyn 57, Queens 38, Bronx 14, Staten Island 9
- religious_feast seed: 46 rows (🎡 carnivals)
- 2 confirmed_in_raw SAPO (Mount Carmel Williamsburg 906428, Our Lady of Snows procession)
- 20 title_match, 3 permit_id_mismatch (never trust Google permit IDs alone)

BRANCH: cursor/multiday-feast-discovery-c1f9 — PR #312

EMOJI / PIN RULES (already wired in discovery + field desk):
- 🎡 religious_feast (multi-day = larger marker--multiday pin)
- 🎉 street_fair
- 🍽️ food_festival
- 🎊 parade / cultural_festival
- 🎄 holiday_market

SAFETY (non-negotiable):
- Do NOT edit location_cache.json, nycif_staged_live_events.json, staged_live_manifest.json
- Do NOT set promotion_allowed=true or run Phase 2E promotion
- Do NOT publish to public map without explicit human approval
- Raw SAPO confirmed rows win over projected duplicates (intake skips confirmed_permit_id)

═══════════════════════════════════════════════════════════════════════════════
GOAL — WAVE 4 + MERGE READINESS + CROSS-REPO MAP VERIFICATION
═══════════════════════════════════════════════════════════════════════════════

1. Hunt the hardest remaining neighborhood parish gaps (Wave 4)
2. Reconcile projected rows against fresh raw SAPO matches
3. Produce merge-readiness + field-desk verification artifacts
4. Keep list_only_count = 0 and all qa_pass = true

Target after Wave 4: seed >= 210, projected discovery >= 200, list_only = 0.

═══════════════════════════════════════════════════════════════════════════════
PHASE 0 — READINESS AUDIT (start here)
═══════════════════════════════════════════════════════════════════════════════

python3 scripts/build_projected_feast_map_readiness_report.py --reference-today 2026-07-18

Read:
- data/reports/projected_feast_map_readiness_report.json
- data/reports/projected_feast_raw_confirmation_notes.json
- data/reports/nyc_feast_festival_reference_match_report.json
- data/staging/nyc_feast_festival_reference_seed.json (list keys — do not duplicate)

Document remaining_gaps_wave4 from readiness report. Priority neighborhoods:

BROOKLYN (still thin on parish carnivals):
  □ Woodhaven / Ozone Park Italian feasts
  □ Gravesend / Bensonhurst church feasts beyond existing rows
  □ Marine Park / Gerritsen Beach (beyond St Pat's parade + Resurrection parish)
  □ Dyker Heights summer church events (beyond Christmas lights)
  □ Bay Ridge parish events beyond St George / Feast of the Cross

QUEENS:
  □ Flushing church processions beyond Lunar NY parade
  □ Ridgewood / Glendale parish feasts
  □ Maspeth beyond Fatima + Parish Feast Day
  □ Woodhaven / Richmond Hill beyond Mariamman
  □ Howard Beach / Ozone Park summer street feasts

BRONX:
  □ Pelham Bay / Country Club parish events
  □ Parkchester / Castle Hill church feasts
  □ Fordham / Belmont beyond existing Mount Carmel + Fordham Plaza
  □ Soundview beyond Hoe Avenue Parish Family Feast

STATEN ISLAND (still thinnest borough — 9 seed rows):
  □ Great Kills / South Beach / New Dorp parish carnivals
  □ Pleasant Plains beyond Travis July 4 parade
  □ Rosebank beyond Mount Carmel Bradley (if distinct from Rosebank seed)

═══════════════════════════════════════════════════════════════════════════════
PHASE 1 — WAVE 4 RESEARCH (go deep — this is the creative work)
═══════════════════════════════════════════════════════════════════════════════

Create: data/staging/nyc_feast_festival_reference_seed_gap_patch_wave4.json

Research sources (use ALL):
1. data/nyc_permits_historical_snapshot.json — 2025 recurring permits by neighborhood street
2. data/raw_nyc_open_data_snapshot.json — 2026 Jul–Dec Religious Event / Street Festival rows
3. data/nyc_permits_historical_snapshot.json — search event_location for:
   WOODHAVEN, OZONE, GRAVESEND, MARINE, GERRITSEN, PELHAM, PARKCHESTER, GREAT KILL, SOUTH BEACH, NEW DORP
4. Parish websites, NY Carnivals (nycarnivals.com), Brooklyn Paper, SI Live for 2026 dates
5. Cross-check nyc_sapo_feast_festival_reference.json after reference report

MATCHING RULES (learned from 3 waves of QA):
- Match on canonical_name + display_location + date window — NOT permit ID alone
- If raw SAPO already has the feast (confirmed_permit_id or strong title_match on same corridor),
  do NOT add a projected duplicate
- Distinguish same saint / different parishes (Mount Carmel Williamsburg ≠ Bergen Beach ≠ Rosebank ≠ Belmont)
- claimed_permit_id is a hint only; document permit_id_mismatch in confirmation notes

ROW SCHEMA:
{
  "key": "stable-slug-forever",
  "canonical_name": "Public map title",
  "aliases": ["search terms", "church name", "neighborhood"],
  "claimed_permit_id": null,
  "projected_start": "2026-MM-DD",
  "projected_end": "2026-MM-DD",
  "event_kind": "religious_feast",
  "typical_multi_day": true,
  "borough": "Brooklyn",
  "location_hint": "STREET CORRIDOR",
  "display_location": "SAPO-style: EAST 69 STREET between VETERANS AVENUE and AVENUE U, Brooklyn, NY",
  "reference_lat": 40.0,
  "reference_lng": -73.9,
  "bulk_import_batch": "operator_gap_fill_wave4_2026_07"
}

Use reference_lat/lng proactively for:
- Parks (Marine Park, Canarsie Park, etc.)
- Odd SAPO strings ("Park: Whole Park", plaza names)
- Any row geocoder failed in prior waves

Target: +12–20 new keys. Prioritize religious_feast 🎡 and ethnic parades 🎊.

═══════════════════════════════════════════════════════════════════════════════
PHASE 2 — MERGE + PIPELINE
═══════════════════════════════════════════════════════════════════════════════

python3 scripts/bulk_import_feast_festival_seed.py \
  --patch data/staging/nyc_feast_festival_reference_seed_gap_patch_wave4.json

python3 scripts/build_nyc_feast_festival_reference_report.py

python3 scripts/build_projected_feast_map_readiness_report.py --reference-today 2026-07-18
# Updates projected_feast_raw_confirmation_notes.json — review new title_match rows

NYCIF_ALLOW_LIVE_GEOSEARCH=1 python3 scripts/intake_projected_feast_events.py --allow-live-geosearch

If list_only_count > 0: fix seed display_location or reference_lat/lng, re-run intake.
NEVER run intake without live geosearch after seed changes (zeros coordinates).

python3 scripts/project_events_discovery_v02.py

All reports must show qa_pass: true.

═══════════════════════════════════════════════════════════════════════════════
PHASE 3 — SPOT-CHECKS (required before claiming success)
═══════════════════════════════════════════════════════════════════════════════

Verify in data/events_discovery_v02_approved.json:

□ st-bernard-madonna-del-carmine-bergen-beach — map_ready, Jul 23–26, major, 🎡
□ feast-of-san-gennaro — map_ready, major, ends 2026-09-20
□ Giglio / Williamsburg OLMC — raw 906428 OR projected Giglio row, map_ready
□ national-puerto-rican-day-parade — map_ready, major
□ international-african-arts-festival-brooklyn — multi-day, map_ready
□ At least 50 religious_feast projected pins total
□ list_only_count = 0

python3 - <<'PY'
import json
from pathlib import Path
approved = json.loads(Path("data/events_discovery_v02_approved.json").read_text())
proj = [e for e in approved["events"] if e.get("nycif",{}).get("projected_feast_reference")]
print("projected_feast_reference:", len(proj))
intake = json.loads(Path("data/reports/projected_feast_events_map_intake_report.json").read_text())
print("map_ready:", intake["map_ready_count"], "list_only:", intake["list_only_count"])
PY

═══════════════════════════════════════════════════════════════════════════════
PHASE 4 — MERGE-READINESS REPORT (new deliverable)
═══════════════════════════════════════════════════════════════════════════════

Extend scripts/build_projected_feast_map_readiness_report.py OR write
data/reports/projected_feast_pr_merge_readiness_report.json with:

- pr_number: 312
- branch: cursor/multiday-feast-discovery-c1f9
- seed_count, intake_count, map_ready_count, list_only_count, projected_discovery_count
- waves_merged: [google_studio_bulk, gap_wave1, gap_wave2, gap_wave3, gap_wave4]
- raw_sapo_confirmed_count, title_match_count, permit_id_mismatch_count
- protected_files_unchanged: true (explicit checklist)
- promotion_allowed_all_false: true
- recommended_next_steps:
    1. Merge PR #312 to main
    2. Verify pins in setoxxx/nycif-field-desk (read field-desk AGENTS.md)
    3. Optional: sync_nyc_open_data.py when human authorizes network sync
    4. Phase 2E promotion ONLY with explicit human "promote to location_cache"
- wave5_gaps: whatever remains after wave 4

═══════════════════════════════════════════════════════════════════════════════
PHASE 5 — FIELD-DESK MAP VERIFICATION (cross-repo checklist)
═══════════════════════════════════════════════════════════════════════════════

Do NOT change nycif-field-desk in this task unless explicitly authorized.
Instead write data/reports/projected_feast_field_desk_verification_checklist.json:

Human/frontend agent should verify after PR merge:
□ Discovery approved feed loads projected_feast_reference rows
□ St. Bernard Jul 23–26 shows 🎡 with larger multi-day pin
□ San Gennaro Sep 10–20 shows 🎡 major pin in Little Italy
□ Street fairs show 🎉, parades show 🎊
□ Projected rows labeled/styled differently from raw SAPO rows (if applicable)
□ No GPS review artifacts loaded as public live data

═══════════════════════════════════════════════════════════════════════════════
PHASE 6 — TESTS & COMMIT
═══════════════════════════════════════════════════════════════════════════════

python3 -m pytest tests/test_bulk_import_feast_festival_seed.py tests/test_projected_feast_discovery.py -q
python3 -m compileall scripts tools tests

Update test thresholds if counts grew.
Add test for pr_merge_readiness_report.json if created.

Commit message must include:
  seed 199→N, map_ready, list_only, discovery count, wave4 added keys sample

Push to cursor/multiday-feast-discovery-c1f9 and update PR #312.

═══════════════════════════════════════════════════════════════════════════════
DELIVERABLES CHECKLIST
═══════════════════════════════════════════════════════════════════════════════

□ nyc_feast_festival_reference_seed_gap_patch_wave4.json
□ Updated seed + intake + discovery artifacts
□ projected_feast_map_readiness_report.json (qa_pass true)
□ projected_feast_raw_confirmation_notes.json (updated)
□ projected_feast_pr_merge_readiness_report.json (new)
□ projected_feast_field_desk_verification_checklist.json (new)
□ Tests green
□ PR #312 updated with before/after table
```

---

## Progress arc (for context)

| Wave | Added | Seed total | Discovery pins |
|------|-------|------------|----------------|
| Google bulk | +119 | 143 | ~135 |
| Gap 1 | +20 | 163 | ~155 |
| Gap 2 | +14 | 177 | ~174 |
| Gap 3 | +22 | **199** | **196** |
| **Gap 4 (next)** | +12–20 target | **210+** | **200+** |

## After Wave 4 (future prompts)

1. **Merge PR #312** — feast data is map-ready for discovery/staging
2. **Field-desk agent** — verify 🎡/🎉 pins render; read `setoxxx/nycif-field-desk/AGENTS.md`
3. **Raw SAPO sync** — `sync_nyc_open_data.py` when authorized; projected rows get replaced by confirmed raw
4. **Phase 2E promotion** — only when human says “promote these approved rows to location_cache”

## Rollback

```bash
git checkout -- data/staging/nyc_feast_festival_reference_seed.json
git checkout -- data/staging/projected_feast_events_map_intake.json
```

Keep patch files; fix rows and re-merge.
