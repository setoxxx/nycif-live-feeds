# Tourist-First Daily Event Layer Gate

## Status

Future downstream QA/product gate. Do not run yet.

This requirement must be carried forward after the GPS staged-feed integration is safely resolved. It must not be implemented inside the GPS adjudication script, and it must not change the current GPS adjudication task.

## Product goal

NYC In Focus should not only show technically valid events. It must show useful, newsworthy, visually interesting events every day, with the first/default visible layer prioritizing events that tourists, visitors, photographers, editors, and general NYC readers would actually want to see.

The map/feed should answer: What can I go see today?

## Gate name

`tourist_first_daily_event_layer_gate`

## Future report artifact

`data/tourist_first_daily_event_layer_gate_report.json`

Do not create or run this report until after the GPS staged-feed integration is resolved under a safe adjudicated contract.

## Scope

This gate should verify that the staged/live event feed has strong everyday coverage and that the first visible layer is not dominated by low-interest permit rows, generic sports reservations, duplicate athletic blocks, or internal Parks-style records.

The first layer should be curated/scored, not merely raw chronological data.

## Required checks

### 1. daily_event_coverage

- There should be displayable events for every day in the upcoming coverage window.
- Flag any date with zero displayable events.
- Flag any date where only low-interest or generic events exist.

### 2. tourist_first_layer

The first/default event layer should prioritize events tourists and general readers care about, including:

- major public festivals
- parades
- concerts
- cultural events
- film, TV, or public appearances
- street fairs
- markets
- major park events
- seasonal events
- civic or newsworthy gatherings
- visually strong public events
- events with likely photo or news value

### 3. newsworthy_event_priority

Events should be scored higher when they are:

- visually interesting
- public-facing
- likely to attract crowds
- tied to NYC culture, tourism, public life, politics, sports, entertainment, or breaking-news potential
- useful for photographers, visitors, and editors

### 4. low_interest_suppression

Generic recurring athletic reservations, routine field permits, duplicate sports blocks, and low-context Parks rows should not dominate the default layer.

These records may still exist in deeper layers or category filters, but they should not be the first thing users see unless there is no stronger event for that day.

### 5. every_day_has_a_reason_to_open

Each day should surface at least a few strong, human-readable, public-facing events when available.

### 6. first_layer_contract

- The default first layer should favor tourist-facing, newsworthy, public-interest events.
- Deeper layers can include complete permit/event data.
- The gate should separate raw completeness from first-layer editorial usefulness.

## Safety and sequencing rules

Do not run Phase 3A yet.

Do not publish to the public map yet.

Do not change the current GPS adjudication task.

Do not modify these files as part of capturing this requirement:

- `data/location_cache.json`
- `data/nycif_staged_live_events.json`
- public-map/public-feed artifacts
- Phase 3A artifacts

## Recommended roadmap placement

1. Finish GPS staged-feed adjudication summary.
2. Patch staged-feed GPS update to apply only the adjudicated safe GPS identities.
3. Validate that staged-feed GPS integration remains fail-closed and does not publish.
4. Create `tourist_first_daily_event_layer_gate` as a separate QA/product gate.
5. Use that gate to verify that every day has meaningful displayable events and that the first map/feed layer prioritizes tourist-facing and newsworthy events.
