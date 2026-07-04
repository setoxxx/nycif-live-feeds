# XRI-G20 Registry Manual-Review Prototype Scaffold Contract

Phase: XRI-G20

Source phase: XRI-G19
Source pull request: #28
Source merge commit SHA: `aea4976a75b60f45033690b725867d65f4c4636c`

## Completion map at this junction

- Completed and merged: XRI-G10 through XRI-G19: 100%.
- Current next phase: XRI-G20: not started at gate entry; in progress only after this branch/pull request is opened.
- Overall toward a safe non-production registry/manual-review prototype: about 75% complete at gate entry.
- Overall toward full production public-map/registry use: about 45-55% complete at gate entry.

Mode: non-production registry/manual-review prototype scaffold gate only.

This is a prototype scaffold only. It must use fixture-only or test-only data and must not implement production registry, importer, database, public map, WordPress, geocoding, approval, promotion, publishing, or runtime behavior.

## Source chain

XRI-G13 through XRI-G19 are the source context: manual-review schema prototype, fixture validator, validator execution gate, failure-case fixtures, failure-case validator execution, summary/handoff gate, and registry implementation planning gate.

## Scaffold requirements

The scaffold must define a registry record identity model, manual-review record shape, stable identity matching using `group_key`, `display_location`, and candidate identity, and must not use `review_rank` as identity.

It must define reviewer decision lifecycle, audit fields, blocking fields, fail-closed validation, fixture/test-only input and output boundaries, production blocking, geocoding blocking, promotion blocking, publishing blocking, registry import blocking, public-output blocking, rollback/stop conditions, future promotion gate requirements, and future production authorization gate requirements.

Allowed reviewer decisions: `hold`, `reject`, `needs_more_context`, `eligible_for_future_review`.

Forbidden reviewer decisions: `approved`, `geocoded`, `promoted`, `published`.

Required blocking fields: `production_blocked`, `geocode_blocked`, `promotion_blocked`, `publishing_blocked`, `registry_import_blocked`. All must default to true. Missing or false blocking fields fail closed unless a later separate gate authorizes otherwise.

The scaffold must not include latitude, longitude, lat, lon, lng, coordinates, geometry, production path, WordPress target, public map target, scheduled workflow target, or publishing target.

## Hard prohibitions

XRI-G20 must not modify production feeds, public map runtime, WordPress, `nycinfocus.com/map`, iframe/embed settings, scheduled workflows, or `data/location_cache.json`; must not run live staging, fetch SODA/live data, geocode, approve/promote candidates, implement production registry database/importer behavior, add runtime publishing behavior, provide production runtime input, provide public output, publish anything, or start XRI-G21.

## Proposed next gate

XRI-G21 non-production prototype scaffold validator gate only, after explicit review and merge approval.

## Review gate

Open a pull request only. Do not merge. Do not start XRI-G21.
