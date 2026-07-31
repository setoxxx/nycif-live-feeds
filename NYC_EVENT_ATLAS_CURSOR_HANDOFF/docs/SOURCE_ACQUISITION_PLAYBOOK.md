# Source Acquisition Playbook

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
