# XRI-G65 Non-Production Controlled Live-Fetch Dry-Run Review Package Gate

## Status

Documentation and report gate only.

## Source State

Completed and merged phases:

- XRI-G10 through XRI-G64

Immediate prior merged pull request:

- PR: #74
- Merge commit SHA: d5993d22097f8e5a83de00053154a41fdd472554

## Purpose

XRI-G65 defines a non-production review-package gate for a later controlled live-fetch dry-run phase.

This gate only records requirements. It does not add application behavior, executable review-package behavior, source adapters, runtime behavior, production behavior, public map behavior, WordPress behavior, scheduled workflow behavior, registry behavior, or cache behavior.

## Allowed Files

Exactly two files are allowed for this phase:

- docs/xri-g65-non-production-controlled-live-fetch-dry-run-review-package-gate.md
- data/reports/xri_g65_non_production_controlled_live_fetch_dry_run_review_package_gate_report.json

## Review Package Requirements For A Later Phase

A later phase must verify all of the following before any controlled dry-run review package is allowed:

- source identity summary is present
- execution authorization summary is present
- source-call contract summary is present
- source-call limit summary is present
- input boundary summary is present
- output boundary summary is present
- artifact-isolation summary is present
- audit-manifest summary is present
- validation status summary is present
- failure-stop status summary is present
- stable identity summary is present
- forbidden identity anchor rejection summary is present
- dry-run-only declaration is present
- no-write declaration is present
- registry paths are not used
- production paths are not used
- public map paths are not used
- WordPress paths are not used
- scheduled workflow paths are not used
- data/location_cache.json is not used
- review package cannot become public map runtime input
- review package cannot become production export input
- review package cannot become registry import input

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

The companion report must confirm that this phase added only documentation/report artifacts and did not add implementation code, review-package code, source adapters, runtime behavior, production behavior, public map behavior, WordPress behavior, scheduled workflow behavior, registry behavior, cache behavior, or XRI-G66 work.

## Stop Condition

Stop after creating only the two allowed XRI-G65 gate files.

Do not merge.

Do not start XRI-G66.
