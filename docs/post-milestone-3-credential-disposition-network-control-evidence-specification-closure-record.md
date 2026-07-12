# Post-Milestone-3 Credential Disposition and Network-Control Evidence Specification Closure Record

## Status

Documentation-only closure record.

- Repository: `setoxxx/nycif-live-feeds`
- Immutable operational SHA: `5a53177047590e4f3cdbbe92ab19388c3571c20f`
- Related milestone: Canonical Milestone 3 — fixture-only validation
- Milestone 3 status: Accepted for fixture-only validation
- Credential value recorded: No
- Original evidence ZIP publication authorized: No
- Closure date: `2026-07-11`
- Confirmation source: repository-owner confirmation supplied outside the repository

## 1. Credential disposition

The original Canonical Milestone 3 evidence ZIP contained an authenticated GitHub HTTPS remote with an embedded GitHub App installation token.

The credential value is not reproduced in this record.

The repository owner confirmed that:

- the exposed GitHub App token is expired;
- it will not be reused; and
- the original Milestone 3 evidence ZIP will remain private.

Credential disposition: `CONFIRMED_EXPIRED`

Credential-disposition closure: `CLOSED`

The original evidence ZIP must remain private and must not be committed, attached to a pull request or issue, uploaded to a release, posted to a public website, or stored in public cloud storage. Only a sanitized derivative may be considered for later publication.

## 2. Final network-control evidence specification

This specification governs any future execution gate that could import, invoke, or otherwise reach code with network capability. It does not authorize such a gate.

### Isolation requirement

A future execution gate must use one primary process-level isolation control from this hierarchy:

1. Runtime or container network disabled.
2. Dedicated network namespace with no external interface.
3. Process-scoped firewall, seccomp, eBPF, or equivalent outbound-denial policy.
4. Proven socket-denial injection attached to the exact interpreter and inherited subprocesses.

Proxy variables alone are insufficient as the primary control and may be used only as defense in depth.

### Fail-closed rule

The gate must stop with `BLOCKED` before executing repository code when:

- the selected isolation mechanism cannot be established;
- the exact test process cannot be shown to inherit the isolation;
- the denial self-test unexpectedly succeeds;
- network-attempt logging is unavailable;
- platform traffic cannot be separated from repository-process traffic; or
- credentials appear in the command log, environment capture, Git remote output, or evidence package.

The operator must not weaken isolation to make a test pass.

### Required process-level proof

Evidence must record:

- parent process ID;
- test interpreter process ID;
- subprocess tree;
- isolation mechanism;
- exact attachment method;
- start time;
- end time;
- network policy identifier or configuration hash; and
- proof that child processes inherit or independently receive the same restriction.

A generic statement such as “network blocked” is insufficient.

### Denial self-test

Before repository code runs, the exact interpreter and isolation boundary must perform controlled attempts that verify denial.

At minimum:

- DNS resolution attempt;
- TCP connection attempt to a documented external test target;
- direct-IP TCP connection attempt;
- HTTPS connection attempt; and
- raw `socket.connect()` attempt.

The evidence must record the attempted destination, expected failure, actual failure, exception type or system error, exit code, and zero successful connections.

The self-test must run inside the same process environment used by the authorized test command.

### Socket-guard proof

When a Python socket guard is used, the evidence must include:

- guard filename;
- absolute path;
- SHA-256;
- loading mechanism;
- interpreter startup proof;
- process ID;
- proof that `socket.connect`, `socket.create_connection`, and relevant asynchronous connection methods are denied;
- attempt log; and
- subprocess inheritance test.

The fixture-only modules statically inspected for Milestone 3 do not themselves import network clients, and they reject live URLs, SODA targets, geocoding, registry writes, publishing, production targets, and related state fields. That static property does not replace process-level isolation for a future broader gate.

### Proxy controls

The following may be set as secondary controls:

- `HTTP_PROXY`
- `HTTPS_PROXY`
- `ALL_PROXY`
- lowercase equivalents
- empty or deny-all `NO_PROXY`

Evidence must confirm exact redacted values, that no external proxy is reachable, that raw socket access remains independently denied, and that no `NO_PROXY` bypass exists.

### Project traffic versus platform traffic

Every observed connection must be classified as one of:

1. repository execution traffic;
2. Git traffic used before isolation to obtain the immutable SHA;
3. package-manager traffic before isolation;
4. Cursor or cloud-agent telemetry;
5. browser or VNC traffic; or
6. unrelated host traffic.

Only category 1 counts as project network activity.

The separation method must use one or more of process ID attribution, cgroup attribution, network namespace attribution, executable path, parent-process relationship, or process start and end timestamps. Host-level logs without process attribution are insufficient.

### Attempt and success accounting

The final record must report:

- project network attempts;
- project successful connections;
- blocked connection attempts;
- unattributed connections;
- platform telemetry connections; and
- evidence gaps.

A PASS requires:

- project successful connections: `0`;
- unattributed connections during the test interval: `0`;
- isolation self-test: `PASS`; and
- process attribution: complete.

### Repository-integrity requirements

The gate must capture:

- initial Git status;
- final Git status;
- pre-run tree hash;
- post-run tree hash;
- protected-path hashes;
- untracked-file inventory;
- branch name or detached status;
- commit SHA; and
- evidence directory location.

No cleanup may occur before final integrity evidence is recorded. Any unauthorized tracked or untracked repository mutation causes `FAIL`.

### Authority boundary

A network-control PASS does not authorize live-source ingestion, registry writes, geocoding, approval, promotion, publishing, staging, production, WordPress, or public-map output.

The inspected fixture-only chain preserves stable identity through `group_key`, `display_location`, and `candidate_identity`, while treating `review_rank` as display-only.

The manual-review and audit layers also reject approval, promotion, publishing, geocoding, production readiness, and public-runtime readiness.

## 3. Secret-handling checklist

### Pre-execution

- Use a sanitized Git remote display.
- Do not print credential-bearing remote URLs.
- Do not print authorization headers.
- Do not print environment variables containing secrets.
- Do not include credential-helper output.
- Do not include private Git configuration.
- Do not include SSH private keys or agent material.
- Use temporary credentials only when unavoidable.
- Ensure temporary credentials expire promptly.

### During execution

- Redact secrets before writing logs.
- Record only sanitized destination identifiers.
- Avoid full environment dumps.
- Avoid `git config --list --show-origin` unless filtered.
- Avoid `env`, `set`, or `printenv` without an allowlist.
- Avoid verbose HTTP-client output that may expose headers.
- Avoid authenticated URLs in command logs.
- Do not place credentials in command-line arguments.

### Before packaging

Run a secret scan over every artifact for patterns including GitHub tokens, bearer tokens, authorization headers, authenticated HTTP URLs, private keys, access keys, passwords, cookies, `.netrc` content, Git credential-store output, and cloud-provider tokens.

The package must record:

- scanner or method used;
- scan scope;
- number of findings;
- disposition of each finding; and
- final unresolved-secret count.

A package may pass only when the final unresolved-secret count is zero and every detected finding has a documented disposition.

## 4. Closure verdict

`VERDICT: CLOSED`

The credential disposition is `CONFIRMED_EXPIRED`.

The network-control evidence specification is complete.

The secret-handling checklist is complete.

Canonical Milestone 3 remains accepted only for fixture-only validation.

No Canonical Milestone 4 work is authorized.

## 5. Authorization boundary

This record closes only the credential-disposition blocker.

It does not authorize:

- execution;
- live fetch;
- ingestion;
- registry writes;
- geocoding;
- staging;
- promotion;
- publishing;
- production;
- WordPress;
- public-map work; or
- Canonical Milestone 4.

Any later work requires separate, explicit authorization using a then-current repository baseline.
