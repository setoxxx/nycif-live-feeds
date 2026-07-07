# XRI-G72 Review-Only Evidence Requirements Gate

Status: gate-only
Baseline commit: 2867401
Baseline source: Merge pull request #84 from setoxxx/xri-g71-post-g70-review-only-next-step-planning-gate
Selected XRI-G69 lane: Lane 1 - review-only planning

## Purpose

This gate defines the evidence requirements that must be satisfied before any later XRI gate may leave Lane 1 review-only planning and select a higher-risk XRI-G69 lane.

XRI-G72 does not authorize implementation, validation, artifact diffs, cache touches, dry runs, live fetch, runtime changes, or production writes.

## Authorized baseline

This gate starts from:

2867401 - Merge pull request #84 from setoxxx/xri-g71-post-g70-review-only-next-step-planning-gate

Future XRI planning after G72 must start from the eventual XRI-G72 merge commit.

## Lane constraint

XRI-G72 remains inside:

Lane 1 - review-only planning

This gate only defines evidence requirements. It does not select a higher-risk lane.

## Evidence required before leaving Lane 1

Before any later gate may select a higher-risk lane, that future gate must include review evidence for all applicable categories below.

### 1. Stable baseline confirmation

Required evidence:

- Current main commit.
- Prior phase merge commit.
- Branch start commit.
- Confirmation that local main and origin/main match before branch creation.
- Confirmation that the working tree was clean before branch creation.

### 2. Exact lane selection

Required evidence:

- The selected XRI-G69 lane number.
- The selected lane name.
- The reason for selecting that lane.
- Explicit statement that all other lanes remain unauthorized.

### 3. File-scope constraints

Required evidence:

- Exact files allowed to change.
- Exact files forbidden from changing.
- Expected changed-file count.
- Confirmation that changed files match the authorized scope before commit and before merge.

### 4. Generated-artifact exclusion or authorization

Required evidence:

- Whether generated artifacts are excluded or authorized.
- If excluded, confirmation that no generated artifact paths changed.
- If authorized, exact generated artifact paths and rollback expectations.

### 5. data/location_cache.json exclusion or authorization

Required evidence:

- Whether data/location_cache.json is excluded or authorized.
- If excluded, confirmation that it did not change.
- If authorized, exact reason, expected diff class, and rollback expectations.

### 6. Script/tool/test/workflow/runtime exclusion or authorization

Required evidence:

- Whether scripts are excluded or authorized.
- Whether tools are excluded or authorized.
- Whether tests are excluded or authorized.
- Whether workflows are excluded or authorized.
- Whether runtime files are excluded or authorized.
- If any are authorized, exact paths and purpose must be listed.

### 7. Command authorization boundaries

Required evidence:

- Commands allowed.
- Commands forbidden.
- Confirmation that no forbidden command was run.
- Confirmation that no workflow was manually triggered unless explicitly authorized.

### 8. Live-fetch exclusion or authorization

Required evidence:

- Whether live fetch remains excluded or is authorized.
- If excluded, confirmation that no live network call was made.
- If authorized, exact source, endpoint family, dry-run boundary, and output handling.

### 9. Dry-run exclusion or authorization

Required evidence:

- Whether dry-run execution remains excluded or is authorized.
- If excluded, confirmation that no dry run occurred.
- If authorized, exact command, fixture/live boundary, and output file handling.

### 10. Production-write exclusion or authorization

Required evidence:

- Whether production writes remain excluded or are authorized.
- Confirmation regarding public map writes.
- Confirmation regarding WordPress writes.
- Confirmation regarding registry writes/imports.
- Confirmation regarding scheduled workflows and generated-artifact auto-commit behavior.

### 11. Rollback expectations

Required evidence:

- Expected rollback method.
- Files that would need rollback if the gate fails.
- Confirmation that no irreversible production action is included.

### 12. Review evidence required before merge

Required evidence:

- Pre-commit status output.
- Post-commit status output.
- PR changed-file list.
- PR commit count.
- PR base and head SHAs.
- Explicit merge approval phrase from Howard.
- Post-merge sync verification.

## Lane 1 permissions retained

XRI-G72 may authorize only:

- Documentation.
- Reports.
- Evidence requirements.
- Scope definitions.
- Future-gate review criteria.
- Review-only planning language.

XRI-G72 may not authorize:

- Scripts.
- Tools.
- Tests.
- Workflows.
- Runtime changes.
- Generated artifact changes.
- Cache changes.
- Fixture validation.
- Artifact-diff review.
- Dry-run execution.
- Live network calls.
- Production writes.

## Explicit non-authorizations

This gate does not authorize:

- Live fetch.
- Dry-run execution.
- Fixture validation.
- Artifact-diff review.
- Cache-touch work.
- NYC Open Data/SODA/API calls.
- Scraping.
- Geocoding.
- WordPress actions.
- Production writes.
- Public map runtime changes.
- Workflow changes.
- Script/tool/test changes.
- Generated artifact changes.
- data/location_cache.json changes.
- Scheduled workflow enablement.
- Generated artifact auto-commit behavior.

## Safety confirmations

- Documentation/report only.
- Remains inside XRI-G69 Lane 1 selected by XRI-G70 and retained by XRI-G71.
- No generated data artifacts modified.
- No data/location_cache.json modification.
- No scripts modified.
- No workflows modified.
- No tools modified.
- No tests modified.
- No public map runtime files modified.
- No fixture validation performed.
- No artifact-diff review performed.
- No live fetch performed.
- No dry-run execution performed.
- No NYC Open Data/SODA/API call performed.
- No scraping performed.
- No geocoding performed.
- No WordPress action performed.
- No production write performed.
- No scheduled workflow enabled.
- No generated artifact auto-commit enabled.

## Next phase rule

After XRI-G72 is reviewed and merged, the next XRI phase must cite the XRI-G72 merge commit as its starting baseline.

Any future phase that seeks to leave Lane 1 must satisfy the evidence requirements documented in this gate and must explicitly select the higher-risk XRI-G69 lane being entered.
