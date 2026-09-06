# `nycif-culture-places` (already exists, gated)

This folder tracks the **deploy source** for the live edge function (`index.ts`),
mirrored from production (live v2). Keep publication fail-closed: do not flip
`business_publication_enabled` or invent storefronts from this repo alone.

## Current reader contract (keep)

Matches iOS `CulturePlacesFeed` / `CulturePlace`:

```json
{
  "authority": "supabase:culture_place_beta_v1",
  "schema_version": "NYCIF_CULTURE_PLACE_BETA_V1",
  "contract": "nycif.culture-places.v1",
  "business_publication_enabled": false,
  "place_count": 0,
  "max_places_ceiling": 5000,
  "truncated": false,
  "note": "Verified storefront pins stay gated until Culture business discovery review passes. Name-lead labels never publish.",
  "places": []
}
```

Place fields: `business_id`, `business_name`, `address`, `community_district`,
`lat`, `lng`, `cultural_tags`, `dietary_tags`, `review_status`, `confidence`,
`area_ids`, `matched_tags`, `reason_codes`, `is_sample`, `feed_version`.

Query: optional `area_id`.

Live behavior (see `index.ts`):
- Paginate with `PAGE_SIZE=1000`, `MAX_PLACES=5000`
- Filter `review_status=ACCEPTED`
- Return `place_count`, `max_places_ceiling`, `truncated`
- Fail-closed while publication is off; `verify_jwt` false on the function

## Planned additive fields (backward compatible)

- `place_kind`: `storefront | worship | civic_nypd | civic_fdny | shelter | pet_care | resource`
- `qualification_hint`: usually the business name
- Settings still read from `culture_reader_settings.business_publication_enabled`

Civic NYPD/FDNY/shelter rows should **not** appear here. Those belong on
`nycif-culture-civic`. This function stays curated Culture places (storefronts,
worship, reviewed community storefronts).

## Fail-closed publish filter

Return a place only when **all** are true:

1. `culture_reader_settings.business_publication_enabled` is true
2. `review_status = 'ACCEPTED'`
3. `is_sample` is not true (unless `allow_sample_places`)
4. `lat`/`lng` are finite and inside the NYC box

Otherwise `places: []` and `place_count: 0`.

## Security

- Client: anon key + user JWT if required by existing pattern.
- Function may use `SUPABASE_SERVICE_ROLE_KEY` **only inside Deno**.
- No public table grants. RLS stays deny-all for anon.
- GET / HEAD / OPTIONS only.
- Deployed with `verify_jwt: false` (matches live).

## Source of truth

`index.ts` in this folder is the checked-in deploy source matching live v2.
Do not flip publication gates from scaffolding PRs.
