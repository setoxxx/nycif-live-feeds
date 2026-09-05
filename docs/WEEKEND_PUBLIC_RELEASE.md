# Weekend public release (no Tuesday wait)

Friday 2026-09-04 is the current official city cut. Saturday/Sunday/Labor Day do not add civic rows. The phone can ship from what is already in Supabase.

## Live Now (probed 2026-09-05)

- 987 events
- 840 certified point pins
- 147 list-only

Of those 147:

- **22** parse as `STREET between X and Y` → corridor A—B candidates
- **125** are named parks / rec centers / “in Fort Tryon Park” → facility pins, not lines

See `data/reports/weekend_corridor_inventory.json`.

## Already merged this weekend

- PR 471 corridor contract
- PR 472 7pm NYC business-day clock
- PR 473 corridor resolver (two endpoints, no midpoint)

## Still required on the phone (local Xcode)

Project: `/Volumes/NYCIF/NYCIF IOS/NYCInFocus/NYCInFocus.xcodeproj`

Paste from `docs/ios/EventService+headers-and-corridor.swift`:

1. Send `apikey` + `Authorization: Bearer` with the anon key.
2. Decode `corridor` / `chip_rows` / `days`.
3. Plot a pin only when `MAP_READY`.
4. Plot A—B dashed line when `CORRIDOR_READY` and both points exist.
5. List-only stays in the list. Relabel “pending” to “List only”.
6. 7 Days subchips call `mode=day&date=YYYY-MM-DD`.

Tonight: the function already reports `stats.tonight` 74/63 but `events` is empty before 18:00. That is an Edge Function change, not missing Friday data.

## Do not merge

- PR 469 feast/calendar midpoints
- DOT / 311 onto the event map
- WordPress map as the product client

## Soft-launch bar this weekend

Ship Now + 7 Days with 840 pins and a list. Corridors and Tonight preview follow as soon as Edge Function + Swift land. Do not wait for Tuesday for those 840.
