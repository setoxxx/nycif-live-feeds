# XRI-G23 Prototype Fixture Manual-Review Sample Set Gate Contract

Phase: XRI-G23

Source phase: XRI-G22
Source pull request: #32
Source merge commit SHA: da84fd4796cd4243034bb2f9ea8dd36e24576163

## Completion map

* Completed and merged: XRI-G10 through XRI-G22: 100%.
* Current next phase: XRI-G23.
* Safe non-production registry/manual-review prototype: about 90% complete.
* Full production public-map/registry use: about 60-65% complete.

## Purpose

Define a fixture-only and test-only manual-review sample set for prototype validation.

## Files

* docs/xri-g23-prototype-fixture-manual-review-sample-set-gate-contract.md
* data/reports/xri_g23_prototype_fixture_manual_review_sample_set_gate_report.json
* data/fixtures/xri-g23-prototype-fixture-manual-review-sample-set.sample.json

## Fixture requirements

The sample file must separate valid_samples and invalid_samples.

Each sample must include fixture_case_id and expected_result.

Invalid samples must include expected_fail_reasons.

Valid samples must include:

* group_key
* display_location
* candidate_identity
* all required blocking fields set to true
* one allowed reviewer decision

Allowed decisions:

* hold
* reject
* needs_more_context
* eligible_for_future_review

Forbidden decisions:

* approved
* geocoded
* promoted
* published

Required blocking fields:

* production_blocked
* geocode_blocked
* promotion_blocked
* publishing_blocked
* registry_import_blocked

review_rank may appear only as an ordering field and must not be identity.

The sample set covers valid decisions and failure cases for missing identity, source, audit, decision, blocking, coordinate, runtime target, and publishing-state rules.

## Hard prohibitions

No production feeds, public map runtime, WordPress, nycinfocus.com/map, iframe/embed settings, scheduled workflows, data/location_cache.json, live staging, SODA/live fetch, geocoding, candidate approval, candidate promotion, production registry database/importer, runtime publishing behavior, production runtime input, public output, production validator execution, production validator wiring, production fixture wiring, publishing, or XRI-G24 start.

## Review gate

Open a pull request only. Do not merge. Do not start XRI-G24.
