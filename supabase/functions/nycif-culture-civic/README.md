# `nycif-culture-civic` (deployed, gated)

Reader-safe civic layer feed. Deployed with `verify_jwt=false` like
`nycif-culture-places`. Gates stay off until Phase C6.

## Purpose

Reader-safe GeoJSON / row feed for sanctuary civic pins:

- 👮 NYPD precincts (`civic_nypd`) — house pins when addressable; optional
  precinct polygon metadata. Dataset `y76i-bdw7` is boundaries; do not invent
  house dots from centroids unless a reviewer accepted that with a reason.
- 🚒 FDNY firehouses (`civic_fdny`) — `hc8x-tcnd`
- Shelters (`shelter`) — only addressable directory rows
- 🐾 Pet care (`pet_care`) — pin layer only; usually off (calendar first)

Not Culture storefronts. Not liquor/dispensary/5pm.

## Response

```json
{
  "authority": "nycif-culture-civic",
  "schema_version": "culture-civic-v1",
  "civic_publication_enabled": false,
  "layers": {
    "nypd": { "enabled": false, "emoji": "👮", "count": 0, "label": "NYPD" },
    "fdny": { "enabled": false, "emoji": "🚒", "count": 0, "label": "FDNY" },
    "shelter": { "enabled": false, "emoji": "🏠", "count": 0, "label": "Shelters" },
    "pet_care": { "enabled": false, "emoji": "🐾", "count": 0, "label": "Pet care" }
  },
  "features": []
}
```

Query: `?layer=nypd|fdny|shelter|pet_care` (optional).

## Fail-closed

Read `culture_reader_settings` first (`id = 'v1'`).

- Master `civic_publication_enabled` false ⇒ empty features.
- Child layer flag false ⇒ that layer count 0.
- `review_status` must be `ACCEPTED` and `addressable` true to pin.
- Census-only shelter rows (`addressable=false`) never appear as points.
- `promotion_allowed` must be true only after explicit Phase C6.

## Security

Same as `nycif-culture-places`: service role in the function only, RLS
deny-all, GET/HEAD/OPTIONS, short cache, last-known-good on error — never
invented pins. `verify_jwt=false`.

## iOS

`CultureService.fetchCivic()` treats HTTP 200 + gate false as “layer gated,”
not “function missing.” Do not bundle local fake precinct/firehouse pins.
