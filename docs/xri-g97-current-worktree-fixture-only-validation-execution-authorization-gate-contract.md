# XRI-G97 Current-Worktree Fixture-Only Validation Execution Authorization Gate

Status: documentation gate only
Baseline commit: dba31c1
Prior gate: XRI-G96 current-worktree isolated local path readiness recapture results

## Purpose

Record the authorization boundary for a later current-worktree fixture-only validation execution result capture.

G97 makes no repository behavior changes.

## G96 readiness basis

G96 restored current-worktree isolated local path readiness.

Captured readiness basis:

```text
venv_path: tmp/xri-g96/venv
venv_python_executable: /Users/howardweiss/GitHub/nycif-live-feeds/tmp/xri-g96/venv/bin/python
venv_pytest_version: pytest 9.1.1
venv_python_executable_check: 0
```

## Authorization decision

A later gate may attempt the fixture-only validation command using the G96 current-worktree interpreter path.

G97 itself does not run validation.

The later gate must capture:

```text
stdout
stderr
exit_code
status_before
status_after
```

## Authorized later command identity

```text
python_executable: tmp/xri-g96/venv/bin/python
module: pytest
target: tests/registry/test_xri_g42_fixture_only_validation_execution.py
```

## Not authorized in G97

G97 does not authorize or perform:

- validation execution in G97,
- pytest test execution in G97,
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
XRI-G98 — current-worktree fixture-only validation execution result capture
```

G98 may run only the authorized fixture-only validation command and must capture stdout, stderr, exit code, status_before, and status_after.

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
