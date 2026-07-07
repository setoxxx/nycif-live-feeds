# XRI-G59 Non-Production Controlled Live-Fetch Dry-Run Source-Call Contract Gate

## Status

Dry-run source-call contract gate only.

This phase does not implement controlled live-fetch behavior, executable dry-run behavior, executable source-call behavior, or dry-run execution.

## Source State

Completed and merged phases:

- XRI-G10 through XRI-G58

Immediate prior merged pull request:

- PR: #68
- Merge commit SHA: fe2e4b907165691610c807115d5cfd19104438d0

## Purpose

XRI-G59 creates a non-production source-call contract gate for a future controlled live-fetch dry-run.

This phase may define future dry-run source-call contract requirements, source-call preconditions, source-call limits, permitted source-call declarations, forbidden source-call behaviors, source identity requirements, source audit requirements, source validation requirements, source failure-stop requirements, and next-phase source-call boundaries.

This phase must not implement live-fetch code, dry-run code, validation code, failure-stop code, audit-logging code, output-boundary code, input-boundary code, source-call code, source-specific adapter code, or production code.

This phase must not execute a dry-run, fetch live sources, call source APIs, call geocoding services, create live candidates, stage live data, write or import registry records, modify production exports, modify public map output, modify WordPress, modify scheduled workflows, touch data/location_cache.json, or start XRI-G60.

## Allowed Files

Exactly two files are allowed for this phase:

- docs/xri-g59-non-production-controlled-live-fetch-dry-run-source-call-contract-gate.md
- data/reports/xri_g59_non_production_controlled_live_fetch_dry_run_source_call_contract_gate_report.json

## Forbidden Actions

This phase must not:

- create executable live-fetch code
- create executable dry-run code
- create executable validation code
- create executable failure-stop code
- create executable audit-logging code
- create executable output-boundary code
- create executable input-boundary code
- create executable source-call code
- create executable source-specific adapter code
- create production code
- execute a dry-run
- fetch live sources
- call NYC Open Data
- call SODA
- call external source APIs
- call geocoding services
- scrape websites
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
- start XRI-G60

## Dry-Run Source-Call-Contract-Only Boundary

XRI-G59 may define future dry-run source-call contract requirements.

No executable source-call behavior is authorized by this gate.

No executable input-boundary behavior is authorized by this gate.

No executable output-boundary behavior is authorized by this gate.

No executable audit-logging behavior is authorized by this gate.

No executable failure-stop behavior is authorized by this gate.

No executable validation behavior is authorized by this gate.

No executable dry-run behavior is authorized by this gate.

No executable live-fetch behavior is authorized by this gate.

No dry-run is executed by this gate.

## Source-Call Contract Design Requirements

Any future dry-run source-call contract should include:

- permitted source-call declaration
- source-call disabled-by-default declaration
- explicit later execution-gate requirement
- source-call limit declaration
- source identity declaration
- source endpoint declaration placeholder
- source authentication declaration placeholder
- source rate-limit declaration placeholder
- source timeout declaration placeholder
- source retry prohibition or retry limit declaration
- source payload boundary declaration
- source response boundary declaration
- no-registry-write declaration
- no-production-write declaration
- no-public-map-write declaration
- no-WordPress-write declaration
- no-scheduled-workflow-write declaration
- no-location-cache-write declaration
- stable identity declaration
- audit declaration
- validation declaration
- failure-stop declaration
- input-boundary linkage declaration
- output-boundary linkage declaration
- next-phase boundary declaration

## Forbidden Source-Call Behaviors

Any future dry-run source-call must not:

- execute without a later explicit execution gate
- run without dry-run mode
- run without no-write mode
- run without source-call limit declaration
- run without source identity declaration
- run without audit declaration
- run without failure-stop declaration
- write source responses to registry paths
- write source responses to production paths
- write source responses to public map paths
- write source responses to WordPress paths
- write source responses to scheduled workflow paths
- write source responses to data/location_cache.json
- use review_rank as identity
- use row position as identity
- use array index as identity
- use source row order as identity
- use reviewer sort order as identity
- create candidates
- stage live data
- approve records
- promote records
- publish records

## Source-Call Failure-Stop Requirements

Any future dry-run must stop before source calls, validation, output production, or promotion if source-call declarations are missing, source-call limits are missing, source identity is missing, audit declarations are missing, no-write declarations are missing, forbidden identity anchors are referenced, or any forbidden write target is reachable.

## Controlled Live-Fetch Boundary

XRI-G59 may describe source-call contract requirements for future controlled live-fetch dry-run work.

It must not create:

- executable source-call logic
- executable input-boundary logic
- executable output-boundary logic
- executable audit-logging logic
- executable failure-stop logic
- executable validation logic
- executable fetch logic
- executable dry-run logic
- source-specific adapters
- source credentials
- source calls
- source downloads
- staging outputs
- candidate outputs
- registry outputs
- public map outputs
- production outputs

## Non-Production Boundary

XRI-G59 is limited to non-production documentation and report artifacts only.

No public runtime path is authorized by this gate.

No production path is authorized by this gate.

## No-Source-Call Boundary

XRI-G59 must not call, test, ping, fetch, download, sample, query, validate, or dry-run against any live external source.

This includes:

- NYC Open Data
- SODA
- external APIs
- websites
- geocoding services

## No-Write Boundary

XRI-G59 must define that any future source-call handling remains no-write unless a later gate explicitly authorizes otherwise.

Future source-call handling must not write to registry paths, production paths, public map paths, WordPress paths, scheduled workflow paths, or data/location_cache.json.

## No-Production Boundary

XRI-G59 must not modify any production-facing file, workflow, runtime, output, deployment path, public map path, WordPress path, registry path, or cache path.

## Stable Identity Rule

Any future dry-run or controlled live-fetch implementation must preserve stable identity using only:

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

## Required Safety Assertions

The companion report must explicitly confirm all required safety assertions for this gate, including that no implementation, executable dry-run code, executable validation code, executable failure-stop code, executable audit-logging code, executable output-boundary code, executable input-boundary code, executable source-call code, source call, registry write, production output, public map output, WordPress change, scheduled workflow change, cache change, or XRI-G60 start occurred.

## Future Dry-Run Source-Call Contract Implementation Requirements

Any future dry-run source-call contract implementation phase must validate:

- stable identity is preserved
- dry-run execution is explicitly isolated from production
- source calls are disabled by default
- source calls require a later explicit execution gate
- source-call declarations exist before execution
- source-call limits exist before execution
- source identity declarations exist before execution
- manifest declarations exist before execution
- no-write declarations exist before execution
- validation declarations exist before execution
- failure-stop declarations exist before execution
- audit declarations exist before execution
- input boundary declarations exist before execution
- output boundary declarations exist before execution
- forbidden identity anchors are rejected
- source responses cannot write to registry, production, public map, WordPress, scheduled workflows, or data/location_cache.json
- no public map output is modified without a separate authorization gate
- no registry writes or imports occur without a separate authorization gate
- source-call failure-stop conditions prevent accidental production, registry, or public output changes

## Stop Condition

Stop after creating only the two allowed XRI-G59 gate files.

Do not merge.

Do not start XRI-G60.

Do not perform any live-fetch, dry-run execution, API, geocode, registry, production, public map, WordPress, or scheduled workflow action.

## Next Phase Boundary

XRI-G60 is not started by this phase.

Any future XRI-G60 work requires a separate explicit authorization.
