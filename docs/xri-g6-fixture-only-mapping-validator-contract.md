# XRI-G6 Fixture-Only Mapping Validator Contract

Phase: XRI-G6
Mode: fixture-only validator contract/prototype
Production allowed: false

This contract defines a fixture-only validator for checking sample mapping records against the XRI-G5 source field mapping contract. It is a planning/prototype gate only. It does not fetch live data, geocode, stage, approve, promote, publish, create a registry database/importer, or touch production systems.

## Allowed files

- `docs/xri-g6-fixture-only-mapping-validator-contract.md`
- `tools/registry/xri_g6_fixture_mapping_validator.py`
- `data/reports/xri_g6_fixture_mapping_validator_report.json`
- `data/fixtures/xri-g6-mapping-validator.sample.json`

## Hard boundary

XRI-G6 validates only embedded or approved sample fixture records. It must not read production feeds, public map runtime, WordPress files, workflow files, or `data/location_cache.json`.

XRI-G6 must not:

- modify production feeds
- modify public map runtime
- modify WordPress
- modify `nycinfocus.com/map`
- modify iframe/embed settings
- modify scheduled workflows
- modify or read `data/location_cache.json`
- run live staging
- fetch SODA/live data
- geocode
- approve candidates
- promote candidates to production
- create a registry database/importer
- start XRI-G12

## Validator requirements

The validator must check:

- required fields per source
- optional fields are recognized
- ambiguity flags are recognized
- `production_allowed` remains false
- supporting-reference-only sources are validated:
  - `cpcm-i88g`
  - `xtsw-fqvh`
- Parks relationship remains contract-only
- no live Parks joiner is created
- prohibited input paths fail closed
- prohibited output paths fail closed

## MVP source coverage

The validator contract covers these XRI-G5 MVP sources:

- `tvpp-9vvx` — NYC Permitted Event Information
- `fudw-fgrp` — Parks Event Listing
- `cpcm-i88g` — Parks Event Locations
- `xtsw-fqvh` — Parks Event Categories
- `6v4b-5gp4` — Public Programs Division Special Events
- `3vyj-dkjt` — Safety Events

## Supporting-reference-only rule

`cpcm-i88g` and `xtsw-fqvh` are supporting-reference-only sources. A valid sample must verify that these sources can be checked against required reference fields without treating them as public event candidates, without requiring event time, and without creating a live joiner.

## Parks relationship rule

Parks remains a future enriched Parks Events layer only:

- `fudw-fgrp` is the primary event listing source
- `cpcm-i88g` is the location reference source
- `xtsw-fqvh` is the category reference source
- `live_joiner_created` must remain false

## Fail-closed paths

Allowed input:

- `data/fixtures/xri-g6-mapping-validator.sample.json`
- embedded sample data when the fixture is absent

Allowed output:

- `data/reports/xri_g6_fixture_mapping_validator_report.json` only when `--write-report` is explicitly used

Blocked examples:

- `data/location_cache.json`
- production feed paths
- public map paths
- WordPress paths
- workflow paths
- arbitrary local JSON paths

## Runtime command

```bash
python tools/registry/xri_g6_fixture_mapping_validator.py --pretty
```

Optional report write command:

```bash
python tools/registry/xri_g6_fixture_mapping_validator.py --write-report --pretty
```

## Next recommended phase gate

XRI-G7 can define fixture-only candidate normalization rules. It must remain sample-only/read-only unless separately approved. It must not fetch live source data, geocode, write production feeds, modify public map runtime, or touch `data/location_cache.json`.
