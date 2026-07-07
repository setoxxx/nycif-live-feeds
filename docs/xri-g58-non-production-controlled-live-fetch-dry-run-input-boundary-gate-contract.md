# XRI-G58 Non-Production Controlled Live-Fetch Dry-Run Input-Boundary Gate Contract

## Status

Dry-run input-boundary gate only.

This phase does not implement controlled live-fetch behavior, executable dry-run behavior, executable input-boundary behavior, or dry-run execution.

## Source State

Completed and merged phases:

- XRI-G10 through XRI-G57

Immediate prior merged pull request:

- PR: #67
- Merge commit SHA: 4c156364b79193a89dfb5ca1cd4aaccaf143c908

## Purpose

XRI-G58 creates a non-production input-boundary gate for a future controlled live-fetch dry-run.

This phase may define future dry-run input-boundary requirements, permitted input declarations, forbidden input sources, source-call precondition rules, manifest input requirements, stable identity input requirements, audit input requirements, validation input requirements, failure-stop input requirements, and next-phase input boundaries.

This phase must not implement live-fetch code, dry-run code, validation code, failure-stop code, audit-logging code, output-boundary code, input-boundary code, source-specific adapter code, or production code.

This phase must not execute a dry-run, fetch live sources, call source APIs, call geocoding services, create live candidates, stage live data, write or import registry records, modify production exports, modify public map output, modify WordPress, modify scheduled workflows, touch data/location_cache.json, or start XRI-G59.

## Allowed Files

Exactly two files are allowed for this phase:

- docs/xri-g58-non-production-controlled-live-fetch-dry-run-input-boundary-gate-contract.md
- data/reports/xri_g58_non_production_controlled_live_fetch_dry_run_input_boundary_gate_report.json

## Forbidden Actions

This phase must not:

- create executable live-fetch code
- create executable dry-run code
- create executable validation code
- create executable failure-stop code
- create executable audit-logging code
- create executable output-boundary code
- create executable input-boundary code
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
- start XRI-G59

## Dry-Run Input-Boundary-Only Boundary

XRI-G58 may define future dry-run input-boundary requirements.

No executable input-boundary behavior is authorized by this gate.

No executable output-boundary behavior is authorized by this gate.

No executable audit-logging behavior is authorized by this gate.

No executable failure-stop behavior is authorized by this gate.

No executable validation behavior is authorized by this gate.

No executable dry-run behavior is authorized by this gate.

No executable live-fetch behavior is authorized by this gate.

No dry-run is executed by this gate.

## Input-Boundary Design Requirements

Any future dry-run input boundary should include:

- permitted input declarations
- forbidden input source declarations
- dry-run-only input declaration
- source-call precondition declaration
- source-call limit declaration
- source identity declaration
- manifest input declaration
- no-registry-input declaration
- no-production-input declaration
- no-public-map-input declaration
- no-WordPress-input declaration
- no-scheduled-workflow-input declaration
- no-location-cache-input declaration
- stable identity input declaration
- audit input declaration
- validation input declaration
- failure-stop input declaration
- output-boundary linkage declaration
- next-phase boundary declaration

## Forbidden Input Sources

Any future dry-run input must not read from or depend on:

- registry paths as mutable source of truth
- production paths as mutable source of truth
- public map paths as mutable source of truth
- WordPress paths
- scheduled workflow paths
- data/location_cache.json
- approval paths
- promotion paths
- publishing paths
- geocoding cache paths
- public runtime paths
- review_rank
- row position
- array index
- source row order
- reviewer sort order

## Input Failure-Stop Requirements

Any future dry-run must stop before fetching, validating, producing, or promoting outputs if any input source is missing a dry-run-only boundary, conflicts with no-write declarations, depends on forbidden identity anchors, or attempts to read from any forbidden mutable production path.

## Controlled Live-Fetch Boundary

XRI-G58 may describe input-boundary requirements for future controlled live-fetch dry-run work.

It must not create:

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

XRI-G58 is limited to non-production documentation and report artifacts only.

No public runtime path is authorized by this gate.

No production path is authorized by this gate.

## No-Source-Call Boundary

XRI-G58 must not call, test, ping, fetch, download, sample, query, validate, or dry-run against any live external source.

This includes:

- NYC Open Data
- SODA
- external APIs
- websites
- geocoding services

## No-Write Boundary

XRI-G58 must define that any future dry-run input handling remains no-write unless a later gate explicitly authorizes otherwise.

Future dry-run input handling must not write to registry paths, production paths, public map paths, WordPress paths, scheduled workflow paths, or data/location_cache.json.

## No-Production Boundary

XRI-G58 must not modify any production-facing file, workflow, runtime, output, deployment path, public map path, WordPress path, registry path, or cache path.

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

The companion report must explicitly confirm all required safety assertions for this gate, including that no implementation, executable dry-run code, executable validation code, executable failure-stop code, executable audit-logging code, executable output-boundary code, executable input-boundary code, source call, registry write, production output, public map output, WordPress change, scheduled workflow change, cache change, or XRI-G59 start occurred.

## Future Dry-Run Input-Boundary Implementation Requirements

Any future dry-run input-boundary implementation phase must validate:

- stable identity is preserved
- dry-run execution is explicitly isolated from production
- source calls are explicitly controlled and auditable
- manifest declarations exist before execution
- permitted input declarations exist before execution
- forbidden input source declarations exist before execution
- no-write declarations exist before execution
- validation declarations exist before execution
- failure-stop declarations exist before execution
- audit declarations exist before execution
- output boundary declarations exist before execution
- forbidden identity anchors are rejected
- dry-run inputs cannot depend on registry, production, public map, WordPress, scheduled workflows, or data/location_cache.json as mutable source of truth
- no public map output is modified without a separate authorization gate
- no registry writes or imports occur without a separate authorization gate
- input failure-stop conditions prevent accidental production, registry, or public output changes

## Stop Condition

Stop after creating only the two allowed XRI-G58 gate files.

Do not merge.

Do not start XRI-G59.

Do not perform any live-fetch, dry-run execution, API, geocode, registry, production, public map, WordPress, or scheduled workflow action.

## Next Phase Boundary

XRI-G59 is not started by this phase.

Any future XRI-G59 work requires a separate explicit authorization.
