# Bulk import NYC feasts & festivals (safe operator prompt)

Use this prompt when you have a **new Google Studio / curated feast list** and want it on the NYC In Focus map **without overwriting** existing seed data or protected feeds.

## Copy-paste prompt for a coding agent

```
Bulk-import NYC feast/festival reference rows into the staging seed and map intake.

SAFETY (non-negotiable):
- Append-only merge into data/staging/nyc_feast_festival_reference_seed.json
- Do NOT edit data/location_cache.json, data/nycif_staged_live_events.json, or public map feeds
- Do NOT set promotion_allowed or approve GPS rows
- Never overwrite an existing seed row with the same `key`
- Prefer name + street + dates over SAPO permit IDs (Google IDs are often wrong)

INPUT:
- Place new rows in data/staging/nyc_feast_festival_reference_seed_bulk_patch.json
- Each row needs at minimum: key, canonical_name, display_location, borough, event_kind, projected_start, projected_end
- Optional: claimed_permit_id (hint only), aliases, location_hint, reference_lat/lng

PIPELINE (run in order):
1. python3 scripts/bulk_import_feast_festival_seed.py
   → writes data/reports/nyc_feast_festival_seed_bulk_merge_report.json (must pass)
2. python3 scripts/build_nyc_feast_festival_reference_report.py
   → match vs raw SAPO snapshot; flag bad permit IDs
3. NYCIF_ALLOW_LIVE_GEOSEARCH=1 python3 scripts/intake_projected_feast_events.py --allow-live-geosearch
   → fills data/staging/projected_feast_events_map_intake.json (preserve existing geocoded rows)
4. python3 scripts/project_events_discovery_v02.py
   → projected rows appear as map_ready with provenance projected_feast_reference

QA CHECKLIST:
- Merge report: qa_passed true, skipped_existing_keys 0 unless intentional duplicates
- Reference report: review confirmed_in_raw vs projected_only counts
- Intake report: map_ready_count should grow; spot-check San Gennaro, Giglio, major parades
- Discovery: projected_feast_reference count in projector report
- Run python3 -m pytest tests/test_bulk_import_feast_festival_seed.py tests/test_projected_feast_intake.py

MAP DISPLAY:
- Religious feasts / carnivals: 🎡 (multi-day = larger pin)
- Street fairs: 🎉
- Food festivals: 🍽️
- Parades / cultural: 🎊
- Holiday markets: 🎄

If a feast already exists in raw SAPO (e.g. Our Lady of Mount Carmel), intake should skip it — raw wins.
```

## Row schema (bulk patch)

```json
{
  "key": "feast-of-san-gennaro",
  "canonical_name": "Feast of San Gennaro",
  "display_location": "Grand St & Mott St, Manhattan",
  "borough": "Manhattan",
  "event_kind": "religious_feast",
  "projected_start": "2026-09-10",
  "projected_end": "2026-09-20",
  "claimed_permit_id": "907551",
  "aliases": ["San Gennaro Festival"],
  "location_hint": "Little Italy"
}
```

`event_kind` values: `religious_feast`, `street_fair`, `food_festival`, `parade`, `cultural_festival`, `holiday_market`

## What changes vs what does not

| Artifact | Changes? |
|----------|----------|
| `data/staging/nyc_feast_festival_reference_seed.json` | Yes — append new keys only |
| `data/staging/projected_feast_events_map_intake.json` | Yes — geocoded projected rows |
| `data/reports/*` | Yes — QA reports |
| `data/location_cache.json` | **No** |
| `data/nycif_staged_live_events.json` | **No** |
| Public map feed | **No** until human promotes |

## Rollback

```bash
git checkout -- data/staging/nyc_feast_festival_reference_seed.json
git checkout -- data/staging/projected_feast_events_map_intake.json
```

Keep the bulk patch file; re-merge after fixing rows.
