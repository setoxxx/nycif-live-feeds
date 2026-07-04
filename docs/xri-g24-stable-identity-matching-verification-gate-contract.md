# XRI-G24 Stable Identity Matching Verification Gate Contract

Phase: XRI-G24

Source phase: XRI-G23
Source pull request: #33
Source merge commit SHA: 95dad9df671b3377b8b6dd8d74a739e01c8ea199

## Purpose

Define a non-production stable identity matching verification gate for the XRI fixture/manual-review prototype path.

This gate verifies identity rules only. It does not implement production registry behavior, production importer behavior, public runtime behavior, geocoding, promotion, approval, or publishing.

## Allowed files

* docs/xri-g24-stable-identity-matching-verification-gate-contract.md
* data/reports/xri_g24_stable_identity_matching_verification_gate_report.json

No optional fixture file is required for this gate.

## Stable identity basis

Stable identity must be based only on:

* group_key
* display_location
* candidate_identity

## Forbidden identity basis

The following field must never be used as identity:

* review_rank

review_rank may appear only as ordering or display metadata. It must not be used to match, reconcile, approve, promote, publish, or otherwise identify a candidate.

## Required fail-closed identity cases

Identity verification must fail closed for:

* missing group_key
* missing display_location
* missing candidate_identity
* review_rank used as identity
* identity drift between expected and observed group_key
* identity drift between expected and observed display_location
* identity drift between expected and observed candidate_identity
* unstable identity where display text changes but review_rank remains the same
* unstable identity where review_rank changes but stable identity remains the same

## Required verification behavior

* Valid XRI-G23 fixture samples remain valid only when group_key, display_location, and candidate_identity are intact.
* Invalid XRI-G23 fixture samples remain invalid when identity fields are missing, unstable, or replaced by review_rank.
* Stable identity matching must not fall back to review_rank.
* Identity drift must be treated as a blocking failure.
* Missing stable identity fields must be treated as blocking failures.
* A changed review_rank alone must not create identity drift when stable identity fields remain unchanged.
* A matching review_rank alone must not preserve identity when stable identity fields drift.

## Hard prohibitions

No production feeds, public map runtime, WordPress, nycinfocus.com/map, iframe/embed settings, scheduled workflows, data/location_cache.json, live staging, SODA/live fetch, geocoding, candidate approval, candidate promotion, production registry database/importer, runtime publishing behavior, production runtime input, public output, production validator execution, production validator wiring, production fixture wiring, publishing, or XRI-G25 start.

## Review gate

Open a pull request only. Do not merge. Do not start XRI-G25.
