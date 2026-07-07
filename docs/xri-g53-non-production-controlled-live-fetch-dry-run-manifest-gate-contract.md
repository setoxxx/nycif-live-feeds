# XRI-G53 Non-Production Controlled Live-Fetch Dry-Run Manifest Gate Contract

## Status

Dry-run manifest gate only.

This phase does not implement controlled live-fetch behavior.

This phase does not implement executable dry-run behavior.

This phase does not execute a dry-run.

## Source State

Completed and merged phases:

- XRI-G10 through XRI-G52

Immediate prior merged pull request:

- PR: #62
- Merge commit SHA: 54fd6a5d1475e88b09b40058513592bd3c6454f5

## Purpose

XRI-G53 creates a non-production manifest gate for a future controlled live-fetch dry-run.

This phase may define a future dry-run manifest structure, required manifest fields, source-call declaration fields, no-write declarations, audit fields, stop-condition fields, and validation expectations for a future controlled live-fetch dry-run implementation.

This phase must not implement live-fetch code.

This phase must not implement executable dry-run code.

This phase must not execute a dry-run.

This phase must not fetch any live source.

This phase must not call NYC Open Data, SODA, external APIs, geocoding services, or scrape websites.

This phase must not write or import registry records.

This phase must not touch production, public map runtime, WordPress, scheduled workflows, or data/location_cache.json.

## Allowed Files

Exactly two files are allowed for this phase:

- docs/xri-g53-non-production-controlled-live-fetch-dry-run-manifest-gate-contract.md
- data/reports/xri_g53_non_production_controlled_live_fetch_dry_run_manifest_gate_report.json

## Forbidden Actions

This phase must not:

- create executable live-fetch code
- create executable dry-run code
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
- start XRI-G54

## Dry-Run Manifest-Only Boundary

XRI-G53 may define the future dry-run manifest structure and required fields.

No executable dry-run behavior is authorized by this gate.

No executable live-fetch behavior is authorized by this gate.

No dry-run is executed by this gate.

## Manifest Design Requirements

Any future dry-run manifest should include:

- phase identifier
- run identifier
- dry-run mode declaration
- no-write declaration
- source-call declaration
- source-call limit declaration
- source identity declaration
- stable identity fields
- forbidden identity fields
- input boundary declaration
- output boundary declaration
- audit logging declaration
- failure-stop declaration
- registry write prohibition
- production write prohibition
- public map write prohibition
- WordPress write prohibition
- scheduled workflow write prohibition
- location_cache protection declaration
- next-phase boundary declaration

## Controlled Live-Fetch Boundary

XRI-G53 may describe manifest requirements for future controlled live-fetch dry-run work.

It must not create:

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

XRI-G53 is limited to non-production documentation and report artifacts only.

No public runtime path is authorized by this gate.

No production path is authorized by this gate.

## No-Source-Call Boundary

XRI-G53 must not call, test, ping, fetch, scrape, download, sample, query, validate, or dry-run against any live external source.

This includes:

- NYC Open Data
- SODA
- external APIs
- websites
- geocoding services

## No-Write Boundary

XRI-G53 must define that any future dry-run remains no-write unless a later gate explicitly authorizes otherwise.

Future dry-run outputs must not write to:

- registry paths
- production paths
- public map paths
- WordPress paths
- scheduled workflow paths
- data/location_cache.json

## No-Production Boundary

XRI-G53 must not modify any production-facing file, workflow, runtime, output, deployment path, public map path, WordPress path, registry path, or cache path.

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

The companion report must explicitly confirm all required safety assertions for this gate, including that no implementation, executable dry-run code, source call, scrape, geocoding, registry write, production output, public map output, WordPress change, scheduled workflow change, cache change, or XRI-G54 start occurred.

## Future Dry-Run Manifest Implementation Validation Requirements

Any future dry-run manifest implementation phase must validate:

- stable identity is preserved
- dry-run execution is explicitly isolated from production
- source calls are explicitly controlled and auditable
- manifest source-call declarations exist before execution
- manifest no-write declarations exist before execution
- manifest failure-stop declarations exist before execution
- dry-run outputs cannot write to registry, production, public map, WordPress, scheduled workflows, or data/location_cache.json
- no public map output is modified without a separate authorization gate
- no registry writes or imports occur without a separate authorization gate
- failure-stop conditions prevent accidental production, registry, or public output changes

## Stop Condition

Stop after creating only the two allowed XRI-G53 gate files.

Do not merge.

Do not start XRI-G54.

Do not perform any live-fetch, dry-run execution, API, scrape, geocode, registry, production, public map, WordPress, or scheduled workflow action.

## Next Phase Boundary

XRI-G54 is not started by this phase.

Any future XRI-G54 work requires a separate explicit authorization.
