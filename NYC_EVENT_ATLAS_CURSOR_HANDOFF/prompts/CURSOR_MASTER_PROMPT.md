# Cursor Master Prompt — NYC Event Atlas Automation

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
