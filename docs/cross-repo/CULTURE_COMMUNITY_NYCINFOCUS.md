# Cross-repo notes — `NYCInFocus` (iOS)

Copy or link this from `setoxxx/NYCInFocus` (see `Features/NYCInFocus/CULTURE-DISPLAY.md`).
**Do not** invent storefronts in the client. **Do not** embed `service_role`.

Authority for the backend slice:  
`setoxxx/nycif-live-feeds` → `docs/CULTURE_COMMUNITY_ENGINEERING_PLAN.md`

## What iOS already does (keep)

- Culture tab: white neighborhood borders, historic dashed rings, area chips.
- Feeds: `nycif-culture-boundaries`, `nycif-culture-areas`, `nycif-culture-places`.
- `CulturePlacesFeed.businessPublicationEnabled` — when false, `place_count` is
  0 and the UI explains storefronts stay off.
- Name-lead labels only after the server publishes a reviewed place.
- Settings copy already says the app never invents businesses.
- `SupabaseService` uses the anon / publishable path only.

## What Howard wants next (after gated feeds exist)

1. **Storefronts inside borders** — ~91 curated rows. Name is the qualify
   hint. Server remains fail-closed until `business_publication_enabled`.
2. **Sanctuary resources** — hotlines as a list/sheet (MOIA, NYC Care);
   pin only when the civic/resource feed returns certified coords.
3. **Civic layers** — 👮 NYPD, 🚒 FDNY, shelters. New endpoint
   `nycif-culture-civic` (deployed, gated; empty until Phase C6).
4. **8-day Culture calendar** — same chip pattern as Home
   Now / Tonight / 7 Days, Culture-sorted, from `nycif-culture-calendar`.
   Tonight = 17:00–23:59:59 America/New_York (same as events).
5. **ASPCA / pet care** — calendar occurrences; do not drop a pin unless
   the feed says `map_ready` and the layer gate is on.
6. **Rolling public-help chips** (server-gated): 🩸 Blood, 🏥 Mobile clinic,
   💼 Jobs, 🎓 College. Same 8-day window. Pins only when that occurrence
   already has certified coords. Do not cache invented fairs on device.

## Client contract (fail closed)

| If the server says… | Client must… |
| --- | --- |
| `business_publication_enabled: false` | Show zero storefront pins |
| `civic_publication_enabled: false` or missing endpoint | Hide civic layers or show empty |
| `calendar_publication_enabled: false` or missing endpoint | Empty Culture calendar, no invented services |
| `waitlist_gated: true` / `pin_policy: zip_area_only` | List or zip hint, no fake van pin |
| `is_sample: true` | Never plot (server should already omit) |
| HTTP 404 on new functions | Treat as “not shipped yet”, not an error that unlocks local fixtures of real businesses |

Do not ship local JSON of invented Canarsie / Midwood / Little Pakistan shops
as a preview. Use empty states.

## Suggested follow-up in that repo (later PR)

- `CultureService.fetchCivic()` / `fetchCalendar()` with the same
  `authorizedRequest` pattern as places.
- Decode new optional fields (`place_kind`, layer gates) without breaking
  current `CulturePlace` if the places feed adds columns.
- Civic emoji pins only from server rows.
- Culture Now / Tonight / 7 Days chips mirroring `EventService` windows.
- Keep WordPress / God View / field-desk admin out of this client.

Publication flips happen on the server, never by an iOS `UserDefaults` flag.
