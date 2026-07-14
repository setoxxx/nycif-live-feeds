# Discovery taxonomy v02 — Field Desk map mirror

Canonical Field Desk runtime mirror for **discovery-taxonomy-v02** Major Events / All Events with inclusive category+interests filters.

Apply the files in this directory onto `setoxxx/nycif-field-desk`. Do not keep a second copy of normalization/rendering logic elsewhere in this repo.

## Push / copy instructions

- **Branch to push (live-feeds):** `cursor/discovery-taxonomy-v02` (or `cursor/discovery-taxonomy-v02-27bf`)
- **Field Desk target branch:** copy these mirror files into the field-desk repo manually
- **`cursor[bot]` cannot push field-desk** — Howard must copy mirror files into `setoxxx/nycif-field-desk`
- **Do not create WordPress plugin 1.4.0 yet** — keep plugin 1.3.1 / PR #164 as rollback until live Pages pass

## Files replaced in this mirror

| File | Role |
|------|------|
| `index.html` | Filter panel order, Explore More, script tags |
| `app-discovery-taxonomy-v02.js` | Map app, feeds, filters, markers |
| `event-feed-schema-v1.js` | Schema projection + discovery fields |
| `public-map-defaults-v01.js` | LocalStorage defaults + version token |
| `public-map-v01.css` | Explore More, filter counts, focus states |
| `service-worker.js` | App-shell cache |
| `README.md` | This file |

Preserve existing overlay scripts in `index.html` (`public-approved-overlays-*.js`) — PUBLIC DATA LAYERS (5PM, Cannabis, Correlation) stay separate with disclaimers.

## Runtime

- **Cache token / VERSION:** `discovery-taxonomy-v02`
- **Service worker CACHE_NAME:** `nycif-v019-discovery-taxonomy-v02`
- **Default mode:** Major Events, Next 7 days, all boroughs, all main + Explore More categories ON
- **Category filter handshake:** `selectedCategories.has(event.category) || event.interests.some(i => selectedCategories.has(i))`
- **Major-only checkbox:** filters `significance === 'major'` / `nycif.is_major`
- **Marker eligibility:** `map_ready` + `event_role === public_event` + no `parent_event_id` + `display_disposition === standalone_public_event`
- **Grouped supporting:** related count on parent popup; child rows do not get competing pins
- **Badges:** LIST ONLY for list-only rows; REVIEW for review layer
- **Search index status:** `Indexing more events…` / `Full event index loaded`
- **Security:** `textContent` for strings; `safeExternalUrl` for links
- **Leaflet CDN:** SRI integrity attributes preserved in `index.html`

## Feed URLs (after live-feeds merge to `main`)

Preview any branch with `?feeds=<branch>` (same as prior mirrors).

| Layer | Path |
|-------|------|
| Major | `data/schema-v1-discovery/major/events.json` |
| Approved manifest | `data/schema-v1-discovery/approved/manifest.json` |
| Review manifest | `data/schema-v1-discovery/review/manifest.json` |
| Approved pages | `data/schema-v1-discovery/approved/pages/page-XXXX.json` |
| Review pages | `data/schema-v1-discovery/review/pages/page-XXXX.json` |

Raw GitHub host (production):

```
https://raw.githubusercontent.com/setoxxx/nycif-live-feeds/main/data/schema-v1-discovery/...
```

## Blank-state actions

When no events match: **Reset Filters**, **Show All Events**, **Enable All Categories** (panel buttons + list empty state).

## WordPress

Do not ship plugin **1.4.0** from this mirror.

## Safety

This mirror does not modify `location_cache.json`, staged protected feeds, or the public map promotion pipeline.
