# XRI-G48 Non-Production Controlled Live-Fetch Implementation Authorization Gate Contract

## Status

Authorization gate only.

This phase does not implement controlled live-fetch behavior.

## Source State

Completed and merged phases:

- XRI-G10 through XRI-G47

Immediate prior merged pull request:

- PR: #57
- Merge commit SHA: 10e3ecb2be540538059530ac014294589a6f9ffe

## Purpose

XRI-G48 authorizes the next non-production planning boundary for a future controlled live-fetch implementation layer.

This gate is limited to documentation and report artifacts only.

It does not create, modify, or execute any live-fetch implementation.

## Allowed Files

Exactly two files are allowed for this phase:

- docs/xri-g48-non-production-controlled-live-fetch-implementation-authorization-gate-contract.md
- data/reports/xri_g48_non_production_controlled_live_fetch_implementation_authorization_gate_report.json

## Forbidden Actions

This phase must not:

- implement executable controlled live-fetch code
- implement executable source-specific adapter code
- implement executable live-fetch code
- fetch live sources
- call NYC Open Data
- call SODA
- call external APIs for source ingestion
- scrape websites
- geocode
- create live candidates
- stage live data
- write registry records
- import registry records
- modify production exports
- modify public map runtime
- modify public map output
- modify WordPress
- modify scheduled workflows
- touch data/location_cache.json
- approve records
- promote records
- publish records
- deploy production
- start XRI-G49

## Stable Identity Rule

Future controlled live-fetch work must preserve stable identity using only:

- group_key
- display_location
- candidate_identity

The following must not be used as identity anchors:

- review_rank
- row position
- array index
- source row order
- source sort order
- reviewer sort order
- review_status
- review_reason
- review_notes
- approval state
- promotion state
- publishing state
- geocoding state
- coordinates
- geometry
- public runtime targets
- production targets

## Production Safety

Production remains untouched.

No production path is authorized by this gate.

## Next Phase Boundary

XRI-G49 is not started by this phase.

Any future XRI-G49 work requires a separate explicit authorization.
