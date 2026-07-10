# XRI-G99 Non-Production Controlled Live-Fetch Dry-Run Review Artifact Purge Verification Attestation Validation Disposition Boundary Gate

## Status

Documentation and report boundary gate only.

This phase defines a proposed non-authoritative attestation-validation disposition contract. It does not execute validation, evaluate an actual package, create an actual disposition record, or grant operational authority.

## Source State

Repository: `setoxxx/nycif-live-feeds`

Current baseline:

- Base branch: `main`
- Base commit: `31f52641848451b306c7b742e782de322648b88f`
- PR #129 is merged.
- PR #110 remains open and unmerged.
- No XRI-G99 branch, pull request, commit, file, implementation, or executable behavior existed before this phase was separately authorized.

## Phase Identity

- Phase number: `XRI-G99`
- Exact title: `XRI-G99 Non-Production Controlled Live-Fetch Dry-Run Review Artifact Purge Verification Attestation Validation Disposition Boundary Gate`
- Track identifier: `controlled_live_fetch_review_artifact_track`
- Proposed branch: `xri-g99-attestation-validation-disposition-boundary-gate`
- Documentation path: `docs/xri-g99-non-production-controlled-live-fetch-dry-run-review-artifact-purge-verification-attestation-validation-disposition-boundary-gate.md`
- Report path: `data/reports/xri_g99_non_production_controlled_live_fetch_dry_run_review_artifact_purge_verification_attestation_validation_disposition_boundary_gate_report.json`
- Baseline branch: `main`
- Baseline commit: `31f52641848451b306c7b742e782de322648b88f`

The phase identity must use the combined phase number, exact title, track identifier, exact allowed paths, proposed branch, predecessor identity, and immutable commit references.

The phase number alone is not sufficient identity.

## Immediate Predecessor

- Phase: `XRI-G98`
- Exact title: `XRI-G98 Namespace Reconciliation and Continuation-Map Boundary Gate`
- Pull request: `#129`
- Merge commit: `31f52641848451b306c7b742e782de322648b88f`

XRI-G98 is the immediate repository predecessor because it reconciled the phase-number collision, reserved XRI-G99 as the earliest available continuation number, required explicit track identification, and required a then-current `main` baseline.

## Logical Lifecycle Predecessor

- Phase: `XRI-G82`
- Exact title: `XRI-G82 Non-Production Controlled Live-Fetch Dry-Run Review Artifact Purge Verification Attestation Validation Boundary Gate`
- Pull request: `#128`
- Merge commit: `1a5910896a855635941f81a6e60b7be351d7053f`

XRI-G82 is the logical lifecycle predecessor because it defined the structural attestation-validation boundary, non-authoritative validation vocabulary, stable identity requirements, evidence restrictions, failure-stop requirements, and the separation between structural validation and acceptance, approval, certification, publishing, staging, registry import, production export, or public-map release.

## Purpose

XRI-G99 defines the contract for classifying a future structural attestation-validation result into one of six controlled, non-authoritative dispositions.

The contract is limited to:

- disposition vocabulary
- required record fields
- stable identity requirements
- validation, attestation, and purge-verification reference requirements
- deterministic first-match decision precedence
- scope, version, identity, and cross-reference consistency rules
- evidence minimization
- confidential-data exclusion
- artifact isolation
- result-artifact recording limits
- later-review limits
- mandatory processing stops
- no-write declarations
- no-authority declarations

XRI-G99 does not perform an actual validation or disposition.

## Allowed Files

Exactly two files are allowed for XRI-G99:

- `docs/xri-g99-non-production-controlled-live-fetch-dry-run-review-artifact-purge-verification-attestation-validation-disposition-boundary-gate.md`
- `data/reports/xri_g99_non_production_controlled_live_fetch_dry_run_review_artifact_purge_verification_attestation_validation_disposition_boundary_gate_report.json`

No third file may be created.

No existing file may be modified, renamed, moved, or deleted.

## Controlled Non-Production Boundary

The contract applies only to controlled non-production review and audit artifacts.

It must not:

- call a live source
- execute a dry run
- perform a purge
- verify an actual purge
- validate an actual attestation
- issue or sign an attestation
- accept, reject, approve, revoke, or supersede an attestation
- certify deletion
- perform certificate validation
- perform cryptographic verification
- authorize operational execution
- modify registry, production, public-map, WordPress, scheduled-workflow, cache, or location-cache targets

## Permitted Disposition Vocabulary

The only permitted disposition values are:

1. `structurally_valid_for_review_storage_only`
2. `structurally_valid_for_audit_reference_only`
3. `structurally_valid_for_later_gate_review_only`
4. `structurally_invalid_for_review`
5. `validation_incomplete`
6. `validation_blocked`

No synonym, abbreviation, inferred status, approval status, rejection status, or operational status is permitted.

## Disposition Meaning and Interpretation Rules

### `structurally_valid_for_review_storage_only`

Meaning:

The referenced validation package is complete, resolved, internally consistent, correctly scoped, and structurally valid for controlled non-production review storage only.

Required conditions:

- `validation_result` is `structurally_valid`.
- All required fields are complete.
- All core references resolve.
- Identity, version, scope, cross-reference, evidence-minimization, confidentiality, artifact-isolation, forbidden-anchor, and no-write checks pass.
- `disposition_purpose` is `review_storage_only`.

Prohibited interpretation:

- not attestation acceptance
- not attestation rejection
- not approval
- not legal certification
- not cryptographic verification
- not promotion
- not publishing
- not staging
- not registry import
- not production export
- not public-map release

Recording and continuation:

- A minimized controlled non-production result artifact may be recorded only in an explicitly permitted review-storage location.
- Later review is allowed only as review of the stored non-authoritative artifact.
- Processing must stop immediately after recording or deciding not to record.
- Authority granted is always `false`.

### `structurally_valid_for_audit_reference_only`

Meaning:

The referenced validation package is structurally valid and may be referenced by a controlled non-production audit record only.

Required conditions:

- `validation_result` is `structurally_valid`.
- All required fields are complete.
- All core references resolve.
- Identity, version, scope, cross-reference, evidence-minimization, confidentiality, artifact-isolation, forbidden-anchor, and no-write checks pass.
- `disposition_purpose` is `audit_reference_only`.

Prohibited interpretation:

- not proof that purge or deletion occurred
- not proof that purge or deletion was independently verified
- not attestation acceptance
- not attestation rejection
- not approval
- not legal certification
- not signature validity
- not cryptographic verification
- not production authority

Recording and continuation:

- A minimized controlled non-production audit-reference artifact may be recorded.
- Later review is allowed only for non-authoritative audit inspection.
- Processing must stop immediately after recording or deciding not to record.
- Authority granted is always `false`.

### `structurally_valid_for_later_gate_review_only`

Meaning:

The referenced validation package is structurally valid enough to be considered by a separately authorized future gate.

Required conditions:

- `validation_result` is `structurally_valid`.
- All required fields are complete.
- All core references resolve.
- Identity, version, scope, cross-reference, evidence-minimization, confidentiality, artifact-isolation, forbidden-anchor, and no-write checks pass.
- `disposition_purpose` is `later_gate_review_only`.

Prohibited interpretation:

- not authorization or start of a later gate
- not automatic continuation
- not attestation acceptance
- not attestation rejection
- not approval
- not promotion
- not publishing
- not staging
- not registry import
- not production export
- not public-map release

Recording and continuation:

- A minimized controlled non-production future-review reference may be recorded.
- Later review is allowed only under a separately approved future gate using a then-current baseline.
- Processing must stop immediately after recording or deciding not to record.
- Authority granted is always `false`.

### `structurally_invalid_for_review`

Meaning:

The required records resolve and are sufficiently complete to evaluate, but one or more structural consistency, scope, identity, version, cross-reference, evidence, or isolation checks fail without triggering a hard safety block.

Required conditions:

- The package is not blocked.
- The package is not merely incomplete.
- All core references required for evaluation resolve.
- At least one deterministic structural check fails.

Prohibited interpretation:

- not attestation rejection
- not attestation revocation
- not attestation supersession
- not proof that the underlying purge, deletion, or validation failed
- not legal invalidity
- not a production decision

Recording and continuation:

- A minimized controlled non-production structurally-invalid result artifact may be recorded.
- Later review is allowed only after remediation and separate authorization.
- Processing must stop.
- Authority granted is always `false`.

### `validation_incomplete`

Meaning:

The package cannot receive a conclusive structural disposition because required information, declarations, references, or purpose values are absent, empty, ambiguous, or not yet supplied.

Required conditions:

- No hard blocking safety condition is present.
- One or more mandatory fields, declarations, references, or purpose values are missing or ambiguous.

Prohibited interpretation:

- not structural validity
- not structural invalidity
- not attestation acceptance
- not attestation rejection
- not approval
- not a legal finding

Recording and continuation:

- A minimized controlled non-production incomplete result artifact may be recorded when recording itself requires no forbidden write.
- Later review is allowed only after missing information is supplied through a separately authorized process.
- Processing must stop until completion.
- Authority granted is always `false`.

### `validation_blocked`

Meaning:

Structural disposition cannot proceed because a prohibited, unsafe, unauthorized, sensitive, or fundamentally unresolvable condition exists.

Required conditions:

- At least one hard-block condition in the first-match decision matrix is present.

Prohibited interpretation:

- not attestation rejection
- not attestation revocation
- not attestation supersession
- not a legal finding
- not proof that the underlying real-world activity failed

Recording and continuation:

- Only a minimized controlled non-production blocked result artifact may be recorded, and only when recording itself requires no forbidden write and exposes no prohibited data.
- No artifact may be written when recording would require a forbidden write or expose prohibited data.
- Later review is not allowed until the blocking condition is resolved under separate authorization.
- Processing must stop immediately.
- Authority granted is always `false`.

## Required Disposition Record Fields

Every conclusive disposition record must contain all of the following fields:

- `disposition_identifier`
- `disposition_version`
- `disposition_status`
- `disposition_purpose`
- `disposition_reason_codes`
- `disposition_timestamp_declaration`
- `disposition_actor_declaration`
- `disposition_actor_authority_declaration`
- `disposition_method_declaration`
- `track_identifier`
- `phase_identity`
- `repository`
- `branch_name`
- `head_sha`
- `pull_request_number`
- `predecessor_phase_identity`
- `predecessor_pull_request`
- `predecessor_merge_commit`
- `logical_lifecycle_predecessor_phase_identity`
- `logical_lifecycle_predecessor_pull_request`
- `logical_lifecycle_predecessor_merge_commit`
- `validation_record_reference`
- `validation_identifier`
- `validation_version`
- `validation_result`
- `validation_scope`
- `attestation_record_reference`
- `attestation_identifier`
- `attestation_version`
- `attestation_scope`
- `purge_verification_record_reference`
- `purge_verification_scope_reference`
- `stable_candidate_identity`
- `source_identity_summary`
- `required_field_completeness_summary`
- `cross_reference_consistency_summary`
- `scope_consistency_summary`
- `identity_consistency_summary`
- `version_consistency_summary`
- `forbidden_anchor_rejection_summary`
- `artifact_isolation_summary`
- `evidence_minimization_declaration`
- `confidential_data_exclusion_declaration`
- `forbidden_path_exclusion_declaration`
- `no_write_declaration`
- `no_registry_write_declaration`
- `no_production_write_declaration`
- `no_public_map_write_declaration`
- `no_wordpress_write_declaration`
- `no_scheduled_workflow_write_declaration`
- `no_location_cache_write_declaration`
- `no_cache_write_declaration`
- `non_authoritative_disposition_declaration`
- `disposition_is_not_acceptance_declaration`
- `disposition_is_not_rejection_declaration`
- `disposition_is_not_approval_declaration`
- `disposition_is_not_promotion_declaration`
- `disposition_is_not_publishing_declaration`
- `disposition_is_not_staging_declaration`
- `disposition_is_not_registry_import_declaration`
- `disposition_is_not_production_export_declaration`
- `disposition_is_not_public_map_release_declaration`
- `disposition_is_not_legal_certification_declaration`
- `disposition_is_not_cryptographic_verification_declaration`
- `disposition_does_not_authorize_execution_declaration`
- `result_artifact_recording_status`
- `later_review_allowed`
- `processing_stop_required`
- `authority_granted`
- `failure_stop_summary`
- `next_phase_boundary_declaration`

Field rules:

- `disposition_identifier` must be immutable, non-empty, and unique within the repository and track.
- `disposition_version` must use `major.minor.patch`.
- `disposition_status` must equal one of the six permitted disposition values.
- `disposition_purpose` must equal `review_storage_only`, `audit_reference_only`, `later_gate_review_only`, or `not_applicable`.
- `disposition_reason_codes` must be a non-empty controlled array.
- `disposition_timestamp_declaration` must use RFC 3339 UTC.
- `disposition_actor_declaration` must identify the actor without unnecessary personal information.
- `disposition_actor_authority_declaration` must state `non_authoritative_structural_disposition_only`.
- `disposition_method_declaration` must identify the deterministic contract version used.
- `track_identifier` must equal `controlled_live_fetch_review_artifact_track`.
- `repository` must equal `setoxxx/nycif-live-feeds`.
- `head_sha` must be an exact immutable 40-character lowercase commit SHA.
- `validation_result` must equal `structurally_valid`, `structurally_invalid`, `incomplete`, or `blocked`.
- Each structural summary must contain `status`, `reason_codes`, and minimized `details`.
- Structural-summary status must equal `pass`, `fail`, `incomplete`, or `blocked`.
- `result_artifact_recording_status` must equal `recorded_controlled_non_production`, `permitted_but_not_recorded`, or `not_recorded_due_to_block`.
- `processing_stop_required` must always be `true`.
- `authority_granted` must always be `false`.
- Every authority and no-write declaration must be explicit and must not be inferred.

For `validation_incomplete` or `validation_blocked`, unavailable values must be represented by explicit controlled status objects.

Values must not be omitted, guessed, synthesized, or assigned misleading defaults.

## Validation-Result Input Contract

A future disposition process may consume only a controlled structural validation record that provides:

- a resolvable `validation_record_reference`
- `validation_identifier`
- `validation_version`
- `validation_result`
- `validation_scope`
- a resolvable `attestation_record_reference`
- `attestation_identifier`
- `attestation_version`
- `attestation_scope`
- a resolvable `purge_verification_record_reference`
- `purge_verification_scope_reference`
- stable candidate identity
- actor and authority declarations
- timestamp and method declarations
- evidence and isolation summaries
- no-write declarations
- non-authoritative validation declarations

The input contract must not treat validation as acceptance, rejection, approval, certification, attestation replacement, purge-verification replacement, or operational authorization.

## Stable Candidate Identity Rule

`stable_candidate_identity` must contain:

- `candidate_identity`
- at least one corroborating stable value from `group_key` or `display_location`

The following rules apply:

- An attestation identifier may supplement but must not replace stable candidate identity.
- A validation identifier may supplement but must not replace stable candidate identity.
- Candidate identity must resolve consistently across the validation, attestation, purge-verification, and disposition references.
- A conflict between stable identity values maps to `structurally_invalid_for_review`.
- A present but unresolvable stable identity maps to `validation_blocked`.
- A missing stable identity maps to `validation_incomplete`.

## Forbidden Identity Anchors

The following fields must not be used as identity:

- `review_rank`
- row position
- array index
- source row order
- source sort order
- reviewer sort order
- mutable review status
- mutable review reason
- mutable review notes
- approval state
- promotion state
- publishing state
- geocoding state
- coordinates
- geometry
- production path
- public runtime path

Use of any forbidden identity anchor maps immediately to `validation_blocked`.

## Cross-Reference Resolution Requirements

The process must resolve and compare:

- validation record to validation identifier and version
- validation record to attestation identifier and version
- attestation record to purge-verification reference and scope
- validation scope to attestation scope
- attestation scope to purge-verification scope
- stable candidate identity across all referenced records
- actor and authority declarations
- method and timestamp declarations
- evidence references
- artifact-isolation declarations
- predecessor phase and merge references

A missing reference maps to `validation_incomplete` when it has not yet been established as unresolvable.

A reference that exists but cannot be resolved maps to `validation_blocked`.

Resolved but conflicting references map to `structurally_invalid_for_review`.

## Scope-Consistency Requirements

The required scope relationship is:

1. `validation_scope` must be equal to or narrower than `attestation_scope`.
2. `attestation_scope` must be equal to or narrower than `purge_verification_scope_reference`.
3. No disposition scope may exceed `validation_scope`.
4. No scope may imply authority beyond structural non-production review.

Scope outcomes:

- Missing scope information maps to `validation_incomplete`.
- Unresolvable scope references map to `validation_blocked`.
- Validation scope exceeding attestation scope maps to `structurally_invalid_for_review`.
- Attestation scope exceeding purge-verification scope maps to `structurally_invalid_for_review`.
- A scope that requires a forbidden write or operational action maps to `validation_blocked`.

## Version-Consistency Requirements

The process must verify consistency among:

- disposition contract version
- disposition record version
- validation version
- attestation version
- purge-verification record version when present
- referenced schema or method versions

Version outcomes:

- Missing required version information maps to `validation_incomplete`.
- Present but unresolvable version references map to `validation_blocked`.
- Resolved but inconsistent version references map to `structurally_invalid_for_review`.
- Version consistency does not establish legal, cryptographic, or operational validity.

## Deterministic Decision Precedence

The decision mode is `first_match_wins`.

Rules are evaluated from priority 1 through priority 7.

Once a rule matches, no lower-priority rule may alter the disposition.

Priority order:

1. `validation_blocked`
2. `validation_incomplete`
3. `structurally_invalid_for_review`
4. `structurally_valid_for_review_storage_only`
5. `structurally_valid_for_audit_reference_only`
6. `structurally_valid_for_later_gate_review_only`
7. default `validation_incomplete`

Decision-boundary clarifications:

- A missing required reference maps to `validation_incomplete`; a reference that is present but cannot be resolved maps to `validation_blocked`.
- Missing actor authority maps to `validation_incomplete`; explicitly unauthorized actor authority maps to `validation_blocked`.
- Missing evidence metadata maps to `validation_incomplete`; prohibited sensitive evidence content maps to `validation_blocked`.
- A non-sensitive structural isolation mismatch with all records available maps to `structurally_invalid_for_review`.
- Inability to maintain isolation without exposure or forbidden writes maps to `validation_blocked`.
- A field-completeness failure maps to `structurally_invalid_for_review` only when every required field is present but a supplied value violates the contract.
- Absent, empty, null, or ambiguous required fields map to `validation_incomplete`.
- Resolved scope, version, identity, or cross-reference conflicts map to `structurally_invalid_for_review`.
- The three structurally valid dispositions are mutually exclusive because `disposition_purpose` must contain exactly one controlled valid-purpose value.

## Deterministic Decision Matrix

### Priority 1 — `validation_blocked`

Select `validation_blocked` when any of the following is true:

- `validation_result` is `blocked`.
- A forbidden identity anchor is used.
- A core validation, attestation, purge-verification, candidate-identity, actor-authority, or artifact-isolation reference exists but cannot be resolved.
- Actor authority is explicitly unauthorized.
- Evidence contains credentials, authentication tokens, API keys, secrets, cryptographic keys, certificates, signatures, unrestricted filesystem paths, unnecessary personal information, or prohibited confidential content.
- The proposed result implies acceptance, rejection, approval, promotion, publishing, staging, registry import, production export, public-map release, legal certification, signature validation, or cryptographic verification.
- Producing or recording the result requires a forbidden write.
- Artifact isolation cannot be maintained.

### Priority 2 — `validation_incomplete`

When Priority 1 does not match, select `validation_incomplete` when any of the following is true:

- `validation_result` is `incomplete`.
- A required field or declaration is absent, empty, ambiguous, or not supplied.
- A required reference is missing but no unsafe or unauthorized condition has occurred.
- `disposition_purpose` is absent, ambiguous, or outside the controlled purpose vocabulary.
- Actor, authority, timestamp, method, or required version declarations are missing.
- Stable candidate identity is missing.
- Required evidence metadata is missing.

### Priority 3 — `structurally_invalid_for_review`

When Priorities 1 and 2 do not match, select `structurally_invalid_for_review` when any of the following is true:

- `validation_result` is `structurally_invalid`.
- All core references resolve but version references conflict.
- Validation scope exceeds attestation scope.
- Attestation scope exceeds purge-verification scope.
- Stable identity values conflict.
- Cross-references disagree.
- Artifact isolation, evidence minimization, confidentiality exclusion, forbidden-path exclusion, or another structural requirement fails without sensitive-data exposure or a forbidden write.
- Every required field is present, but a supplied value violates the field contract.

### Priority 4 — `structurally_valid_for_review_storage_only`

When Priorities 1 through 3 do not match, select `structurally_valid_for_review_storage_only` only when all of the following are true:

- `validation_result` is `structurally_valid`.
- Every required field, reference, declaration, and structural summary passes.
- `disposition_purpose` is `review_storage_only`.

### Priority 5 — `structurally_valid_for_audit_reference_only`

When Priorities 1 through 4 do not match, select `structurally_valid_for_audit_reference_only` only when all of the following are true:

- `validation_result` is `structurally_valid`.
- Every required field, reference, declaration, and structural summary passes.
- `disposition_purpose` is `audit_reference_only`.

### Priority 6 — `structurally_valid_for_later_gate_review_only`

When Priorities 1 through 5 do not match, select `structurally_valid_for_later_gate_review_only` only when all of the following are true:

- `validation_result` is `structurally_valid`.
- Every required field, reference, declaration, and structural summary passes.
- `disposition_purpose` is `later_gate_review_only`.

### Priority 7 — default `validation_incomplete`

When no earlier rule matches, select `validation_incomplete`.

No other disposition is permitted.

## Result-Artifact Recording Rules

Recording a result artifact is optional and never grants authority.

Permitted recording statuses:

- `recorded_controlled_non_production`
- `permitted_but_not_recorded`
- `not_recorded_due_to_block`

Rules:

- Recording may occur only in an explicitly permitted controlled non-production review or audit artifact location.
- A recorded artifact must contain only the minimum information required to identify the non-authoritative result and its controlled references.
- A blocked artifact may be recorded only if recording requires no forbidden write and exposes no prohibited information.
- No artifact may be recorded when recording would expose sensitive data or require a forbidden write.
- A result artifact must not be used as registry input, production input, public-map input, WordPress input, scheduled-workflow input, or cache input.
- Recording never changes `processing_stop_required: true`.
- Recording never changes `authority_granted: false`.

## Later-Review Rules

Later review:

- requires separate explicit authorization
- requires a then-current repository baseline
- must identify its phase, track, branch, paths, predecessor, PR, and immutable commit references
- must not inherit execution authority from XRI-G99
- must not begin automatically

Disposition-specific rules:

- `structurally_valid_for_review_storage_only`: later review of the stored non-authoritative artifact is allowed.
- `structurally_valid_for_audit_reference_only`: later non-authoritative audit inspection is allowed.
- `structurally_valid_for_later_gate_review_only`: later review is allowed only under a separately approved future gate.
- `structurally_invalid_for_review`: later review is allowed only after remediation and separate authorization.
- `validation_incomplete`: later review is allowed only after missing information is supplied.
- `validation_blocked`: later review is prohibited until the blocking condition is resolved under separate authorization.

No disposition authorizes a subsequent phase.

## Failure-Stop Conditions

Every disposition requires `processing_stop_required: true`.

### Conditions mapping to `validation_blocked`

- Stable candidate identity is present but cannot be resolved.
- `review_rank`, row position, array index, source order, sort order, mutable status, mutable notes, coordinates, geometry, production path, or runtime path is used as identity.
- The validation record cannot be resolved.
- The attestation reference cannot be resolved.
- The purge-verification reference cannot be resolved.
- Actor authority is explicitly unauthorized.
- Evidence contains credentials, authentication tokens, API keys, secrets, cryptographic keys, certificates, signatures, unrestricted filesystem paths, unnecessary personal information, or prohibited confidential content.
- A disposition would imply acceptance, rejection, approval, promotion, publishing, staging, registry import, production export, public-map release, legal certification, signature validation, or cryptographic verification.
- A write is required to a registry, production, public-map, WordPress, scheduled-workflow, cache, location-cache, test, fixture, tool, script, or another forbidden target.
- Artifact isolation cannot be maintained.

### Conditions mapping to `validation_incomplete`

- Stable candidate identity is missing.
- A required validation, attestation, or purge-verification reference is missing but not yet proven unresolvable.
- Actor, authority, timestamp, method, purpose, or another required declaration is missing.
- A required field is blank, null, ambiguous, or omitted.
- Required evidence metadata is missing.
- The upstream validation result is incomplete.

### Conditions mapping to `structurally_invalid_for_review`

- Validation scope exceeds attestation scope.
- Attestation scope exceeds purge-verification scope.
- Version references are inconsistent.
- Cross-references conflict.
- Stable identity fields conflict.
- Required records resolve but do not describe the same candidate, attestation, validation, or purge-verification event.
- A complete package fails evidence-minimization, confidential-data exclusion, forbidden-path exclusion, isolation, or consistency checks without sensitive-data exposure or a forbidden write.
- Every required field is present, but a supplied value violates the field contract.

No failure-stop condition may be bypassed through manual interpretation, positional identity, mutable status, or an authority claim.

## Evidence-Minimization and Confidentiality Restrictions

Evidence must be limited to the minimum controlled non-production information required to associate a disposition with its validation, attestation, purge-verification, and stable candidate identity references.

The following content is prohibited:

- source credentials
- authentication tokens
- API keys
- production secrets
- private runtime configuration
- public-map deployment credentials
- WordPress credentials
- scheduled-workflow credentials
- cryptographic keys
- cryptographic signatures
- certificates
- unrestricted filesystem paths
- registry write paths
- production write paths
- public-map write paths
- WordPress write paths
- scheduled-workflow write paths
- cache write paths
- location-cache write paths
- unnecessary personal information
- unredacted confidential review content
- raw evidence when a controlled evidence reference is sufficient

Unsupported claims that purge, deletion, independent verification, legal certification, signature validity, or cryptographic validity occurred are prohibited.

## Artifact-Isolation Requirements

The proposed XRI-G99 artifacts must remain isolated:

- Only the two approved XRI-G99 paths are allowed.
- No existing file may be modified.
- No third file may be created.
- No fixture, test, generated artifact, runtime file, tool, script, workflow, registry record, production file, public-map file, WordPress file, cache file, or `data/location_cache.json` may be accessed for write.
- No disposition artifact is created by this boundary gate.
- No validation package is evaluated by this boundary gate.

Failure to maintain isolation maps to `validation_blocked`.

## No-Source-Call Boundary

XRI-G99 must not call, test, ping, fetch, scrape, download, sample, query, or validate against:

- NYC Open Data
- SODA
- external APIs
- geocoding services
- websites
- live external sources

XRI-G99 must not execute a live fetch or dry run.

## No-Write Boundary

XRI-G99 grants no write authority to:

- registry paths
- production paths
- public-map paths
- WordPress paths
- scheduled-workflow paths
- cache paths
- `data/location_cache.json`
- test paths
- fixture paths
- tool paths
- script paths
- generated runtime paths

Only the two approved documentation/report artifacts may be created in a separately authorized implementation step.

## No-Authority Boundary

A structural disposition is not:

- attestation issuance
- attestation signing
- attestation acceptance
- attestation rejection
- attestation approval
- attestation revocation
- attestation supersession
- legal certification
- certificate validation
- cryptographic verification
- deletion certification
- purge authorization
- purge-verification authorization
- registry import
- approval
- promotion
- publishing
- staging
- production export
- public-map release
- WordPress input
- scheduled-workflow input
- cache input
- permission to execute a live fetch
- permission to execute a dry run
- permission to start a subsequent phase

`authority_granted` must always be `false`.

## PR #110 Isolation Boundary

PR #110 is outside XRI-G99.

XRI-G99 must not:

- modify PR #110
- merge PR #110
- close PR #110
- rebase PR #110
- retarget PR #110
- review PR #110
- comment on PR #110
- rename or delete its branch
- treat PR #110 as completed
- decide whether PR #110 should be merged, closed, superseded, approved, or rejected

The XRI-G99 report must record only that PR #110 was observed as open and unmerged and remained untouched.

## No-Production Boundary

XRI-G99 must not modify or authorize modification of any production-facing:

- file
- code
- runtime
- workflow
- deployment
- export
- registry
- public-map output
- WordPress target
- scheduled workflow
- cache
- location cache
- test
- fixture
- tool
- script

XRI-G99 creates no production or public-runtime authority.

## Required Safety Assertions

The companion report must confirm:

- documentation/report-only scope
- exactly two allowed files
- no existing file modified
- no third file created
- no implementation created
- no executable behavior created
- no validation executed
- no actual disposition performed
- no disposition record created
- no live fetch executed
- no dry run executed
- no purge executed
- no actual purge verification executed
- no attestation issued
- no attestation signed
- no attestation accepted
- no attestation rejected
- no attestation approved
- no attestation revoked
- no attestation superseded
- no certificate validation performed
- no cryptographic verification performed
- no deletion certified
- no registry modified
- no production modified
- no public map modified
- no WordPress modified
- no scheduled workflow modified
- no cache modified
- `data/location_cache.json` untouched
- PR #110 untouched, open, and unmerged
- no subsequent phase authorized
- no subsequent phase started
- no automatic continuation

## Stop Condition

Stop after creating only the two approved XRI-G99 documentation and report files in a separately authorized implementation step.

Do not:

- merge
- execute validation
- make an actual disposition
- create a disposition record
- call a live source
- execute a dry run
- perform or verify a purge
- issue, sign, accept, reject, approve, revoke, or supersede an attestation
- certify deletion
- perform certificate or cryptographic validation
- write to a forbidden target
- modify or decide the status of PR #110
- begin a subsequent phase

## Next-Phase Boundary

XRI-G99 does not authorize or start a subsequent phase.

There is no automatic continuation.

Any future phase requires separate planning, explicit authorization, a then-current `main` baseline, a globally available phase number, an explicit track identifier, exact allowed paths, and a new stop condition.
