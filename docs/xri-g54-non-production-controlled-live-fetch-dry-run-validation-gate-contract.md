# XRI-G54 Non-Production Controlled Live-Fetch Dry-Run Validation Gate Contract

## Status

Dry-run validation gate only.

This phase does not implement controlled live-fetch behavior.

This phase does not implement executable dry-run behavior.

This phase does not execute a dry-run.

## Source State

Completed and merged phases:

- XRI-G10 through XRI-G53

Immediate prior merged pull request:

- PR: #63
- Merge commit SHA: 15e1727922273a35c622b6c00d149e7f472f340b

## Purpose

XRI-G54 creates a non-production validation gate for a future controlled live-fetch dry-run.

This phase may define future dry-run validation requirements, manifest validation checks, no-write validation checks, source-call declaration checks, stable identity validation checks, audit validation checks, and failure-stop validation expectations for a future controlled live-fetch dry-run implementation.

This phase must not implement live-fetch code.

This phase must not implement executable dry-run code.

This phase must not execute a dry-run.

This phase must not fetch any live source.

This phase must not call NYC Open Data, SODA, external APIs, geocoding services, or scrape websites.

This phase must not write or import registry records.

This phase must not touch production, public map runtime, WordPress, scheduled workflows, or data/location_cache.json.

## Allowed Files

Exactly two files are allowed for this phase:

- docs/xri-g54-non-production-controlled-live-fetch-dry-run-validation-gate-contract.md
- data/reports/xri_g54_non_production_controlled_live_fetch_dry_run_validation_gate_report.json

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
- start XRI-G55

## Dry-Run Validation-Only Boundary

XRI-G54 may define future dry-run validation checks.

No executable validation behavior is authorized by this gate.

No executable dry-run behavior is authorized by this gate.

No executable live-fetch behavior is authorized by this gate.

No dry-run is executed by this gate.

## Validation Design Requirements

Any future dry-run validation should verify:

- dry-run mode declaration exists
- no-write declaration exists
- source-call declaration exists
- source-call limit declaration exists
- source identity declaration exists
- stable identity fields exist
- forbidden identity fields are rejected as anchors
- input boundary declaration exists
- output boundary declaration exists
- audit logging declaration exists
- failure-stop declaration exists
- registry write prohibition exists
- production write prohibition exists
- public map write prohibition exists
- WordPress write prohibition exists
- scheduled workflow write prohibition exists
- location_cache protection declaration exists
- next-phase boundary declaration exists

## Controlled Live-Fetch Boundary

XRI-G54 may describe validation requirements for future controlled live-fetch dry-run work.

It must not create:

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

XRI-G54 is limited to non-production documentation and report artifacts only.

No public runtime path is authorized by this gate.

No production path is authorized by this gate.

## No-Source-Call Boundary

XRI-G54 must not call, test, ping, fetch, scrape, download, sample, query, validate, or dry-run against any live external source.

This includes:

- NYC Open Data
- SODA
- external APIs
- websites
- geocoding services

## No-Write Boundary

XRI-G54 must define that any future dry-run validation remains no-write unless a later gate explicitly authorizes otherwise.

Future dry-run validation outputs must not write to:

- registry paths
- production paths
- public map paths
- WordPress paths
- scheduled workflow paths
- data/location_cache.json

## No-Production Boundary

XRI-G54 must not modify any production-facing file, workflow, runtime, output, deployment path, public map path, WordPress path, registry path, or cache path.

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

The companion report must explicitly confirm all required safety assertions for this gate, including that no implementation, executable dry-run code, executable validation code, source call, scrape, geocoding, registry write, production output, public map output, WordPress change, scheduled workflow change, cache change, or XRI-G55 start occurred.

## Future Dry-Run Validation Implementation Requirements

Any future dry-run validation implementation phase must validate:

- stable identity is preserved
- dry-run execution is explicitly isolated from production
- source calls are explicitly controlled and auditable
- manifest declarations exist before execution
- no-write declarations exist before execution
- failure-stop declarations exist before execution
- forbidden identity anchors are rejected
- dry-run outputs cannot write to registry, production, public map, WordPress, scheduled workflows, or data/location_cache.json
- no public map output is modified without a separate authorization gate
- no registry writes or imports occur without a separate authorization gate
- failure-stop conditions prevent accidental production, registry, or public output changes

## Stop Condition

Stop after creating only the two allowed XRI-G54 gate files.

Do not merge.

Do not start XRI-G55.

Do not perform any live-fetch, dry-run execution, API, scrape, geocode, registry, production, public map, WordPress, or scheduled workflow action.

## Next Phase Boundary

XRI-G55 is not started by this phase.

Any future XRI-G55 work requires a separate explicit authorization.
