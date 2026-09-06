# NYCIF Live Feeds

This repo is the daily factory for the NYC In Focus **event list and map**.

The phone does not read GitHub JSON. GitHub pulls official city sources, writes a single Supabase shape, and the app reads that.

```
NYC Open Data / api.nyc.gov
    → Discovery snapshots in this repo
    → Catch-up writer (official event contract)
    → RPC nycif_apply_staging_event_batch
    → event_occurrences / event_sources
    → view event_reader_rolling_v1
    → Edge Function nycif-native-map-feed
    → iOS EventService
    → list + pins
```

Do not publish bad data. Staging, review, and catch-up writes to the **native app** (Supabase `event_occurrences` → `nycif-native-map-feed`) are the product path. Promoting GPS into `data/location_cache.json` still requires an explicit human promote. WordPress is not a live map; at launch it becomes QR codes to the app.

## What the map needs

Every official row must match `scripts/official_event_contract.py`. That is the same shape `event_reader_rolling_v1` already exposes to the phone.

### List row (always)

| Field | Rule |
|---|---|
| `occurrence_id` | 64-char SHA-256 from OccurrenceIdentityV2. Never invent an id. |
| `title` | Non-empty |
| `start_at` | timestamptz with America/New_York offset |
| `end_at` | timestamptz or null; `end_at` must not be before `start_at` |
| `timezone` | `America/New_York` |
| `borough` | Manhattan / Brooklyn / Queens / Bronx / Staten Island / Citywide |
| `display_location` | Human place text. If unknown: `Location under review` |
| `public_category` | parks, arts, family, sports, market, housing, general, … |
| `status` | `active` |
| `source_active` | `true` |
| `source.source_name` | `nyc_open_data` |
| `source.source_dataset` | One of the datasets below |
| `source.source_event_id` | Stable city id |
| `metadata.reader.source_dataset` | Must match `source.source_dataset` |
| `metadata.reader.source_event_id` | Must match `source.source_event_id` |
| `metadata.reader.event_role` | `public_event` for the public list |

### Pin row (only when certified)

The map draws a pin only when **all** of these are true:

- `map_ready` is `true`
- `lat` / `lng` are finite and inside NYC `(40.4–41.1, -74.35–-73.65)`
- `metadata.reader.certified_pin` is `true`
- `metadata.reader.map_eligibility_state` is `MAP_READY`
- `metadata.reader.display_disposition` is `MAP`

If it is not a certified pin:

- `map_ready` is `false`
- `lat` and `lng` are **null** (no invented dots)
- `certified_pin` is `false`
- `map_eligibility_state` is `LIST_ONLY`

Today on the phone is the **overlap** window, not “starts today”:

`start_at < tomorrow_midnight_ET AND coalesce(end_at, start_at + 3 hours) >= today_midnight_ET`

That is why Today can show hundreds of listings: Parks pins when official coords exist, every public street permit is pinned, calendar/feast rows without official coords stay list-only.

## How each dataset is displayed

| Dataset | City source | List | Pin |
|---|---|---|---|
| `nyc-parks-bigapps-events` | NYC Open Data `w3wp-dpdi` | Yes | Only with official Parks lat/lng in NYC **and** pin evidence (`exact_pin_eligible` or `OFFICIAL_SOURCE_COORDINATE_SITE_VALIDATED`) |
| `tvpp-9vvx` | NYC Open Data street activity permits | Yes | **Always.** Parks facility coords, NYC DCP LION centerline midpoint, Geoclient blockface midpoint, or NYC GeoSearch. No Google. |
| `nyc-citywide-events-calendar-api` | api.nyc.gov Event Calendar | Yes | Only if the city snapshot already has official in-bounds coords. No geocoder fill. |
| `nyc-projected-feast-reference` | NYCIF feast intake | Yes | **Never**. Proposed geocoder coords stay off the map until a human promote. |

Civic help-place snapshots (SNAP, Homebase, Workforce1, …) are **not** this event calendar. Do not dump them onto the public event map.

## Culture community (gated, not public)

Sanctuary-city Culture enrichment (curated storefronts, civic 👮/🚒/shelters, 8-day Culture calendar, rolling public-help 🩸🏥💼🎓) is planned in [`docs/CULTURE_COMMUNITY_ENGINEERING_PLAN.md`](docs/CULTURE_COMMUNITY_ENGINEERING_PLAN.md). Publication stays off. Howard must drop the ~91 storefront CSV — this repo does not invent businesses or help-calendar events. Daily 6:00 AM ET help-calendar pull: [`.github/workflows/culture-help-calendar-daily.yml`](.github/workflows/culture-help-calendar-daily.yml) (staging artifacts + gated upsert into `culture_calendar_occurrence_v1`; no gate flip). Weekly civic: [`.github/workflows/culture-civic-weekly.yml`](.github/workflows/culture-civic-weekly.yml). Flip recipe: [`docs/CULTURE_CALENDAR_CIVIC_PUBLICATION.md`](docs/CULTURE_CALENDAR_CIVIC_PUBLICATION.md). Manual commands: [`scripts/culture/README.md`](scripts/culture/README.md). Cross-repo notes: [`docs/cross-repo/`](docs/cross-repo/).

## How we provide the data

1. **6:00pm America/New_York** — `Discovery Feed Refresh` pulls the city APIs into GitHub snapshots (`data/raw_nyc_open_data_snapshot.json`, `data/nyc_parks_bigapps_events_snapshot.json`, `data/nyc_citywide_events_calendar_snapshot.json`).
2. After that job succeeds — `Supabase Official Source Catch-up` turns those snapshots into the contract above and **pushes** them into Supabase. It does not expire rows. It does not edit `location_cache.json`.
3. The phone reads Supabase. Catch-up JSON under `data/reports/` is a job artifact, not what the app loads.

Run catch-up manually from Actions → **Supabase Official Source Catch-up** → `main` only after Discovery snapshots are fresh (Parks snapshot younger than 18 hours).

## Daily machine (new vs gone vs pins)

Do not eyeball the feed. Each Discovery run writes `data/reports/official_daily_machine_report.json` and `data/reports/official_occurrence_index.json`. Catch-up **will not write** to Supabase unless that report `qa_pass` is true.

The machine does four things:

1. **Account for every snapshot row** — accepted, or rejected with a reason. Silent drops fail the job.
2. **Diff against yesterday’s index** — `added`, `still_present`, `removed_from_city`. Removed rows are **reported only**. Catch-up still does not expire.
3. **Pin 100% of official coordinates** — every Parks row with official in-bounds evidence, and every calendar row that already has official in-bounds coords, must come out `map_ready`. Missing those pins fails the job.
4. **Pin every public TVPP row** — street permits go on the map from Parks facilities, NYC DCP LION, Geoclient, or NYC GeoSearch. Projected feast stays list-only. Multi-site Parks rows without a single official coordinate stay on the list (`list_only_samples`). That is accounted, not a miss.

`qa_pass: true` means the factory is the well-functioning machine. Open the report instead of walking the JSON by hand.

## NYC Developer Portal subscriptions → GitHub secrets

Put **Primary keys only** in GitHub repo secrets. Never commit keys. Never paste keys into issues, PRs, or this README.

Use **Settings → Secrets and variables → Actions**. Name them exactly as below. If a product already has a secret, overwrite it with the current Primary key.

| Portal product | State you reported | GitHub secret name | What it feeds |
|---|---|---|---|
| Event Calendar (started 2026-07-02) | Active | `NYC_EVENT_CAL_API_KEY` | Citywide Events Calendar → list (pin only if official coords) |
| Event Calendar Public Developers (started 2026-08-17) | Active | `NYC_EVENT_CALENDAR_API_KEY` | Same calendar job (alias). Keep both in sync. |
| Geoclient V2 User (started 2026-08-17) | Active | `NYC_GEOCLIENT_APP_ID` and `NYC_GEOCLIENT_APP_KEY` | Street-segment / intersection lookup. **Does not** auto-pin events. |
| DOT Public Developers (requested 2026-08-16) | Active | `NYC_DOT_API_KEY` | Not wired into the event map yet. Add the secret now so we can attach DOT feeds later without inventing pins. |
| NYC 311 Public Developers (started 2026-08-17) | Active | `NYC_311_API_KEY` | Not wired into the event map yet. 311 is service requests, not the Today event list. |
| NYC 311 Public-High Demand | Submitted | wait until **Active**, then `NYC_311_HIGH_DEMAND_API_KEY` | Same: not event pins. |
| NYC OTI Locator User (requested 2026-08-16) | Active | `NYC_OTI_LOCATOR_API_KEY` | Address locator. **Does not** auto-pin events. |
| Unlimited | Submitted | wait until **Active** | Do not add until the portal shows Active + a Primary key. |

Already used by Discovery / catch-up (keep these current):

- `SOCRATA_APP_TOKEN` or `NYC_SODA_APP_TOKEN` — NYC Open Data (Parks `w3wp-dpdi`, TVPP `tvpp-9vvx`)
- `SUPABASE_SERVICE_ROLE_KEY` — catch-up write into staging project `oggwpvdirkrnzoolparx`

Geoclient and OTI keys pin TVPP street segments (Geoclient) and may propose other coordinates in review artifacts. They must not set `map_ready=true` on feast, or on calendar rows that lack official source coords. TVPP pins may also come from the committed LION centerline cache and NYC GeoSearch.

## Protected files

Do not edit unless a human explicitly names the file and the operation:

- `data/location_cache.json`
- `data/nycif_staged_live_events.json`
- `data/staged_live_manifest.json`
- `data/previous_staged_live_events_snapshot.json`

## Local setup

Python **3.11**. Install and test:

```
python3 -m pip install -r requirements.txt
python3 -m pytest
```

`requirements.txt` is `rapidfuzz==3.*` and `pytest==9.0.2`.

Agent rules: `AGENTS.md`.
