# Data Model and Canonicalization Rules

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
