# Culture calendar + civic publication (Howard)

Edges `nycif-culture-calendar` and `nycif-culture-civic` are live and
**fail-closed**. They return HTTP 200 with empty `occurrences` / `features`
until the matching publication gate is true **and** a row is `ACCEPTED` with
`promotion_allowed=true`.

This repo may load official Open Data / fixture-fallback rows into the live
tables while every gate stays `false`. That is staging behind the gate, not
publication.

## What is already loaded (behind the gate)

| Table | Reader | Loaded by |
| --- | --- | --- |
| `culture_calendar_occurrence_v1` | `nycif-culture-calendar` | Daily 6:00 AM ET job + one-shot backfill |
| `culture_civic_facility_v1` | `nycif-culture-civic` | Weekly Monday 6:00 AM ET job + one-shot backfill |
| `culture_reader_settings` (`id='v1'`) | both | **Do not write** from pull/load jobs |

New rows arrive as `review_status=pending`, `promotion_allowed=false`,
`map_ready=false`, `map_eligible=false`. Flipping a gate alone still returns
empty arrays. That is intentional.

## Gated backfill results (2026-09-06)

Loaded into `oggwpvdirkrnzoolparx` with every publication / layer gate
**false**. Public edges stayed HTTP 200 with empty arrays.

| Table | Rows | Status |
| --- | --- | --- |
| `culture_calendar_occurrence_v1` | 661 | all `pending`, `promotion_allowed=false`, `map_ready=false` |
| `culture_civic_facility_v1` | 297 | all `pending`, `promotion_allowed=false`, `map_eligible=false` |
| `culture_reader_settings` | unchanged | do not write from pull/load jobs |

Calendar breakdown:

| Source | Kind | Rows | Notes |
| --- | --- | --- | --- |
| Workforce1 live SODA `kf2b-aeh5` | `job_fair` | 656 | Official pull. The live dataset currently returns March 2020 rows, not the current week. |
| NYBC fixture | `blood_drive` | 1 | Title contains `(fixture)` — do not accept unless intentional |
| SHOW fixture | `mobile_clinic` + `resource_van` | 2 | Live puller not wired (exit 3) |
| NYS DOL fixture | `job_fair` | 1 | Live puller not wired (exit 3) |
| ASPCA fixture | `pet_mobile` | 1 | Live puller not wired (exit 3) |
| CUNY | — | 0 | Registry only; no events invented |

Civic breakdown:

| Kind | Dataset | Rows | Notes |
| --- | --- | --- | --- |
| `civic_nypd` | `y76i-bdw7` | 78 | Live precinct polygons. `addressable=false`. Not house pins. |
| `civic_fdny` | `hc8x-tcnd` | 219 | Live firehouses. In-bounds coords, `addressable=true`, still `map_eligible=false`. |
| `shelter` | `g9nt-57fp` | 0 | Live census succeeded and returned 0 rows (`census_only`). Related dirs `bmxf-3rd4` / `ntcm-2w4k` were not substituted. Not a silent drop. |

Only 5 calendar rows fall in/near the reader's 8-day window, and those 5 are
fixtures. Accepting the 2020 Workforce1 rows and flipping gates will **not**
fill iOS Now/Tonight/7 Days until SODA has current events. The daily 6:00 AM
ET job re-pulls `kf2b-aeh5` and upserts without undoing ACCEPTED rows.

## One-shot / replay

```bash
# Dry-run (pull live SODA where wired, else fixtures; no Supabase write)
python3 scripts/culture/backfill_calendar_civic.py --dataset all

# Fixture-only offline
python3 scripts/culture/backfill_calendar_civic.py --dataset all --fixture-only

# Upsert into oggwpvdirkrnzoolparx (gates stay false)
SUPABASE_URL=https://oggwpvdirkrnzoolparx.supabase.co \
SUPABASE_SERVICE_ROLE_KEY=… \
python3 scripts/culture/backfill_calendar_civic.py --dataset all --write
```

Daily calendar-only load (same as Actions):

```bash
python3 scripts/culture/load_calendar_civic_staging.py --dataset calendar --write
```

## Review SQL (read-only)

```sql
select id,
       calendar_publication_enabled,
       help_calendar_publication_enabled,
       civic_publication_enabled,
       nypd_layer_enabled,
       fdny_layer_enabled,
       shelter_layer_enabled,
       blood_layer_enabled,
       mobile_clinic_layer_enabled,
       jobs_layer_enabled,
       college_layer_enabled,
       pet_care_layer_enabled,
       business_publication_enabled
from public.culture_reader_settings
where id = 'v1';

select source_dataset, occurrence_kind, review_status, promotion_allowed, count(*)
from public.culture_calendar_occurrence_v1
group by 1, 2, 3, 4
order by 1, 2;

select place_kind, source_dataset, review_status, addressable, promotion_allowed, count(*)
from public.culture_civic_facility_v1
group by 1, 2, 3, 4, 5
order by 1, 2;
```

## Flip after review (manual, not automated)

Do not run this during the gated backfill. Run only after you have reviewed
the pending official rows and want iOS chips to light up.

### 1. Accept the official rows you want public

Example: Workforce1 SODA rows you reviewed:

```sql
update public.culture_calendar_occurrence_v1
set
  review_status = 'ACCEPTED',
  manual_review_status = 'approved',
  manual_reviewer = 'howard',
  manual_reviewed_at_utc = now(),
  approval_decision_reason = 'Official Workforce1 SODA kf2b-aeh5 after review',
  promotion_allowed = true
where source_dataset = 'kf2b-aeh5'
  and review_status = 'pending';
```

Example: FDNY firehouses that already have in-bounds city coords:

```sql
update public.culture_civic_facility_v1
set
  review_status = 'ACCEPTED',
  manual_review_status = 'approved',
  manual_reviewer = 'howard',
  manual_reviewed_at_utc = now(),
  approval_decision_reason = 'Official FDNY listing hc8x-tcnd after review',
  promotion_allowed = true
where place_kind = 'civic_fdny'
  and addressable is true
  and lat is not null
  and review_status = 'pending';
```

NYPD `y76i-bdw7` rows are precinct **polygons**, not house pins. Leave them
`addressable=false` until a precinct-house address file is reviewed.
Census-only `g9nt-57fp` shelter rows must stay unpinned.

Do not accept fixture-titled rows (title contains `(fixture)`) unless you
intentionally want those test shapes.

### 2. Flip only the gates you want

```sql
update public.culture_reader_settings
set
  calendar_publication_enabled = true,          -- master calendar
  help_calendar_publication_enabled = true,     -- public-help chips
  jobs_layer_enabled = true,                    -- 💼
  -- blood_layer_enabled = true,                -- 🩸
  -- mobile_clinic_layer_enabled = true,        -- 🏥
  -- college_layer_enabled = true,              -- 🎓
  -- pet_care_layer_enabled = true,             -- 🐾
  civic_publication_enabled = true,             -- master civic
  fdny_layer_enabled = true,                    -- 🚒
  -- nypd_layer_enabled = true,                 -- 👮 after house-address review
  -- shelter_layer_enabled = true,              -- after addressable directory
  updated_at = now()
where id = 'v1';
```

Leave `business_publication_enabled` false until the ~91 storefront CSV is
reviewed. This document does not flip that flag.

### 3. Smoke

```bash
curl -sS "https://oggwpvdirkrnzoolparx.supabase.co/functions/v1/nycif-culture-calendar?mode=seven" \
  -H "apikey: $ANON" -H "Authorization: Bearer $ANON" | jq '{calendar_publication_enabled, occurrences:(.occurrences|length)}'
curl -sS "https://oggwpvdirkrnzoolparx.supabase.co/functions/v1/nycif-culture-civic" \
  -H "apikey: $ANON" -H "Authorization: Bearer $ANON" | jq '{civic_publication_enabled, features:(.features|length), layers}'
```

If a gate is true and counts are still 0, no `ACCEPTED` + `promotion_allowed`
rows match the 8-day window / layer filter. Do not invent replacements.
