# Discovery taxonomy v02 — Field Desk map mirror

Thin deployment package for **discovery-taxonomy-v02**. It does **not** duplicate the full map application JavaScript inside this folder.

Core runtime lives in sibling:

```text
docs/field-desk-map-deploy/schema-v1-major-all-v01/
  event-feed-schema-v1.js
  app-schema-v1-major-all-v01.js   # reads window.NYCIF_DISCOVERY_V02 hooks
```

## Push / copy instructions (Field Desk)

`cursor[bot]` cannot push `setoxxx/nycif-field-desk`. Howard must copy:

| Copy from live-feeds | Into field-desk |
|----------------------|-----------------|
| `discovery-taxonomy-v02/index.html` | `index.html` (or review path) |
| `discovery-taxonomy-v02/discovery-patch-v02.js` | `./discovery-patch-v02.js` |
| `discovery-taxonomy-v02/public-map-defaults-v01.js` | `./public-map-defaults-v01.js` |
| `discovery-taxonomy-v02/public-map-v01.css` | merge / replace |
| `discovery-taxonomy-v02/service-worker.js` | `./service-worker.js` |
| `schema-v1-major-all-v01/app-schema-v1-major-all-v01.js` | `./app-schema-v1-major-all-v01.js` |
| `schema-v1-major-all-v01/event-feed-schema-v1.js` | `./event-feed-schema-v1.js` |

**Preserve** in field-desk (do not delete):

- Existing overlay scripts already on Pages (`public-approved-overlays-*.js`) — this mirror also ships copies for offline preview
- `boot-today-*`, `date-normalizer-*`, calendar/VIP polish scripts if still referenced after HTML swap
- Overlay JSON under `data/`
- Plugin 1.3.1 / map-restore-v02 rollback path

After copying into field-desk, change script `src` values that point at `../schema-v1-major-all-v01/` to local `./` paths.

## Runtime

- **Cache / version token:** `discovery-taxonomy-v02`
- **Service worker CACHE_NAME:** `nycif-v019-discovery-taxonomy-v02`
- **Config object:** `window.NYCIF_DISCOVERY_V02` from `discovery-patch-v02.js` (must load **before** the app)
- **Default mode:** Major Events, Next 7 days, all boroughs, all main + Explore More categories ON
- **Category filter handshake:** `category match OR any interest match` (inclusive OR across selected interests)
- **Marker eligibility:** `map_ready` + `event_role === public_event` + no `parent_event_id` + `display_disposition === standalone_public_event`
- **Search index copy:** `Indexing more events…` / `Full event index loaded`

## Feed URLs

Preview branch feeds with `?feeds=<branch>` (e.g. `?feeds=cursor/discovery-taxonomy-v02-27bf`).

| Layer | Path |
|-------|------|
| Major | `data/schema-v1-discovery/major/events.json` |
| Approved manifest | `data/schema-v1-discovery/approved/manifest.json` |
| Review manifest | `data/schema-v1-discovery/review/manifest.json` |
| Approved pages | `data/schema-v1-discovery/approved/pages/page-XXXX.json` |
| Review pages | `data/schema-v1-discovery/review/pages/page-XXXX.json` |

Production host after merge to `main`:

```text
https://raw.githubusercontent.com/setoxxx/nycif-live-feeds/main/data/schema-v1-discovery/...
```

## GitHub Pages test checklist

1. Push field-desk branch with the files above
2. Open Pages URL with `?v=discovery-taxonomy-v02&resetFilters=1&feeds=cursor/discovery-taxonomy-v02-27bf`
3. Confirm Major default, Kids/Classes/Volunteer on main panel, Explore More expands
4. Confirm Parks label is **Parks / outdoors**
5. Toggle each PUBLIC DATA LAYER and confirm pins/status change (script tag alone is not enough)
6. Existing-profile + incognito + mobile

## WordPress

Do **not** create plugin **1.4.0** until live Pages pass. Keep PR #164 / 1.3.1 as rollback.

## Safety

This mirror does not modify `location_cache.json`, protected staged feeds, or public-map promotion.
