# Canonical Milestone 5: Dependency Reproducibility & Workflow Hardening Definition

Milestone: Canonical Milestone 5
Gate type: documentation-only definition (no implementation)

## Baseline

* Baseline SHA: `09d3e88e2d4432b43b4a8f39595941fe68fc7068`
* Committed tree: `80d25e48404c1da42637f2cb02a95a29c0efc3c9`
* This is the commit merged by PR #136 (Canonical Milestone 4 closure).

**Baseline-verification note:** the session's checked-out branch (`claude/nycif-live-feeds-setup-58vl9d`) sits one commit behind this baseline (it is the parent of the merge), and the local `refs/heads/main` branch in this workspace is a stale ref that was never advanced past its creation point. The authoritative `origin/main` remote-tracking ref (fetched earlier in this session and cached, not re-fetched for this gate) correctly points to `09d3e88e2d4432b43b4a8f39595941fe68fc7068`, matching GitHub's actual `main` branch as confirmed via the GitHub API. The commit's content was verified directly via `git cat-file`/`git ls-tree` without checking it out, since switching branches was prohibited by this same authorization. This is recorded rather than silently resolved, consistent with how equivalent baseline-reference discrepancies were handled in prior Canonical Milestone gates.

## Purpose

Define — without implementing — a bounded Canonical Milestone 5 scope addressing dependency reproducibility, Python-version declaration, least-privilege workflow permissions, and fail-closed reliability-gate behavior, based on a complete read-only audit of the repository at the baseline commit.

## Repository audit summary

Audit performed against a disposable `git archive` snapshot of the baseline commit (reused and re-verified from the prior overnight-audit gate: 354 tracked files, content-identity proven via `git hash-object` blob comparison against `git ls-tree` at this exact commit). No repository code was imported or executed during the static-audit phases; AST parsing, text inspection, and workflow YAML inspection only.

## A. Dependency matrix

Exactly two third-party dependencies exist across the entire codebase:

| Package | Import name | Used by | Required by tests? | Required by production/live-source scripts? | Importable in audited interpreter? | Installed version | Version constraint documented anywhere? |
|---|---|---|---|---|---|---|---|
| pytest | `pytest` | 5 files under `tests/registry/` | Yes (test framework itself) | No | Yes — `9.0.2` | `9.0.2` | No manifest; no constraint anywhere |
| rapidfuzz | `rapidfuzz` | 1 file: `scripts/generate_gps_staged_feed_integration_match_diagnostic.py` | No | Yes (that one script) | **No** — `ImportError` in the audited interpreter | N/A (not installed) | **Yes, but only as inline `pip install 'rapidfuzz==3.*'` duplicated in two separate workflow YAML files** (`gps-staged-feed-integration-diagnostic.yml`, `gps-staged-feed-integration-update.yml`) — no single source of truth |

Everything else imported across `scripts/**`, `tools/**`, and `tests/**` is Python standard library (`json`, `pathlib`, `datetime`, `re`, `typing`, `dataclasses`, `smtplib`, `ssl`, `urllib`, `csv`, `hashlib`, `math`, `argparse`, `collections`, `copy`, `email`, `os`, `sys`, `traceback`, `__future__`) or repository-local (`tools.registry.*` imported by `tests/registry/*`).

**Proposed dependency structure:** a single `requirements.txt` at the repository root is sufficient — there is no evidence of a need for separate dev/test/optional dependency tiers, since the only two third-party packages are pytest (test-only) and rapidfuzz (one non-test script only). A `pyproject.toml` would be over-engineering for a dependency-free-of-build-system batch pipeline; `requirements.txt` matches the repository's existing "plain Python scripts, no package build" convention.

Proposed matrix separation:
* **Runtime (used by non-test scripts):** `rapidfuzz==3.*` (matching the version constraint already used twice in workflow YAML)
* **Live-source dependencies:** none beyond stdlib `urllib` (no separate HTTP client library)
* **Development/test-only:** `pytest==9.0.2` (pin to the version already verified working)
* **Optional tooling:** none identified

Security/maintenance note: neither package's installed metadata exposes license information queryable from this interpreter (`pytest`'s installed distribution metadata reports `License: unspecified`; `rapidfuzz` isn't installed here to query). This audit did not search the internet for either package's actual license per the authorization's scope; a future implementation phase should record license info from the actual install source.

## B. Python-version analysis

* All 4 workflows pin `actions/setup-python@v5` with `python-version: '3.11'` — uniformly consistent, no version matrix.
* Audited interpreter: `3.11.15`, matches CI exactly.
* Syntax scan: one file (`scripts/build_live_delta_report.py`) uses the walrus operator (`:=`), which requires Python ≥ 3.8. No `match`/`case` statements found. 36 of 41 files use `from __future__ import annotations`, which defers annotation evaluation and reduces version sensitivity of type-hint syntax.
* **Recommendation:** declare exactly `3.11` as the supported version (matching what CI already runs and what has actually been tested), rather than claiming a broader range that has never been exercised. No evidence supports testing a version matrix at this time.

## C. Workflow-permission audit

| Workflow | Trigger(s) | Permissions | Notable steps |
|---|---|---|---|
| `live-sync-qa.yml` | `workflow_dispatch` (2 required inputs: `allow_live_fetch`, `allow_email`, both default `"no"`) | `contents: read` | Job itself gated behind `if: github.event.inputs.allow_live_fetch == 'yes'`; runs the full live pipeline (NYC Open Data fetch, feed generation, reliability gate, conditional email) |
| `gps-staged-feed-integration-adjudication-summary.yml` | `workflow_dispatch` + `push` on `main` (path-filtered) | `contents: write` | Commits and pushes `data/gps_staged_feed_integration_adjudication_summary.json` directly to `main` |
| `gps-staged-feed-integration-diagnostic.yml` | `workflow_dispatch` + `push` on `main` (path-filtered) | `contents: write` | Installs `rapidfuzz==3.*` via inline pip; commits/pushes diagnostic JSON to `main` |
| `gps-staged-feed-integration-update.yml` | `workflow_dispatch` + `push` on `main` (path-filtered) | `contents: write` | Installs `rapidfuzz==3.*` via inline pip; commits/pushes staged-feed update JSON to `main` |

No scheduled (`cron`) triggers exist on any workflow — all four require either manual dispatch or a push to `main` matching a narrow path filter. No artifact-upload or deployment steps exist anywhere.

**Least-privilege analysis of the three `contents: write` workflows:** each genuinely needs write access, since each ends with a `git commit && git push origin HEAD:main` step — the permission is not gratuitous. However:
* All three grant `contents: write` at the **workflow level**, applying to every step (including the `actions/setup-python` and `pip install` steps), rather than scoping it to only the final commit job/step. GitHub Actions permissions cannot be scoped narrower than job-level, but job-level scoping (rather than workflow-level, where there's only one job anyway here) would not by itself reduce blast radius further in this specific case since each workflow has exactly one job.
* The more significant finding is **what runs under that write-scoped token**, not the permission declaration itself — see Section D and the "commit runs on `if: always()`" finding below.

Proposed least-privilege table: no change recommended to the permission *level* (write is genuinely required); the recommended hardening is on *what is allowed to trigger a write*, addressed in the fail-closed analysis below.

## D. Fail-closed control-flow analysis

### `live-sync-qa.yml` — full step trace

The job only runs at all if a human explicitly sets `allow_live_fetch: yes` on manual dispatch (default `no`). Within the job, steps run in this order: build location cache → sync NYC Open Data → build enriched feed → build staged production feed → build GPS repository/review-groups/geocoding-proposals/filled-proposals/manual-approval-queue/manual-review-sheet/manual-approval-staging/reviewed-approval-artifact → validate manual approvals → build live-delta report → audit remainder-year coverage → audit row disposition → **build backend reliability gate report** (`|| echo "BACKEND_GATE_FAILED=true" >> "$GITHUB_ENV"`) → **email live delta report** (only if `allow_email == 'yes'`) → audit feed anomalies → **enforce backend reliability gate** (`if: env.BACKEND_GATE_FAILED == 'true'`, prints a message and `exit 1`).

**Precise finding (more nuanced than "the gate is swallowed"):** the job as a whole *does* eventually fail closed — the final step explicitly checks the flag and exits 1, so CI status is not masked. However, the **email step is not conditioned on `BACKEND_GATE_FAILED`** — it is gated only on the separate `allow_email` input. This means: if the reliability gate fails on a given run, and a human has set `allow_email: yes`, the live-delta email is still sent reporting on data that has already failed the reliability gate, *before* the job registers overall failure. Because this workflow's permission is `contents: read` (no artifact upload, no push), the **email is the only external side-effect channel** that can escape the runner regardless of gate outcome — the generated JSON/feed files stay local to the ephemeral runner.

### The three `contents: write` workflows — commit-step trace

Each of the three workflows' final "Commit ... artifact" step is guarded by **`if: always()`**, meaning it runs regardless of whether the preceding generation/update script succeeded or failed. Each of the three generation/update scripts (`generate_gps_staged_feed_integration_adjudication_summary.py`, `generate_gps_staged_feed_integration_match_diagnostic.py`, `apply_gps_staged_feed_integration_update.py`) writes its output via a **direct overwrite** — `path.open("w")` followed by `json.dump(...)` — with no temporary-file-then-rename pattern, no backup, and no post-write validation. If such a script is killed mid-write (OOM, runner timeout, SIGKILL), a truncated/invalid JSON file could exist on disk when the `if: always()` commit step runs; that step only checks `git diff --cached --quiet` (whether anything changed), not whether the content is well-formed, before committing and pushing to `main` under `contents: write`.

**Combined fail-open pattern:** `if: always()` (runs regardless of upstream failure) + non-atomic write (can leave partial output) + `contents: write` (push capability) is the single most concrete workflow-hardening finding in this audit. Likelihood is low (requires a crash precisely during the write syscall window), but the current design provides no protection against it.

### Other soft-fail patterns found

* Three `git reset --hard origin/main` calls (one per `contents: write` workflow, in a "sync latest main" step run immediately after `actions/checkout@v4`) — redundant given checkout already retrieves `main`, but not dangerous since it only affects the ephemeral CI runner's local clone, never a persistent developer checkout.
* No `continue-on-error: true` usage found anywhere.
* No `set +e` usage found anywhere.
* No unguarded shell pipelines lacking `pipefail` were identified as a distinct risk beyond the two patterns above.

## E. Entry-point inventory summary

24 `scripts/**` files, 12 `tools/registry/**` files, 5 `tests/registry/**` files. All scripts are standalone `python scripts/foo.py` entry points (not an importable package); `tools/registry/xri_g40` through `xri_g44` are imported directly by their matching test files.

**Orphaned entry points (not referenced by any workflow, script, or test):** `tools/registry/xri_g6_fixture_mapping_validator.py`, `xri_g7_fixture_candidate_normalizer.py`, `xri_g8_fixture_candidate_preview_report.py`, `xri_g9_fixture_review_sorting_grouping.py`, `xri_g10_fixture_grouped_review_export.py`, `xri_g11_fixture_grouped_export_validator.py`, and `registry_candidate_extractor_prototype.py` — seven early-phase prototype modules from this repository's XRI-G gate series, superseded by the later `xri_g40`–`xri_g44` series, left in the tree with no active caller and no test.

**Network-capable entry points, none reachable from `tests/`:**
* `scripts/sync_nyc_open_data.py` — live-source capable (NYC Open Data SODA endpoint); self-documented as "report-only... does not overwrite production map feeds"
* `scripts/send_live_delta_email.py` — production-capable (real SMTP email), secrets-gated
* `scripts/build_test_enriched_feed.py`, `scripts/build_gps_manual_review_sheet.py` — `urllib.parse`/`urllib.request` present but usage is utility-level, not test-invoked

**Filesystem-mutation-capable entry points:** 22 of 24 `scripts/**` files show write/mutation patterns; **0** of `tests/**` or `tools/registry/**` files do — confirming the test suite is entirely fixture-only/read-only by construction.

## F. Exception-handling findings

23 files use broad `except Exception` (0 bare `except:`). None were found wrapping the direct-overwrite JSON write calls themselves in the three commit-triggering scripts (the writes are unguarded, not wrapped in error-swallowing handlers — meaning a write failure would propagate as an uncaught exception and correctly fail the script's own exit code; the `if: always()` workflow pattern is the actual gap, not the exception handling around the write). Severity of the broad-exception pattern generally: **Low** — no evidence found of a broad handler masking a reliability-relevant failure as success; this is a code-quality observation, not a demonstrated correctness bug.

## G. Atomic-write and data-integrity findings

| Target | Write pattern | Atomic? | Validated before write? | Consequence of interrupted write |
|---|---|---|---|---|
| `data/gps_staged_feed_integration_adjudication_summary.json` | `path.open("w")` + `json.dump` | No | No | Truncated file could be committed via `if: always()` |
| `data/gps_staged_feed_integration_match_diagnostic.json` | `path.open("w")` + `json.dump` | No | No | Same as above |
| `data/nycif_staged_live_events.json`, `data/gps_staged_feed_integration_update_report.json` | `path.open("w")` + `json.dump` | No | No | Same as above |
| Other `data/**` report/artifact files generated by the remaining 21 scripts | Same direct-overwrite pattern (confirmed via static scan) | No | Varies | Not auto-committed (these workflows lack `contents: write`/commit steps), so the blast radius is confined to the ephemeral CI runner filesystem |

`data/location_cache.json` was not observed being written by any of the audited scripts in a mutation-hint match tied to a commit-capable workflow; no direct evidence in this audit of an automated write path to that file.

## H. Test-coverage map

* **Directly tested:** `tools/registry/xri_g40` through `xri_g44` (5 modules; 82 tests total), all fixture-only.
* **Untested — 0% of `scripts/**` (24 of 24 files):** including, critically, `backend_reliability_gate.py` (the reliability gate itself), `sync_nyc_open_data.py` (the live-source entry point), `send_live_delta_email.py` (the external-notification entry point), and all three `contents: write` commit-triggering scripts.
* **Untested — 7 of 12 `tools/registry/**` files:** the orphaned prototypes listed in Section E.
* **Highest-risk untested paths, ranked:** (1) `backend_reliability_gate.py` — the safety gate itself has no test proving it actually gates correctly; (2) the three commit-triggering scripts that push directly to `main`; (3) `sync_nyc_open_data.py` and `send_live_delta_email.py` — the only two scripts with genuine external side effects.

No coverage percentage is claimed beyond what is directly demonstrable: 5 of 36 non-orphaned first-party modules (scripts + active tools) have direct test coverage; the remaining 31 do not.

## I. Supply-chain findings

* All GitHub Actions (`actions/checkout@v4`, `actions/setup-python@v5`) are pinned to **mutable major-version tags**, not immutable commit SHAs — a standard, low-severity hardening opportunity; both are official GitHub-maintained actions, which somewhat lowers likelihood of a supply-chain compromise relative to third-party actions.
* No `curl`/`wget`/remote-script execution found in any workflow.
* No unsafe deserialization (`pickle`, `eval`, `exec`) found anywhere in the codebase (confirmed by prior static audit, re-confirmed here).
* No shell command injection risk found from unescaped workflow-input interpolation into `run:` blocks — the two `workflow_dispatch` inputs (`allow_live_fetch`, `allow_email`) are only ever compared via `==` in `if:` conditions, never interpolated into a shell command string.
* Secrets referenced (by name only, values never inspected): `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `REPORT_TO_EMAIL`, `REPORT_FROM_EMAIL`, `REPORT_MAX_EVENTS` — all scoped to the single email step in `live-sync-qa.yml`, not exposed to any other step.

## J. Documentation and operational-readiness gaps

Neither `README.md` (4 lines, states only the repository's purpose) nor `AGENTS.md` (the repo's coding-agent contract, 17 section headers) mentions: Python version, `rapidfuzz`, `pytest`, dependency-installation instructions, rollback procedure, or incident response, at this baseline commit. `AGENTS.md` does document protected files, the public-map rule, GPS pipeline phases, QA requirements, and commit rules, but has no dedicated "dependencies" or "local setup" section. (PR #133, still open/draft/unmerged, proposes adding Cursor-Cloud-specific setup notes to `AGENTS.md` — out of scope for and untouched by this gate.)

## Ranked risk register

| ID | Severity | Likelihood | Confidence | Title | Affected files | Evidence | Consequence / failure scenario | Current mitigating controls | Remaining gap | Smallest safe remediation | Proposed M5 subphase | Separate authorization required |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| RISK-01 | Medium | High | High | No dependency manifest | (repo root) | No `requirements.txt`/`pyproject.toml`; `rapidfuzz==3.*` duplicated only inline in 2 workflow YAML files | Version drift between the 2 inline installs; no single source of truth; contributor/CI environments can diverge | Inline pip pins exist in 2 of 3 places that need rapidfuzz | Add `requirements.txt` pinning `rapidfuzz==3.*` and `pytest==9.0.2` | M5-B | Yes |
| RISK-02 | Medium | High (in this interpreter) | High | `rapidfuzz` unavailable in the audited pytest interpreter | `scripts/generate_gps_staged_feed_integration_match_diagnostic.py` | `ImportError` confirmed live; not required by `tests/` | That one script cannot run under this interpreter; no impact on test suite | Workflows install it ad hoc via pip for their own runs | No manifest-driven install for local/dev use | Document + pin per RISK-01 | M5-B | Yes |
| RISK-03 | Medium-High | Low-Medium | High | `contents: write` + `if: always()` unconditional commit-and-push | 3 workflow YAML files | Direct read of workflow YAML: commit step guarded only by `if: always()`, not by upstream step success | A crashed generation script combined with a partial write could still be committed/pushed to `main` | `git diff --cached --quiet` skips a no-op commit; permission genuinely needed for the workflow's purpose | No check that the generation step itself succeeded before committing | Change commit step condition from `if: always()` to `if: success()` (or explicit exit-code check) | M5-D | Yes |
| RISK-04 | Medium | Medium | High | Reliability-gate failure doesn't gate the email step | `.github/workflows/live-sync-qa.yml` | Direct read: email step condition is `allow_email == 'yes'` only, not `BACKEND_GATE_FAILED` | A live-delta email can be sent reporting on data that already failed the reliability gate, before the job's final fail-closed step | Job's last step does still fail the overall CI run; job requires manual `allow_live_fetch`/`allow_email` opt-in | Email step isn't conditioned on gate outcome | Add `&& env.BACKEND_GATE_FAILED != 'true'` to the email step's `if:` | M5-D | Yes |
| RISK-05 | Low | N/A | High | Broad `except Exception` in 23 files | 23 files across `scripts/**` | AST-confirmed count; none found wrapping the direct-write calls in the 3 commit-triggering scripts | Could mask unexpected errors as silent success in other contexts | None found actively masking a reliability-relevant failure in this audit | Narrow to specific exception types where the surrounding code makes the expected failure modes clear | M5-optional | Yes |
| RISK-06 | Medium | Low-Medium | Medium | Non-atomic direct-overwrite writes on auto-committed files | 3 scripts feeding the 3 `contents: write` workflows | `path.open("w")` + `json.dump`, no temp-file+rename | Interrupted write (OOM/timeout/kill) could leave truncated JSON that RISK-03's `if: always()` gap would then commit | None (writes are direct, unguarded) | No atomic replace pattern anywhere in the 3 scripts | Write to a temp file in the same directory, then `os.replace()` onto the target | M5-optional | Yes |
| RISK-07 | High | N/A (coverage gap, not a live bug) | High | 0% test coverage across all 24 `scripts/**` files, including the reliability gate itself | All of `scripts/**` | Cross-referenced every script against every test file; 0 matches | The safety gate, the live-source sync, the email sender, and all 3 auto-commit scripts have no automated correctness check | The 5 `tools/registry` fixture modules are well-tested; scripts are not | No test harness exists for scripts at all | Add unit tests for `backend_reliability_gate.py` first, as the highest-leverage safety-critical untested path | M5-E | Yes |
| RISK-08 | Low | N/A | High | 7 orphaned `tools/registry` prototype modules | `xri_g6`–`xri_g11`, `registry_candidate_extractor_prototype.py` | Confirmed zero references from any workflow, script, or test | Dead code increases audit surface with no functional benefit | None needed (inert) | Consider removal or archival in a future cleanup phase | M5-optional | Yes |
| RISK-09 | Low | Low | High | GitHub Actions pinned to mutable tags, not SHAs | All 4 workflow files | `actions/checkout@v4`, `actions/setup-python@v5` | A compromised upstream tag could theoretically introduce malicious code into CI | Both actions are official, GitHub-maintained | No SHA pinning | Pin to specific commit SHAs with version comments | M5-optional | Yes |
| RISK-10 (positive control) | — | — | High | No scheduled workflows; live pipeline requires explicit dual manual opt-in | All 4 workflow files | Confirmed no `schedule:`/`cron:` anywhere; `live-sync-qa.yml` job gated on `allow_live_fetch == 'yes'`, email further gated on `allow_email == 'yes'` | N/A — this is a control already in place, not a gap | — | — | None needed | — | — |
| RISK-11 | Low | — | Medium | Documentation gap: no Python version, dependency, or operational-readiness section in README/AGENTS.md | `README.md`, `AGENTS.md` | Grep-confirmed absence of "python", "rapidfuzz", "pytest", "rollback", "incident" in either file at this commit | New contributors/agents lack a single documented source for setup/dependency/version expectations | AGENTS.md documents protected files, QA requirements, and commit rules | No dependency/setup section | Add a "Dependencies and Python version" section to AGENTS.md or README | M5-F | Yes |

## Proposed Canonical Milestone 5 subphases

### Required implementation candidates
* Dependency manifest (`requirements.txt`) — RISK-01, RISK-02
* Python-version declaration matching CI's actual `3.11` — Section B
* Workflow-permission/control-flow correction: `if: always()` → `if: success()` on the 3 commit steps — RISK-03
* Fail-closed reliability-gate correction: condition the email step on `BACKEND_GATE_FAILED` — RISK-04
* Tests proving the corrected fail-closed behavior (both RISK-03 and RISK-04) — RISK-07 (partial)
* Documentation update recording the dependency manifest, Python version, and the corrected fail-closed behavior — RISK-11

### Optional candidates
* Broad-exception narrowing — RISK-05
* Atomic-write conversion (temp file + `os.replace()`) for the 3 auto-committed scripts — RISK-06
* Orphaned prototype-module cleanup — RISK-08
* GitHub Action SHA pinning — RISK-09
* Broader test coverage for `scripts/**` beyond the fail-closed tests above — RISK-07 (remainder)

### Explicitly excluded from Canonical Milestone 5
Live source fetches, live API access, ingestion, scraping, geocoding, registry imports, `data/location_cache.json` changes, staging, promotion, publishing, production, WordPress, public-map output, deployment, enabling/modifying scheduled workflows, and any change to PR #133.

## Proposed phased implementation sequence (definition only — not executed)

**M5-A — Dependency and Python-version contract**
* Starting baseline: the merge commit of this M5 definition PR
* Files allowed to change: none (contract/definition step only, or a small addendum doc if needed)
* Commands allowed: read-only (`python3 -c`, `pip show`, static inspection)
* Commands prohibited: `pip install`, workflow execution, live fetches
* Tests required: none (definition step)
* Network policy: none (fully offline)
* Evidence required: confirmation of the exact pinned versions to be used in M5-B
* Pass criteria: exact versions agreed and recorded; Fail criteria: any ambiguity in target versions
* Rollback: N/A (no files changed)
* PR size limit: N/A (may be folded into M5-B)
* Merge requirements: none beyond normal review
* Stop conditions: disagreement on target Python/dependency versions

**M5-B — Dependency-manifest implementation**
* Files allowed to change: `requirements.txt` (new file) only
* Files prohibited from changing: everything else, including workflows and scripts
* Commands allowed: `pip install -r requirements.txt --dry-run`-style verification if available offline; otherwise static review only
* Commands prohibited: any workflow run, any live-source script execution
* Tests required: confirm `pytest`/`rapidfuzz` versions in the manifest match what's already used by CI's inline installs
* Network policy: none required for the manifest file itself
* Evidence required: manifest content diff, confirmation it matches RISK-01's proposed versions
* Pass criteria: manifest added, no other file touched; Fail criteria: any other file changed
* Rollback: revert the single new file
* PR size limit: 1 new file
* Merge requirements: standard PR review
* Stop conditions: any attempt to also modify workflows in the same PR

**M5-C — Workflow least-privilege hardening**
* Files allowed to change: the 3 `contents: write` workflow YAML files (declarations only, not job logic beyond what M5-D also touches)
* Files prohibited: scripts, tests, data
* Commands allowed: YAML linting/validation only, no execution
* Tests required: none (workflow YAML has no test harness in this repo)
* Network policy: none
* Evidence required: diff showing only permission-related or condition-related lines changed
* Pass criteria: no functional pipeline behavior changed beyond the explicit least-privilege/condition fix; Fail criteria: any unrelated workflow change
* Rollback: revert the workflow file changes
* PR size limit: 3 files
* Merge requirements: standard PR review; workflow changes should be manually dispatched once, post-merge, by a human, to confirm no regression (out of scope for this agent to trigger)
* Stop conditions: any required change beyond `if: always()` → `if: success()`

**M5-D — Fail-closed reliability-gate correction**
* Files allowed to change: `live-sync-qa.yml` only
* Files prohibited: everything else
* Commands allowed: none (offline YAML edit and review)
* Tests required: a new offline test (if a testable Python helper is extracted) or, at minimum, a clearly documented manual verification plan, since GitHub Actions YAML itself isn't unit-testable in this repo's current structure
* Network policy: none
* Evidence required: before/after YAML diff; explicit written trace of the corrected control flow
* Pass criteria: email step's `if:` includes the gate-failure check; Fail criteria: any other step's condition changed
* Rollback: revert the single line/condition change
* PR size limit: 1 file
* Merge requirements: standard PR review
* Stop conditions: ambiguity about correct GitHub Actions expression syntax for the combined condition

**M5-E — Offline tests and validation**
* Files allowed to change: new test file(s) under `tests/` only
* Files prohibited: `scripts/**` implementation logic (tests should test existing behavior, not require rewriting scripts, unless a script must be refactored into an importable function purely to make it testable — if so, that refactor is itself a separate, explicitly-scoped sub-step requiring its own authorization)
* Commands allowed: `pytest` (fixture-only, network-isolated, matching the Canonical Milestone 4 execution pattern)
* Network policy: `unshare --net --map-root-user`, matching prior milestones
* Evidence required: full CM4-style execution evidence (denial tests, namespace proof, secret scan)
* Pass criteria: new tests pass, existing 82 tests still pass, 0 regressions; Fail criteria: any existing test breaks
* Rollback: revert new test files
* PR size limit: new test files only
* Merge requirements: standard PR review plus a fresh execution-evidence gate, following the Canonical Milestone 4 precedent
* Stop conditions: any required change to non-test files beyond what M5-B/M5-D already covered

**M5-F — Documentation and closure**
* Files allowed to change: `AGENTS.md` or `README.md` (dependency/setup section addition) plus a closure doc/report pair, following the Canonical Milestone 4 closure precedent
* Files prohibited: everything else
* Commands allowed: none (documentation only)
* Tests required: none
* Network policy: none
* Evidence required: closure evidence following the same pattern as `docs/canonical-milestone-4-...-closure.md`
* Pass criteria: documentation accurately reflects M5-B through M5-E's actual merged state; Fail criteria: documentation describes unmerged/aspirational behavior as if already true
* Rollback: revert the documentation changes
* PR size limit: small, documentation-only
* Merge requirements: standard PR review
* Stop conditions: any implementation work discovered still outstanding when this phase begins

## Evidence

* Evidence directory: `/tmp/nycif-cm5-definition-readiness-09d3e88e`
* This document and its companion JSON report are the only two files this authorization permits creating.

## Final definition verdict

**READY_FOR_SEPARATE_M5_A_AUTHORIZATION**

**No implementation is authorized by this document.** M5-A through M5-F above are proposed phase definitions only; none has been executed, and no code, test, workflow, or dependency file has been created or modified as part of this gate beyond the two documentation/report files this authorization explicitly permits.
