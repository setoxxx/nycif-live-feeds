# ADR-0013: Tiered Approximate Marker Layer

## Status

Draft — awaiting SHADOW-2 Step 2 completion, branch audit results, and explicit Phase 2B authorization.

This ADR is documentation only. It does not authorize map rendering, coordinate generation, promotion, production-feed modification, or deployment.

## Context

The current SHADOW-2 baseline contains 1,901 review occurrences with `coordinate_status: list_only`:

- 1,292 classified `approximate_area`
- 495 classified `unresolved`
- 70 classified `certified_street_segment`
- 39 classified `exact_address`
- 5 classified `exact_intersection`

The unresolved subset is not locationless: the prior artifact review found location text on all 495 occurrences, with 452 containing recognized park or facility terminology. PR #362 adds deterministic diagnostics to verify these counts and trace source-coordinate retention.

ADR-0012 established the exact-coordinate stack as non-clustered. This ADR defines a future approximate layer that remains structurally, visually, and operationally separate from exact pins.

## Key Finding: Source Coordinates May Already Exist

`scripts/sync_nyc_parks_bigapps_events.py` preserves event-level coordinates, `park_names`, and `park_ids`. The latest synchronization report records 1,804 of 1,825 Parks rows with coordinates.

Before implementing any centroid fallback, the pipeline must determine whether source coordinates or park identifiers are being lost during normalization, occurrence expansion, schema projection, or review classification.

A source-provided coordinate must be evaluated before replacing it with a less precise centroid.

## Decision

The future map may support three approximate marker classes and one non-rendered state, subject to a separately approved implementation PR.

| Tier | Evidence required | Map treatment | Clustering |
|---|---|---|---|
| `approximate_area` | Approved borough, neighborhood, ZIP, tract, or other area anchor under the Phase 2B contract | Translucent area marker with disclaimer | Yes |
| `certified_facility` | Authoritative facility identifier and coordinate or centroid | Distinct semi-opaque facility marker | No |
| `park_level_anchor` | Authoritative park identifier and park geometry/centroid where the sub-facility is not precisely located | Translucent park-level marker with park label | Yes |
| `unresolved` | No approved geographic anchor | No marker; remains `list_only` | N/A |

Only the first three classes may enter an approximate map source. `unresolved` remains excluded from all map sources.

The labels above describe the proposed rendering contract. They do not override the existing SHADOW-2 evidence classifier or grant semantic certification by themselves.

## Required Investigation Order

1. Run PR #362's updated SHADOW-2 audit on its branch.
2. Inspect raw Parks records for coordinates, `park_names`, and `park_ids`.
3. Match raw records to projected occurrences using `source_dataset` and `source_event_id`.
4. Identify where coordinates or park identifiers disappear.
5. Repair normalization or projection defects without changing coordinate status or promotion flags.
6. Rebuild and rerun SHADOW-2.
7. Measure how many records become eligible through retained source evidence.
8. Investigate an authoritative NYC Parks/DPR properties geometry dataset for remaining park-level cases.
9. Define acceptable borough, neighborhood, ZIP, or tract anchors before implementing `approximate_area` markers.
10. Obtain explicit Phase 2B authorization before map implementation or deployment.

## MapLibre Architecture

Exact and approximate records must use separate sources.

- `exact-events`: existing exact source, `cluster: false`
- `approximate-clustered-events`: future source for approved `approximate_area` and `park_level_anchor` records, `cluster: true`
- `approximate-facility-events`: future source for approved `certified_facility` records, `cluster: false`

MapLibre clustering is configured at the source level. A `clusterable` feature property cannot exempt selected features from clustering within a clustered source.

## Visual Contract

| Attribute | Exact pin | Approximate marker |
|---|---|---|
| Visual weight | Solid, high contrast | Translucent or semi-opaque |
| Clustering | Never | Tier-dependent |
| Meaning | Supported exact coordinate | Area, facility, or park-level anchor |
| Popup | Exact address or venue evidence | Precision label, disclaimer, and list-view link |
| Z-order | Above approximate layers | Below exact layer |

Every approximate popup must disclose that the point is not an exact event location.

## Data Contract

A future approximate feature must include, at minimum:

- stable occurrence or stack identifier
- `precision_tier`
- authoritative anchor type
- anchor identifier where available
- anchor name
- source dataset
- event or occurrence count
- disclaimer text
- evidence provenance
- reconciliation version
- `promotion_allowed: false` until a separately authorized promotion gate succeeds

No feature may use a fabricated default coordinate.

## Prohibited Fallbacks

The implementation must not:

- place unmatched records at a generic New York City coordinate
- silently substitute a borough centroid for missing facility evidence
- derive a facility coordinate from free text alone
- promote `list_only` records automatically
- mix exact and approximate records in one source
- treat classifier tier names as proof of authoritative certification
- alter production feeds or the public map without explicit authorization

## Acceptance Criteria for a Future Implementation PR

- [ ] PR #362 branch audit completed and reviewed
- [ ] Source-coordinate loss investigation completed and documented
- [ ] Fresh baseline reconciles list-only and approximate counts
- [ ] Authoritative anchor datasets identified and versioned
- [ ] Eligibility function requires all approved evidence conditions
- [ ] No placeholder or generic default coordinates
- [ ] Exact, clustered approximate, and non-clustered facility sources remain separate
- [ ] Unresolved records remain absent from all map sources
- [ ] Every approximate popup displays a precision disclaimer
- [ ] Reconciliation report explains rescued, excluded, and unchanged counts
- [ ] Performance and accessibility tests completed
- [ ] Explicit Phase 2B approval recorded before merge or deployment

## Consequences

### Positive

- Preserves exact-pin trust while exposing defensible approximate coverage.
- Allows source-coordinate repairs to be measured before adding centroid fallbacks.
- Supports park and facility use cases without manufacturing precision.
- Keeps unresolved records fail-closed.

### Negative

- Requires multiple MapLibre sources and reconciliation paths.
- Depends on authoritative park/facility geometry and identity matching.
- Adds user-interface disclosure and accessibility requirements.
- Does not immediately rescue all 1,292 `approximate_area` occurrences or all 495 unresolved occurrences.

## Open Questions

1. Which authoritative NYC Parks/DPR dataset should provide park identifiers, boundaries, and representative points?
2. Which area-anchor types are acceptable for `approximate_area`, and at what zoom levels?
3. Should repeated occurrences at one facility stack by facility, date, or source event?
4. What minimum evidence is required to transition from `unresolved` to `park_level_anchor`?
5. What retention and versioning rules apply when an authoritative geometry dataset changes?
