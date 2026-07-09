# XRI-G97 Current-Worktree Fixture-Only Validation Execution Authorization Gate

Status: documentation gate only
Baseline commit: dba31c1
Prior gate: XRI-G96 current-worktree isolated local path readiness recapture results

## Purpose

Record the authorization boundary for a later current-worktree fixture-only validation execution attempt.

G97 makes no repository behavior changes.

## Readiness basis

XRI-G96 confirmed current-worktree isolated local path readiness:

```text
venv_path: tmp/xri-g96/venv
venv_python_executable: /Users/howardweiss/GitHub/nycif-live-feeds/tmp/xri-g96/venv/bin/python
venv_python_executable_check: 0
venv_pytest_version: pytest 9.1.1
```

## Authorized later command identity

A later gate may run the exact fixture-only validation command below and capture stdout, stderr, and exit code:

```text
tmp/xri-g96/venv/bin/python -m pytest tests/registry/test_xri_g42_fixture_only_validation_execution.py
```

## Capture requirements for later gate

The later execution result capture gate must capture:

- branch,
- head commit,
- upstream,
- status before,
- exact command identity,
- stdout,
- stderr,
- exit code,
- status after.

## Not authorized in G97

G97 does not authorize or perform:

- fixture validation execution in G97,
- pytest test execution in G97,
- live-source access,
- dry-run against live sources,
- production writes,
- dependency file edits,
- script edits,
- tool edits,
- test edits,
- workflow edits,
- cache changes,
- generated artifact changes,
- runtime feed changes,
- data/location_cache.json changes,
- WordPress actions,
- registry writes/imports.

## Next safe gate

```text
XRI-G98 — current-worktree fixture-only validation execution result capture
```

G98 may run only the exact fixture-only command authorized above and must capture the result without changing repository behavior.

## Safety confirmations

- Documentation/report only.
- Starts from XRI-G96 merge commit dba31c1.
- Authorization boundary only.
- No validation execution in G97.
- No pytest test run in G97.
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
