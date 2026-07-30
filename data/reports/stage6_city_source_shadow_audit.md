# Stage 6 city-source shadow audit

Generated: `2026-07-30T14:08:40.968911Z`

Overall result: **PASS**

No production feed was modified. Each source remains shadow-only unless a separate promotion review is approved.

## Film Permits (`tg4x-b46p`)

- Role: `event_candidate`
- Rows: `18290`
- Updated: `2026-07-29T19:30:47Z`
- Current/future rows: `0`
- Direct geometry fields: `none`
- Location fields: `parkingheld`
- Approved overlap: source IDs `0`, semantic `0`
- Disposition: **blocked_no_current_future_rows**
  - no current or future rows
  - location text requires borough-safe resolution before mapping

## DOB NOW: Build – Approved Permits (`rbx6-tga4`)

- Role: `infrastructure_corroboration`
- Rows: `976147`
- Updated: `2026-07-29T18:49:42Z`
- Current/future rows: `0`
- Direct geometry fields: `latitude, longitude`
- Location fields: `house_no, street_name, bin`
- Approved overlap: source IDs `0`, semantic `0`
- Disposition: **infrastructure_context_only_not_public_event_feed**
  - no current or future rows

## Street Construction Permits (2022 - Present) (`tqtj-sjs8`)

- Role: `infrastructure_corroboration`
- Rows: `3792120`
- Updated: `2026-07-29T20:38:40Z`
- Current/future rows: `None`
- Direct geometry fields: `none`
- Location fields: `onstreetname, fromstreetname, tostreetname`
- Approved overlap: source IDs `0`, semantic `0`
- Disposition: **infrastructure_context_only_not_public_event_feed**
  - current/future query unavailable: no_primary_date_field
  - location text requires borough-safe resolution before mapping

## Weekday Traffic Updates (`vihk-m25f`)

- Role: `advisory_candidate`
- Rows: `None`
- Updated: `2011-07-30T01:03:15Z`
- Current/future rows: `None`
- Direct geometry fields: `none`
- Location fields: `none`
- Approved overlap: source IDs `0`, semantic `0`
- Disposition: **blocked_stale_or_non_current_advisory_source**
  - source metadata/data update is 5479.55 days old
  - current/future query unavailable: no_primary_date_field
  - no usable location fields
