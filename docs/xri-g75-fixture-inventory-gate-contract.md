# XRI-G75 Fixture Inventory Gate

Status: gate-only
Baseline commit: 67fd192
Baseline source: Merge pull request #87 from setoxxx/xri-g74-fixture-only-validation-scope-command-gate
Prior gate: XRI-G74 fixture-only validation scope and command gate

## Purpose

This gate authorizes fixture inventory only.

XRI-G75 is intended to identify committed fixture paths and existing validation commands before any fixture-only validation execution is allowed.

## Authorized inventory scope

A future inventory step may inspect the repository to identify:

- committed fixture files,
- committed test files,
- existing validation commands,
- package or dependency manifests,
- read-only command candidates,
- and paths that must remain forbidden.

## Authorized command class

Only read-only repository inspection commands may be used in the future inventory step, such as listing files and searching filenames or committed text.

No validation command may be executed under this gate.

## Inventory outputs required

The future inventory result must document:

- exact fixture file paths found, if any,
- exact test or validation files found, if any,
- exact existing validation commands found, if any,
- whether any command is safe to run fixture-only,
- and whether another gate is required before execution.

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
- G75 starts from XRI-G74 merge commit 67fd192.
- Fixture inventory only.
- No fixture validation performed.
- No validation command executed.
- No validation command invented.
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

After XRI-G75 is reviewed and merged, the next XRI phase may perform fixture inventory only. It must cite the XRI-G75 merge commit as its starting baseline and must not run validation unless a later gate explicitly authorizes an exact fixture-only command based on inventory evidence.
