# Field-desk public map deploy (RC)

Single canonical public map runtime for NYC In Focus GitHub Pages.

## Canonical runtime (only path for production)

| Source (this repo) | Field Desk Pages root |
|---|---|
| `schema-v1-major-all-v01/index.html` | `index.html` |
| `schema-v1-major-all-v01/app-schema-v1-major-all-v01.js` | `app-schema-v1-major-all-v01.js` |
| `schema-v1-major-all-v01/public-display-mode-v01.js` | `public-display-mode-v01.js` |
| `schema-v1-major-all-v01/public-map-v01.css` | `public-map-v01.css` |
| `schema-v1-major-all-v01/service-worker.js` | `service-worker.js` |
| `discovery-taxonomy-v02/discovery-patch-v02.js` | `discovery-patch-v02.js` |
| `discovery-taxonomy-v02/public-approved-overlays-v01.js` | `public-approved-overlays-v01.js` |
| `shared/nycif-tip-jar-v01.js` | `nycif-tip-jar-v01.js` |

Cache bust token: **`public-map-v10`** (RC). Tip jar module: **`nycif-tip-jar-v01.js?v=06`**.

## Deploy

**Automatic (preferred):** merge to `main` — the `Deploy to Field Desk Pages` workflow copies canonical sources into `setoxxx/nycif-field-desk` and pushes.

**Manual sync** (when you have a local field-desk checkout):

```bash
./scripts/sync_complete_map_to_field_desk.sh /path/to/nycif-field-desk
```

## Retired legacy runtimes (removed from this repo)

These older public-map entrypoints are **not** part of RC and were removed from `docs/field-desk-map-deploy/`:

- `app-v06-safe.js` + root `index.html` (M10 staged-live map)
- Root `public-map-defaults-v01.js` duplicate
- `COMPLETE_MAP_PAGES_HANDSHAKE.patch`

`desk.html` on Field Desk may still reference `app-v06-safe.js` for the operator desk overlay — that is separate from the public map and will be migrated in a later milestone.

## Staging / review lanes (not production)

| Package | Purpose |
|---|---|
| [`supplemental-export-preview/`](./supplemental-export-preview/README.md) | M11 approved export preview (`approved-export-preview.html`) |
| [`civic-people-facing-v01/`](./civic-people-facing-v01/README.md) | Jobs / volunteer / help-places review lane (`?v=civic-people-facing-v01`) |

Do not point WordPress or the public embed at staging lanes.

## Verify after deploy

- https://setoxxx.github.io/nycif-field-desk/?v=public-map-v10&resetFilters=1&feeds=main
- Tip jar: clear glass button, police strobe on random pulse, centered panel, “Follow Howard Weiss”
- https://nycinfocus.com/map/ — bump iframe `v=` to `public-map-v10` after Pages deploy + QA ([ChatGPT runbook](../wordpress-plugin-deploy/CHATGPT-WORDPRESS-DEPLOY-PROMPT.md))
- Mobile/desktop: [`PUBLIC-MAP-DISPLAY-MODES.md`](../wordpress-plugin-deploy/PUBLIC-MAP-DISPLAY-MODES.md)

## Supplemental approved export preview (M11)

```bash
./scripts/sync_supplemental_export_preview_to_field_desk.sh /path/to/nycif-field-desk
```
