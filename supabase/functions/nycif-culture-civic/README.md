# `nycif-culture-civic` (planned — not deployed)

Outline only. Do not deploy from this scaffold PR.

## Purpose

Reader-safe GeoJSON / row feed for sanctuary civic pins:

- 👮 NYPD precincts (`civic_nypd`) — house pins when addressable; optional
  precinct polygon metadata. Dataset `y76i-bdw7` is boundaries; do not invent
  house dots from centroids unless a reviewer accepted that with a reason.
- 🚒 FDNY firehouses (`civic_fdny`) — `hc8x-tcnd`
- Shelters (`shelter`) — only addressable directory rows

Not Culture storefronts. Not liquor/dispensary/5pm.

## Suggested response

```json
{
  "authority": "nycif-culture-civic",
  "schema_version": "culture-civic-v1",
  "civic_publication_enabled": false,
  "layers": {
    "nypd": { "enabled": false, "emoji": "👮", "count": 0 },
    "fdny": { "enabled": false, "emoji": "🚒", "count": 0 },
    "shelter": { "enabled": false, "count": 0 }
  },
  "features": []
}
```

Query: `?layer=nypd|fdny|shelter` (optional).

## Fail-closed

Read `culture_reader_settings` first.

- Master `civic_publication_enabled` false ⇒ empty features.
- Child layer flag false ⇒ that layer count 0.
- `review_status` must be `ACCEPTED` and `addressable` true to pin.
- Census-only shelter rows (`addressable=false`) never appear as points.
- `promotion_allowed` must be true only after explicit Phase C6.

## Security

Same as `nycif-culture-places`: service role in the function only, RLS
deny-all, GET/HEAD/OPTIONS, short cache, last-known-good on error — never
invented pins.

## iOS

`NYCInFocus` should treat a missing function (404) as “layer not shipped.”
Do not bundle local fake precinct/firehouse pins.
