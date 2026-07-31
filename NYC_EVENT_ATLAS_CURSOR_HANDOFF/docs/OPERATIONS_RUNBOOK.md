# Operations Runbook

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
