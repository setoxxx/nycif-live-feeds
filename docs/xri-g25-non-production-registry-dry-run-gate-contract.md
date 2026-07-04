# XRI-G25 Non-Production Registry Dry-Run Gate Contract

Phase: XRI-G25

Source phase: XRI-G24
Source pull request: #34
Source merge commit SHA: c36ce7dc5163c26186b64a294097809fc8c69c37

## Purpose

Define a non-production registry dry-run gate for the XRI fixture/manual-review prototype path.

This gate verifies report-only dry-run expectations for candidate registry eligibility without writing to a registry, importing records, geocoding, approving, promoting, publishing, or touching public/runtime systems.

## Allowed files

* docs/xri-g25-non-production-registry-dry-run-gate-contract.md
* data/reports/xri_g25_non_production_registry_dry_run_gate_report.json

No optional fixture file is required for this gate.

## Dry-run boundaries

The dry-run gate must enforce:

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

## Stable identity basis

Stable identity remains based only on:

* group_key
* display_location
* candidate_identity

## Forbidden identity basis

The following field must never be used as identity:

* review_rank

review_rank may appear only as ordering or display metadata.

## Required dry-run pass cases

The dry-run gate must define pass coverage for:

* valid stable identity present
* dry-run report-only candidate evaluation
* stable identity preserved despite review_rank change
* no-write/no-import dry-run result

## Required dry-run fail-closed cases

The dry-run gate must fail closed for:

* missing group_key
* missing display_location
* missing candidate_identity
* review_rank used as identity
* identity drift
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

## Output rule

Dry-run report output is report-only, non-production only, and not a production artifact.

## Hard prohibitions

No production feeds, public map runtime, WordPress, nycinfocus.com/map, iframe/embed settings, scheduled workflows, data/location_cache.json, live staging, SODA/live fetch, geocoding, candidate approval, candidate promotion, production registry database/importer, registry writes, registry imports, runtime publishing behavior, production runtime input, public output, WordPress output, production validator execution, production validator wiring, production fixture wiring, publishing, or XRI-G26 start.

## Review gate

Open a pull request only. Do not merge. Do not start XRI-G26.
