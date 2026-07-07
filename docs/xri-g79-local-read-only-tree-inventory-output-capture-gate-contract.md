# XRI-G79 Local Read-Only Tree Inventory Output Capture Gate

Status: gate-only
Baseline commit: a57c343
Baseline source: Merge pull request #91 from setoxxx/xri-g78-read-only-repository-tree-inventory-results-gate
Prior gate: XRI-G78 read-only repository tree inventory results gate

## Purpose

This gate authorizes Howard-side local read-only repository tree inventory output capture after XRI-G78 could not complete the inventory from the assistant environment.

G79 does not authorize validation execution. It does not authorize live fetch, dry-run execution, generated artifact changes, cache changes, public map/runtime changes, or production writes.

## Authorized local read-only commands

Howard may run read-only commands in a clean local checkout at the G79 baseline or later branch based on it.

Allowed command classes:

- git status --short
- git rev-parse HEAD
- git ls-tree -r --name-only HEAD
- find . -type f with safe exclusions for .git and dependency/vendor folders
- grep or equivalent text search over committed text files
- reading package, dependency, workflow, script, test, and fixture filenames/content if present
- redirecting command output to documentation/report-only artifacts

## Required local inventory output

The local inventory must capture:

- exact HEAD commit inspected,
- exact commands run,
- total committed file count if available,
- top-level directory inventory,
- fixture-like paths, if any,
- test-like paths, if any,
- package/dependency manifest paths, if any,
- workflow paths, if any,
- script/tool paths, if any,
- validation-related text matches, if any,
- conclusion on whether an exact fixture-only validation command can be proposed later.

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
- G79 starts from XRI-G78 merge commit a57c343.
- Local read-only tree inventory output capture gate only.
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

After XRI-G79 is reviewed and merged, the next XRI phase may capture the local read-only inventory output in documentation/report-only artifacts. It must cite the XRI-G79 merge commit as its starting baseline and must not run validation unless a later gate authorizes an exact fixture-only command based on proven file paths and command evidence.
