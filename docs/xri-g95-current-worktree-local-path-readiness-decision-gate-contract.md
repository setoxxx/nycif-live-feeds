# XRI-G95 Current-Worktree Local Path Readiness Decision Gate

Status: documentation gate only
Baseline commit: 00dd804
Prior gate: XRI-G94 local path audit status

## Purpose

Record the decision after G94 showed the expected local path was unavailable in the current worktree.

G95 makes no repository behavior changes.

## Finding from G94

G94 did not produce a fixture assertion result. The local path needed for the fixture-only command was unavailable in the current worktree.

This is classified as a current-worktree local path readiness issue.

## Decision

The next safe path is a current-worktree local readiness recapture gate.

That gate may verify or recreate only the local temporary interpreter path under tmp for this worktree and may capture path availability output.

It must not run the fixture validation command.

## Not authorized in G95

G95 does not authorize or perform:

- fixture validation execution,
- pytest test execution,
- live-source access,
- production writes,
- dependency file edits,
- script edits,
- tool edits,
- test edits,
- workflow edits,
- cache changes,
- generated artifact changes,
- runtime feed changes,
- data/location_cache.json changes.

## Next safe gate

```text
XRI-G96 — current-worktree isolated local path readiness recapture gate
```

G96 may capture current-worktree local path readiness only. G96 must not run fixture validation.

## Safety confirmations

- Documentation/report only.
- Starts from XRI-G94 merge commit 00dd804.
- Decision boundary only.
- No validation execution in G95.
- No pytest test run in G95.
- No dependency file changes.
- No generated data artifacts modified.
- No data/location_cache.json modification.
- No scripts modified.
- No workflows modified.
- No tools modified.
- No tests modified.
- No public map runtime files modified.
- No live fetch performed.
- No dry-run against live sources performed.
- No NYC Open Data/SODA/API call performed.
- No scraping performed.
- No geocoding performed.
- No WordPress action performed.
- No registry write/import performed.
- No production write performed.
