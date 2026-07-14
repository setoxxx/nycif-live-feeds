# Tiered NYC Location Resolver

Every NYC permit location should resolve through public data before reaching human review.

## Three tiers (automatic)

| Tier | Source | When |
|------|--------|------|
| **1** | Unified gazetteer | `location_cache` + Parks facility/events + `manual_gps_reference` + GeoSearch cache (~45k keys) |
| **2** | GeoSearch cache | Previously geocoded queries persisted in `data/nyc_geosearch_gazetteer_cache.json` |
| **3** | NYC GeoSearch live | Official NYC Planning PAD API (free, no key) when `NYCIF_ALLOW_LIVE_GEOSEARCH=yes` |

If all tiers fail → `data/location_resolver_unresolved_queue.json` (admin review handful).

## Scripts

```bash
python3 scripts/build_nyc_location_gazetteer.py
python3 scripts/build_location_resolver_report.py
NYCIF_ALLOW_LIVE_GEOSEARCH=yes python3 scripts/build_test_enriched_feed.py
```

## Safety

- Resolver output is used for **test/staging feeds only** until manually approved.
- Does not auto-promote to `location_cache.json` or the public map.
- All rows remain `manual_review_status: pending`, `promotion_allowed: false`.

## Current results (2026-07-14)

- Gazetteer: **45,437** lookup keys from public in-repo sources
- GPS review audit: **1,948 / 1,950** resolved → **2** unresolved (Catherine Scott Promenade)
- Live permit enrichment: **0** needs_review rows (down from ~3,110) when tiers 1–3 enabled
