# `nycif-culture-places` (already exists, gated)

This folder is an **outline**, not a replacement deploy. The live function
already serves the iOS Culture tab and returns
`business_publication_enabled: false` / `place_count: 0`.

Do not flip the gate in this scaffold. Do not invent storefronts.

## Current reader contract (keep)

Matches iOS `CulturePlacesFeed` / `CulturePlace`:

```json
{
  "authority": "nycif-culture-places",
  "schema_version": "culture-places-v1",
  "business_publication_enabled": false,
  "place_count": 0,
  "note": "Name-lead labels never publish until review passes.",
  "places": []
}
```

Place fields: `business_id`, `business_name`, `address`, `community_district`,
`lat`, `lng`, `cultural_tags`, `dietary_tags`, `review_status`, `confidence`,
`area_ids`, `matched_tags`, `reason_codes`, `is_sample`, `feed_version`.

Query: optional `area_id`.

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
3. `is_sample` is not true
4. `promotion_allowed` is true (after an explicit human Phase C6)
5. `lat`/`lng` are finite and inside the NYC box, **or** the row is
   explicitly list-only (then coords must be null)
6. `manual_reviewer` and `manual_reviewed_at_utc` and
   `approval_decision_reason` are present

Otherwise `places: []` and `place_count: 0`.

## Security

- Client: anon key + user JWT if required by existing pattern.
- Function may use `SUPABASE_SERVICE_ROLE_KEY` **only inside Deno**.
- No public table grants. RLS stays deny-all for anon.
- GET / HEAD / OPTIONS only.

## Do not implement in the scaffold PR

No `index.ts` here until a follow-up that deploys with the gate still false.
The live function must keep returning an empty published set.
