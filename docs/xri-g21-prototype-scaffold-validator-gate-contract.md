# XRI-G21 Prototype Scaffold Validator Gate Contract

Phase: XRI-G21

Source phase: XRI-G20
Source pull request: #30
Source merge commit SHA: `66dee31c63aaba2bf63ea2311243816232d26f7f`

## Completion map at this junction

- Completed and merged: XRI-G10 through XRI-G20: 100%.
- Current next phase: XRI-G21: not started at gate entry; in progress only after this branch/pull request is opened.
- Overall toward a safe non-production registry/manual-review prototype: about 80% complete at gate entry.
- Overall toward full production public-map/registry use: about 50-60% complete at gate entry.

Mode: non-production prototype scaffold validator gate only.

This is a validator gate only. It defines validation requirements for the XRI-G20 registry/manual-review prototype scaffold. It must validate fixture-only/test-only scaffold records and must not be consumed by production runtime, public map runtime, registry import, scheduled workflows, WordPress, geocoding, approval, promotion, publishing, database behavior, or production validator execution.

## Source chain

XRI-G13 through XRI-G20 are the source context: manual-review schema prototype, fixture validator, validator execution gate, failure-case fixtures, failure-case validator execution, summary/handoff gate, registry implementation planning gate, and registry/manual-review prototype scaffold gate.

## Validator requirements

The validator gate must define validation rules for the registry record identity model, manual-review record shape, stable identity fields, reviewer decision lifecycle, audit fields, blocking fields, fail-closed behavior, fixture/test-only input and output boundaries, production blocking, geocoding blocking, promotion blocking, publishing blocking, registry import blocking, public-output blocking, rollback/stop conditions, future promotion gate requirements, and future production authorization gate requirements.

Stable identity fields are `group_key`, `display_location`, and candidate identity. `review_rank` must not be used as identity.

Allowed reviewer decision values: `hold`, `reject`, `needs_more_context`, `eligible_for_future_review`.

Forbidden reviewer decision values: `approved`, `geocoded`, `promoted`, `published`.

Required blocking fields: `production_blocked`, `geocode_blocked`, `promotion_blocked`, `publishing_blocked`, `registry_import_blocked`.

All blocking fields must default to true. Missing blocking fields fail closed. False blocking fields fail closed unless a later separate gate explicitly authorizes otherwise.

The validator gate must fail closed on missing `group_key`, missing `display_location`, missing candidate identity, missing source fields, missing audit fields, missing reviewer decision, invalid reviewer decision, `review_rank` used as identity, production/public/runtime targets, geocoding coordinate fields, or approval/promotion/publishing state.

Forbidden fields and targets include latitude, longitude, lat, lon, lng, coordinates, geometry, production path, WordPress target, public map target, scheduled workflow target, and publishing target.

## Hard prohibitions

XRI-G21 must not modify production feeds, public map runtime, WordPress, `nycinfocus.com/map`, iframe/embed settings, scheduled workflows, or `data/location_cache.json`; must not run live staging, fetch SODA/live data, geocode, approve/promote candidates, implement production registry database/importer behavior, add runtime publishing behavior, provide production runtime input, provide public output, run production validator execution, publish anything, or start XRI-G22.

## Proposed next gate

XRI-G22 non-production prototype scaffold validator execution gate only, after explicit review and merge approval.

## Review gate

Open a pull request only. Do not merge. Do not start XRI-G22.
