# XRI-G22 Prototype Scaffold Validator Execution Gate Contract

Phase: XRI-G22

Source phase: XRI-G21
Source pull request: #31
Source merge commit SHA: `9f266380ca81e2375e21fb1c4b697b6ff581c1a1`

## Completion map at this junction

- Completed and merged: XRI-G10 through XRI-G21: 100%.
- Current next phase: XRI-G22: not started at gate entry; in progress only after this branch/pull request is opened.
- Overall toward a safe non-production registry/manual-review prototype: about 85% complete at gate entry.
- Overall toward full production public-map/registry use: about 55-60% complete at gate entry.

Mode: non-production prototype scaffold validator execution gate only.

This is a validator execution gate only. It records expected validation execution requirements and pass/fail result for the XRI-G21 prototype scaffold validator gate. It must remain fixture-only/test-only and must not be consumed by production runtime, public map runtime, registry import, scheduled workflows, WordPress, geocoding, approval, promotion, publishing, database behavior, production validator execution, or production validator wiring.

## Source chain

XRI-G13 through XRI-G21 are the source context: manual-review schema prototype, fixture validator, validator execution gate, failure-case fixtures, failure-case validator execution, summary/handoff gate, registry implementation planning gate, registry/manual-review prototype scaffold gate, and prototype scaffold validator gate.

## Execution coverage

The execution gate must record validation coverage for the registry record identity model, manual-review record shape, stable identity fields, reviewer decision lifecycle, audit fields, blocking fields, fail-closed behavior, fixture/test-only input and output boundaries, production blocking, geocoding blocking, promotion blocking, publishing blocking, registry import blocking, public-output blocking, rollback/stop conditions, future promotion gate requirements, and future production authorization gate requirements.

Stable identity fields are `group_key`, `display_location`, and candidate identity. `review_rank` must not be used as identity.

Allowed reviewer decision values checked: `hold`, `reject`, `needs_more_context`, `eligible_for_future_review`.

Forbidden reviewer decision values checked: `approved`, `geocoded`, `promoted`, `published`.

Required blocking fields checked: `production_blocked`, `geocode_blocked`, `promotion_blocked`, `publishing_blocked`, `registry_import_blocked`.

Required execution result: all blocking fields default to true; missing blocking fields fail closed; false blocking fields fail closed unless a later separate gate explicitly authorizes otherwise.

The execution gate must confirm fail-closed behavior for records with latitude, longitude, lat, lon, lng, coordinates, geometry, production path, WordPress target, public map target, scheduled workflow target, publishing target, missing group_key, missing display_location, missing candidate identity, missing source fields, missing audit fields, missing reviewer decision, invalid reviewer decision, review_rank used as identity, production/public/runtime target, geocoding coordinate field, or approval/promotion/publishing state.

## Hard prohibitions

XRI-G22 must not modify production feeds, public map runtime, WordPress, `nycinfocus.com/map`, iframe/embed settings, scheduled workflows, or `data/location_cache.json`; must not run live staging, fetch SODA/live data, geocode, approve/promote candidates, implement production registry database/importer behavior, add runtime publishing behavior, provide production runtime input, provide public output, run production validator execution, add production validator wiring, publish anything, or start XRI-G23.

## Proposed next gate

XRI-G23 non-production prototype fixture/manual-review sample set gate only, after explicit review and merge approval.

## Review gate

Open a pull request only. Do not merge. Do not start XRI-G23.
