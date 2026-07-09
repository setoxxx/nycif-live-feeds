# XRI-G66 Non-Production Controlled Live-Fetch Dry-Run Manual Approval Handoff Gate

## Status

Documentation and report gate only.

## Source State

Completed and merged phases:

- XRI-G10 through XRI-G65

Immediate prior merged pull request:

- PR: #75
- Merge commit SHA: bb8ea40e448b0f58130522eae8b24c6c7b148ccb

## Purpose

XRI-G66 defines a non-production manual-approval-handoff gate for a later controlled live-fetch dry-run phase.

This gate only records requirements. It does not add application behavior, executable manual-approval-handoff behavior, source adapters, runtime behavior, production behavior, public map behavior, WordPress behavior, scheduled workflow behavior, registry behavior, approval behavior, promotion behavior, publishing behavior, or cache behavior.

## Allowed Files

Exactly two files are allowed for this phase:

- docs/xri-g66-non-production-controlled-live-fetch-dry-run-manual-approval-handoff-gate.md
- data/reports/xri_g66_non_production_controlled_live_fetch_dry_run_manual_approval_handoff_gate_report.json

## Manual Approval Handoff Requirements For A Later Phase

A later phase must verify all of the following before any controlled dry-run manual approval handoff is allowed:

- source identity summary is present
- execution authorization summary is present
- source-call contract summary is present
- source-call limit summary is present
- input boundary summary is present
- output boundary summary is present
- artifact-isolation summary is present
- audit-manifest summary is present
- review-package summary is present
- validation status summary is present
- failure-stop status summary is present
- stable identity summary is present
- forbidden identity anchor rejection summary is present
- dry-run-only declaration is present
- no-write declaration is present
- human-review-only declaration is present
- no-approval-action declaration is present
- no-promotion-action declaration is present
- no-publishing-action declaration is present
- registry paths are not used
- production paths are not used
- public map paths are not used
- WordPress paths are not used
- scheduled workflow paths are not used
- data/location_cache.json is not used
- handoff cannot become public map runtime input
- handoff cannot become production export input
- handoff cannot become registry import input

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

The companion report must confirm that this phase added only documentation/report artifacts and did not add implementation code, manual-approval-handoff code, source adapters, runtime behavior, production behavior, public map behavior, WordPress behavior, scheduled workflow behavior, registry behavior, approval behavior, promotion behavior, publishing behavior, cache behavior, or XRI-G67 work.

## Stop Condition

Stop after creating only the two allowed XRI-G66 gate files.

Do not merge.

Do not start XRI-G67.
