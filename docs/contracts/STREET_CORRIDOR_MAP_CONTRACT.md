# Street corridor map contract (A — B)

Status: draft on `feat/street-corridor-ab-map`. Does **not** authorize `location_cache.json` writes, Google geocoding, or promoting a single guessed midpoint as `MAP_READY`.

## Why this exists

NYC street events and closures arrive as block faces, not buildings:

```text
18 AVENUE between 73 STREET and 75 STREET, Brooklyn
```

The native feed currently marks those rows `LIST_ONLY` (147 on `mode=now` as of 2026-09-05) because `official_event_contract.py` only allows:

- `MAP_READY` + one certified lat/lng, or
- `LIST_ONLY` + no coordinates

Street closures must draw as a corridor on the iPhone:

```text
73 St × 18 Ave     ● - - - - - ●     75 St × 18 Ave
                   dashed blue line
```

This is the same evidence tier already named `certified_street_segment` in `docs/LOCATION_EVIDENCE_CONTRACT.md`. This document is the **map rendering + official-row** half of that tier.

## Product path

GitHub `nycif-live-feeds` is the factory. The phone reads Supabase `nycif-native-map-feed`, not `raw.githubusercontent.com` JSON.

Corridor work belongs in catch-up → `event_occurrences.metadata.reader` → Edge Function. Do not add a second static GitHub map file for this.

## States

| `map_eligibility_state` | `certified_pin` | `mapped` | Draw |
|---|---|---|---|
| `MAP_READY` | true | true | one pin |
| `CORRIDOR_READY` | false | true | pin A + pin B + dashed line |
| `LIST_ONLY` | false | false | list row only |

`certified_pin` stays false on corridors. A corridor is not an exact building pin.

Projected feast (`nyc-projected-feast-reference`) stays list-only until a human promote. TVPP / Parks street permits are the first corridor candidates.

## Required reader fields for `CORRIDOR_READY`

```json
{
  "map_eligibility_state": "CORRIDOR_READY",
  "certified_pin": false,
  "display_disposition": "CORRIDOR",
  "geometry_type": "CORRIDOR",
  "corridor": {
    "main_street": "18 Avenue",
    "from_street": "73 Street",
    "to_street": "75 Street",
    "borough": "Brooklyn",
    "point_a": {"lat": 40.6181, "lng": -74.0102},
    "point_b": {"lat": 40.6169, "lng": -74.0088},
    "line": [
      [-74.0102, 40.6181],
      [-74.0088, 40.6169]
    ],
    "resolver": "nyc-geosearch+lion",
    "reason_code": "CERTIFIED_STREET_SEGMENT"
  }
}
```

`lat` / `lng` on the occurrence stay **null**. The phone must not treat a midpoint as `MAP_READY`.

`line` coordinates are `[lng, lat]` GeoJSON order.

## Parse rules

`scripts/street_corridor_parse.py` accepts:

- `MAIN between FROM and TO`
- optional borough suffix
- DOT-style ALL CAPS streets (`18 AVENUE`, `WEST 23 STREET`)

Reject:

- borough-only (`Manhattan`)
- venue names without two cross streets
- `X and Y` with no `between` (that is not automatically an intersection)
- missing borough when the same street names exist in more than one borough

Permanent regression from the location-evidence contract:

> East 74 Street between Avenue U and Avenue T → Brooklyn, never Manhattan.

## Resolve rules (not in this PR)

A later catch-up step must:

1. GeoSearch / Geoclient / LION each endpoint: `MAIN & FROM`, `MAIN & TO`.
2. Both points in-bounds and same borough as source.
3. Haversine distance between A and B ≤ 0.6 miles (about 6 short blocks). Longer stretches stay `LIST_ONLY` or split.
4. Prefer LION centerline vertices between A and B when available; otherwise the two-point line.
5. Record resolver + reason. `promotion_allowed` stays false until catch-up writes the reader blob through `nycif_apply_staging_event_batch`.

Do not use Google. Do not write `data/location_cache.json` for this.

## iOS draw rules

Only when `map_eligibility_state == "CORRIDOR_READY"` and both points are finite:

- two small annotations at A and B
- `MKPolyline` dashed, system blue
- tap either end or the line → same event card

Do not geocode list-only strings on device.

## What this PR does not do

- No catch-up write
- No Edge Function deploy
- No `location_cache.json` edit
- No change to existing `MAP_READY` point policy
