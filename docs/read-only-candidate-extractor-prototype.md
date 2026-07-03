# XRI-G4 Read-Only Candidate Extractor Prototype

Phase: XRI-G4
Mode: read-only prototype
Production allowed: false

This document describes a sample-only candidate extractor prototype for NYCIF location-registry planning.

The prototype is designed to shape sample rows into candidate records for review. It is not a registry database, importer, live source pull, public map integration, or production publishing step.

Allowed files for this phase:

- docs/read-only-candidate-extractor-prototype.md
- tools/registry/registry_candidate_extractor_prototype.py
- data/reports/registry_candidate_extractor_prototype_report.json
- data/fixtures/registry-candidate-extractor.sample.json

Allowed inputs:

- embedded sample rows
- data/fixtures/registry-candidate-extractor.sample.json

Blocked inputs:

- data/location_cache.json
- production feed artifacts
- public map files
- workflow files
- arbitrary local JSON paths

Safety boundaries:

- sample-only and dry-run by default
- no live fetches
- no geocoding
- no production feed writes
- no public map runtime changes
- no location cache reads or writes
- no candidate approval or promotion
- no XRI-G12 work

Self-check:

```bash
python tools/registry/registry_candidate_extractor_prototype.py --self-check
```

The self-check must confirm blocked input paths are rejected and the only allowed output is the prototype report.

Review gate:

Open a PR and stop. Do not merge until Howard and ChatGPT review the changed files and safety report.
