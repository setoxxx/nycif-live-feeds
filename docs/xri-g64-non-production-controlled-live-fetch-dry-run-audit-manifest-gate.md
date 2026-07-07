# XRI-G64 Non-Production Controlled Live-Fetch Dry-Run Audit Manifest Gate

## Status

Documentation and report gate only.

## Source State

Completed and merged phases:

- XRI-G10 through XRI-G63

Immediate prior merged pull request:

- PR: #73
- Merge commit SHA: aed9f3c8b1e094e5e6516883e53c45de7ba865a3

## Purpose

XRI-G64 defines a non-production audit-manifest gate for a later controlled live-fetch dry-run phase.

This gate only records requirements. It does not add application behavior, executable audit-manifest behavior, source adapters, runtime behavior, production behavior, public map behavior, WordPress behavior, scheduled workflow behavior, registry behavior, or cache behavior.

## Allowed Files

Exactly two files are allowed for this phase:

- docs/xri-g64-non-production-controlled-live-fetch-dry-run-audit-manifest-gate.md
- data/reports/xri_g64_non_production_controlled_live_fetch_dry_run_audit_manifest_gate_report.json

## Audit Manifest Requirements For A Later Phase

A later phase must verify all of the following before any controlled dry-run audit manifest is allowed:

- source identity declaration is present
- execution authorization declaration is present
- source-call contract declaration is present
- source-call limit declaration is present
- input boundary declaration is present
- output boundary declaration is present
- artifact-isolation declaration is present
- dry-run-only declaration is present
- no-write declaration is present
- audit timestamp declaration is present
- source-response boundary declaration is present
- validation status declaration is present
- failure-stop status declaration is present
- stable identity declaration is present
- forbidden identity anchors are rejected
- registry paths are not used
- production paths are not used
- public map paths are not used
- WordPress paths are not used
- scheduled workflow paths are not used
- data/location_cache.json is not used
- audit manifest cannot become public map runtime input
- audit manifest cannot become production export input
- audit manifest cannot become registry import input

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

The companion report must confirm that this phase added only documentation/report artifacts and did not add implementation code, audit-manifest code, source adapters, runtime behavior, production behavior, public map behavior, WordPress behavior, scheduled workflow behavior, registry behavior, cache behavior, or XRI-G65 work.

## Stop Condition

Stop after creating only the two allowed XRI-G64 gate files.

Do not merge.

Do not start XRI-G65.
