# Projector V2 surgical patch specification

Status: REVIEWABLE PATCH SPEC ONLY — target file not modified by this document.

Target branch: `fix/projector-v2-semantic-cutover`
Target file: `scripts/project_events_discovery_v02.py`
Target PR: #384

## Editing rule

Use a true line-level/patch-level repository editor. Do not reconstruct or whole-file replace the projector. Do not reformat unrelated code. Do not change taxonomy, grouping policy, or major-event policy.

## Required seams

### 1. Imports
Import the existing Projector V2 shared semantic/occurrence authority adapter using the branch's established import convention. Preserve current startup/import behavior.

### 2. Rejection authority
Replace legacy source-wide/date widening with OccurrenceIdentityV2 scope semantics:
- `EXACT_START`: only the exact occurrence;
- `DAY`: only that source/day;
- `SOURCE_ALL_OCCURRENCES`: explicit source-wide rejection only;
- ambiguous identity must never widen implicitly.

Same source/day events with different exact starts must remain distinct and an exact-start rejection must not suppress the sibling occurrence.

### 3. Raw intake accounting
Every raw row must terminate in exactly one of these eight intake classes:
1. `documented_duplicate`
2. `rejected_exact`
3. `rejected_day`
4. `rejected_source_all`
5. `outside_window`
6. `identity_ambiguous_review`
7. `accepted_review_supplemental`
8. `invalid`

No unclassified drop path is allowed.

### 4. Projected occurrence reference
Projected records must carry the V2 occurrence reference/identity precision required by the shared authority. Legacy date-only/source-wide occurrence authority must not remain authoritative.

### 5. Semantic map authority
Route publication through the shared semantic map decision contract. Coordinate presence alone must never grant exact publication authority.

Exact public publication requires the shared authority result corresponding to:
- `MAP_READY`;
- `certified_pin == true`;
- public event eligibility;
- standalone/public occurrence eligibility;
- no unresolved parent/grouping suppression.

### 6. GENERAL_AREA privacy
For `GENERAL_AREA`, public output must strip exact:
- latitude/longitude;
- address;
- venue target;
- directions target.

Do not encode a centroid or approximate coordinate as an exact venue pin.

`REVIEW_REQUIRED` and `LIST_ONLY` must not expose exact public location.

### 7. Display disposition/grouping
Use the shared semantic disposition as the location-publication authority. Preserve existing event grouping/taxonomy/major-event policy except where the V2 occurrence identity is required to distinguish occurrences.

### 8. Marker eligibility
Markers may be emitted only when the shared decision is exact/public-map eligible. Required public marker condition remains `MAP_READY` plus certified exact authority and the existing public/standalone eligibility gates.

### 9. find_samples / accessibility
Update sample selection and accessibility/text alternatives so they consume the same semantic disposition and cannot reintroduce exact location for `GENERAL_AREA`, `REVIEW_REQUIRED`, or `LIST_ONLY` records.

### 10. Zero-loss counters
Add/verify exact counters for:
- `silent_identity_loss`
- `implicit_source_all_count`
- `unsupported_exact_pin_count`
- `legacy_occurrence_authority_count`
- `legacy_coordinate_authority_count`

All five targets are zero.

### 11. Reconciliation assertion
Enforce exactly:

`raw_rows = documented_duplicate + rejected_exact + rejected_day + rejected_source_all + outside_window + identity_ambiguous_review + accepted_review_supplemental + invalid`

Do not soften this assertion into a warning or best-effort metric.

## Required integration tests

Add/extend projector integration coverage for:
- same source/day, different exact starts remain distinct;
- exact-start rejection preserves sibling occurrence;
- day rejection rejects only source/day;
- source-all rejection requires explicit source-wide scope;
- ambiguous identity never widens implicitly;
- exact marker needs semantic MAP_READY + certified authority;
- coordinates without evidence cannot publish an exact marker;
- GENERAL_AREA strips exact address/venue/coordinates/directions target;
- REVIEW_REQUIRED and LIST_ONLY expose no exact public location;
- all eight raw-intake buckets participate in strict reconciliation;
- all five zero-target counters equal zero on the integration fixture.

## Post-splice exact-head gates

On one exact head require:
- Projector V2 Authority QA PASS;
- Projector integration QA PASS;
- Schema v1 PR QA PASS;
- Discovery Taxonomy v02 QA PASS;
- Occurrence Identity Enforcement PASS if triggered;
- Incoming Data Residual PASS if triggered;
- Daily Refresh Reliability PASS if triggered;
- Sonar Quality Gate PASS;
- 0 Security Hotspots.

## Completion label

Do not call the splice complete until the target file itself is patched, the strict reconciliation passes, all five zero-target counters are zero, and all required exact-head checks are green.

No merge, production refresh, WordPress change, hosting change, repository-visibility change, or destructive cleanup is authorized by this specification.
