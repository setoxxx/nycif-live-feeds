# Phase 3A - Tourist Mode Foundation

## Purpose

Phase 3A introduces a tourist-first strategy layer for NYC In Focus without changing the public map, the staged event feed, or GPS promotion behavior.

This phase is strategy/data modeling only.

## Product thesis

NYC In Focus should support a default Tourist Mode that answers:

> What should I do near me in New York City right now?

The existing live-event and GPS QA pipeline remains the operational engine. Tourist Mode adds a visitor discovery layer on top of that engine.

## Phase 3A safety contract

Phase 3A must not modify:

- `data/location_cache.json`
- `data/nycif_staged_live_events.json`
- public map/frontend code
- WordPress/public-map embeds
- GPS approval or promotion artifacts

Phase 3A may create only staging and strategy files, such as:

- tourist category taxonomy
- tourist place schema
- seed tourist place records
- source policies
- QA rules

All Phase 3A tourist records must remain non-public by default.

## Default product mode

Recommended default future map mode:

- `tourist_default`

Secondary modes may include:

- `local_mode`
- `press_event_mode`
- `photo_mode`
- `family_mode`
- `culture_mode`
- `free_low_cost_mode`

## Tourist category strategy

Tourist categories should be visitor-intent based, not only agency/source based.

Primary category families:

1. Must-See NYC
2. Free Things To Do
3. Museums & Culture
4. Parks & Scenic Spots
5. Food & Markets
6. Shopping
7. Broadway & Entertainment
8. Sports & Arenas
9. Family-Friendly
10. Photo Spots
11. Neighborhood Walks
12. Events Happening Now
13. Hidden Gems
14. Rainy Day
15. Nightlife / Evening

NYC In Focus should own a distinctive editorial category:

- Photo Worthy

## Relationship to existing live event data

Tourist records are not live events.

Live events answer:

- what is happening now
- where a permitted/civic/park event is occurring
- how an event may affect access or activity nearby

Tourist records answer:

- what is worth visiting
- what category a place belongs to
- what visitor intent it serves
- whether it is public-ready after QA

Future map behavior should combine these layers only after both are QA-approved.

Example future experience:

- Tourist opens Times Square.
- Map shows Times Square as a must-see place.
- Map overlays live permitted events nearby.
- Map suggests photo-worthy nearby areas and free public spaces.

## Source policy

Tourist seed data should prefer source-backed entries.

Recommended source order:

1. official NYC Tourism + Conventions or official venue/city sources
2. NYC Parks or other government agency sources
3. official museum/venue/attraction source
4. reputable public tourism rankings or public visitor-interest references
5. NYCIF editorial/manual review

Every record should preserve source notes and source URLs.

## QA policy

Every tourist record starts as:

- `qa_status: pending`
- `public_ready: false`
- `public_map_modified: false`
- `staged_feed_modified: false`
- `location_cache_modified: false`

A tourist place may become public-ready only after:

- valid NYC coordinates are confirmed
- source URLs are recorded
- category assignment is reviewed
- short description is reviewed
- duplicate/near-duplicate place checks pass
- the human explicitly approves public use

## Recommended Phase 3A files

- `data/tourist_categories_phase3a.json`
- `data/tourist_place_schema_phase3a.json`
- `data/tourist_seed_places_phase3a.json`

## Phase 3B recommendation

Create a validator for the tourist layer that checks:

- required fields exist
- lat/lng are within NYC bounds
- `public_ready` remains false unless explicitly approved
- categories match the taxonomy
- every seed record has at least one source URL
- no tourist seed file is loaded as the public event feed

## Phase 3C recommendation

Create an admin/test-only tourist preview in the frontend repo.

Do not connect tourist seed data to the public map until a public-ready export exists and the human explicitly approves publication.
