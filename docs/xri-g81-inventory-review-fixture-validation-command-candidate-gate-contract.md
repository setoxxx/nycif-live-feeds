# XRI-G81 Inventory Review and Fixture-Only Validation Command Candidate Gate

Status: gate-only / candidate-only
Baseline commit: fd9d2de
Baseline source: Merge pull request #93 from setoxxx/xri-g80-local-read-only-tree-inventory-capture
Prior gate: XRI-G80 local read-only tree inventory capture

## Purpose

This gate reviews the XRI-G80 local read-only inventory and identifies exact fixture-only validation command candidates for a later authorization gate.

G81 does not authorize validation execution. It does not authorize live fetch, dry-run execution, generated artifact changes, cache changes, public map/runtime changes, or production writes.

## Evidence reviewed

XRI-G80 captured:

- 269 committed files.
- Top-level paths including `.github`, `data`, `docs`, `scripts`, `status`, `tests`, and `tools`.
- Fixture-like paths under `data/fixtures`.
- Test-like paths under `tests/registry`.
- No manifest-like dependency paths.
- Workflow-like paths under `.github/workflows`.
- Script/tool-like paths under `scripts`, `tests`, and `tools`.

G81 also reviewed the exact fixture-only validation execution test and implementation files:

- `tests/registry/test_xri_g42_fixture_only_validation_execution.py`
- `tools/registry/xri_g42_fixture_only_validation_execution.py`

The test imports only pytest plus local fixture-only parser/validation modules and builds an inline fixture payload.

The implementation validates stable identity fields, normalized shape, display-only review_rank handling, and deterministic fixture-only validation output.

## Primary candidate command

The primary candidate command is:

```bash
python3 -m pytest tests/registry/test_xri_g42_fixture_only_validation_execution.py
```

## Secondary candidate command

A broader fixture-only registry test candidate is:

```bash
python3 -m pytest tests/registry/test_xri_g40_fixture_only_source_ingestion_scaffold.py tests/registry/test_xri_g41_fixture_only_parser_normalizer.py tests/registry/test_xri_g42_fixture_only_validation_execution.py tests/registry/test_xri_g43_fixture_only_manual_review_handoff.py tests/registry/test_xri_g44_fixture_only_audit_reporting.py
```

## Candidate limitation

G80 found no package/dependency manifest path. Because of that, G81 does not prove the local environment dependency state and does not authorize execution.

The candidate commands may be proposed to a later execution-authorization gate only after the later gate explicitly accepts:

- exact baseline commit,
- exact command,
- allowed output artifacts,
- failure handling,
- forbidden files,
- and proof that the command is fixture-only and non-production.

## Decision

G81 identifies exact command candidates only.

G81 blocks all validation execution.

The next safe gate is an exact fixture-only validation execution authorization gate. That later gate may authorize only one exact command and must keep all generated outputs documentation/report-only unless separately authorized.

## Still forbidden

This gate does not authorize:

- fixture validation execution,
- live fetch,
- dry-run execution against live sources,
- artifact-diff review against generated production artifacts,
- cache-touch work,
- data/location_cache.json changes,
- generated artifact changes,
- workflow changes,
- script/tool/test implementation changes,
- public map runtime changes,
- NYC Open Data/SODA/API calls,
- scraping,
- geocoding,
- WordPress actions,
- registry writes/imports,
- production writes,
- scheduled workflow enablement,
- generated artifact auto-commit behavior.

## Safety confirmations

- Documentation/report only.
- G81 starts from XRI-G80 merge commit fd9d2de.
- Inventory review and command candidate gate only.
- Candidate commands identified but not executed.
- No fixture validation performed.
- No validation command executed.
- No generated data artifacts modified.
- No data/location_cache.json modification.
- No scripts modified.
- No workflows modified.
- No tools modified.
- No tests modified.
- No public map runtime files modified.
- No live fetch performed.
- No dry-run execution performed.
- No NYC Open Data/SODA/API call performed.
- No scraping performed.
- No geocoding performed.
- No WordPress action performed.
- No registry write/import performed.
- No production write performed.

## Next phase rule

After XRI-G81 is reviewed and merged, the next XRI phase may be an exact fixture-only validation execution authorization gate. It must cite the XRI-G81 merge commit as its starting baseline and must not execute validation unless that later gate explicitly authorizes one exact command.
