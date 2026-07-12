# Canonical Milestone 5: Dependency Reproducibility & Workflow Hardening Closure

Milestone: Canonical Milestone 5
Gate type: documentation-only closure (no executable behavior changed by this document)

## Purpose

Record the now-merged Canonical Milestone 5 state: dependency reproducibility, Python-version declaration, workflow least-privilege hardening, and fail-closed reliability-gate behavior. This closure describes only verified, already-merged facts.

## Subphase PRs and merge commits

| Subphase | Scope | PR | Merge commit |
|---|---|---|---|
| Definition | Read-only repository audit; proposed M5-A through M5-F scope | #137 | `3fc3d52edfe5017ca7e3dafeab228b13e97c08bd` |
| M5-A | Dependency and Python-version contract confirmation (read-only gate; no code/PR) | — | evidence-only, confirmed `rapidfuzz==3.*` / `pytest==9.0.2` / Python `3.11` |
| M5-B | Added `requirements.txt` | #138 | `1ccac068e32d73fc5f1988e2e7e4b08ae0786265` |
| M5-C | Changed the three GPS commit-workflow conditions from `if: always()` to `if: success()` | #139 | `5d401fb7ab479fb7596527c5305e69ef2d97e8fb` |
| M5-D | Added `env.BACKEND_GATE_FAILED != 'true'` to the email-notification step's condition | #140 | `0619c2811ae0b779be546db49fd7a43e6c0e53de` |
| M5-E | Added 12 offline workflow-safety tests under `tests/workflows/` | #141 | `4a771a4604e2c1705b25745db8b64c22ebf7d799` |

Final main SHA prior to this M5-F closure: `4a771a4604e2c1705b25745db8b64c22ebf7d799`.

Note: two automated pipeline commits ("Generate GPS staged feed adjudication summary", "Generate GPS staged feed match diagnostic") landed on `main` between M5-C and M5-D via the repository's own `gps-staged-feed-integration-*` workflows. These are routine automated data-generation commits, not Milestone 5 deliverables, and were left untouched throughout M5-D/E/F per explicit instruction.

## Dependency versions

- `requirements.txt`:
  ```
  rapidfuzz==3.*
  pytest==9.0.2
  ```
- Python version: `3.11` (matches every workflow's `actions/setup-python@v5` declaration; no broader version range is tested or claimed).

## Corrected workflow conditions

- `.github/workflows/live-sync-qa.yml`, "Email live delta report" step:
  ```
  if: github.event.inputs.allow_email == 'yes' && env.BACKEND_GATE_FAILED != 'true'
  ```
- `.github/workflows/gps-staged-feed-integration-adjudication-summary.yml`, `-diagnostic.yml`, `-update.yml`, each "Commit ..." step:
  ```
  if: success()
  ```

## M5-E test count and result

`tests/workflows/test_canonical_milestone_5_workflow_safety.py` — 12 tests, all offline/deterministic/read-only text-based assertions against committed workflow YAML (no third-party YAML library required; PyYAML was found not to be installed in the authorized pytest interpreter, so plain-text/regex parsing was used instead — a discrepancy recorded rather than silently worked around).

Isolation mechanism: `env -i` (8-variable allowlist: `PATH`, `HOME`, `LANG`, `LC_ALL`, `TMPDIR`, `PYTHONDONTWRITEBYTECODE`, `PYTEST_DISABLE_PLUGIN_AUTOLOAD`, `PYTHONHASHSEED`) → `unshare --net --map-root-user` → `strace -ff -e trace=network,process`, using the Canonical Milestone 4 dual live-namespace-capture pattern (parent self-reports its namespace; child self-reports its namespace over a private pipe before exec; parent independently reads `/proc/<child_pid>/ns/net` while the child is still alive — all three matched).

Denial-test accounting: 5 attempts (DNS, hostname TCP, direct-IP TCP, HTTPS, raw socket), 0 successful connections, all `ENETUNREACH`/DNS-failure, all attributable to the parent's deliberate self-test process. Test-run accounting: new-test run 12/12 passed; full-suite run 94/94 passed (82 pre-existing + 12 new); 0 network syscalls from either pytest child process.

## Repository-integrity result

Unchanged except each subphase's explicitly authorized file(s). No generated JSON, cache, `.pyc`, or temporary artifact was left in the repository by any subphase.

## Secret-scan result

0 unresolved findings across all M5-B, M5-C, M5-D, and M5-E evidence and PR diffs.

## Unresolved required-risk count

0. Every risk classified as "required" in the Canonical Milestone 5 definition (no dependency manifest, `rapidfuzz` unavailable without a manifest, `contents: write` + `if: always()` unconditional commit, reliability-gate failure not gating the email step, 0% script test coverage for the fail-closed controls specifically) has a corresponding merged fix or, for the untested-scripts risk, a test now proving the two fail-closed controls (M5-C's `if: success()`, M5-D's combined email condition) at the workflow-configuration level.

## Deferred optional risks (not Milestone 5 failures)

These were explicitly labeled optional in the Canonical Milestone 5 definition and remain deferred, not regressions or unresolved required work:

- Broad-exception narrowing (23 files use `except Exception`).
- Atomic-write conversion (temp-file + `os.replace()`) for the three scripts feeding the `contents: write` workflows.
- Removal/archival of 7 orphaned `tools/registry` prototype modules (`xri_g6`–`xri_g11`, `registry_candidate_extractor_prototype.py`).
- GitHub Action SHA pinning (currently pinned to mutable `@v4`/`@v5` tags).
- Broader `scripts/**` test coverage beyond the specific fail-closed controls M5-E now tests (the reliability gate's own internal logic, the live-source sync script, and the email sender remain without dedicated unit tests).

## Explicit scope confirmations

- No live-source fetch occurred during M5-D, M5-E, or M5-F.
- No email was sent.
- No workflow was dispatched.
- No GPS identity-drift remediation occurred.
- No staged-feed update occurred.
- No geocoding occurred.
- No registry write occurred.
- No promotion or publishing occurred.
- No production, WordPress, or public-map change occurred.
- PR #133 remained untouched throughout M5-B, M5-C, M5-D, M5-E, and M5-F.
- Automatic continuation into another milestone is not authorized by this document.

## Final closure verdict

**PASS** — M5-B, M5-C, M5-D, and M5-E are merged and verified as recorded above.
