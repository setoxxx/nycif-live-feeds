# NYC Event Atlas — Complete Method and Cursor Handoff


---

# Executive Summary

This repository is a technical handoff for continuing the NYC Event Atlas from the existing cumulative dataset.

## Current baseline

- Input file: `NYC_EVENTS_MASTER_CUMULATIVE.csv`
- Current rows: 827 event occurrences
- Export schema: 59 columns, preserved exactly
- Current statuses: Confirmed, Permitted, TBA
- Goal: incremental, source-backed additions and explicit updates without duplicate occurrences

## What this package provides

1. A source-acquisition playbook for government data, official calendars, JSON-LD, ICS, WordPress, PDFs, and ordinary HTML.
2. A SQLite schema that separates raw evidence, extracted candidates, canonical events, sources, updates, and review tasks.
3. Runnable Python modules for:
   - source discovery
   - Socrata permit extraction
   - JSON-LD and iCalendar extraction
   - normalization
   - exact and fuzzy duplicate detection
   - validation
   - CSV/TXT/GeoJSON/KML export
4. A Cursor master prompt and execution checklist.
5. A current-database audit and source inventory generated from the 827-row cumulative file.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate              # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
cp .env.example .env

python scripts/bootstrap_db.py
python scripts/import_existing.py /path/to/NYC_EVENTS_MASTER_CUMULATIVE.csv
python scripts/discover_sources.py
python scripts/fetch_permits.py --start 2026-07-16 --end 2026-12-31
python scripts/run_pipeline.py --start 2026-07-16 --end 2026-12-31
python scripts/export_dataset.py --out data/exports
python scripts/validate_exports.py data/exports/NYC_EVENTS_MASTER_CUMULATIVE.csv
```

## Core operating rule

Never edit the canonical cumulative CSV directly. Every run should:

1. acquire raw evidence;
2. store immutable snapshots;
3. extract candidates;
4. normalize;
5. compare against canonical events;
6. auto-accept only high-confidence non-duplicates;
7. queue ambiguous matches for review;
8. apply updates through the update ledger;
9. validate;
10. export.

See `docs/OPERATIONS_RUNBOOK.md` for the complete cycle.

---

# Architecture

## Why the database needs layers

A public event can appear in a permit feed, an organizer page, a parish bulletin, a BID calendar, a PDF vendor schedule, and media listings. The system must preserve evidence separately from the canonical event row.

## Recommended layers

### 1. Source registry
Tracks every monitored domain or feed, its acquisition method, authority level, crawl policy, update frequency, and last result.

### 2. Raw evidence store
Immutable HTTP bodies, downloaded PDFs/ICS/CSV/JSON, screenshot references, hashes, headers, retrieval timestamps, and parser version.

### 3. Extracted candidates
One candidate per discovered occurrence before normalization. Preserve the source-native title, date text, location text, and source record ID.

### 4. Normalized candidates
Candidates mapped into the 59-field schema, but not yet canonical.

### 5. Canonical events
Accepted event occurrences with permanent IDs.

### 6. Event series
Stable identity for recurring programs such as Queens Night Market or a yearly feast.

### 7. Event-source links
Many-to-many evidence links with field-level support notes.

### 8. Update ledger
Explicit changes to existing permanent IDs. The cumulative export applies the update while Part files retain the update row.

### 9. Review queue
Ambiguous duplicates, conflicts, weak sources, unresolved TBA items, and geocoding failures.

## Pipeline

```text
source registry
    -> acquisition
    -> raw snapshots
    -> extractor
    -> source-native candidates
    -> normalization
    -> relevance filter
    -> exact duplicate check
    -> fuzzy candidate matching
    -> review / accept / reject
    -> enrichment
    -> validation
    -> Part export + cumulative export + manifest
```

## Update semantics

- New occurrence: allocate a new borough-specific `EVENT_ID`.
- Existing occurrence changed: create an update-ledger row referencing the permanent ID.
- Same series, different date/location: new occurrence with existing `SERIES_ID`.
- Event cancelled: update status; do not delete history.
- Source disappears: retain event but flag source health and require reverification.

---

# Source Acquisition

## Acquisition order

Always choose the most structured and authoritative source available:

1. Official API or downloadable dataset
2. Official CSV/JSON/XLSX distribution
3. Official ICS/iCalendar feed
4. Schema.org Event JSON-LD
5. WordPress REST API or CMS JSON endpoint
6. Static HTML event listing/detail page
7. Official PDF schedule or bulletin
8. Rendered browser extraction for JavaScript-only pages
9. Official social post only when no durable page exists
10. Secondary media/calendar listing only as corroboration

## Government permit sources

### NYC Permitted Event Information

Dataset ID: `tvpp-9vvx`

Useful endpoints:

```text
Metadata:
https://data.cityofnewyork.us/api/views/tvpp-9vvx

SODA JSON:
https://data.cityofnewyork.us/resource/tvpp-9vvx.json

SODA CSV:
https://data.cityofnewyork.us/resource/tvpp-9vvx.csv

Full-download CSV:
https://data.cityofnewyork.us/api/views/tvpp-9vvx/rows.csv?accessType=DOWNLOAD

Full-download JSON:
https://data.cityofnewyork.us/api/views/tvpp-9vvx/rows.json?accessType=DOWNLOAD
```

Native fields:

```text
event_id
event_name
start_date_time
end_date_time
event_agency
event_type
event_borough
event_location
event_street_side
street_closure_type
community_board
police_precinct
cemsid
```

Recommended focused query:

```sql
SELECT :id, :updated_at, *
WHERE start_date_time >= '2026-07-16T00:00:00.000'
  AND start_date_time <  '2027-01-01T00:00:00.000'
  AND event_type IN (
    'Street Festival',
    'Religious Event',
    'Parade',
    'Single Block Festival',
    'Farmers Market',
    'Open Street Partner Event',
    'Street Event',
    'Block Party',
    'Athletic Race / Tour',
    'Open Culture',
    'Plaza Event',
    'Plaza Partner Event',
    'Special Event'
  )
ORDER BY start_date_time, event_id
```

Do not ingest all `Special Event` rows blindly. The feed contains large volumes of routine athletic reservations. Apply name and venue rejection rules, then review the remaining named events.

### E-Apply/SAPO

Use the public Find Events interface for human verification and missing fields. Search by date range, borough, agency and event type. Save the query parameters and result snapshot. A SAPO permit is strong evidence for dates and street closure, but setup/breakdown times may not equal public program hours.

### NYC Parks and citywide calendar

Use official event pages for public program times and descriptions. Permit records may describe access windows instead of audience hours. Link the permit and event page when both exist.

## Source discovery on a new domain

For every domain:

1. Read `robots.txt` and obey exclusions.
2. Look for sitemap references in `robots.txt`.
3. Check `/sitemap.xml`, `/wp-sitemap.xml`, and common CMS sitemap paths.
4. Inspect HTML `<head>` for:
   - `application/ld+json`
   - `text/calendar` or `.ics` links
   - RSS/Atom links
   - WordPress REST link relation
   - OpenGraph metadata
5. Inspect page source for embedded JSON state (`__NEXT_DATA__`, Nuxt payloads, Drupal settings, Algolia records).
6. Check browser network calls for JSON calendar endpoints only when static structured data is absent.
7. Record the discovered method in `sources.yaml` so future runs do not rediscover it.

## JSON-LD

Search every `<script type="application/ld+json">` block recursively. Accept `Event` and subtypes such as `MusicEvent`, `Festival`, `ScreeningEvent`, and `SportsEvent`. Extract `name`, `startDate`, `endDate`, `eventStatus`, `location`, `organizer`, `offers`, and `url`. Repeated dates should become distinct occurrence rows.

## iCalendar / ICS

Parse `VEVENT` records, expand `RRULE`, `RDATE`, and `EXDATE` only within the requested time window, and preserve the source UID. Store both the master recurring event and generated occurrences internally; export one row per occurrence.

## WordPress

Discover the REST root from the `api.w.org` link or test `/wp-json/`. Search post types and plugin routes for events. Many sites use event plugins with custom routes; enumerate the API index before writing a scraper.

## HTML

Prefer event detail pages over list-card text. Use source-specific selectors stored in YAML. Never rely on a brittle global CSS selector. Capture the page title, event title, visible date/time, location, organizer and canonical URL.

## PDFs and bulletins

- Download and hash the original PDF.
- Extract text with `pypdf` or `PyMuPDF`.
- If the PDF is scanned, put it in manual/OCR review rather than silently returning no text.
- Preserve page numbers for every extracted fact.
- Visually inspect street-limit tables, route diagrams and date grids.

## JavaScript-only pages

Use Playwright only after structured methods fail. Wait for a stable event-list selector or network response, not an arbitrary sleep. Capture the final HTML and relevant JSON network response into the raw-evidence store.

## Social media

Treat social media as volatile evidence. Capture permalink, post date, account identity, screenshot path and quoted facts. Seek a durable official page or permit before marking high confidence.

---

# Data Model

## Exact export schema

The cumulative export must preserve the 59 columns in `src/nyc_event_atlas/schema.py` exactly and in that order.

## Occurrence versus series

- `EVENT_ID` identifies one occurrence or one continuous multi-day event.
- `SERIES_ID` identifies the recurring concept.
- A weekly market has one series and many occurrence rows.
- A continuous ten-day feast is normally one occurrence row, with separate rows only for materially distinct processions, Masses, fireworks, parades or ticketed companion programs.

## Stable IDs

Borough prefixes:

```text
MN Manhattan
BK Brooklyn
QN Queens
BX The Bronx
SI Staten Island
CW Citywide
ADJ NYC-adjacent
```

Allocate the next integer from the canonical database, never by counting the current Part file.

## Source confidence

- High: official government, organizer, venue, institution, parish or event page
- Medium: BID, Community Board, civic association, established promoter schedule or reliable media
- Low: generic event aggregator or unverified secondary listing

A low-confidence source cannot independently support `Confirmed`.

## Event status

- Confirmed: direct source states the event/date
- Permitted: official permit feed, but public program details may still need corroboration
- Announced: official announcement with partial details
- TBA: official confirmation of a planned event, no date
- Postponed, Cancelled: direct source states status

## Date policy

- Store dates as `YYYY-MM-DD`.
- Store local time separately in `HH:MM` 24-hour format.
- Use `America/New_York` internally.
- Setup/breakdown times from permits go in `TIME_NOTES` unless verified as public hours.
- Active exhibits may start before the research window if their end date overlaps the window.

## Unknown and TBA

- `Unknown`: not established.
- `TBA`: official source says it will occur but withholds the date.
- Never convert historical dates into current-year confirmation.

## Street parsing

Preserve original location text in `RESEARCH_NOTES`. Parse common patterns:

```text
STREET between AVENUE A and AVENUE B
AVENUE from STREET 1 to STREET 2
PARK NAME: SUBLOCATION
```

If parsing is uncertain, keep `STREET_FROM` and `STREET_TO` as `Unknown`.

## Geocoding

Use NYC Geoclient for NYC addresses, intersections and blockfaces. Store geocoder response and quality indicator. Do not assign a street midpoint unless the official endpoints are known and the midpoint method is disclosed. Coordinates must be WGS84 decimal degrees.

## Update ledger

An update record should include:

- update ID
- original permanent `EVENT_ID`
- changed field names
- old values
- new values
- source URL
- verification date
- reason

The cumulative export applies the update to the original ID. The Part export retains the update row for auditability.

---

# Permit Mapping

| Permit field | Export field | Notes |
|---|---|---|
| event_id | PERMIT_ID | Preserve as text |
| event_name | EVENT_NAME | Reject generic routine sports rows unless editorially relevant |
| start_date_time | START_DATE / START_TIME | Usually permit setup window; record caveat |
| end_date_time | END_DATE / END_TIME | Usually breakdown window; record caveat |
| event_agency | PERMIT_AGENCY | Official permitting agency |
| event_type | CATEGORY/SUBCATEGORY | Use controlled mapping |
| event_borough | BOROUGH | Convert Bronx to The Bronx |
| event_location | VENUE/FULL_ADDRESS/STREET fields | Preserve raw text in notes |
| event_street_side | RESEARCH_NOTES | Do not force into route fields |
| street_closure_type | RESEARCH_NOTES | Valuable for photographer access planning |
| community_board | RESEARCH_NOTES/internal field | Consider adding internal column, not export schema |
| police_precinct | RESEARCH_NOTES/internal field | Consider adding internal column |
| cemsid | SERIES_ID candidate/internal external ID | Useful for grouping repeated permit records |

Set `EVENT_STATUS=Permitted` unless a separate official public event page confirms the program. Set `PRIMARY_SOURCE` to the dataset/API URL and add the E-Apply detail page or organizer page as secondary evidence when available.

---

# Deduplication

## Stage 1: exact identifiers

Automatically match when any of these are equal and non-empty:

- same permit ID
- same source-native UID
- same organizer event ID
- same canonical URL with same occurrence date

## Stage 2: exact occurrence key

Build:

```text
normalized_title | start_date | normalized_venue_or_street | normalized_organizer
```

Normalization removes punctuation, legal suffixes, ordinal noise and common filler words, but must not remove saints, neighborhoods, dates, cultural identities or numbered series names.

## Stage 3: fuzzy candidate generation

Compare only records sharing at least one blocking key:

- same borough and date
- same ZIP and date ±1 day
- same organizer and month
- same permit location
- same normalized title prefix

Suggested scoring:

```text
40% title token-set similarity
20% location similarity
15% organizer similarity
15% date proximity
10% source/permit identity
```

Recommended actions:

- 95–100: auto-match only if date and borough are compatible
- 88–94: manual review
- 75–87: possible series relationship; do not merge
- below 75: new candidate

## Common false merges

- parade versus accompanying festival
- same event name in different boroughs
- recurring weekly market occurrences
- same movie screened at different parks
- church feast versus religious procession
- multi-date concert series
- event announcement page versus actual occurrence

## Common missed duplicates

- abbreviated saint names
- sponsor prefixes
- punctuation and apostrophe differences
- route endpoint changes
- organizer renaming
- `Festival`, `Fest`, `Fair`, and `Street Fair` variants
- Spanish/English title pairs

The system should present candidate pairs and evidence to a reviewer rather than optimizing for a fully automatic merge rate.

---

# Operations

## Daily permit refresh

1. Pull Socrata metadata and compare `rowsUpdatedAt` with the last run.
2. Query relevant event types for the target window.
3. Save raw JSON and request parameters.
4. Import unseen `event_id` rows.
5. Reprocess rows whose `:updated_at` changed.
6. Apply editorial relevance filters.
7. Join to organizer pages where possible.
8. Queue generic names such as `Celebration` for review unless location/organizer creates clear news value.

## Weekly source refresh

- producer schedules
- public libraries
- NYC Parks
- museums, zoos and gardens
- BIDs and Community Boards
- parish and cultural calendars
- holiday organizers

## Monthly deep search

- search each borough/neighborhood + year + event keywords
- inspect source sitemaps for newly created event pages
- inspect community-board agendas and newsletters
- compare historical series whose current-year dates are missing
- recheck TBA records

## Event-change monitoring

Use ETag, Last-Modified and SHA-256 body hashes. If a source changes:

1. re-extract;
2. compare field-level values;
3. create an update candidate;
4. do not overwrite canonical data until accepted.

## Quality gates before export

- 59 columns, exact order
- unique `EVENT_ID`
- stable `SERIES_ID`
- valid date formats
- borough vocabulary valid
- status vocabulary valid
- ratings integers 1–5
- direct source exists
- `LAST_VERIFIED` exists
- coordinate pairs complete and in range
- exact duplicate key absent
- GeoJSON parses
- KML parses
- research log and manifest created

## Recommended cadence

- permits: daily
- high-value organizers: every 1–3 days during event season
- ordinary institutions/BIDs: weekly
- church bulletins: weekly, especially Thursday–Sunday
- holiday sources: daily once announcement season begins
- full TBA recheck: weekly

---

# Search Queries

Use search for discovery, then verify on direct sources.

## General patterns

```text
site:nyc.gov 2026 "street festival" Brooklyn
site:nycgovparks.org/events/2026/10 Halloween Queens
site:*.org 2026 feast procession "Staten Island"
site:*.com/events 2026 "Howard Beach" festival
"2026" "18th Avenue" feast Brooklyn
"2026" "86th Street" festival Bensonhurst
"2026" parish carnival Queens
"2026" tree lighting Bronx official
"2026" menorah lighting Staten Island official
```

## Source-targeted patterns

```text
site:data.cityofnewyork.us "NYC Permitted Event Information"
site:nyceventpermits.nyc.gov/cems/findevents "Event Type"
site:cb*.org 2026 festival
site:nyc.gov/assets/*/downloads/pdf 2026 events
site:org "2026" "calendar" "feast"
```

## Historical-series discovery

Search the prior year only to identify the organizer and likely source, never to confirm the current date:

```text
"Event Name" 2025 organizer
"Event Name" official
"Event Name" permit NYC
```

Then find a direct 2026 source or leave the occurrence unconfirmed.

---

# Current Audit

Generated from the cumulative CSV supplied with the project.

## Baseline

- 827 rows
- 59 columns
- 409 series
- 786 Confirmed
- 36 Permitted
- 5 TBA

## Borough distribution

- Manhattan: 295
- Queens: 180
- Brooklyn: 178
- Staten Island: 105
- The Bronx: 65
- Citywide: 4

## Largest categories

- Street Fair: 98
- Film Screening: 73
- Community Program: 63
- Bike Event: 51
- Outdoor Concert: 50
- Family Program: 46
- Seasonal Event: 31
- Food Market: 30
- Farmers Market: 29
- Public Market: 25

## Enrichment gaps

- Coordinates unknown: 784 of 827 (94.8%)
- Nearest subway unknown: 720 (87.1%)
- Nearest bus unknown: 783 (94.7%)
- Permit ID unknown: 791 (95.6%)
- Street endpoints unknown: about 76%
- End time unknown: 244 (29.5%)

## Important data-quality observations

1. The database is strongest for public programs and street fairs, but geospatial enrichment is sparse.
2. Manhattan remains overrepresented relative to The Bronx and Staten Island.
3. Source confidence is high for almost every row, but field-level evidence is not represented in the 59-column export; the internal database should add it.
4. Permit ingestion should materially improve closure, precinct, Community Board and permit-ID coverage.
5. Recurrent sources dominate many rows. Incremental source monitoring will produce better results than repeated broad web searches.

---

# Cursor Prompt

You are taking over an existing NYC Event Atlas dataset with 827 canonical event occurrences and an exact 59-column export schema.

## Non-negotiable rules

- Read the cumulative CSV before adding records.
- Preserve all existing `EVENT_ID` and `SERIES_ID` values.
- Never silently overwrite prior records.
- Add only new occurrences or explicit update-ledger entries.
- Preserve `Unknown` instead of guessing.
- Use `TBA` only when an official source confirms a 2026 event but has not announced the date.
- Store every raw response or document with retrieval time, source URL, HTTP metadata, and SHA-256 hash.
- Every canonical event must have at least one direct source and `LAST_VERIFIED`.
- Treat editorial `PHOTO_VALUE` and `NEWS_VALUE` as assessments, not source facts.
- Never auto-merge ambiguous fuzzy matches.

## First tasks

1. Initialize SQLite from `sql/schema.sql`.
2. Import `NYC_EVENTS_MASTER_CUMULATIVE.csv` using `scripts/import_existing.py`.
3. Run the source-discovery process from `config/sources.yaml`.
4. Fetch the current NYC permitted-event dataset through Socrata.
5. Filter the permit feed to editorially relevant event types and remove routine sports/practice records.
6. Crawl official organizer and institution calendars using the least invasive structured method available:
   API > CSV/JSON > ICS > JSON-LD > WordPress REST > sitemap/event pages > PDF > rendered browser.
7. Normalize each extracted occurrence to the 59-column schema.
8. Run exact keys and fuzzy duplicate scoring.
9. Put uncertain candidates into `review_queue`; do not force acceptance.
10. Export a new Part file and a refreshed cumulative dataset only after validation passes.

## Priority source areas

- NYC Permitted Event Information and historical dataset
- SAPO/E-Apply public search
- NYC Parks, DOT/Open Streets, NYPD parade/race records
- Street-fair producer schedules
- BIDs, Community Boards, chambers and civic associations
- Parish/church/temple/mosque calendars and bulletins
- Public libraries, museums, zoos, gardens, parks and waterfront institutions
- Holiday-market, tree-lighting, menorah-lighting, Kwanzaa and New Year’s Eve sources
- Direct confirmation of Santa Rosalia / 18th Avenue Feast

## Definition of done for each run

- raw snapshots saved and hashed
- candidates normalized
- duplicate review complete
- source links resolvable
- dates and coordinates validated
- IDs unique
- exact 59-column order preserved
- GeoJSON and KML valid
- research log written
- manifest written
- cumulative export rebuilt

---

# Key Official Technical References

- NYC Open Data dataset metadata and API documentation for dataset `tvpp-9vvx`
- Socrata SODA/SoQL query, pagination, output-format and app-token documentation
- NYC SAPO and E-Apply Find Events
- NYC API portal for Geoclient and the citywide Events Calendar API
- Schema.org Event and Google Event structured-data documentation
- RFC 5545 iCalendar
- RFC 9309 Robots Exclusion Protocol
- WordPress REST API handbook
