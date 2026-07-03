# XRI-G19 Registry Implementation Planning Gate Contract

Phase: XRI-G19

Source phase: XRI-G18  
Source pull request: #27  
Source merge commit SHA: `d0ab68f2d507ed81665f7f5aeeb46df0b6d7967b`

Mode: non-production registry implementation planning gate only.

This is planning only. It defines requirements and safety boundaries for a future registry/manual-review implementation phase. It does not implement database, importer, production, public map, WordPress, geocoding, approval, promotion, publishing, or runtime behavior.

## Source chain

XRI-G13 through XRI-G18 are the source context: manual-review schema prototype, fixture validator, validator execution gate, failure-case fixtures, failure-case validator execution, and summary/handoff gate.

## Planning requirements

Future work requires a separate explicit prompt and must begin as non-production only. Fixture-only or test-only data must be used unless a later gate authorizes otherwise.

Stable identity matching must use `group_key`, `display_location`, and candidate identity. `review_rank` must not be used as identity.

Future work must fail closed on missing identity fields, source fields, display/location text fields, invalid reviewer decision fields, and forbidden approval/promotion/publishing/geocoding values.

Production, geocoding, promotion, publishing, and registry import must remain blocked unless a later separate gate authorizes otherwise.

Fixture/report artifacts must not become production runtime input and must not publish to public map, WordPress, feeds, scheduled workflows, or any runtime surface.

## Minimum future requirements

A future implementation phase must define a registry record identity model, manual-review record schema, stable matching strategy, reviewer decision lifecycle, audit fields, blocking fields, fail-closed validator requirements, non-production fixture/test strategy, promotion gate requirements, production-authorization gate requirements, rollback/stop conditions, public-output blocking conditions, geocoding blocking conditions, and publishing blocking conditions.

## Hard prohibitions

XRI-G19 must not modify production feeds, public map runtime, WordPress, `nycinfocus.com/map`, iframe/embed settings, scheduled workflows, or `data/location_cache.json`; must not run live staging, fetch SODA/live data, geocode, approve/promote candidates, implement registry database/importer behavior, add runtime publishing behavior, publish anything, or start XRI-G20.

## Proposed next gate

XRI-G20 non-production registry/manual-review prototype scaffold gate only, after explicit review and merge approval.

## Review gate

Open a pull request only. Do not merge. Do not start XRI-G20.
