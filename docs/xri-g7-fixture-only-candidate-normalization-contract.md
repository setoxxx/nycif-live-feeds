# XRI-G7 Fixture-Only Candidate Normalization Contract

Phase: XRI-G7
Mode: fixture-only candidate normalization contract/prototype
Production allowed: false

XRI-G7 defines fixture-only rules for turning validated sample mapping records into blocked candidate-preview records.

## Allowed files

- `docs/xri-g7-fixture-only-candidate-normalization-contract.md`
- `tools/registry/xri_g7_fixture_candidate_normalizer.py`
- `data/reports/xri_g7_fixture_candidate_normalizer_report.json`
- `data/fixtures/xri-g7-candidate-normalizer.sample.json`

## Hard boundary

This phase is sample-only. It must not modify production feeds, public map runtime, WordPress, `nycinfocus.com/map`, iframe/embed settings, workflows, or `data/location_cache.json`. It must not run live staging, fetch SODA/live data, geocode, approve, promote, create a registry database/importer, or start XRI-G12.

## Required behavior

The normalizer must:

- normalize fixture/sample records only
- perform no network calls
- perform no SODA live fetch
- perform no geocoding API call
- perform no production writes
- set `production_allowed: false`
- keep preview records blocked with:
  - `approval_status: candidate_only`
  - `geocode_status: not_geocoded`
  - `promotion_status: blocked`
- generate deterministic `candidate_identity_key` from fixture fields only
- preserve source location text where present without geocoding
- allow missing source location text only with a location/context ambiguity flag
- preserve ambiguity flags
- keep `cpcm-i88g` and `xtsw-fqvh` as supporting-reference-only records, not public event candidates
- fail closed on prohibited input and output paths

## Preview fields

Preview records must include source identity, normalized title/reference text, source-owned key, source location text where present, ambiguity flags, blocked status fields, and a deterministic identity key. Preview records are not production records.

## Supporting reference rule

`cpcm-i88g` and `xtsw-fqvh` must remain:

- `preview_type: supporting_reference_only`
- `supporting_reference_only: true`
- `public_event_candidate: false`
- `production_allowed: false`
- `approval_status: candidate_only`
- `geocode_status: not_geocoded`
- `promotion_status: blocked`

## Identity rule

`candidate_identity_key` may use only fixture-safe fields: source dataset ID, source-owned key, title/reference text, event start when present, and source location/reference text. It must not use review rank, row order, display order, coordinates, geocoding, `data/location_cache.json`, or production feed state.

## Location text rule

Missing source location text is valid only when paired with one of these ambiguity flags: `location_missing`, `safety_event_context_required`, or `agency_program_location_uncertain`. These flags do not authorize geocoding, approval, promotion, or production publication.

## Fail-closed paths

Allowed input:

- `data/fixtures/xri-g7-candidate-normalizer.sample.json`
- embedded sample data when the fixture is absent

Allowed output:

- `data/reports/xri_g7_fixture_candidate_normalizer_report.json` only when `--write-report` is explicitly used

Blocked examples include `data/location_cache.json`, production feed paths, public map paths, WordPress paths, workflow paths, and arbitrary local JSON paths.

## Runtime command

```bash
python tools/registry/xri_g7_fixture_candidate_normalizer.py --pretty
```

## Next recommended phase gate

XRI-G8 can define fixture-only candidate preview review report formatting. It must remain sample-only/read-only unless separately approved.
