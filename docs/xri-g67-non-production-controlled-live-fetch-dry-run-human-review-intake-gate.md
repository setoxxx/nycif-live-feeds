# XRI-G67 Non-Production Controlled Live-Fetch Dry-Run Human Review Intake Gate

## Status

Documentation and report gate only.

## Source State

Completed and merged phases:

- XRI-G10 through XRI-G66

Immediate prior merged pull request:

- PR: #112
- Merge commit SHA: 0e7229d008228bff84f2f4ed02ef8d141bb14f0d

## Purpose

XRI-G67 defines a non-production human-review-intake gate for a later controlled live-fetch dry-run phase.

This gate only records requirements. It does not add application behavior, executable human-review-intake behavior, source adapters, runtime behavior, production behavior, public map behavior, WordPress behavior, scheduled workflow behavior, registry behavior, approval behavior, promotion behavior, publishing behavior, or cache behavior.

## Allowed Files

Exactly two files are allowed for this phase:

- docs/xri-g67-non-production-controlled-live-fetch-dry-run-human-review-intake-gate.md
- data/reports/xri_g67_non_production_controlled_live_fetch_dry_run_human_review_intake_gate_report.json

## Human Review Intake Requirements For A Later Phase

A later phase must verify all of the following before any controlled dry-run human review intake is allowed:

- source identity summary is present
- execution authorization summary is present
- source-call contract summary is present
- source-call limit summary is present
- input boundary summary is present
- output boundary summary is present
- artifact-isolation summary is present
- audit-manifest summary is present
- review-package summary is present
- manual-approval-handoff summary is present
- validation status summary is present
- failure-stop status summary is present
- stable identity summary is present
- forbidden identity anchor rejection summary is present
- dry-run-only declaration is present
- no-write declaration is present
- human-review-only declaration is present
- intake-is-not-approval declaration is present
- no-approval-action declaration is present
- no-promotion-action declaration is present
- no-publishing-action declaration is present
- registry paths are not used
- production paths are not used
- public map paths are not used
- WordPress paths are not used
- scheduled workflow paths are not used
- data/location_cache.json is not used
- human review intake cannot become public map runtime input
- human review intake cannot become production export input
- human review intake cannot become registry import input

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

The companion report must confirm that this phase added only documentation/report artifacts and did not add implementation code, human-review-intake code, manual-approval-handoff code, source adapters, runtime behavior, production behavior, public map behavior, WordPress behavior, scheduled workflow behavior, registry behavior, approval behavior, promotion behavior, publishing behavior, cache behavior, or XRI-G68 work.

## Stop Condition

Stop after creating only the two allowed XRI-G67 gate files.

Do not merge.

Do not start XRI-G68.
