# Canonical Milestone 7-A: Shared GPS Identity Helper Foundation

Milestone: Canonical Milestone 7-A
Verified baseline SHA: `8796d64ea628007327e715f0995c16e6ab071c78` (Canonical Milestone 6 merge; verified equal to `origin/main` at execution time)
Branch: `canonical-milestone-7a-identity-helper-foundation`
Merge base with `origin/main`: `8796d64ea628007327e715f0995c16e6ab071c78` (branch created at, and ahead/behind 0/0 from, the baseline before this work; this milestone adds one implementation commit on top — the head SHA is recorded on the pull request)

## Exact scope

Canonical Milestone 7-A only: inventory all active normalization/identity logic, separate active from historical and fixture-only systems, create one shared active-pipeline helper module preserving every existing valid identity output bit-for-bit, prove compatibility with deterministic tests, and document the contract and the M7-B migration plan.

**Not** in scope and **not** performed: M7-B caller migration, duplicate-key enforcement, positional review-array changes, any `data/**` change, any workflow change, any deployment/public-map/WordPress change, any website, API, account, notification, chat, geofencing, iOS, or Android feature.

## Exact changed files

1. `scripts/gps_identity.py` — new shared helper module (no caller imports it yet).
2. `tests/registry/test_canonical_milestone_7a_gps_identity_helper.py` — new compatibility/regression suite (239 tests).
3. `docs/canonical_milestone_7a_normalization_inventory.md` — new complete inventory.
4. `docs/canonical_milestone_7a_identity_helper_foundation.md` — this document.

No other file was created, modified, or deleted. The optional narrow updates to `docs/gps_identity_model.md` / `docs/gps_pipeline_data_flow.md` were **not** needed: both remain accurate as Milestone 6 audit documents of caller-owned code, which M7-A does not change.

## Inventory summary (full detail: `docs/canonical_milestone_7a_normalization_inventory.md`)

- **Active** (`scripts/`): two normalization profiles — the legacy profile (`norm()`, nine bit-identical copies) and the ampersand profile (`norm_text()`/`normalize()`, three bit-identical copies) — plus four identity builders (`group_key`, `stable_key`, `stable_event_identity` ×2 copies, `candidate_keys`) and their accessor families (three deliberately distinct location accessors; two deliberately distinct CEMSID readers).
- **Historical** (`tools/registry/xri_g6`–`xri_g11`): dash-separated `slug()` + SHA-256 `candidate_identity_key`. Untouched; never a migration target.
- **Fixture-only** (`tools/registry/xri_g40`–`xri_g44`): whitespace-collapse-only `_clean_text()` + caller-supplied identity tuple. Untouched; never a migration target.
- `review_rank` remains display-only everywhere; the helper takes no `review_rank` or row-position input by construction, and a key-access recorder test proves no helper function even reads the key.

## Helper API (`scripts/gps_identity.py`)

| Function | Compatibility profile preserved |
|---|---|
| `normalize_text_legacy(value)` | `norm()` — 9 active copies; no ampersand expansion |
| `normalize_text_with_ampersand(value)` | `norm_text()`/`normalize()` — 3 active copies; `&` → `" and "` |
| `row_location(row)` | staged-feed location accessor (no strip, no address fallback) |
| `event_cemsids(row)` | staged-feed CEMSID set (no strip, no comma-split) |
| `build_group_key(row)` | `group_key()` — review-group identity |
| `build_stable_identity_key(row)` | `stable_key()` — registry-side stable identity |
| `build_stable_event_identity(row)` | `stable_event_identity()` — staged-event natural key |
| `build_repository_candidate_keys(row)` | `candidate_keys()` — location-cache candidate keys |

Module properties (all test-enforced): deterministic; side-effect free (inputs never mutated); importable (`from scripts import gps_identity`); typed; documented (each docstring names its source caller); no file I/O, network, current-time, environment-variable, or geocoding access; no global mutable state; deterministic sorting of identity collections; the two normalization profiles are deliberately NOT collapsed.

## Bit-for-bit compatibility result

- **Changed valid identity count: 0.** `test_zero_identity_changes_across_full_matrix` compares all four identity builders against oracle functions copied verbatim from the current caller sources across a 26-row edge-case matrix (missing fields, punctuation, ampersands, Unicode, numerics, booleans, whitespace-only values, comma CEMSID strings, list CEMSIDs with duplicates/padding, group-key overrides, fallback-precedence rows) and reports every mismatching input/output pair; it passes with zero.
- Golden literal anchors (independent of both helper and oracles) pin key outputs, including `"bryant park 42nd st"` vs `"bryant park and 42nd st"` for the two profiles and the full five-component `stable_event_identity` string for a fully populated row.

## Migration-map status

Documented in the inventory (Section G), **not executed**. Each of the twelve active caller files is mapped to its exact helper replacement and profile. The primary M7-B hazard — migrating a legacy-profile call site onto the ampersand profile or vice versa — is mitigated by helper docstrings naming their source callers and by the inventory's per-profile caller table.

## Test commands and results

All commands run from the repository root at the worktree for this branch; pytest interpreter is the established uv-tool environment (`pytest 9.0.2`, Python 3.11.15).

| Command | Result | Exit code |
|---|---|---|
| `python -m pytest tests/registry/test_canonical_milestone_7a_gps_identity_helper.py -q` | 239 passed | 0 |
| `python -m pytest tests/registry -q` | 337 passed | 0 |
| `python -m pytest -q` (full suite) | 349 passed (110 pre-existing + 239 new) | 0 |
| `python3 -m compileall scripts tools tests` | OK | 0 |
| `python3 -c "from scripts import gps_identity; print('import-ok')"` | `import-ok` | 0 |
| Repository-wide helper/identity pattern search (`grep -rnE "def (norm\|normalize\|...)"` per the M7-A specification) | inventory complete; results recorded in the inventory document | 0 |

## Network-isolation evidence

Measured, not assumed: the targeted + registry suites (337 tests) were additionally executed under `env -i` (minimal variable allowlist) inside `unshare --net --map-root-user`, passing identically (exit 0). A five-attempt denial probe (DNS resolution, hostname TCP, direct-IP TCP, HTTPS, raw `socket.connect()`) executed under the same `env -i` + `unshare --net --map-root-user` invocation shape reported **0 successful connections** (all five denied). Limitation stated for precision: the denial probe ran as a separate process launch with the same isolation configuration, not as a parent/child PID-pinned capture of the pytest process itself (the stricter Milestone 4 protocol); the helper module additionally contains no network-capable import, which the test suite verifies statically and at call time.

## Compile / import result

`python3 -m compileall scripts tools tests` exit 0; `from scripts import gps_identity` prints `import-ok` (PEP 420 namespace-package import from the repository root, matching how the existing `tools.registry` test imports already work).

## Secret scan result

Pattern scan (AWS key IDs, GitHub tokens, Slack tokens, private-key blocks, assigned `api_key`/`password`/`secret`/`token` values, `Authorization:` headers) over all four changed files: **zero matches**. No credential value appears in any changed file.

## Repository integrity result

- `git status`: only the four in-scope files; `__pycache__`/`.pytest_cache` artifacts generated during validation were removed before commit.
- `git diff --name-only origin/main...HEAD` before commit: empty (branch exactly at baseline); after commit: exactly the four files above.
- Protected paths untouched: no `data/**`, no `.github/workflows/**`, no deployment or configuration file, no public-map file, no WordPress code.
- Prohibited caller files untouched: `build_gps_repository.py`, `build_gps_review_groups.py`, `build_gps_geocoding_filled_proposals.py`, `build_gps_manual_approval_staging.py`, `generate_gps_staged_feed_integration_match_diagnostic.py`, `apply_gps_staged_feed_integration_update.py` (also test-pinned: `test_no_active_caller_was_migrated_in_m7a`, `test_active_callers_still_define_their_own_identity_functions`).
- PR #133 (unrelated draft, Cursor environment notes) untouched.

## Residual risks

1. **Oracle drift:** the test oracles are verbatim copies of caller algorithms at the M7-A baseline; if a caller's local algorithm were changed before M7-B migrates it, the oracle (and helper) would detect the divergence only via the caller-definition pin tests, not automatically. M7-B removes this window by making the helper the single definition.
2. **Profile misassignment at migration time:** choosing the wrong normalization profile during M7-B would change identity; mitigated by the inventory's per-caller profile table and helper docstrings, and by the requirement that M7-B re-run this compatibility suite.
3. **Known Milestone 6 gap unchanged by design:** `build_gps_repository.py`'s first-writer-wins silent duplicate skip remains; duplicate-key enforcement is deferred to its separately authorized milestone.
4. **Latent positional arrays unchanged by design:** `recommended_approve_rows`/`do_not_approve_rows` in the findings artifact remain written-but-never-read; explicitly out of M7-A scope.

## Planned M7-B migration targets

The twelve active caller files listed in the inventory's migration map (six identity-critical callers named in the M7-A specification plus the six additional `norm()` hosts), each migrating to the exact helper functions named there — under separate explicit authorization only.

## Explicit protected boundaries

No `data/**` change; no workflow change; no deployment or configuration change; no public-map, WordPress, or publishing change; no live-source ingestion; no external API call; no scraping; no geocoding; no promotion; no email action; PR #133 untouched.

## Relationship to future NYCIF platform identity consistency

The NYCIF platform plan (field-desk repository: platform dependency graph, feature registry, phase timeline) requires one trustworthy event identity before the app-facing API, map, story feed, notifications, accounts, and iOS/Android clients can be built (Phase 2 → Phase 3 gate). This helper is the single-definition foundation for that: every future website, API, map, notification, account, or mobile surface that needs to reference an event identity will, after M7-B migration, resolve it through one shared implementation instead of twelve independent copies — eliminating the class of cross-surface identity drift that would otherwise appear as duplicate map pins, broken saved-event references, or mismatched notification targets.

## Confirmations

- No runtime platform feature was implemented: no website, API, account, notification, chat, geofencing, mobile, publication, geocoding, promotion, WordPress, deployment, workflow, or public-map behavior was added or changed. The helper is inert until M7-B migrates callers.
- M7-B (caller migration), M7-C, duplicate-key enforcement, positional-array work, APIs, accounts, notifications, website runtime, and mobile all remain **unauthorized** by this milestone.
- Milestone 6 history is not rewritten; its audit documents are unchanged.

## SonarQube repair addendum (follow-up commit on PR #144)

SonarQube Cloud's first analysis of PR #144 failed the Quality Gate (Reliability Rating on New Code = C, required A) with two Major "Fix this condition that always evaluates to true" findings, both on the same pattern — the ``if str(item)`` filter inside the ``event_cemsids`` set comprehension:

1. `scripts/gps_identity.py` (helper implementation);
2. `tests/registry/test_canonical_milestone_7a_gps_identity_helper.py` (the verbatim oracle copy of the same caller code).

**Repair:** both comprehensions were restructured into an explicit loop that converts each item with ``str()`` exactly once and adds it only when the converted string is non-empty. Semantics are bit-for-bit identical to the callers' comprehension: `""` excluded; `None` → `"None"`, `0` → `"0"`, `False` → `"False"` all included; whitespace-only strings included (no stripping); duplicates collapsed by the set; input order irrelevant; no input mutation. The active caller files still contain the original comprehension form — they are unchanged (M7-B scope), and the oracle docstring now records that its loop form is a semantics-identical restructuring of the callers' code.

**Focused regression added:** `test_event_cemsids_sonar_repair_falsy_and_duplicate_items` — pins the exact falsy/duplicate/whitespace item semantics above against both helper and oracle, plus the resulting `stable_event_identity` agreement and input non-mutation.

**Post-repair validation (all exit 0):** targeted suite 240 passed; `tests/registry` 338 passed; full suite 350 passed; compileall OK; `import-ok`; changed valid identity count remains **0** (golden matrix re-run); secret scan zero matches; diff vs `origin/main` remains exactly the four authorized M7-A files.

## Final verdict

**PASS** (implementation and all locally executable required QA; external GitHub Actions / SonarQube status is reported on the pull request).
