# XRI-G27 Non-Production Manual Review Export Contract Gate Contract

Phase: XRI-G27

Source phase: XRI-G26
Source pull request: #36
Source merge commit SHA: 4555e453dce951b17b97dcd5ec9ec92b86689eb3

## Purpose

Define a non-production manual review export contract gate for the XRI fixture/manual-review prototype path.

This gate defines contract/report-only export field expectations, non-production review boundaries, stable identity requirements, review_rank identity prohibition, review_rank ordering/display allowance, no production export behavior, no-write/no-import constraints, and fail-closed expectations only. It introduces no executable production behavior.

## Allowed files

* docs/xri-g27-non-production-manual-review-export-contract-gate-contract.md
* data/reports/xri_g27_non_production_manual_review_export_contract_gate_report.json

No optional fixture file is required for this gate.

## Export contract boundaries

The export contract gate must enforce:

* contract-only / report-only
* non-production only
* no production export behavior
* no production registry database writes
* no registry imports
* no public runtime output
* no public map output
* no WordPress output
* no scheduled workflow changes
* no geocoding
* no approval
* no promotion
* no publishing
* no data/location_cache.json access
* no executable production behavior

## Stable identity basis

Stable identity remains based only on:

* group_key
* display_location
* candidate_identity

## Forbidden identity basis

The following field must never be used as identity:

* review_rank

## Allowed ordering/display field

The following field may appear only as ordering or display metadata:

* review_rank

## Required manual-review export contract fields

The export contract must declare these fields:

* group_key
* display_location
* candidate_identity
* review_status
* review_reason
* review_notes
* review_rank
* source_phase
* export_mode
* production_artifact

## Required field constraints

The export contract must enforce:

* group_key must be present
* display_location must be present
* candidate_identity must be present
* review_status must be present
* review_reason must be present
* export_mode must be non_production_manual_review_export_contract
* production_artifact must be false
* review_rank must not be used as identity

## Required export-contract pass cases

The export contract gate must define pass coverage for:

* source XRI-G26 review summary gate identified
* source XRI-G26 merge SHA recorded
* export contract boundaries summarized
* required fields declared
* stable identity basis summarized
* review_rank identity prohibition summarized
* review_rank ordering/display use summarized
* no production export behavior confirmed
* no-write/no-import confirmation summarized
* fail-closed expectations summarized

## Required export-contract fail-closed cases

The export contract gate must fail closed for:

* missing source phase
* missing source pull request
* missing source merge commit SHA
* missing export contract boundary summary
* missing required export field
* missing group_key
* missing display_location
* missing candidate_identity
* missing review_status
* missing review_reason
* review_rank used as identity
* identity drift
* export_mode not non-production
* production_artifact true
* attempted production export behavior
* attempted registry write target
* attempted registry import target
* attempted geocode target
* attempted approval state
* attempted promotion state
* attempted publishing state
* attempted public map target
* attempted WordPress target
* attempted scheduled workflow target
* attempted location_cache access
* attempted executable production behavior

## Output rule

Manual review export contract output is contract-only/report-only, non-production only, and not a production artifact.

## Hard prohibitions

No production feeds, public map runtime, WordPress, nycinfocus.com/map, iframe/embed settings, scheduled workflows, data/location_cache.json, live staging, SODA/live fetch, geocoding, candidate approval, candidate promotion, production registry database/importer, production export behavior, registry writes, registry imports, runtime publishing behavior, production runtime input, public output, WordPress output, executable production behavior, production validator execution, production validator wiring, production fixture wiring, publishing, or XRI-G28 start.

## Review gate

Open a pull request only. Do not merge. Do not start XRI-G28.
