# Issue 375 — Daily Refresh `unknown_stage` Resolution

Status: implementation complete; PR validation in progress

Branch: `fix/issue-375-daily-refresh-diagnostics`

Production actions authorized by this branch: code hardening and CI validation only until all required PR checks pass

## Scope

Identify the first failing command in the scheduled Discovery Feed Refresh, remove the `unknown_stage` reporting gap, preserve fail-closed behavior, and confirm Event 923896 archived certification remains valid.

## Confirmed root cause

Two defects combined to produce the repeated non-actionable BLOCKED reports.

### 1. The failing preflight was outside the failure trap

The old workflow ran `Verify daily production contracts` before installing its shell failure trap. A failure there did not write `/tmp/nycif-daily-failure`, so the later BLOCKED publisher substituted:

- stage: `unknown_stage`
- line: `unknown`
- exit code: `1`

The public-feed transaction had not started. The status artifact could not identify that fact because preflight execution was uninstrumented.

### 2. A historical Event 923896 test depended on mutable current pages

The failing command was `python scripts/test_live_event_intake_refresh.py`.

GitHub Actions logs confirmed the first failing assertion was `test_required_event_aug1_real_approved_pages_pass`. That test forced Event 923896 into August 1 `live_occurrence` mode while scanning the repository's current approved pages. The event had legitimately aged out of the current serving window, so the test found zero occurrences and failed.

That assertion was valid only while the event was current. It is not a valid standing production preflight after the event date.

## Event 923896 status

The immutable recovery certificate remains the authoritative post-event evidence:

- artifact: `data/reports/event_923896_snapshot_recovery_certificate.json`
- schema version: `1.0.0`
- `qa_pass`: `true`
- failures: `[]`
- health status: `READY`
- strict reconciliation: `true`
- approved page match count: `1`
- approved list match count: `1`

No certificate content was changed by this fix.

## Implemented changes

### Structured stage runner

Added `scripts/run_daily_refresh_stage.py`.

Each wrapped command now records:

- deterministic stage
- safe command identifier
- exit code
- exception class
- bounded sanitized error summary
- whether a public-feed commit occurred
- shell line when available

Common token, key, authorization, password, and signature patterns are redacted from both captured summaries and streamed command output.

### Date-safe intake preflight

Added `scripts/test_live_event_intake_refresh_current.py`.

The standing preflight now preserves:

- fixture-based August 1 live-occurrence validation
- missing and duplicate occurrence fail-closed tests
- coordinate validation
- real immutable archived-certificate validation after August 1

It does not require the past occurrence to remain in mutable current approved pages.

### Instrumented production transaction

Added `scripts/run_discovery_feed_refresh.sh` and routed the scheduled workflow through it.

The script preserves the existing atomic transaction:

1. run preflight contracts
2. reset to current `main`
3. fetch official sources
4. rebuild all discovery projections
5. enforce strict reconciliation
6. rebuild overlays and emergency fallback
7. run the daily health gate
8. validate every runtime family
9. write the rollback pointer
10. stage only approved artifacts
11. commit and push only when health is READY

A rejected push causes a complete reset and rebuild. Generated conflicts are never merged and production is never force-pushed.

### Fail-closed BLOCKED publisher

Added `scripts/publish_blocked_daily_refresh.sh` and upgraded `scripts/record_blocked_daily_data_health.py`.

On failure, the publisher:

- fetches current `main`
- refuses to overwrite newer health when another transaction advanced `main`
- resets away all partial generated output
- commits only BLOCKED status and God View artifacts
- retains the previous serving commit as authority
- emits `platform_or_uninstrumented_failure` instead of `unknown_stage` when a platform-level failure occurs before repository code can capture context

### Regression gates

Added `.github/workflows/daily-refresh-reliability-check.yml` and expanded `scripts/test_daily_production_hardening.py`.

Coverage includes:

- shell syntax
- Python compilation
- date-safe Event 923896 behavior
- secret redaction
- structured failure context
- explicit non-unknown stage classification
- fail-closed BLOCKED payloads
- previous-serving-commit retention
- production workflow entrypoint contracts

The Discovery Taxonomy QA workflow now uses the date-safe intake regression instead of the obsolete mutable-page assertion.

## Validation evidence

- Daily Refresh Reliability Check run 5: passed
- Shell entrypoint syntax: passed
- Reliability Python compilation: passed
- Date-safe live intake regressions: passed
- Daily production hardening regressions: passed
- GitHub Actions reproduced the old failure as exactly zero current approved matches for Event 923896 on the obsolete August 1 real-page assertion
- Remaining repository PR checks must pass on the current head before review status changes

## Release procedure

1. Require all PR checks to pass on the same head commit.
2. Review the final diff for unexpected public data or certificate changes.
3. Mark PR ready for review.
4. Merge to `main` only after the green gate.
5. Monitor the automatically triggered Discovery Feed Refresh.
6. Confirm either:
   - READY with a complete atomic public-feed commit, or
   - BLOCKED with a deterministic stage and no public-feed commit.
7. Confirm Event 923896 certificate hash and contents remain unchanged.
8. Close Issue 375 only after one successful production refresh records READY.

## Safety invariants

- No partial public-feed commit.
- No force push.
- No generated conflict merge.
- No Event 923896 certificate replacement.
- No production rerun from the feature branch.
- The previous serving feed remains authoritative until a complete refresh is READY.
