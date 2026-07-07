# XRI-G77 Read-Only Repository Tree Inventory Gate

Status: gate-only
Baseline commit: 9957806
Baseline source: Merge pull request #89 from setoxxx/xri-g76-fixture-inventory-results-gate
Prior gate: XRI-G76 fixture inventory results gate

## Purpose

This gate authorizes a fuller read-only repository tree inventory after XRI-G76 failed to prove exact fixture paths or exact validation commands through GitHub search.

G77 does not authorize validation execution. It does not authorize live fetch, dry-run execution, generated artifact changes, cache changes, public map/runtime changes, or production writes.

## Authorized inventory activity

A future XRI phase may perform read-only repository tree inventory using commands that only list committed files and search committed text.

Allowed command classes include:

- git ls-tree against a fixed commit,
- find or equivalent file listing inside a clean local checkout,
- grep or equivalent text search over committed files,
- reading package or dependency manifests if present,
- reading test or fixture file names if present,
- recording results in a documentation/report artifact only.

## Required inventory questions

The future tree inventory must answer:

- What committed files exist at the authorized baseline?
- Are there any fixture directories or fixture-like files?
- Are there any test directories or test-like files?
- Are there any package manifests or dependency manifests?
- Are there any scripts, tools, or workflows that contain existing validation commands?
- Is any exact command safe to propose as fixture-only later?
- Which files must remain forbidden for execution or modification?

## Required output

The future inventory result must document:

- exact baseline commit inspected,
- exact read-only commands used,
- exact fixture paths found, if any,
- exact test paths found, if any,
- exact validation command candidates found, if any,
- exact package or dependency manifests found, if any,
- conclusion on whether a future fixture-only validation command can be proposed,
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
- G77 starts from XRI-G76 merge commit 9957806.
- Read-only repository tree inventory gate only.
- No repository tree inventory executed in this gate.
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

After XRI-G77 is reviewed and merged, the next XRI phase may perform the read-only repository tree inventory. It must cite the XRI-G77 merge commit as its starting baseline and must not run validation unless a later gate authorizes an exact fixture-only command based on proven file paths and command evidence.
