# XRI-G96 Current-Worktree Isolated Local Path Readiness Recapture Gate

Status: documentation gate only
Baseline commit: cb85991
Prior gate: XRI-G95 current-worktree local path readiness decision gate

## Purpose

Authorize a later local-only readiness recapture in the current worktree after G94 showed that the expected temporary local path was unavailable.

G96 makes no repository behavior changes.

## Authorization decision

G96 authorizes the next gate to verify or recreate only the current-worktree temporary local interpreter path under `tmp/` and capture readiness outputs.

The next gate must not run fixture validation.

## Allowed next-gate capture scope

The next gate may capture:

- current branch,
- current head,
- upstream branch,
- status before,
- system Python version,
- system Python path,
- local temporary environment creation output,
- local interpreter path,
- local pytest availability,
- status after.

## Not authorized in G96

G96 does not authorize or perform:

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
XRI-G97 — current-worktree isolated local path readiness recapture results
```

G97 may capture current-worktree local readiness outputs only. G97 must not run fixture validation.

## Safety confirmations

- Documentation/report only.
- Starts from XRI-G95 merge commit cb85991.
- Readiness recapture authorization boundary only.
- No validation execution in G96.
- No pytest test run in G96.
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
