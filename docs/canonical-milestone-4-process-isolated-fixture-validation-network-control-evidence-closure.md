# Canonical Milestone 4: Process-Isolated Fixture Validation Network-Control Evidence Closure

Milestone: Canonical Milestone 4
Milestone identifier: canonical-milestone-4-process-isolated-fixture-validation-network-control-evidence-closure

## Purpose

Record closure evidence for a process-isolated, network-denied, fixture-only pytest execution used to validate `tests/registry/test_xri_g42_fixture_only_validation_execution.py` under a minimal, explicitly allowlisted environment. This closure is evidence-of-execution only. It introduces no executable production behavior, no test changes, no script changes, and no tool changes.

## Starting baseline

* Starting HEAD SHA: `20576cc384bdcb63ed81e52d28ae6df095be0488`
* Starting committed tree SHA: `caf73c17a14cbc99f6ef8c71e5d0af7694a21eab`

## Interpreter and pytest identity

* Interpreter invocation path: `/root/.local/share/uv/tools/pytest/bin/python`
* Resolved interpreter: `/usr/bin/python3.11`
* Python version: `3.11.15`
* Interpreter SHA-256: `f56a588548dd013906ae1dcd1b6faa417f4e204da634ff354840d9643e78ff9e`
* pytest version: `9.0.2`
* pytest module: `/root/.local/share/uv/tools/pytest/lib/python3.11/site-packages/pytest/__init__.py`

## Isolation mechanism

* Network isolation: `unshare --net --map-root-user` (dedicated network namespace, loopback only, no external interface)
* Environment isolation: outermost invocation started from an empty environment via `env -i`, not a copy of the host environment
* Process/network syscall tracing: `strace -ff -e trace=network,process`

## Minimal environment allowlist

The execution environment supplied to the isolated wrapper, the denial-test process, the child launcher, and the pytest interpreter contained exactly these variable names and values:

```
PATH=/root/.local/share/uv/tools/pytest/bin:/usr/bin:/bin
HOME=/tmp/nycif-cm4-fixture-execution-r3-20576cc384bdcb63/home
LANG=C.UTF-8
LC_ALL=C.UTF-8
TMPDIR=/tmp/nycif-cm4-fixture-execution-r3-20576cc384bdcb63/tmp
PYTHONDONTWRITEBYTECODE=1
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
PYTHONHASHSEED=0
```

No credential-bearing variable (GitHub tokens, AWS credentials, Claude session/OAuth variables, proxy variables, Git credential variables, private Git configuration, cookies, authorization headers, cloud-provider credentials, SSH agent variables, or credential-file descriptors) was present in, or reached, the pytest process.

Note: the authorizing instructions referred to this as a "nine-name allowlist" in one section while listing eight variable names with eight values in another section. The eight explicitly named and valued variables above are what was constructed and verified; no ninth variable was specified with a value, so none was added. This discrepancy is recorded here rather than silently resolved.

## Direct parent and pytest-child namespace proof

* Parent wrapper PID `4089`, network-namespace identity `net:[4026532276]`, captured live via `/proc/self/ns/net` inside the parent process itself.
* Child launcher PID `4093`, network-namespace identity `net:[4026532276]`, captured live via `/proc/self/ns/net` inside the child process itself, before it executed pytest, and transmitted to the parent over a private synchronization pipe.
* Parent independently read `/proc/4093/ns/net` while PID 4093 was still alive (blocked waiting on the synchronization pipe) and observed `net:[4026532276]`.
* All three values (parent self-report, child self-report, parent's independent observation of the child) matched exactly before the parent signaled the child to proceed.
* `strace` process tracing shows PID `4093` first executing the child launcher, then the identical PID executing `execve("/root/.local/share/uv/tools/pytest/bin/python", ["...", "-m", "pytest", ...])` — proving the same captured child PID exec'd into the authorized pytest interpreter, preserving PID continuity, with no `setns`, second `unshare`, or namespace transition observed.

## Denial self-test result

Five standalone denial attempts were performed inside the isolated namespace, using the authorized interpreter, immediately before pytest:

1. DNS resolution of `example.com` — denied (`gaierror: Temporary failure in name resolution`)
2. TCP connection to `example.com:443` — denied (`gaierror: Temporary failure in name resolution`)
3. Direct-IP TCP connection to `1.1.1.1:443` — denied (`OSError: Network is unreachable`)
4. HTTPS request to `https://example.com/` — denied (`URLError: Network is unreachable`)
5. Raw `socket.connect()` to `1.1.1.1:443` — denied (`OSError: Network is unreachable`)

Attempts: 5. Successful connections: 0. Because proxy variables were excluded from the minimal environment (unlike the prior R2 run), no proxy-directed loopback connection occurred during the HTTPS test this time.

## Pytest command and result

```
/root/.local/share/uv/tools/pytest/bin/python -m pytest \
  -q \
  -p no:cacheprovider \
  --basetemp "/tmp/nycif-cm4-fixture-execution-r3-20576cc384bdcb63/pytest-tmp" \
  tests/registry/test_xri_g42_fixture_only_validation_execution.py
```

Result: collected 7, passed 7, failed 0, skipped 0, errors 0, exit code 0. Run exactly once. Cache disabled (`-p no:cacheprovider`). Temporary output directed outside the repository.

## Network-accounting result

* Successful external connections: 0
* Pytest/repository-process network syscalls: 0
* Unattributed connections: 0
* Every strace trace file mapped to a known, authorized PID (parent `4089`, child/pytest `4093`)

## Process-attribution result

Complete. Parent PID `4089` (PPID `4086`), child/pytest PID `4093` (PPID `4089`, observed independently by the parent via `/proc/4093/status`). No unexpected process or trace file was present.

## Repository-integrity result

* HEAD unchanged: `20576cc384bdcb63ed81e52d28ae6df095be0488`
* Committed tree unchanged: `caf73c17a14cbc99f6ef8c71e5d0af7694a21eab`
* Tracked working tree clean before and after
* Untracked-file inventory empty before and after

## Protected-file count and comparison

Protected-path inventory: 223 files across `data/**` (including `data/location_cache.json`), `scripts/**`, `tools/**`, `tests/**`, `.github/workflows/**`, and top-level feed/public-map metadata files. Identical file set and identical SHA-256 hashes before and after execution. (Earlier gates in this milestone reported 225 for the same file set; that count included two non-file header/timestamp lines in a differently-formatted manifest, not two additional protected files — the underlying protected file set was always 223.)

## Secret-scan result

All execution artifacts (wrapper source, child-launcher source, strace traces, stdout/stderr, integrity logs, protected-path manifests, environment-allowlist records, evidence manifest) were scanned for GitHub tokens, bearer/authorization values, authenticated URLs, Claude session/resume URLs, session identifiers, private keys, AWS access keys, passwords, cookies, `.netrc` content, credential-helper/store output, private Git configuration, proxy values, and high-entropy credential-like strings. Unresolved findings: 0.

## Evidence

* Local evidence directory: `/tmp/nycif-cm4-fixture-execution-r3-20576cc384bdcb63`
* Completed evidence-manifest SHA-256: `060c4b784bf3616a12eefe56a3e61c40da7a5828a0994ab5ea3f17b85a38c697`

## Prior (R2) deficiencies and how R3 resolved them

1. **Full host environment inheritance.** R2's wrapper used `env = dict(os.environ)`, passing the complete host environment — including `GH_TOKEN`, `GITHUB_TOKEN`, AWS credentials, Claude OAuth/session token file descriptors, and private Git configuration variable names — into the pytest subprocess. R3 starts the entire isolated invocation from an empty environment (`env -i`) and constructs an explicit minimal allowlist for every process in the chain, verified above.
2. **Inferred, not directly proven, pytest-child namespace inheritance.** R2 relied on the general Linux namespace-inheritance rule and a differently-shaped prior process pair. R3 directly captures the parent's own namespace, has the child self-report its live namespace over a private synchronization channel before it execs pytest, and has the parent independently read the child's `/proc/<pid>/ns/net` while the child is still alive and blocked — with all three values matching, and `strace` proving the same PID that reported its namespace is the PID that exec'd into pytest.

## Scope confirmation

No live source fetch, ingestion, scraping, geocoding, registry write, staging, approval, promotion, publishing, production, WordPress, public-map, or scheduled-workflow work occurred as part of this milestone's execution, remediation, or documentation.

## Final verdict

**PASS**

## Milestone status

**COMPLETE**

## Next phase

**NOT AUTHORIZED**
