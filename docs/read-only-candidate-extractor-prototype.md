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

Safety boundaries:

- sample-only and dry-run by default
- no live fetches
- no geocoding
- no production feed writes
- no public map runtime changes
- no location cache changes
- no candidate approval or promotion
- no XRI-G12 work

Review gate:

Open a PR and stop. Do not merge until Howard and ChatGPT review the changed files and safety report.
