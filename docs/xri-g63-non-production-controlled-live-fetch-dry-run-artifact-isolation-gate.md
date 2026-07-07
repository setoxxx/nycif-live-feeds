# XRI-G63 Non-Production Controlled Live-Fetch Dry-Run Artifact Isolation Gate

## Status

Documentation and report gate only.

## Source State

Completed and merged phases:

- XRI-G10 through XRI-G62

Immediate prior merged pull request:

- PR: #72
- Merge commit SHA: 915c738d792f00f079bff21eeac9cd98447d8cc0

## Purpose

XRI-G63 defines a non-production artifact-isolation gate for a later controlled live-fetch dry-run phase.

This gate only records requirements. It does not add application behavior, executable artifact-isolation behavior, source adapters, runtime behavior, production behavior, public map behavior, WordPress behavior, scheduled workflow behavior, registry behavior, or cache behavior.

## Allowed Files

Exactly two files are allowed for this phase:

- docs/xri-g63-non-production-controlled-live-fetch-dry-run-artifact-isolation-gate.md
- data/reports/xri_g63_non_production_controlled_live_fetch_dry_run_artifact_isolation_gate_report.json

## Artifact Isolation Requirements For A Later Phase

A later phase must verify all of the following before any controlled dry-run artifact is allowed:

- report-only artifact boundary is declared
- dry-run-only artifact boundary is declared
- source responses are isolated
- candidate outputs are isolated
- audit artifacts are isolated
- validation artifacts are isolated
- failure-stop artifacts are isolated
- stable identity declaration is present
- forbidden identity anchors are rejected
- registry paths are not used
- production paths are not used
- public map paths are not used
- WordPress paths are not used
- scheduled workflow paths are not used
- data/location_cache.json is not used
- approval paths are not used
- promotion paths are not used
- publishing paths are not used
- artifacts cannot become public map runtime inputs
- artifacts cannot become production export inputs
- artifacts cannot become registry import inputs

## Stable Identity Rule

Permitted stable identity fields:

- group_key
- display_location
- candidate_identity

Forbidden identity anchors:

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

The companion report must confirm that this phase added only documentation/report artifacts and did not add implementation code, artifact-isolation code, source adapters, runtime behavior, production behavior, public map behavior, WordPress behavior, scheduled workflow behavior, registry behavior, cache behavior, or XRI-G64 work.

## Stop Condition

Stop after creating only the two allowed XRI-G63 gate files.

Do not merge.

Do not start XRI-G64.
