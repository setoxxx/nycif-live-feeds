# Cross-repo notes — `nycif-data-pipeline`

Copy or link this from `setoxxx/nycif-data-pipeline` when that repo is next
touched. **Do not** treat this file as permission to publish the WordPress
Culture embed or to invent storefronts.

Authority for this product slice:  
`setoxxx/nycif-live-feeds` → `docs/CULTURE_COMMUNITY_ENGINEERING_PLAN.md`

## What already exists here

`culture/` is a **protected-staging DCWP classification pipeline**:

- Inventory: NYC DCWP legally operating businesses `w7w3-xahh`
- Evidence overlay required for any cultural tag
- Name is a review lead (`REVIEW_NAME_LEAD_NEEDS_EVIDENCE`), never `ACCEPTED`
- Kosher/halal require certification / business-provided designation
- Validator fails closed (`NAME_LEAD_IN_FEED`)
- Staging embed: `wordpress/staging/nycif-culture-map-embed.html`

That embed is **not** a live public map. NYC In Focus official Culture pins
go to the native app via Supabase (`nycif-culture-places`, gated). At app
launch, WordPress becomes QR codes to the app.

## What live-feeds is adding (do not duplicate blindly)

Howard wants sanctuary-city Culture community enrichment:

- Curated storefronts inside borders (~91 CSV from Howard — **not** DCWP
  auto-labels)
- MOIA / health / pantries / KYR / multilingual services
- NYPD `y76i-bdw7`, FDNY `hc8x-tcnd`, shelters (addressable directory)
- ASPCA Community Medicine as **calendar** rows, not guessed pins
- 8-day Culture calendar

Ingest + SQL + edge outlines live in `nycif-live-feeds` under
`scripts/culture/`, `supabase/migrations/`, `supabase/functions/nycif-culture-*`.

## Coordination rules

1. **Do not invent businesses** from DCWP names, surnames, or neighborhood.
2. DCWP matches may feed a **review worklist** only. They must not skip
   Howard’s CSV or the live-feeds `ACCEPTED` + publication gates.
3. Do not wire `public/feeds/culture/*.json` into WordPress `/map/` or treat
   the staging embed as production.
4. Do not put `service_role` in any client. Do not flip
   `business_publication_enabled`.
5. If pipeline geocoding is reused, keep GeoSearch + staging-only proposals
   (`promotion_allowed: false`), same as `culture/pipeline/geocode_candidates.py`.
6. Civic people-facing datasets already pulled in live-feeds
   (`pnpe-ubtz` KYR, `bmxf-3rd4` drop-in, SNAP/Homebase) stay review-only
   until a live-feeds Culture resource gate is explicitly enabled.

## Suggested one-line README add (when editing that repo)

> Native-app Culture civic + curated-list work is planned in
> `setoxxx/nycif-live-feeds` `docs/CULTURE_COMMUNITY_ENGINEERING_PLAN.md`.
> This `culture/` slice remains evidence-gated staging and is not a live
> WordPress destination.
