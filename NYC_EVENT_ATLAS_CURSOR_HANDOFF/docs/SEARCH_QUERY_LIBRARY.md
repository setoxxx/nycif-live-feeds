# Search Query Library

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
