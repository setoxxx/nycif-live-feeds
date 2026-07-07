# XRI-G82 Exact Fixture-Only Validation Execution Authorization Gate

Status: gate-only / exact-command authorization
Baseline commit: 5863ebf
Baseline source: Merge pull request #94 from setoxxx/xri-g81-inventory-review-fixture-validation-command-candidate-gate
Prior gate: XRI-G81 inventory review and fixture-only validation command candidate gate

## Purpose

This gate authorizes one exact fixture-only validation command for a later execution step.

G82 itself does not execute validation. It does not run pytest. It does not authorize live fetch, dry-run execution, generated artifact changes outside the later execution report, cache changes, public map/runtime changes, or production writes.

## Evidence basis

XRI-G80 captured the local read-only repository inventory and found:

- fixture-like paths under `data/fixtures`,
- test-like paths under `tests/registry`,
- five fixture-only registry test files,
- no manifest-like dependency file paths,
- workflow paths under `.github/workflows`,
- script/tool-like paths under `scripts`, `tests`, and `tools`.

XRI-G81 reviewed the inventory and identified command candidates without execution.

The selected primary command targets only the exact fixture-only validation execution test file:

- `tests/registry/test_xri_g42_fixture_only_validation_execution.py`

The reviewed implementation target is:

- `tools/registry/xri_g42_fixture_only_validation_execution.py`

## Authorized exact command

Only the following command is authorized for the next execution phase:

```bash
python3 -m pytest tests/registry/test_xri_g42_fixture_only_validation_execution.py
```

No other pytest target, script, workflow, live fetch, dry-run command, or production command is authorized by G82.

## Execution boundary for later phase

A later phase may execute only the exact command above and may capture only:

- command executed,
- exit code,
- stdout/stderr summary,
- PASS/FAIL result,
- environment note such as Python/pytest availability,
- documentation/report-only result artifacts.

The later execution phase must not modify:

- `data/location_cache.json`,
- generated map/runtime feed files,
- source adapter code,
- scripts,
- tools,
- tests,
- workflows,
- production artifacts,
- public map/runtime files.

If the command fails because pytest or dependencies are missing, the later phase must stop and report failure without installing packages, modifying dependencies, changing code, or broadening the command.

## Explicit non-authorizations

This gate does not authorize:

- executing the command inside G82,
- any command other than the exact authorized command,
- fixture validation beyond the exact G42 test file,
- live fetch,
- dry-run execution against live sources,
- artifact-diff review against generated production artifacts,
- cache-touch work,
- data/location_cache.json changes,
- generated artifact changes except a later documentation/report-only execution result if separately gated,
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
- G82 starts from XRI-G81 merge commit 5863ebf.
- Exact fixture-only validation execution authorization gate only.
- One exact command selected.
- Command not executed in G82.
- No fixture validation performed in G82.
- No validation command executed in G82.
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

After XRI-G82 is reviewed and merged, the next XRI phase may execute only this exact command:

```bash
python3 -m pytest tests/registry/test_xri_g42_fixture_only_validation_execution.py
```

The next phase must cite the XRI-G82 merge commit as its starting baseline, must capture the result in documentation/report-only artifacts, and must stop on any dependency/environment failure without changing code or dependencies.
