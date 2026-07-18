# NYC feast & festival bulk import — full operator prompt

Use this when you want **maximum coverage** of real NYC street fairs, religious feasts, parades, and holiday markets on the NYC In Focus map — **without breaking existing data**.

Current baseline (as of PR #312): **143** curated seed rows, **~135** projected pins in discovery. Many neighborhood church feasts are still missing.

---

## Copy-paste prompt (full power — give this to a coding agent)

```
You are working in setoxxx/nycif-live-feeds (read AGENTS.md first).

GOAL
Bulk-expand NYC feast/festival map coverage with real, news-worthy events — religious carnivals,
street fairs, ethnic parades, holiday markets — using the safe append-only staging pipeline.
Maximize thoroughness: research gaps, fill missing neighborhood feasts, geocode, run discovery,
and prove QA with report artifacts. Do NOT touch protected feeds or publish to the public map.

THIS IS THE HIGHEST-VALUE DATA UPDATE
These events are what people look for on the map: San Gennaro, Giglio, Mount Carmel carnivals,
Avenue U church feasts, ethnic parades, summer street fairs. Get them visible with correct
emoji pins (🎡 feasts, 🎉 fairs, 🎊 parades, 🍽️ food, 🎄 markets) and larger pins for multi-day.

═══════════════════════════════════════════════════════════════════════════════
PHASE 0 — AUDIT WHAT WE ALREADY HAVE (do not duplicate)
═══════════════════════════════════════════════════════════════════════════════

1. Read data/staging/nyc_feast_festival_reference_seed.json — list all keys by borough.
2. Read data/reports/nyc_feast_festival_reference_match_report.json — note:
   - confirmed_in_raw_snapshot (raw SAPO wins; intake skips these)
   - not_in_raw_snapshot (projected-only; these need seed + geocode)
   - permit_id_mismatch (NEVER trust Google permit IDs alone)
3. Read data/staging/projected_feast_events_map_intake.json — count map_ready vs list_only.
4. Spot-check discovery:
   python3 - <<'PY'
   import json
   from pathlib import Path
   approved = json.loads(Path("data/events_discovery_v02_approved.json").read_text())
   proj = [e for e in approved["events"] if e.get("nycif",{}).get("projected_feast_reference")]
   print("projected_feast_reference in approved:", len(proj))
   PY

═══════════════════════════════════════════════════════════════════════════════
PHASE 1 — RESEARCH & BUILD THE BULK PATCH (your main creative work)
═══════════════════════════════════════════════════════════════════════════════

Create or extend:
  data/staging/nyc_feast_festival_reference_seed_bulk_patch.json

RULES FOR PATCH ROWS
- Each row MUST have: key, canonical_name, display_location, borough, event_kind,
  projected_start, projected_end
- key = lowercase slug, stable forever (e.g. st-bernard-madonna-del-carmine-bergen-beach)
- canonical_name = public-facing title on the map
- display_location = SAPO-style street segment when possible:
    "EAST 69 STREET between VETERANS AVENUE and AVENUE U, Brooklyn, NY"
- aliases = 2–6 alternate names people search (include church name, neighborhood, "feast of...")
- claimed_permit_id = optional HINT ONLY — often wrong in Google lists; verify against raw snapshot
- typical_multi_day = true for carnivals that run multiple evenings
- event_kind one of:
    religious_feast | street_fair | food_festival | parade | cultural_festival | holiday_market
- bulk_import_batch = descriptive tag (e.g. operator_gap_fill_2026_07)

RESEARCH SOURCES (use all that apply)
1. Operator-provided Google Studio / curated lists (Parts 1–9 already merged once)
2. data/raw_nyc_open_data_snapshot.json — search event_name + event_location + July–December window
3. data/nyc_permits_historical_snapshot.json — recurring church feasts from prior years
4. Parish/social-club sites, NY Carnivals, local papers (Brooklyn Paper, etc.)
5. Cross-check nyc_sapo_feast_festival_reference.json after running the reference report

MATCHING RULES (critical — learned from QA)
- Match on canonical_name + display_location + date window, NOT permit ID alone
- Google Studio permit IDs are frequently wrong (e.g. 907551 ≠ San Gennaro in raw snapshot)
- If a feast is already confirmed in raw SAPO (e.g. Our Lady of Mount Carmel Williamsburg 906428),
  do NOT add a duplicate projected row — raw intake wins
- Distinguish same saint / different parishes:
    - Mount Carmel Williamsburg (Havemeyer) ≠ Mount Carmel Rosebank ≠ Mount Carmel Bergen Beach / St. Bernard

KNOWN GAPS TO FILL (verify dates; add if missing from seed)
Brooklyn church / neighborhood feasts often missing from bulk lists:
  □ St. Bernard of Clairvaux — Feast of Madonna del Carmine / Our Lady of Mount Carmel
      Location: East 69th Street & Avenue U, Bergen Beach (2055 E 69th St)
      Historical permit: "St. Bernard Parish Block Party" on EAST 69 STREET between
      VETERANS AVENUE and AVENUE U (see nyc_permits_historical_snapshot event_id 874871)
      Typically late July multi-night carnival (🎡). Project 2026 dates from 2025 pattern if
      no official 2026 posting yet; note confidence in aliases/location_hint.
  □ Other Brooklyn gaps to hunt: Gerritsen Beach, Marine Park, Bensonhurst, Gravesend,
    Bay Ridge, Dyker Heights, Carroll Gardens, Red Hook church feasts
Queens: Astoria/Steinway Italian feasts, Ridgewood, Maspeth, Corona
Staten Island: beyond Rosebank Mount Carmel — South Beach, Pleasant Plains, etc.
Manhattan: East Harlem, Yorkville, lower east side parish feasts
Bronx: Arthur Ave adjacent, Belmont, Morris Park

For EVERY gap you find, add a patch row. Aim for completeness, not minimal diff.

EXAMPLE ROW (St. Bernard — adapt dates after research):
{
  "key": "st-bernard-madonna-del-carmine-bergen-beach",
  "canonical_name": "Feast of Madonna del Carmine (St. Bernard, Bergen Beach)",
  "aliases": [
    "Feast of Our Lady of Mount Carmel St. Bernard",
    "St. Bernard Parish Feast",
    "St. Bernard of Clairvaux Feast",
    "Gioiosa Marina Social Club Feast",
    "Bergen Beach Mount Carmel Feast"
  ],
  "claimed_permit_id": null,
  "projected_start": "2026-07-23",
  "projected_end": "2026-07-26",
  "event_kind": "religious_feast",
  "typical_multi_day": true,
  "borough": "Brooklyn",
  "location_hint": "EAST 69 STREET & AVENUE U",
  "display_location": "EAST 69 STREET between VETERANS AVENUE and AVENUE U, Brooklyn, NY",
  "bulk_import_batch": "operator_gap_fill_2026_07"
}

═══════════════════════════════════════════════════════════════════════════════
PHASE 2 — SAFE MERGE (append-only; never overwrite)
═══════════════════════════════════════════════════════════════════════════════

python3 scripts/bulk_import_feast_festival_seed.py

Inspect data/reports/nyc_feast_festival_seed_bulk_merge_report.json:
  - qa_pass MUST be true
  - added_count > 0 for new work; skipped_duplicate_count only for intentional dupes
  - seed_after should grow; existing keys unchanged

If validation errors: fix patch rows, re-run. Never hand-edit seed to overwrite keys.

═══════════════════════════════════════════════════════════════════════════════
PHASE 3 — SAPO REFERENCE MATCH REPORT
═══════════════════════════════════════════════════════════════════════════════

python3 scripts/build_nyc_feast_festival_reference_report.py

Review data/reports/nyc_feast_festival_reference_match_report.json:
  - How many newly confirmed_in_raw_snapshot?
  - Flag permit_id_mismatch rows — document in PR notes, do not auto-trust IDs
  - not_in_raw_snapshot rows are expected for projected feasts not yet in committed raw snapshot

═══════════════════════════════════════════════════════════════════════════════
PHASE 4 — GEOCODE INTAKE (requires network)
═══════════════════════════════════════════════════════════════════════════════

NYCIF_ALLOW_LIVE_GEOSEARCH=1 python3 scripts/intake_projected_feast_events.py --allow-live-geosearch

Inspect data/reports/projected_feast_events_map_intake_report.json:
  - qa_pass MUST be true
  - map_ready_count should be high (target >90% of intake)
  - list_only rows: try better display_location or location_hint, re-run
  - Mount Carmel Williamsburg (906428) should be skipped (already in raw)

WARNING: Running intake WITHOUT live geosearch can zero coordinates — always use
NYCIF_ALLOW_LIVE_GEOSEARCH=1 after seed changes.

═══════════════════════════════════════════════════════════════════════════════
PHASE 5 — DISCOVERY PROJECTOR
═══════════════════════════════════════════════════════════════════════════════

python3 scripts/project_events_discovery_v02.py

Verify output ends with qa_pass: true, reconciles: true.
Count projected_feast_reference rows in approved feed (should be 100+).

═══════════════════════════════════════════════════════════════════════════════
PHASE 6 — SPOT-CHECKS (required before claiming success)
═══════════════════════════════════════════════════════════════════════════════

Confirm these appear in data/events_discovery_v02_approved.json with map_ready coords:
  □ Feast of San Gennaro (feast-of-san-gennaro) — religious, major, 🎡
  □ Williamsburg Giglio / San Paolino feast
  □ St. Bernard / Madonna del Carmine Bergen Beach (if added)
  □ National Puerto Rican Day Parade
  □ Macy's Thanksgiving Day Parade (list or map per coords)
  □ At least 3 Brooklyn street fairs (🎉) and 3 religious feasts (🎡)

For multi-day feasts verify:
  - nycif.is_major or civic/arts classification with feast tags
  - end_date_time spans multiple days
  - frontend uses marker--multiday for larger pins (already in PR #312)

═══════════════════════════════════════════════════════════════════════════════
PHASE 7 — TESTS & COMMIT
═══════════════════════════════════════════════════════════════════════════════

python3 -m pytest tests/test_bulk_import_feast_festival_seed.py tests/test_projected_feast_discovery.py -q
python3 -m compileall scripts tools tests

Commit with clear message. PR body must state:
  - seed before/after counts
  - map_ready / projected discovery counts
  - explicit list of newly added notable feasts (incl. St. Bernard if added)
  - safety: no protected file edits, promotion_allowed false, no public map publish

═══════════════════════════════════════════════════════════════════════════════
SAFETY — NON-NEGOTIABLE
═══════════════════════════════════════════════════════════════════════════════

DO NOT EDIT:
  - data/location_cache.json
  - data/nycif_staged_live_events.json
  - data/staged_live_manifest.json
  - data/previous_staged_live_events_snapshot.json
  - public map feed outputs

DO NOT:
  - set promotion_allowed = true
  - set manual_review_status = approved
  - run Phase 2E promotion
  - publish or promote to public map unless human explicitly says so

Projected feast rows are staging for map visibility until SAPO raw confirms them.

═══════════════════════════════════════════════════════════════════════════════
DELIVERABLES
═══════════════════════════════════════════════════════════════════════════════

1. Updated bulk patch JSON with all new rows
2. Merge + reference + intake + discovery reports (qa_pass true)
3. Test pass
4. Summary table: borough breakdown, new keys added, map_ready count, notable spot-checks
5. List of remaining gaps for next import batch
```

---

## Quick reference

| Artifact | Role |
|----------|------|
| `data/staging/nyc_feast_festival_reference_seed_bulk_patch.json` | New rows to merge |
| `data/staging/nyc_feast_festival_reference_seed.json` | Curated source of truth (append-only) |
| `data/staging/projected_feast_events_map_intake.json` | Geocoded rows for discovery |
| `data/reports/nyc_feast_festival_seed_bulk_merge_report.json` | Merge QA |
| `data/reports/nyc_feast_festival_reference_match_report.json` | Raw SAPO match QA |
| `data/reports/projected_feast_events_map_intake_report.json` | Geocode QA |

## Map emoji taxonomy

| `event_kind` | Emoji | Notes |
|--------------|-------|-------|
| `religious_feast` | 🎡 | Carnivals, church feasts — use `typical_multi_day: true` for week-long |
| `street_fair` | 🎉 | Avenue fairs, summer strolls |
| `food_festival` | 🍽️ | Smorgasburg-style, taste-of events |
| `parade` | 🎊 | Ethnic parades, Macy's, etc. |
| `cultural_festival` | 🎊 | Non-parade cultural street events |
| `holiday_market` | 🎄 | Winter village, holiday markets |

Multi-day events get larger map pins (`marker--multiday`) when `end > start`.

## Rollback

```bash
git checkout -- data/staging/nyc_feast_festival_reference_seed.json
git checkout -- data/staging/projected_feast_events_map_intake.json
```

Keep the bulk patch file; fix rows and re-merge.
