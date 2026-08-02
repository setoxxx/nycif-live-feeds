# NYCIF Location Evidence Contract v1.0

## Status

Protected SHADOW-2 contract. Read-only audit authority only. This contract does not authorize feed mutation, approval changes, public-map changes, cache writes, deployment, promotion, or production publication.

## Purpose

This contract defines the universal location-evidence vocabulary for NYCIF event occurrences. It governs how Enigma describes location evidence, how V1 normalizers should emit location metadata, and how future map layers distinguish an exact pin, an approximate marker, and list-only presentation.

Classification is not certification. A record can be classified into an exact-capable tier while remaining `unvalidated`; it is not eligible for an exact public pin until every required semantic check passes.

## Scope

- Approved and review page shards
- Countable raw official-source snapshots named by the source-lineage registry
- Enigma SHADOW-2 read-only audits
- Future V1 normalizer metadata
- Future Borg municipality-marker behavior

## Required common fields

Every location-evidence result must carry:

- `tier`
- `validation_state`: `validated`, `unvalidated`, `invalid`, or `not_applicable`
- `exact_pin_eligible`
- `promotion_allowed`
- `reason_code` and `reason_detail` when validation is incomplete or failed
- evidence provenance sufficient to reproduce the decision

`promotion_allowed` defaults to `false`. SHADOW-2 never changes it to `true`.

## The seven location-precision tiers

### 1. `exact_source_coordinate`

The source system supplied latitude and longitude for the specific dated occurrence.

Required claim evidence:

- finite latitude and longitude
- not Null Island
- explicit source-coordinate provenance, such as `source_provided`
- occurrence-level source identity

Exact-pin eligibility requires semantic validation of borough, location label or source geometry, and any trusted-distance comparison required by the source policy.

### 2. `exact_address`

A complete numbered street address is available and can be geocoded to a building or parcel.

Required claim evidence:

- numbered street address
- borough or municipality context when needed to disambiguate
- geocoder provenance after resolution

A generic street-name result is not an exact address.

### 3. `exact_intersection`

Two street names identify a specific intersection.

Required claim evidence:

- two explicit cross-street fields, or a strict intersection expression
- both values must be street-like, not merely two phrases joined by “and”

Exact-pin eligibility requires both street names in the returned label and a borough match.

### 4. `certified_street_segment`

A street segment between two endpoints is represented by a validated midpoint.

Required claim evidence:

- main street
- first cross street
- second cross street

Certification additionally requires:

- both endpoints resolved independently
- both endpoints in the stated borough
- endpoint distance within the documented safety range
- midpoint calculated from the two endpoints or loaded from an explicitly certified segment reference
- no generic street-name fallback

Event `923896` is the permanent regression fixture: East 74 Street between Avenue U and Avenue T must resolve as Brooklyn, never Manhattan.

### 5. `certified_facility`

A named park, facility, or venue is matched to an authoritative facility record.

Required claim evidence:

- facility or park name
- authoritative facility identifier

A name alone is not certified. Exact-pin eligibility requires registry validation and, where geometry exists, containment within the facility boundary.

### 6. `approximate_area`

Only broad geography is known, such as a borough, neighborhood, municipality, or explicitly approximate centroid.

Approximate-area coordinates must never render as a normal exact pin. A future map may use a visibly approximate marker only when the rendering contract and disclosure text are separately approved. Otherwise the record remains list-only.

Municipality centroids used by Borg belong to this tier.

### 7. `unresolved`

No usable location evidence exists, required evidence is malformed, or the available claim cannot safely be classified.

Unresolved records are list-only and must remain visible in audit reconciliation.

## Validation states

| State | Meaning | Exact pin eligible |
|---|---|---:|
| `validated` | All tier-specific semantic checks passed | only for tiers 1–5 |
| `unvalidated` | Evidence claim exists but semantic checks have not run or are incomplete | no |
| `invalid` | A required check failed | no |
| `not_applicable` | No exact-location validation applies | no |

No field-presence classifier may emit `exact_pin_eligible: true`.

## Universal semantic checks

The validator must apply the checks required by the claimed tier:

- coordinate is finite and nonzero
- coordinate lies within the permitted regional envelope
- returned borough matches the source borough
- returned street tokens match the source street or intersection
- segment endpoints resolve in the same borough and midpoint lies between them
- authoritative facility identifier exists and matches the facility
- generic street-only fallback was not used
- distance from a trusted coordinate is within the source-specific threshold
- geocoder and evidence provenance are recorded

The one-kilometer trusted-distance threshold is a review trigger, not universal proof of correctness. Source-specific thresholds may be stricter.

## Strict prohibitions

### Generic fallback pins

A coordinate produced by geocoding only a generic street name, neighborhood name, borough, or municipality must not be promoted to an exact tier. It is `approximate_area`, `unresolved`, or `review_required` depending on the disposition policy.

### Cross-borough coordinates

A coordinate whose resolved borough conflicts with the source borough is invalid for exact-pin use. A Brooklyn event with a Manhattan coordinate is more harmful than a list-only event.

### Presence-only certification

The following are prohibited:

- treating any finite coordinate as source-provided
- treating a facility name without an authoritative ID as certified
- treating a “street between X and Y” string as certified before endpoint validation
- treating arbitrary text joined by “and” as an intersection

## Stable reason codes

- `BOROUGH_MISMATCH`
- `STREET_TOKEN_MISMATCH`
- `GENERIC_FALLBACK`
- `NULL_ISLAND`
- `NONFINITE_COORDINATE`
- `COORDINATE_SOURCE_UNPROVEN`
- `FACILITY_ID_UNKNOWN`
- `SEGMENT_UNCERTIFIED`
- `SEGMENT_ENDPOINT_MISMATCH`
- `DISTANCE_FROM_TRUSTED_EXCEEDED`
- `MISSING_EVIDENCE`
- `MALFORMED_EVIDENCE`

Reason codes describe evidence or validation. They do not themselves authorize a disposition change.

## Disposition contract

Location tier and publication disposition are separate fields. Every audited input occurrence must receive exactly one disposition:

- `map_ready`
- `list_only`
- `duplicate_of`
- `excluded_with_reason`
- `review_required`

The audit must prove:

```text
input occurrences
= map_ready
+ list_only
+ duplicate_of
+ excluded_with_reason
+ review_required
```

Malformed artifacts and malformed records must be counted explicitly. They must never be silently skipped.

## Repair queue contract

SHADOW-2 may emit suggested evidence and coordinates only into a deterministic repair queue. Every suggestion must include:

- canonical occurrence identity
- current tier and validation state
- proposed tier or coordinate, when any
- source and geocoder evidence
- reason codes
- `promotion_allowed: false`

SHADOW-2 must not mutate approved pages, review pages, raw snapshots, `data/location_cache.json`, public feeds, or approval state.

## Shared authority

This contract is the shared vocabulary for Enigma SHADOW-2, future V1 location metadata, and future Borg approximate-area rendering. Any change requires a version bump and explicit owner approval.
