# XRI-G62 Non-Production Controlled Live-Fetch Dry-Run Read-Only Harness Contract Gate

## Status

Documentation and report gate only.

## Source State

Completed and merged phases:

- XRI-G10 through XRI-G61

Immediate prior merged pull request:

- PR: #71
- Merge commit SHA: 50b7a3ece93b236512f3f67acdf1ccc0523e8e15

## Purpose

XRI-G62 defines a non-production read-only harness contract gate for a later controlled live-fetch dry-run phase.

This gate only records requirements. It does not add application behavior, executable harness behavior, source adapters, runtime behavior, production behavior, public map behavior, WordPress behavior, scheduled workflow behavior, registry behavior, or cache behavior.

## Allowed Files

Exactly two files are allowed for this phase:

- docs/xri-g62-non-production-controlled-live-fetch-dry-run-read-only-harness-contract-gate.md
- data/reports/xri_g62_non_production_controlled_live_fetch_dry_run_read_only_harness_contract_gate_report.json

## Harness Contract Requirements For A Later Phase

A later phase must verify all of the following before any controlled dry-run harness is allowed:

- disabled-by-default mode is declared
- dry-run-only mode is declared
- no-write mode is declared
- source-call handling is disabled by default
- later execution gate is required
- source-call limit is present
- source identity is present
- input boundary is present
- output boundary is present
- audit declaration is present
- validation declaration is present
- failure-stop declaration is present
- stable identity declaration is present
- forbidden identity anchors are rejected
- dry-run artifact output is isolated
- registry write targets are not available
- production write targets are not available
- public map write targets are not available
- WordPress write targets are not available
- scheduled workflow write targets are not available
- data/location_cache.json write target is not available

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

The companion report must confirm that this phase added only documentation/report artifacts and did not add implementation code, harness code, source adapters, runtime behavior, production behavior, public map behavior, WordPress behavior, scheduled workflow behavior, registry behavior, cache behavior, or XRI-G63 work.

## Stop Condition

Stop after creating only the two allowed XRI-G62 gate files.

Do not merge.

Do not start XRI-G63.
