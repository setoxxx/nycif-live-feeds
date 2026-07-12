# Canonical Milestone 4 Process-Isolated Fixture-Only Validation Network-Control Evidence Gate Contract

## Status

Documentation-only definition gate.

- Repository: `setoxxx/nycif-live-feeds`
- Required immutable baseline: `ff50e799715865f1122f0b35b3d242df62c2edaf`
- Milestone: `Canonical Milestone 4`
- Exact title: `Canonical Milestone 4 — Process-Isolated Fixture-Only Validation Reproducibility and Network-Control Evidence Gate`
- Contract identifier: `canonical_milestone_4_process_isolated_fixture_validation_network_control_evidence_gate_contract`
- Contract version: `1.0.0`
- Authority granted by this file: `false`
- Automatic continuation: `false`
- Processing stop required: `true`

## Purpose

Define the review boundary for a possible later, separately authorized fixture-only validation execution under process-level outbound-network denial, complete process attribution, repository-integrity controls, and sanitized evidence capture.

This gate does not execute repository code or tests. It does not create an environment, install dependencies, select an executable runtime, or authorize a later command. It only defines the controls that a future authorization would have to satisfy.

## Immediate predecessor and baseline

The immediate predecessor is the post-Milestone-3 credential-disposition and network-control evidence closure merged at baseline `ff50e799715865f1122f0b35b3d242df62c2edaf`.

Canonical Milestone 3 remains accepted only for fixture-only validation. Its original evidence ZIP remains private. The exposed GitHub App installation token is recorded as `CONFIRMED_EXPIRED`, and the credential-disposition closure is `CLOSED`.

Any later gate must reverify the then-current `main` SHA. A baseline mismatch requires `BLOCKED` and a new explicit authorization.

## Candidate fixture-only lane

The existing candidate test target is:

`tests/registry/test_xri_g42_fixture_only_validation_execution.py`

The existing candidate implementation lane is limited to:

- `tools/registry/xri_g41_fixture_only_parser_normalizer.py`
- `tools/registry/xri_g42_fixture_only_validation_execution.py`

These paths are identified for future review only. This contract does not authorize their execution or modification.

## Process-level network isolation

A future execution gate must use one primary process-level isolation control from this hierarchy:

1. Runtime or container network disabled.
2. Dedicated network namespace with no external interface.
3. Process-scoped firewall, seccomp, eBPF, or equivalent outbound-denial policy.
4. Proven socket-denial injection attached to the exact interpreter and inherited subprocesses.

Proxy variables alone are insufficient as the primary control. They may be used only as defense in depth.

The future gate must record the selected mechanism, attachment method, policy identifier or configuration hash, parent process ID, interpreter process ID, subprocess tree, start time, end time, and proof that child processes inherit or independently receive the same restriction.

## Fail-closed conditions

A future execution gate must stop with `BLOCKED` before repository code runs when:

- the selected isolation mechanism cannot be established;
- the exact process cannot be shown to inherit the isolation;
- the denial self-test unexpectedly succeeds;
- network-attempt logging is unavailable;
- project traffic cannot be distinguished from platform or host traffic;
- unattributed connections exist during the test interval;
- a credential appears in a command, environment capture, Git remote display, log, or evidence package;
- the repository baseline differs from the separately authorized SHA; or
- any required protected-path or repository-integrity evidence is unavailable.

Isolation must not be weakened to make a test pass.

## Denial self-test

Before any repository code runs, the exact future interpreter and isolation boundary must perform controlled attempts covering:

- DNS resolution;
- hostname-based TCP connection;
- direct-IP TCP connection;
- HTTPS connection; and
- raw `socket.connect()`.

For every attempt, evidence must record a sanitized destination identifier, expected failure, actual failure, exception type or operating-system error, exit code, and whether a connection succeeded.

A passing self-test requires zero successful connections. It must run inside the same process environment and isolation boundary intended for the later fixture-only validation command.

## Process attribution and traffic accounting

Every observed connection during the authorized interval must be classified as one of:

1. repository execution traffic;
2. pre-isolation Git traffic;
3. pre-isolation package-manager traffic;
4. cloud-agent or platform telemetry;
5. browser or remote-desktop traffic; or
6. unrelated host traffic.

Attribution must use process ID, cgroup, network namespace, executable path, parent-child relationship, or bounded timestamps. Host-level logs without process attribution are insufficient.

The final future record must report:

- project network attempts;
- project successful connections;
- blocked attempts;
- unattributed connections;
- platform telemetry connections; and
- evidence gaps.

A future PASS requires:

- project successful connections: `0`;
- unattributed connections: `0`;
- isolation self-test: `PASS`; and
- process attribution: complete.

## Repository-integrity controls

A future execution gate must capture, before cleanup:

- initial Git status;
- final Git status;
- pre-run tree hash;
- post-run tree hash;
- protected-path hashes;
- untracked-file inventory;
- branch or detached-head status;
- commit SHA; and
- evidence-directory location.

Any unauthorized tracked or untracked repository mutation causes `FAIL`.

Protected paths include, without limitation:

- `data/location_cache.json`
- `scripts/**`
- `tools/**`
- `tests/**`
- `.github/workflows/**`
- runtime feed files
- public-map files
- generated data artifacts
- registry data
- cache files
- dependency manifests
- environment files
- credentials
- the original Milestone 3 evidence ZIP

## Secret handling

Before execution:

- display only sanitized Git remotes;
- do not print authenticated URLs, authorization headers, secrets, private Git configuration, credential-helper output, SSH private-key material, or complete environment dumps;
- do not place credentials in command-line arguments.

During execution:

- redact secrets before logs are written;
- record only sanitized destination identifiers;
- avoid verbose client output that can expose headers;
- use allowlisted environment capture only.

Before packaging:

- scan every evidence artifact for GitHub tokens, bearer tokens, authorization headers, authenticated URLs, private keys, access keys, passwords, cookies, `.netrc` content, credential-store output, and cloud-provider tokens;
- record scanner or method, scope, finding count, disposition of each finding, and unresolved-secret count.

A future package may pass only when the unresolved-secret count is zero and every finding has a documented disposition.

## Definition-gate acceptance criteria

This documentation-only gate passes only when:

1. The branch starts from `ff50e799715865f1122f0b35b3d242df62c2edaf`.
2. Exactly the two authorized new files exist in the branch diff.
3. No existing file is modified, renamed, moved, or deleted.
4. No repository code or test is executed.
5. No virtual environment is created and no dependency is installed.
6. The exact future fixture-only target is identified without being executed.
7. Process-isolation, denial-self-test, attribution, integrity, and secret-handling requirements are defined.
8. The contract grants no execution authority.
9. PR #133 remains untouched.
10. The final gate status is `READY_FOR_SEPARATE_EXECUTION_AUTHORIZATION` or `BLOCKED`.

## Definition-gate failure and stop conditions

This gate must be `BLOCKED` if:

- the authorized baseline changed before branch creation;
- either authorized path conflicted with an existing file;
- any third file changed;
- any existing file changed;
- repository code or tests ran;
- an environment was created or dependencies were installed;
- PR #133 was modified;
- the contract weakened the post-Milestone-3 controls;
- a credential or authenticated URL was recorded; or
- this gate purported to authorize execution or operational work.

## Explicit authority boundary

This definition gate does not authorize:

- repository-code execution;
- test execution;
- virtual-environment creation;
- dependency installation;
- live fetch;
- source ingestion;
- API, SODA, or scraping access;
- geocoding;
- registry writes or imports;
- approval;
- staging;
- promotion;
- publishing;
- production;
- WordPress;
- public-map output;
- scheduled-workflow changes;
- cache or location-cache changes;
- modification, closure, reopening, or merger of PR #133; or
- automatic continuation to any later phase.

A future network-control PASS would not itself grant any of those authorities.

## Future authorization boundary

The smallest permissible later step is a separate authorization package that selects a then-current immutable baseline, exact interpreter identity, exact process-isolation mechanism, exact denial-self-test procedure, exact fixture-only command, exact evidence directory, exact protected-path hash set, and exact allowed output files.

Until that authorization is separately supplied, processing stops.

## Verdict

`READY_FOR_SEPARATE_EXECUTION_AUTHORIZATION`

This verdict confirms only that the documentation definition is complete. It grants no execution or operational authority.