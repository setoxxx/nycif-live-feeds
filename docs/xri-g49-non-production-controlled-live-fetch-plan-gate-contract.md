# XRI-G49 Non-Production Controlled Live-Fetch Plan Gate Contract

## Status

Plan gate only.

This phase does not implement controlled live-fetch behavior.

## Source State

Completed and merged phases:

- XRI-G10 through XRI-G48

Immediate prior merged pull request:

- PR: #58
- Merge commit SHA: dce3bad4b35c33af548783358c482d418834d2aa
- Merged at: 2026-07-07T00:16:20Z

## Purpose

XRI-G49 creates a non-production planning gate for a future controlled live-fetch implementation.

This phase may define safe planning boundaries, file contracts, execution limits, source-control rules, and validation requirements for future controlled live-fetch work.

This phase must not implement live-fetch code.

This phase must not fetch any live source.

This phase must not call NYC Open Data, SODA, external APIs, or scrape websites.

This phase must not touch production or public outputs.

## Allowed Files

Exactly two files are allowed for this phase:

- docs/xri-g49-non-production-controlled-live-fetch-plan-gate-contract.md
- data/reports/xri_g49_non_production_controlled_live_fetch_plan_gate_report.json

## Forbidden Actions

This phase must not:

- create executable live-fetch code
- create executable source-specific adapter code
- create production code
- fetch live sources
- call NYC Open Data
- call SODA
- call external source APIs
- scrape websites
- geocode
- create live candidates
- stage live data
- write registry records
- import registry records
- approve records
- promote records
- publish records
- modify production exports
- modify public map runtime
- modify public map output
- modify WordPress
- modify scheduled workflows
- touch data/location_cache.json
- start XRI-G50

## Non-Production Boundary

XRI-G49 is limited to non-production planning artifacts.

No production path is authorized by this gate.

No public runtime path is authorized by this gate.

## No-Live-Fetch Boundary

No controlled live-fetch code is implemented in this phase.

No source fetch is performed in this phase.

No source adapter is implemented in this phase.

## No-Source-Call Boundary

This gate does not call:

- NYC Open Data
- SODA
- external APIs
- websites
- geocoding services

## Stable Identity Rule

Any future controlled live-fetch plan must preserve stable identity using only:

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
- production path
- public runtime path

## Future Validation Requirements

Any future implementation phase must validate:

- stable identity is preserved
- live-fetch execution is explicitly isolated from production
- source calls are explicitly controlled and auditable
- no public map output is modified without a separate authorization gate
- no registry writes or imports occur without a separate authorization gate
- data/location_cache.json remains protected unless a future gate explicitly authorizes changes

## Stop Condition

Stop after creating only the two allowed XRI-G49 gate files.

Do not merge.

Do not start XRI-G50.

Do not perform any live-fetch, API, scrape, geocode, registry, production, public map, WordPress, or scheduled workflow action.

## Next Phase Boundary

XRI-G50 is not started by this phase.

Any future XRI-G50 work requires a separate explicit authorization.
