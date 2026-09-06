# Culture + sanctuary-city community engineering plan

Status: **scaffold / reviewable plan** — not a production deploy.
Publication: **off**. `culture_reader_settings.business_publication_enabled` stays `false`.
Storefronts: **Howard must drop the ~91 CSV**. This repo does not invent businesses.

This document is the implementation map for Culture community enrichment in
`setoxxx/nycif-live-feeds`, with handoff notes for `setoxxx/nycif-data-pipeline`
and `setoxxx/NYCInFocus`. Official reader destination is the native app via
Supabase edge functions. WordPress `/map/` is not a live event or Culture
destination.

---

## 1. Product intent

NYC is a sanctuary city. Culture in the app is **not** a generated Yellow Pages
of fake “ethnic businesses.” It is:

1. **Reviewed storefronts inside documented cultural borders** — Canarsie
   Haitian/Jamaican, Midwood Jewish, Little Pakistan, places of worship, and
   Howard’s curated list (~91). **The store name is the qualification hint**
   (“this name is why it belongs in this area”), never a stereotype inferred
   from owner surname or census tract.
2. **Sanctuary-city resources people actually look for** — immigration legal
   help (MOIA hotline), health (NYC Care / H+H / FQHCs), food pantries,
   community/faith centers, know-your-rights, multilingual city services.
   Pin only when we have a real address. Hotlines stay **non-map resources**.
3. **Civic safety layer** — NYPD precincts (👮) and FDNY firehouses (🚒).
4. **Homeless shelters** — prefer an addressable directory, not a census table.
5. **Low-cost pet care / ASPCA Community Medicine** — rolling calendar
   occurrences (zip / waitlist / van day), **not** invented fixed pins.
6. **8-day Culture calendar** — same Now / Tonight / 7 Days UX pattern as
   events, but Culture-sorted (worship services, cultural festivals, ASPCA van
   days, community clinics) for **today + next 7 days**.
7. **Rolling public-help calendar** (map pin only when that occurrence already
   has lat/lng) — mobile blood drives, H+H S.H.O.W. clinics / resource vans,
   ASPCA mobile pet, Workforce1 and NYS DOL job fairs/workshops, CUNY career
   events. These **move**. Store them as `culture_calendar_occurrence_v1`, not
   fake fixed storefronts.

---

## 2. Current production state (2026-09-06)

| Surface | State |
| --- | --- |
| `nycif-culture-boundaries` | Live. ~105 neighborhood rings. White “line in the sand.” |
| `nycif-culture-areas` | Live. ~53 areas. `business_count` 0. |
| `nycif-culture-places` | **Gated.** `business_publication_enabled: false`. `place_count` 0 on the public reader. |
| `culture_place_beta_v1` | ~23 **sample** rows. **0 ACCEPTED.** Samples must never publish. |
| `culture_reader_settings.business_publication_enabled` | `false` |
| iOS Culture tab (`NYCInFocus`) | Borders + area chips. Empty storefront pins until the feed flag flips. Client does not invent businesses. No `service_role` in the app. |
| `nycif-data-pipeline` `culture/` | Protected-staging DCWP classification (evidence-gated). WordPress staging embed is **not** a live destination. Name-lead never yields `ACCEPTED`. |
| Official event map | Unchanged. Culture is a **separate** reader lane. Do not merge civic Culture rows into `event_occurrences`. |

Tonight liquor / dispensary / 5pm layers are a **different** authority
(`nycif_night_layer_cache`). Do not read `culture_place_beta_v1` for those.

---

## 3. Non-negotiable safety

- Do not publish bad data.
- Do not invent storefronts, worship sites, clinics, or van pins.
- Do not flip `business_publication_enabled` or any new layer gate in this
  scaffold.
- Do not write `data/location_cache.json`, `data/nycif_staged_live_events.json`,
  or WordPress `/map/`.
- Do not put `SUPABASE_SERVICE_ROLE_KEY` in iOS, Android, or any public client.
- Edge functions fail closed: if a layer gate is false, return empty features
  plus the gate flag. Never leak sample / pending / rejected rows.
- A name is a **review lead**, not evidence. That rule already exists in
  `nycif-data-pipeline` (`REVIEW_NAME_LEAD_NEEDS_EVIDENCE`). Keep it.
- Kosher / halal tags require documented certification or business-provided
  designation — never cuisine text, name, or neighborhood.
- Census / ACS is aggregate context only.
- GPS: NYC bounds from `scripts/schema_v1_common.py` (`40.4774–40.9176`,
  `-74.2591–-73.7004`). No Google geocoder. Proposed coords stay
  `promotion_allowed=false` until a human approve.
- Civic Open Data pulls write staging artifacts, then may upsert **pending**
  rows into live civic/calendar tables. They do not promote or flip gates.

Required safety fields on every Culture staging row (same family as GPS review):

`group_key` / `place_id`, `display_location`, `borough`, `proposed_lat`,
`proposed_lng`, `geocoder_source`, `geocoder_confidence`, `confidence_reason`,
`manual_review_status`, `manual_review_notes`, `manual_reviewer`,
`manual_reviewed_at_utc`, `approval_decision_reason`, `promotion_allowed`,
`public_map_modified`, `location_cache_modified`, `staged_feed_modified`.

---

## 4. Recommended data model

Keep **curated Culture places** and **official civic facilities** separate.
Reuse `place_kind` on places for human-curated rows. Use
`culture_civic_facility_v1` for city Open Data facilities. Use
`culture_calendar_occurrence_v1` for the 8-day reader. Keep
`culture_reader_settings` as the fail-closed publication singleton.

SQL draft: `supabase/migrations/20260906050000_culture_community_scaffold_v1.sql`.
It is idempotent (`IF NOT EXISTS`) and **does not enable publication**.

### 4.1 `culture_reader_settings` (singleton)

Existing:

- `business_publication_enabled` — **must remain `false`** until Howard
  approves ACCEPTED storefronts.

Add per-layer gates (all default `false`):

| Gate | Reader |
| --- | --- |
| `business_publication_enabled` | `nycif-culture-places` storefronts / worship |
| `civic_publication_enabled` | master civic switch |
| `nypd_layer_enabled` | 👮 precincts |
| `fdny_layer_enabled` | 🚒 firehouses |
| `shelter_layer_enabled` | shelters |
| `pet_care_layer_enabled` | ASPCA / low-cost pet care **pins** (usually off; calendar first) |
| `resource_layer_enabled` | pinable sanctuary resources |
| `calendar_publication_enabled` | `nycif-culture-calendar` |
| `help_calendar_publication_enabled` | Master switch for public-help chips |
| `blood_layer_enabled` | 🩸 blood drives |
| `mobile_clinic_layer_enabled` | 🏥 SHOW / resource vans |
| `jobs_layer_enabled` | 💼 Workforce1 / DOL |
| `college_layer_enabled` | 🎓 CUNY career events |

A layer is visible only when **its gate AND** (for civic children)
`civic_publication_enabled` are true **and** the row is `ACCEPTED` with
certified NYC coords (or is an explicit non-map resource).

### 4.2 `culture_place_beta_v1` (extend, do not replace)

Existing reader contract (iOS `CulturePlace`): `business_id`, `business_name`,
`address`, `community_district`, `lat`, `lng`, `cultural_tags`, `dietary_tags`,
`review_status`, `confidence`, `area_ids`, `matched_tags`, `reason_codes`,
`is_sample`, `feed_version`.

Add:

- `place_kind` — `storefront | worship | civic_nypd | civic_fdny | shelter | pet_care | resource`
- `qualification_hint` — usually the name; optional reviewer sentence
- `map_eligible` — generated / constrained: never true unless ACCEPTED + coords
  + matching layer gate
- `is_sample` already present — samples stay unpublished even if a flag is
  flipped by mistake (edge function must exclude `is_sample`)

The ~23 current samples stay `is_sample=true`, `review_status` ≠ `ACCEPTED`.

**Do not** dump NYPD/FDNY/shelter Open Data into this table by default. Those
rows are civic facilities, not Culture businesses.

### 4.3 `culture_civic_facility_v1` (new)

Official city facilities for the civic edge feed.

| Column | Notes |
| --- | --- |
| `facility_id` | Stable hash of dataset + source id |
| `place_kind` | `civic_nypd` / `civic_fdny` / `shelter` |
| `source_dataset` | `y76i-bdw7` / `hc8x-tcnd` / `g9nt-57fp` (or replacement directory) |
| `source_facility_id` | City row id |
| `display_name` | “84th Precinct”, “Engine 221 / Ladder 104” |
| `address`, `borough`, `lat`, `lng` | Null coords ⇒ list-only / omit pin |
| `emoji` | 👮 / 🚒 / shelter glyph |
| `geometry` | Optional precinct polygon (NYPD). Pins are **houses**, not invented centroids, unless a reviewer accepts a centroid with a documented reason. |
| `addressable` | False for census-only shelter rows |
| review + safety fields | Same fail-closed set |

### 4.4 `culture_calendar_occurrence_v1` (new, 8-day reader)

Same identity discipline as events (`occurrence_id` style hash; do not invent
ids). **Not** written into `event_occurrences`.

| Column | Notes |
| --- | --- |
| `occurrence_id` | Deterministic |
| `calendar_kind` / `occurrence_kind` | Culture: `worship_service` / `cultural_festival` / `aspca_van` / `community_clinic` / `other`. Help: `blood_drive` / `mobile_clinic` / `job_fair` / `workshop` / `pet_mobile` / `resource_van`. |
| `title`, `start_at`, `end_at`, `timezone` | `America/New_York` |
| `place_id` / `facility_id` | Optional link |
| `map_ready` | True only with certified NYC coords |
| `zip_codes` | ASPCA / clinic service area when a street pin is not public |
| `waitlist_gated` | True for ASPCA Community Medicine until a public site exists |
| `pin_policy` | `certified_pin` / `list_only` / `zip_area_only` |

Reader window: **today 00:00 ET through today+7 24:00 ET** (8 civil days).
Chips: Culture Now / Culture Tonight / Culture 7 Days — same overlap rules as
`nycif-native-map-feed` (`TONIGHT` = 17:00–23:59:59 ET).

### 4.5 `culture_resource_v1` (new, mostly non-map)

Sanctuary resources.

| `resource_kind` | Pin? | Example |
| --- | --- | --- |
| `immigration_legal` | Address yes / hotline no | MOIA Immigrant Affairs hotline |
| `health` | Clinic address yes | NYC Care, H+H, FQHC |
| `food_pantry` | Address yes | Official pantry directory (TBD source) |
| `community_faith` | Address yes | Reviewed worship / community center |
| `know_your_rights` | Event/site yes, flyer no | Existing civic snapshot `pnpe-ubtz` |
| `multilingual_city` | Office yes / 311 no | City language-access offices |

Hotlines: `is_hotline=true`, `lat`/`lng` null, never `map_ready`.

---

## 5. Sources

| Need | Source | Notes |
| --- | --- | --- |
| Curated storefronts (~91) | **Howard CSV** → `scripts/culture/import_curated_storefronts.py` | Required. Template: `data/culture/curated_storefronts.template.csv`. Missing file = hard fail, **zero invented rows**. |
| Places of worship | Howard CSV `place_kind=worship` and/or later official directory | Do not scrape Google. |
| Cultural area rings | Existing `nycif-culture-boundaries` / `nycif-culture-areas` | Already live. Match storefronts by `area_ids` or point-in-polygon. |
| NYPD precincts | NYC Open Data Police Precincts `y76i-bdw7` | **Polygons.** This repo already builds `data/nypd_precinct_boundaries_reference.json` (preview geofence, `promotion_allowed=false`). Culture pull writes a **separate** staging artifact. 👮 pins need official house addresses; do not silently pin polygon centroids. |
| FDNY firehouses | FDNY Firehouse Listing `hc8x-tcnd` | Addressable listing. Map name + address + coords when present and in NYC. |
| Shelters | `g9nt-57fp` **inspected first** | If the payload is census-only (borough counts, no address), **do not pin**. Prefer an addressable DHS / drop-in directory. Related existing civic snapshots: Homeless Drop-In `bmxf-3rd4`, Homebase `ntcm-2w4k`. |
| MOIA / KYR | Existing civic `pnpe-ubtz` + MOIA hotline (non-map) | Reuse `scripts/civic_people_facing_common.py` catalog; do not duplicate into the event calendar. |
| SNAP / benefits / markets | Existing civic help-place snapshots | Stay in civic review lane until a Culture resource gate is explicitly enabled. |
| NYC Care / H+H / FQHC | Official directories (TBD, not invented) | Phase 2 ingest after a named dataset is approved. |
| Food pantries | Official city / Food Bank directory (TBD) | Same. |
| ASPCA Community Medicine | ASPCA published schedule (zip / waitlist) | Calendar occurrences (`pet_mobile`). `waitlist_gated=true`. No fake van pins. Stub: `pull_aspca_mobile.py`. |
| Mobile blood drives 🩸 | New York Blood Center `donate.nybc.org` | `pull_nybc_blood_drives.py` — fixture in CI; live scrape/API **not wired**. Do not invent drive sites. |
| Mobile clinics / vans 🏥 | NYC H+H S.H.O.W. + other H+H mobile schedules | `pull_show_mobile_clinics.py`. Require address **and** time before a pin is even *proposed*. |
| Workforce1 job fairs 💼 | NYC Open Data `kf2b-aeh5` | **Real SODA pull:** `pull_workforce1_events.py`. Reuses civic field names (`event_title`, `event_date`, `check_in_*`). Not merged into `event_occurrences`. |
| NYS DOL / Career Center 💼 | dol.ny.gov / Trumba NYC-region | `pull_dol_career_events.py` — NYC-region filter; live Trumba not wired. Albany etc. dropped. |
| CUNY career fairs 🎓 | Public campus career pages | `data/culture/cuny_career_source_registry.json` + `pull_cuny_career_events.py`. Registry-only ⇒ **0** invented events. |
| DCWP licenses (`w7w3-xahh`) | `nycif-data-pipeline` `culture/` only | Evidence overlay + human review. **Not** a storefront publisher. Name-lead ≠ ACCEPTED. |

Do not use Google Places to backfill Howard’s list.

---

## 6. Phased delivery

### Phase C0 — this PR (scaffold)

Docs, SQL draft, Python skeletons, edge-function outlines, fail-closed
validator. **No publication. No invented storefronts. No production apply
required.**

### Phase C1 — civic ingest (staging only)

1. Run `pull_nypd_precincts`, `pull_fdny_firehouses`, `pull_shelters` against
   fixtures or SODA.
2. Inspect shelter addressability. If `g9nt-57fp` is census-only, file a
   replacement directory and keep pins off.
3. Human review of civic staging. Still `promotion_allowed=false`.

### Phase C2 — Howard storefront CSV

1. Howard drops `data/culture/curated_storefronts.csv` (or a private path).
2. `import_curated_storefronts.py` writes pending staging rows.
3. Reviewers accept **row by row**. Name is the qualify hint, not auto-ACCEPT.
4. `validate_before_publish.py` must pass before anyone discusses a flag flip.

### Phase C3 — sanctuary resources + ASPCA calendar

Hotlines first (non-map). Addressable clinics/pantries second. ASPCA as
8-day occurrences with zip/waitlist semantics.

### Phase C3b — rolling public-help calendar (this follow-up)

Staging fetchers only. Gates stay false.

| Chip | Emoji | `occurrence_kind` | Script |
| --- | --- | --- | --- |
| Blood | 🩸 | `blood_drive` | `pull_nybc_blood_drives.py` (stub + fixture) |
| Mobile clinic | 🏥 | `mobile_clinic`, `resource_van` | `pull_show_mobile_clinics.py` (stub + fixture) |
| Jobs | 💼 | `job_fair`, `workshop` | `pull_workforce1_events.py` (SODA `kf2b-aeh5`), `pull_dol_career_events.py` (stub + NYC filter) |
| College | 🎓 | `job_fair` / `workshop` + `source_family=cuny` | `pull_cuny_career_events.py` + source registry |
| Pet care | 🐾 | `pet_mobile` | `pull_aspca_mobile.py` (stub + fixture) |

Shared shape: `scripts/culture/calendar_normalize.py` →
`culture_calendar_occurrence_v1` JSON. `map_ready` stays false. Missing
title or start ⇒ row dropped, never invented.

#### Approved pull cadence (Howard, 2026-09-06)

Daily job: `.github/workflows/culture-help-calendar-daily.yml`. Staging
artifacts plus a gated upsert into `culture_calendar_occurrence_v1` when
`SUPABASE_SERVICE_ROLE_KEY` is present. No gate flips, no edge deploys.

GitHub cron is UTC-only. `0 10 * * *` is **6:00 AM America/New_York during
EDT (UTC−4)**. During EST (UTC−5) the same cron fires at 5:00 AM local.
Ops keep 10:00 UTC year-round as the morning ET job.

| Cadence | America/New_York | UTC cron (EDT) | Sources |
| --- | --- | --- | --- |
| Daily | 6:00 AM | `0 10 * * *` | Workforce1, NYS DOL, CUNY, NYBC, H+H SHOW, ASPCA |
| Weekly | Monday 6:00 AM | `0 10 * * 1` | NYPD precincts, FDNY firehouses, shelters |
| Optional later | 2:00 PM | `0 18 * * *` (EDT; not scheduled yet) | Blood / mobile refresh if a live scrape is later wired |

Manual run notes: `scripts/culture/README.md`.

### Phase C4 — edge readers (still gated)

Extend `nycif-culture-places` (already exists, gated). Add
`nycif-culture-civic` and `nycif-culture-calendar`. Deploy with **all gates
false**. iOS can decode empty feeds.

Live apply (2026-09-06): `20260906154500_culture_calendar_civic_live_v1.sql`
adds civic/calendar tables and gate columns on the existing
`culture_reader_settings` singleton (`id = 'v1'`). Do **not** apply the
draft `id = 1` scaffold as-is. `business_publication_enabled` is not
assigned. Edge source: `supabase/functions/nycif-culture-calendar/index.ts`
and `nycif-culture-civic/index.ts`, `verify_jwt=false`.

### Phase C5 — iOS Culture UX

`NYCInFocus` only, after feeds exist:

- Keep borders.
- Add civic layer toggles (👮 🚒 shelter) that honor server gates.
- Add Culture Now / Tonight / 7 Days over `nycif-culture-calendar`.
- Resource sheet for hotlines.
- Still no client-side invention. Still no `service_role`.

### Phase C6 — publication (explicit human only)

A flag may flip only if:

- `validate_before_publish` `qa_pass` and `publication_allowed=true`
- every published row is `ACCEPTED` with reviewer, timestamp, reason
- coords certified or row is an explicit hotline
- samples excluded
- WordPress untouched
- native-app feed verified after catch-up / edge deploy

This phase is **not** authorized by this PR.

---

## 7. Ingest scripts (this repo)

Package: `scripts/culture/`.

| Script | Role |
| --- | --- |
| `common.py` | Staging paths, safety envelope, NYC bounds, SODA helper, place kinds |
| `pull_nypd_precincts.py` | `y76i-bdw7` → `data/culture/staging/nypd_precincts.json` |
| `pull_fdny_firehouses.py` | `hc8x-tcnd` → `data/culture/staging/fdny_firehouses.json` |
| `pull_shelters.py` | `g9nt-57fp` → staging + addressability report |
| `import_curated_storefronts.py` | CSV → staging. Missing CSV exits nonzero. |
| `calendar_normalize.py` | Shared help-calendar occurrence shape + chips |
| `pull_workforce1_events.py` | SODA `kf2b-aeh5` → calendar staging |
| `pull_nybc_blood_drives.py` | NYBC stub + fixture (no live scrape in CI) |
| `pull_show_mobile_clinics.py` | H+H SHOW stub + fixture |
| `pull_dol_career_events.py` | DOL/Trumba stub + NYC-region filter |
| `pull_cuny_career_events.py` | CUNY source registry; 0 events unless fixture |
| `pull_aspca_mobile.py` | ASPCA waitlist/zip calendar stub |
| `validate_before_publish.py` | Fail-closed gate. Default outcome: publication blocked. |
| `load_calendar_civic_staging.py` | Upsert pending staging rows into live calendar/civic tables. Dry-run default. Never flips gates. |
| `backfill_calendar_civic.py` | One-shot pull (live + fixture fallback) then load. |

Daily Actions job (6:00 AM ET / `0 10 * * *` UTC):
`.github/workflows/culture-help-calendar-daily.yml` runs Workforce1 live
SODA, stubs via `--fixture` when `--live` exits 2/3, then
`validate_before_publish.py`. Uploads `data/culture/staging/` and
`reports/` as artifacts. When the service-role secret is present, upserts
pending calendar rows into `culture_calendar_occurrence_v1`. Does not
commit staging JSON. Does not flip gates.

Weekly civic job: `.github/workflows/culture-civic-weekly.yml` (`0 10 * * 1`
UTC). Same fail-closed load into `culture_civic_facility_v1`.

One-shot replay + Howard flip recipe:
`docs/CULTURE_CALENDAR_CIVIC_PUBLICATION.md`.
`scripts/culture/backfill_calendar_civic.py` / `load_calendar_civic_staging.py`.

All writes stay under `data/culture/**`. They must not rewrite
`data/nypd_precinct_boundaries_reference.json` (already used by press
geofence preview) or protected event files.

Offline: `--fixture` loads a tiny committed fixture. Live SODA is optional
and never auto-promotes.

---

## 8. Edge functions

Outlines live next to the existing native-map function:

- `supabase/functions/nycif-culture-places/README.md` — already live and
  gated; extend `place_kind`, keep `business_publication_enabled`.
- `supabase/functions/nycif-culture-civic/` — gated reader (`index.ts`).
- `supabase/functions/nycif-culture-calendar/` — gated reader (`index.ts`).

Shared rules:

- CORS GET/HEAD/OPTIONS only.
- Anon key from the client; **service role only inside the function**.
- Read `culture_reader_settings` first. Gate false ⇒ `{ enabled: false, features: [] }`.
- Exclude `is_sample`, non-`ACCEPTED`, out-of-bounds, and `promotion_allowed=false` rows.
- Cache like the native map feed (short public max-age). Last-known-good on
  upstream failure — never a half-built invented layer.

---

## 9. iOS / NYCInFocus handoff

See `docs/cross-repo/CULTURE_COMMUNITY_NYCINFOCUS.md`.

Today the app already:

- Calls `nycif-culture-places` / `areas` / `boundaries`
- Honors `businessPublicationEnabled`
- Shows a storefront-off explanation
- Uses name-lead labels **only when published**
- Ships no `service_role`

iOS PR #12 already reads the gated calendar/civic edges. Missing or
gate-false responses stay empty. The client must not fabricate pins.

---

## 10. nycif-data-pipeline handoff

See `docs/cross-repo/CULTURE_COMMUNITY_NYCIF_DATA_PIPELINE.md`.

That repo’s `culture/` slice is **DCWP evidence classification** for a
protected-staging WordPress embed. It must stay:

- evidence-gated
- name-lead → worklist only
- not a live WordPress map
- not the source of invented storefronts for the native app

This live-feeds lane is the **official** Culture civic + curated-list path
into Supabase. Pipeline DCWP matches may later **inform** a review worklist;
they must not skip Howard’s CSV or the ACCEPTED gate.

---

## 11. What this PR does **not** do

- Does not enable publication.
- Does not invent or seed ~91 storefronts.
- Does not apply the SQL migration to production.
- Does not deploy new edge functions.
- Does not change iOS or data-pipeline repos (notes only).
- Does not write WordPress, `location_cache.json`, or the official event feed.
- Does not treat `g9nt-57fp` census rows as shelter pins.
- Does not pin ASPCA vans at guessed addresses.
- Does not invent blood drives, SHOW clinics, DOL fairs, or CUNY career events.
- Does not wire live NYBC / Trumba / CUNY scrapes (CI is fixture-only).

---

## 12. What to run next

```bash
python3 -m pytest tests/test_culture_community_scaffold.py tests/test_culture_help_calendar.py tests/test_culture_help_calendar_daily_workflow.py tests/test_culture_calendar_civic_load.py
python3 -m compileall scripts/culture tests/test_culture_community_scaffold.py tests/test_culture_help_calendar.py tests/test_culture_help_calendar_daily_workflow.py tests/test_culture_calendar_civic_load.py
python3 scripts/culture/validate_before_publish.py
# Expected: qa_pass true, publication_allowed false
# Daily 6am ET job: Actions → Culture help-calendar daily pull (workflow_dispatch)
# Weekly civic: Actions → Culture civic weekly pull
# One-shot: python3 scripts/culture/backfill_calendar_civic.py --dataset all
# Howard flip (after review only): docs/CULTURE_CALENDAR_CIVIC_PUBLICATION.md
```

After Howard drops the CSV:

```bash
python3 scripts/culture/import_curated_storefronts.py --csv data/culture/curated_storefronts.csv
python3 scripts/culture/validate_before_publish.py
```

Civic pulls (optional network):

```bash
python3 scripts/culture/pull_nypd_precincts.py --fixture tests/fixtures/culture/nypd_precincts.fixture.json
python3 scripts/culture/pull_fdny_firehouses.py --fixture tests/fixtures/culture/fdny_firehouses.fixture.json
python3 scripts/culture/pull_shelters.py --fixture tests/fixtures/culture/shelters_census_only.fixture.json
python3 scripts/culture/pull_workforce1_events.py --fixture tests/fixtures/culture/workforce1_events.fixture.json
# optional live SODA (not required for CI):
# python3 scripts/culture/pull_workforce1_events.py --live
python3 scripts/culture/pull_nybc_blood_drives.py --fixture tests/fixtures/culture/nybc_blood_drives.fixture.json
python3 scripts/culture/pull_show_mobile_clinics.py --fixture tests/fixtures/culture/show_mobile_clinics.fixture.json
python3 scripts/culture/pull_dol_career_events.py --fixture tests/fixtures/culture/dol_career_events.fixture.json
python3 scripts/culture/pull_cuny_career_events.py
python3 scripts/culture/pull_aspca_mobile.py --fixture tests/fixtures/culture/aspca_mobile.fixture.json
python3 -m pytest tests/test_culture_help_calendar.py
```

Still unapproved / unpromoted after this PR: every storefront, civic pin,
shelter, ASPCA occurrence, sanctuary resource, blood drive, mobile clinic,
job fair, and college career event.

---

## 13. Review checklist

- [x] Plan checked into `nycif-live-feeds`
- [ ] Howard CSV received (blocked)
- [ ] Shelter dataset confirmed addressable (or replacement chosen)
- [ ] SQL reviewed against live `culture_place_beta_v1` before any apply
- [x] Edge functions deployed gated (PR #479)
- [x] iOS calendar / civic chips merged (`NYCInFocus` #12); still empty until Phase C6
- [ ] Explicit human order to flip any publication gate
- [ ] Howard CSV received for storefronts (still blocked; unrelated to help calendar)
- [x] Help-calendar fetchers + fixtures (Workforce1 SODA-ready; others stubbed)
- [x] Daily 6am ET help-calendar Actions job (staging + gated table load)
- [x] Weekly civic Actions job (NYPD / FDNY / shelters → gated table load)
- [x] One-shot backfill + Howard flip recipe (`docs/CULTURE_CALENDAR_CIVIC_PUBLICATION.md`)
