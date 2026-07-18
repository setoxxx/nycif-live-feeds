NYCIF Events Map 1.5.0-rc1

Purpose
- Embeds the deployed NYC In Focus Field Desk map in WordPress posts/pages (in-article).
- Uses approved public discovery feed: feeds=main (not a git commit SHA).
- Runtime cache bust: public-map-v10 (device-aware mobile/desktop layout inside iframe).
- Preserves geolocation and fullscreen permissions on the iframe.
- WordPress does not download or parse event JSON.

Production /map/ page (IMPORTANT)
- https://nycinfocus.com/map/ does NOT use this shortcode.
- Page 2647 uses the fullscreen #nycifMapAppShell Custom HTML block.
- Deploy /map/ via CHATGPT-WORDPRESS-DEPLOY-PROMPT.md in the live-feeds repo.

Install / upgrade from 1.4.0-rc1
1. WordPress → Plugins → Add New → Upload Plugin.
2. Upload nycif-events-map-1.5.0-rc1.zip (build from docs/wordpress-plugin-deploy/nycif-events-map/).
3. Replace the existing NYCIF Events Map plugin.
4. Clear WordPress/page/CDN caches.
5. Settings → NYCIF Events Map — confirm canonical runtime URL shows public-map-v10 and feeds=main.
6. Test https://nycinfocus.com/map/ in private window (desktop + mobile) — shell page, not shortcode.
7. Test any pages that still use [nycif_events_map] shortcode.

What changed from 1.4.0-rc1
- RETIRED: NYCIF_MAP_RUNTIME_TOKEN = discovery-taxonomy-v03
- RETIRED: NYCIF_DISCOVERY_FEED_REF = bf7dedd... (commit SHA)
- NEW: NYCIF_RUNTIME_CACHE_BUST = public-map-v10
- NEW: NYCIF_APPROVED_FEED_REF = main
- feed_ref shortcode attribute deprecated; commit SHAs normalize to main

Shortcode
  [nycif_events_map]
  [nycif_events_map height="90vh" cache="public-map-v10" feeds="main" clusters="1"]

Repositories
- Field Desk: https://github.com/setoxxx/nycif-field-desk
- Live feeds: https://github.com/setoxxx/nycif-live-feeds

Rollback
- Previous package: nycif-events-map-1.4.0-rc1.zip
- Legacy safe rollback lineage: nycif-events-map-1.3.1-safe-rollback.zip
- SHA-256 (legacy): ea5b0ac0632fe09f99758b34cab67fa45bf753be4ca724b9bdeb5fa0d79101e9

Safety
- No GPS review artifacts, staged feed, or supplemental export on feeds=main.
- Plugin is for in-article embeds; public /map/ uses freeze doc shell only.
