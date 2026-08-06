# Issue 375 — Daily Refresh `unknown_stage` Investigation

Status: active investigation

Branch: `fix/issue-375-daily-refresh-diagnostics`

Production actions authorized by this branch: none

## Scope

Identify the first failing command in the scheduled Discovery Feed Refresh, remove the `unknown_stage` reporting gap, preserve fail-closed behavior, and confirm Event 923896 archived certification remains valid.

## Evidence reviewed

- Merge commit `d0d178c3b1c066427914655f9b0f642fe7e7bb01`
- First later READY refresh commit `58ea2e356a2006793f36c0a6230db9e0e4130396`
- BLOCKED status commits:
  - `71410d81c422d1dd9011c5117cdabf0005da6dcc`
  - `3e42933a03eaff186811a06321989d9f98089e26`
  - `efb88a23cf47ecccb702c76ebbfbd7975d1e644e`
- `.github/workflows/discovery-feed-refresh.yml`
- `scripts/test_live_event_intake_refresh.py`
- `scripts/test_daily_production_hardening.py`
- `scripts/record_blocked_daily_data_health.py`
- `status/nycif-daily-data-health.json`
- `data/reports/event_923896_snapshot_recovery_certificate.json`

## Confirmed diagnostic defect

The workflow records detailed failure context only inside the step named `Build, validate, and commit READY discovery feed`.

The earlier step named `Verify daily production contracts` is not wrapped by the failure trap and does not write `/tmp/nycif-daily-failure`.

When checkout, Python setup, or the preflight contract step fails, the later BLOCKED publisher cannot recover a stage name and falls back to:

- stage: `unknown_stage`
- line: `unknown`
- exit code: `1`

Therefore the current BLOCKED artifact does not prove that the production transaction itself began. The first failure is before the instrumented build transaction unless separate workflow logs show otherwise.

## Root-cause candidate under verification

The first preflight command is:

`python scripts/test_live_event_intake_refresh.py`

That script contains a historical test named `test_required_event_aug1_real_approved_pages_pass`. The test forces Event 923896 validation into `live_occurrence` mode for August 1, 2026, but scans the repository's current mutable approved pages.

After the event date, production health correctly uses the immutable archived certificate. A later feed refresh may legitimately age the past event out of current approved pages while the certificate remains valid. The historical live-mode test can then fail on the next scheduled preflight even though archived certification is healthy.

The commit sequence is consistent with this failure mode:

1. A READY refresh completed after the date-aware certificate merge.
2. The READY refresh could update current approved pages.
3. Every later scheduled run stopped before instrumented production stages and emitted `unknown_stage`.

This candidate must be confirmed against the failed job log before the PR is marked ready.

## Event 923896 status

The committed certificate remains intact:

- validation mode required after event date: `archived_certification`
- certificate artifact: `data/reports/event_923896_snapshot_recovery_certificate.json`
- certificate schema version: `1.0.0`
- certificate `qa_pass`: `true`
- certificate failures: `[]`
- health status recorded in certificate: `READY`
- strict reconciliation recorded in certificate: `true`

The current investigation does not classify the repeated `unknown_stage` reports as Event 923896 certificate failures.

## Planned code changes

1. Instrument each repository-controlled preflight command before execution.
2. Replace the `unknown_stage` fallback with an explicit platform-or-uninstrumented classification.
3. Record:
   - stage
   - safe command identifier
   - exit code
   - exception class
   - sanitized error summary
   - whether a public-feed commit occurred
4. Remove the production preflight dependency on mutable current pages for a historical August 1 live-occurrence assertion.
5. Preserve fixture-based live-occurrence tests for August 1.
6. Preserve real immutable archived-certificate validation for dates after August 1.
7. Add regression coverage proving a repository-controlled executable failure cannot emit `unknown_stage`.
8. Preserve the rule that failed refreshes cannot commit partial public-feed output.

## Safety

- No production rerun from this branch.
- No merge.
- No deploy.
- No public-feed replacement.
- No certificate replacement.
- No partial generated data committed.
- The previous serving feed remains authoritative while investigation continues.
